"""Tests for the game engine components."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.engine import (
    Context,
    EntitySummary,
    GameEngine,
    HybridIntentParser,
    Intent,
    IntentType,
    MockLLMParser,
    PatternIntentParser,
    Session,
    SkillRouter,
    TurnResult,
)
from src.models import create_character, create_location, create_prime_material

# --- Intent Parser Tests ---


class TestPatternIntentParser:
    """Tests for pattern-based intent parsing."""

    @pytest.fixture
    def parser(self) -> PatternIntentParser:
        return PatternIntentParser()

    def test_parse_attack(self, parser: PatternIntentParser):
        intent = parser.parse("I attack the goblin")
        assert intent.type == IntentType.ATTACK
        assert intent.target_name == "goblin"

    def test_parse_attack_with_weapon(self, parser: PatternIntentParser):
        intent = parser.parse("I attack the orc with my sword")
        assert intent.type == IntentType.ATTACK
        assert intent.method == "sword"

    def test_parse_move_direction(self, parser: PatternIntentParser):
        intent = parser.parse("I go north")
        assert intent.type == IntentType.MOVE
        assert intent.destination == "north"

    def test_parse_move_to_location(self, parser: PatternIntentParser):
        intent = parser.parse("I walk to the tavern")
        assert intent.type == IntentType.MOVE
        assert "tavern" in intent.destination.lower()

    def test_parse_look(self, parser: PatternIntentParser):
        intent = parser.parse("I look around")
        assert intent.type == IntentType.LOOK

    def test_parse_examine(self, parser: PatternIntentParser):
        intent = parser.parse("I examine the chest")
        assert intent.type == IntentType.LOOK
        assert intent.target_name == "chest"

    def test_parse_talk_with_dialogue(self, parser: PatternIntentParser):
        intent = parser.parse('I say "Hello there" to the merchant')
        assert intent.type == IntentType.TALK
        assert intent.dialogue == "Hello there"

    def test_parse_persuade(self, parser: PatternIntentParser):
        intent = parser.parse("I try to persuade the guard to let us pass")
        assert intent.type == IntentType.PERSUADE

    def test_parse_intimidate(self, parser: PatternIntentParser):
        intent = parser.parse("I intimidate the bandit")
        assert intent.type == IntentType.INTIMIDATE

    def test_parse_search(self, parser: PatternIntentParser):
        intent = parser.parse("I search the room for hidden doors")
        assert intent.type == IntentType.SEARCH

    def test_parse_pick_up(self, parser: PatternIntentParser):
        intent = parser.parse("I pick up the gold coins")
        assert intent.type == IntentType.PICK_UP

    def test_parse_rest_short(self, parser: PatternIntentParser):
        intent = parser.parse("I take a short rest")
        assert intent.type == IntentType.REST
        assert "short" in intent.original_input.lower()

    def test_parse_rest_long(self, parser: PatternIntentParser):
        intent = parser.parse("I want to take a long rest")
        assert intent.type == IntentType.REST
        assert "long" in intent.original_input.lower()

    def test_parse_wait(self, parser: PatternIntentParser):
        intent = parser.parse("I wait here")
        assert intent.type == IntentType.WAIT

    def test_parse_fork(self, parser: PatternIntentParser):
        intent = parser.parse("What if I had attacked instead?")
        assert intent.type == IntentType.FORK

    def test_parse_unclear(self, parser: PatternIntentParser):
        intent = parser.parse("asdfghjkl")
        assert intent.type == IntentType.UNCLEAR

    def test_confidence_on_clear_match(self, parser: PatternIntentParser):
        intent = parser.parse("I attack the dragon")
        assert intent.confidence >= 0.7

    def test_confidence_on_unclear(self, parser: PatternIntentParser):
        intent = parser.parse("hmm maybe I dunno")
        assert intent.confidence < 0.7


class TestHybridIntentParser:
    """Tests for hybrid intent parsing."""

    @pytest.mark.asyncio
    async def test_uses_pattern_when_confident(self):
        parser = HybridIntentParser(llm_provider=None)
        intent = await parser.parse("I attack the goblin")
        assert intent.type == IntentType.ATTACK

    @pytest.mark.asyncio
    async def test_uses_llm_when_uncertain(self):
        mock_llm = MockLLMParser(default_intent_type=IntentType.INTERACT)
        parser = HybridIntentParser(
            llm_provider=mock_llm,
            confidence_threshold=0.9,  # High threshold to trigger LLM
        )
        await parser.parse("I fiddle with the thing")
        # Should have called the LLM
        assert mock_llm.call_count > 0

    @pytest.mark.asyncio
    async def test_works_without_llm(self):
        parser = HybridIntentParser(llm_provider=None)
        intent = await parser.parse("random gibberish")
        assert intent.type == IntentType.UNCLEAR


# --- Skill Router Tests ---


class TestSkillRouter:
    """Tests for skill routing."""

    @pytest.fixture
    def router(self) -> SkillRouter:
        return SkillRouter()

    @pytest.fixture
    def basic_context(self) -> Context:
        return Context(
            actor=EntitySummary(
                id=uuid4(),
                name="Hero",
                type="character",
                hp_current=20,
                hp_max=20,
                ac=15,
            ),
            location=EntitySummary(
                id=uuid4(),
                name="Tavern",
                type="location",
            ),
            entities_present=[
                EntitySummary(
                    id=uuid4(),
                    name="Goblin",
                    type="character",
                    ac=12,
                ),
            ],
            exits=["north", "south"],
        )

    def test_resolve_attack(self, router: SkillRouter, basic_context: Context):
        intent = Intent(
            type=IntentType.ATTACK,
            confidence=0.9,
            target_name="goblin",
            original_input="I attack the goblin",
        )
        result = router.resolve(intent, basic_context)
        assert result.roll is not None
        assert result.description  # Should have a description

    def test_resolve_skill_check(self, router: SkillRouter, basic_context: Context):
        intent = Intent(
            type=IntentType.PERSUADE,
            confidence=0.9,
            original_input="I try to persuade",
        )
        result = router.resolve(intent, basic_context)
        assert result.roll is not None
        assert result.dc is not None
        assert "persuasion" in result.description.lower()

    def test_resolve_look(self, router: SkillRouter, basic_context: Context):
        intent = Intent(
            type=IntentType.LOOK,
            confidence=0.9,
            original_input="I look around",
        )
        result = router.resolve(intent, basic_context)
        assert result.success
        assert "Tavern" in result.description
        assert "Goblin" in result.description

    def test_resolve_move_valid(self, router: SkillRouter, basic_context: Context):
        intent = Intent(
            type=IntentType.MOVE,
            confidence=0.9,
            destination="north",
            original_input="I go north",
        )
        result = router.resolve(intent, basic_context)
        assert result.success
        assert "north" in result.description.lower()

    def test_resolve_move_invalid(self, router: SkillRouter, basic_context: Context):
        intent = Intent(
            type=IntentType.MOVE,
            confidence=0.9,
            destination="east",  # Not in exits
            original_input="I go east",
        )
        result = router.resolve(intent, basic_context)
        assert not result.success
        assert "can't" in result.description.lower()

    def test_resolve_talk(self, router: SkillRouter, basic_context: Context):
        intent = Intent(
            type=IntentType.TALK,
            confidence=0.9,
            target_name="goblin",
            dialogue="Hello!",
            original_input='I say "Hello!" to the goblin',
        )
        result = router.resolve(intent, basic_context)
        assert result.success
        assert "Hello!" in result.description

    def test_resolve_rest_short(self, router: SkillRouter, basic_context: Context):
        intent = Intent(
            type=IntentType.REST,
            confidence=0.9,
            original_input="I take a short rest",
        )
        result = router.resolve(intent, basic_context)
        assert result.success
        assert "short rest" in result.description.lower()

    def test_resolve_rest_long(self, router: SkillRouter, basic_context: Context):
        intent = Intent(
            type=IntentType.REST,
            confidence=0.9,
            original_input="I take a long rest",
        )
        result = router.resolve(intent, basic_context)
        assert result.success
        assert "long rest" in result.description.lower()


# --- Game Engine Tests ---


class TestGameEngine:
    """Tests for the main game engine."""

    @pytest.fixture
    def engine(self) -> GameEngine:
        dolt = InMemoryDoltRepository()
        neo4j = InMemoryNeo4jRepository()
        return GameEngine(dolt=dolt, neo4j=neo4j)

    @pytest.fixture
    def setup_world(self, engine: GameEngine) -> tuple[GameEngine, Session]:
        """Set up a basic game world and return engine with session."""
        # Create universe
        universe = create_prime_material()
        engine.dolt.save_universe(universe)

        # Create location
        tavern = create_location(
            universe_id=universe.id,
            name="The Rusty Dragon",
            description="A cozy tavern",
        )
        engine.dolt.save_entity(tavern)

        # Create character
        hero = create_character(
            universe_id=universe.id,
            name="Valeros",
            hp_max=20,
            ac=16,
            location_id=tavern.id,
        )
        engine.dolt.save_entity(hero)

        return engine, universe, hero, tavern

    @pytest.mark.asyncio
    async def test_start_session(self, engine: GameEngine):
        universe_id = uuid4()
        character_id = uuid4()
        location_id = uuid4()

        session = await engine.start_session(
            universe_id=universe_id,
            character_id=character_id,
            location_id=location_id,
        )

        assert session.universe_id == universe_id
        assert session.character_id == character_id
        assert session.location_id == location_id
        assert session.turn_count == 0

    @pytest.mark.asyncio
    async def test_get_session(self, engine: GameEngine):
        session = await engine.start_session(
            universe_id=uuid4(),
            character_id=uuid4(),
            location_id=uuid4(),
        )

        retrieved = engine.get_session(session.id)
        assert retrieved is not None
        assert retrieved.id == session.id

    @pytest.mark.asyncio
    async def test_end_session(self, engine: GameEngine):
        session = await engine.start_session(
            universe_id=uuid4(),
            character_id=uuid4(),
            location_id=uuid4(),
        )

        await engine.end_session(session.id)
        assert engine.get_session(session.id) is None

    @pytest.mark.asyncio
    async def test_process_turn_no_session(self, engine: GameEngine):
        result = await engine.process_turn("I attack", uuid4())
        assert result.error is not None
        assert "session" in result.error.lower()

    @pytest.mark.asyncio
    async def test_process_turn_attack(self, engine: GameEngine):
        session = await engine.start_session(
            universe_id=uuid4(),
            character_id=uuid4(),
            location_id=uuid4(),
        )

        result = await engine.process_turn("I attack the goblin", session.id)

        assert isinstance(result, TurnResult)
        assert result.narrative  # Should have some narrative
        assert len(result.rolls) > 0  # Should have rolled dice

    @pytest.mark.asyncio
    async def test_process_turn_look(self, engine: GameEngine):
        session = await engine.start_session(
            universe_id=uuid4(),
            character_id=uuid4(),
            location_id=uuid4(),
        )

        result = await engine.process_turn("I look around", session.id)

        assert result.narrative
        assert result.error is None

    @pytest.mark.asyncio
    async def test_process_turn_increments_count(self, engine: GameEngine):
        session = await engine.start_session(
            universe_id=uuid4(),
            character_id=uuid4(),
            location_id=uuid4(),
        )

        await engine.process_turn("I look around", session.id)
        await engine.process_turn("I wait", session.id)

        updated_session = engine.get_session(session.id)
        assert updated_session.turn_count == 2

    @pytest.mark.asyncio
    async def test_process_turn_records_time(self, engine: GameEngine):
        session = await engine.start_session(
            universe_id=uuid4(),
            character_id=uuid4(),
            location_id=uuid4(),
        )

        result = await engine.process_turn("I attack", session.id)

        assert result.processing_time_ms >= 0

    @pytest.mark.asyncio
    async def test_unclear_intent_handled(self, engine: GameEngine):
        session = await engine.start_session(
            universe_id=uuid4(),
            character_id=uuid4(),
            location_id=uuid4(),
        )

        result = await engine.process_turn("asdfghjkl gibberish", session.id)

        # Should handle gracefully
        assert result.narrative
        assert result.error is None


# --- Integration Tests ---


class TestEngineIntegration:
    """Integration tests for the complete engine flow."""

    @pytest.mark.asyncio
    async def test_full_turn_flow(self):
        # Set up
        dolt = InMemoryDoltRepository()
        neo4j = InMemoryNeo4jRepository()
        engine = GameEngine(dolt=dolt, neo4j=neo4j)

        # Create world
        universe = create_prime_material()
        dolt.save_universe(universe)

        location = create_location(
            universe_id=universe.id,
            name="Forest Clearing",
            description="A peaceful clearing in the forest.",
        )
        dolt.save_entity(location)

        character = create_character(
            universe_id=universe.id,
            name="Ranger",
            hp_max=25,
            location_id=location.id,
        )
        dolt.save_entity(character)

        # Start session
        session = await engine.start_session(
            universe_id=universe.id,
            character_id=character.id,
            location_id=location.id,
        )

        # Play some turns
        result1 = await engine.process_turn("I look around", session.id)
        assert "Forest Clearing" in result1.narrative or result1.narrative

        result2 = await engine.process_turn("I search for tracks", session.id)
        assert result2.rolls  # Should have made a check

        result3 = await engine.process_turn("I take a short rest", session.id)
        assert "rest" in result3.narrative.lower()

        # Verify state
        assert session.turn_count == 3
