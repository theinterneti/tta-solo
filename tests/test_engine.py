"""Tests for the game engine components."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.engine import (
    AgentMessage,
    AgentOrchestrator,
    AgentRole,
    Context,
    EntitySummary,
    GameEngine,
    GMAgent,
    HybridIntentParser,
    Intent,
    IntentType,
    LorekeeperAgent,
    MessageType,
    MockLLMParser,
    PatternIntentParser,
    RulesLawyerAgent,
    Session,
    SkillRouter,
    TurnResult,
)
from src.models import (
    Relationship,
    RelationshipType,
    create_character,
    create_item,
    create_location,
    create_prime_material,
)

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


# --- Context Retrieval Tests (Phase 2) ---


class TestContextRetrieval:
    """Tests for enhanced context retrieval."""

    @pytest.fixture
    def setup_world(self):
        """Set up a world with relationships for context testing."""
        dolt = InMemoryDoltRepository()
        neo4j = InMemoryNeo4jRepository()

        # Create universe
        universe = create_prime_material()
        dolt.save_universe(universe)

        # Create locations
        tavern = create_location(
            universe_id=universe.id,
            name="The Rusty Dragon",
            description="A cozy tavern with a roaring fireplace.",
            danger_level=0,
        )
        dolt.save_entity(tavern)

        forest = create_location(
            universe_id=universe.id,
            name="Dark Forest",
            description="A foreboding forest.",
            danger_level=5,
        )
        dolt.save_entity(forest)

        # Create CONNECTED_TO relationship between locations
        connection = Relationship(
            universe_id=universe.id,
            relationship_type=RelationshipType.CONNECTED_TO,
            from_entity_id=tavern.id,
            to_entity_id=forest.id,
            description="north",
        )
        neo4j.create_relationship(connection)

        # Create character
        hero = create_character(
            universe_id=universe.id,
            name="Valeros",
            hp_max=30,
            ac=16,
            location_id=tavern.id,
        )
        dolt.save_entity(hero)

        # Create NPC in tavern
        barkeep = create_character(
            universe_id=universe.id,
            name="Ameiko",
            hp_max=15,
            location_id=tavern.id,
        )
        dolt.save_entity(barkeep)

        # Register NPC as LOCATED_IN tavern
        located_in = Relationship(
            universe_id=universe.id,
            relationship_type=RelationshipType.LOCATED_IN,
            from_entity_id=barkeep.id,
            to_entity_id=tavern.id,
        )
        neo4j.create_relationship(located_in)

        # Create item for inventory
        sword = create_item(
            universe_id=universe.id,
            name="Longsword",
            description="A well-balanced blade.",
        )
        dolt.save_entity(sword)

        # Hero CARRIES sword
        carries = Relationship(
            universe_id=universe.id,
            relationship_type=RelationshipType.CARRIES,
            from_entity_id=hero.id,
            to_entity_id=sword.id,
        )
        neo4j.create_relationship(carries)

        # Hero KNOWS barkeep
        knows = Relationship(
            universe_id=universe.id,
            relationship_type=RelationshipType.KNOWS,
            from_entity_id=hero.id,
            to_entity_id=barkeep.id,
            trust=0.8,
            description="A trusted friend.",
        )
        neo4j.create_relationship(knows)

        # Add atmosphere to tavern
        atmosphere = Relationship(
            universe_id=universe.id,
            relationship_type=RelationshipType.HAS_ATMOSPHERE,
            from_entity_id=tavern.id,
            to_entity_id=tavern.id,  # Self-reference for mood
            description="warm and welcoming",
        )
        neo4j.create_relationship(atmosphere)

        return {
            "dolt": dolt,
            "neo4j": neo4j,
            "universe": universe,
            "tavern": tavern,
            "forest": forest,
            "hero": hero,
            "barkeep": barkeep,
            "sword": sword,
        }

    @pytest.mark.asyncio
    async def test_context_includes_inventory(self, setup_world):
        """Test that context includes actor's inventory."""
        world = setup_world
        engine = GameEngine(dolt=world["dolt"], neo4j=world["neo4j"])

        session = await engine.start_session(
            universe_id=world["universe"].id,
            character_id=world["hero"].id,
            location_id=world["tavern"].id,
        )

        context = await engine._get_context(session)

        assert len(context.actor_inventory) == 1
        assert context.actor_inventory[0].name == "Longsword"

    @pytest.mark.asyncio
    async def test_context_includes_exits(self, setup_world):
        """Test that context includes location exits."""
        world = setup_world
        engine = GameEngine(dolt=world["dolt"], neo4j=world["neo4j"])

        session = await engine.start_session(
            universe_id=world["universe"].id,
            character_id=world["hero"].id,
            location_id=world["tavern"].id,
        )

        context = await engine._get_context(session)

        assert len(context.exits) == 1
        assert context.exits[0] == "north"

    @pytest.mark.asyncio
    async def test_context_includes_known_entities(self, setup_world):
        """Test that context includes actor's relationships."""
        world = setup_world
        engine = GameEngine(dolt=world["dolt"], neo4j=world["neo4j"])

        session = await engine.start_session(
            universe_id=world["universe"].id,
            character_id=world["hero"].id,
            location_id=world["tavern"].id,
        )

        context = await engine._get_context(session)

        assert len(context.known_entities) == 1
        assert context.known_entities[0].entity.name == "Ameiko"
        assert context.known_entities[0].relationship_type == "KNOWS"
        assert context.known_entities[0].trust == 0.8

    @pytest.mark.asyncio
    async def test_context_includes_entities_present(self, setup_world):
        """Test that context includes entities at the location."""
        world = setup_world
        engine = GameEngine(dolt=world["dolt"], neo4j=world["neo4j"])

        session = await engine.start_session(
            universe_id=world["universe"].id,
            character_id=world["hero"].id,
            location_id=world["tavern"].id,
        )

        context = await engine._get_context(session)

        assert len(context.entities_present) == 1
        assert context.entities_present[0].name == "Ameiko"

    @pytest.mark.asyncio
    async def test_context_includes_mood(self, setup_world):
        """Test that context includes location mood/atmosphere."""
        world = setup_world
        engine = GameEngine(dolt=world["dolt"], neo4j=world["neo4j"])

        session = await engine.start_session(
            universe_id=world["universe"].id,
            character_id=world["hero"].id,
            location_id=world["tavern"].id,
        )

        context = await engine._get_context(session)

        assert context.mood == "warm and welcoming"

    @pytest.mark.asyncio
    async def test_context_includes_danger_level(self, setup_world):
        """Test that context includes location danger level."""
        world = setup_world
        engine = GameEngine(dolt=world["dolt"], neo4j=world["neo4j"])

        # Test safe location
        session1 = await engine.start_session(
            universe_id=world["universe"].id,
            character_id=world["hero"].id,
            location_id=world["tavern"].id,
        )
        context1 = await engine._get_context(session1)
        assert context1.danger_level == 0

        # Test dangerous location
        session2 = await engine.start_session(
            universe_id=world["universe"].id,
            character_id=world["hero"].id,
            location_id=world["forest"].id,
        )
        context2 = await engine._get_context(session2)
        assert context2.danger_level == 5

    @pytest.mark.asyncio
    async def test_context_with_empty_relationships(self):
        """Test context when actor has no relationships."""
        dolt = InMemoryDoltRepository()
        neo4j = InMemoryNeo4jRepository()

        universe = create_prime_material()
        dolt.save_universe(universe)

        location = create_location(universe_id=universe.id, name="Empty Room")
        dolt.save_entity(location)

        character = create_character(
            universe_id=universe.id, name="Loner", location_id=location.id
        )
        dolt.save_entity(character)

        engine = GameEngine(dolt=dolt, neo4j=neo4j)
        session = await engine.start_session(
            universe_id=universe.id,
            character_id=character.id,
            location_id=location.id,
        )

        context = await engine._get_context(session)

        assert context.actor.name == "Loner"
        assert context.location.name == "Empty Room"
        assert context.actor_inventory == []
        assert context.exits == []
        assert context.known_entities == []
        assert context.entities_present == []
        assert context.mood is None


# --- Agent System Tests (Phase 3) ---


class TestAgentMessage:
    """Tests for agent message protocol."""

    def test_create_message(self):
        msg = AgentMessage(
            type=MessageType.REQUEST_CONTEXT,
            from_agent=AgentRole.GM,
            to_agent=AgentRole.LOREKEEPER,
            payload={"session_id": "test"},
        )
        assert msg.type == MessageType.REQUEST_CONTEXT
        assert msg.from_agent == AgentRole.GM
        assert msg.to_agent == AgentRole.LOREKEEPER

    def test_reply_links_correlation_id(self):
        original = AgentMessage(
            type=MessageType.REQUEST_CONTEXT,
            from_agent=AgentRole.GM,
        )
        reply = original.reply(
            type=MessageType.CONTEXT_RESPONSE,
            payload={"context": "test"},
            from_agent=AgentRole.LOREKEEPER,
        )
        assert reply.correlation_id == original.id
        assert reply.to_agent == AgentRole.GM
        assert reply.from_agent == AgentRole.LOREKEEPER


class TestLorekeeperAgent:
    """Tests for the Lorekeeper agent."""

    @pytest.fixture
    def setup_lorekeeper(self):
        dolt = InMemoryDoltRepository()
        neo4j = InMemoryNeo4jRepository()

        universe = create_prime_material()
        dolt.save_universe(universe)

        location = create_location(
            universe_id=universe.id,
            name="Test Location",
            danger_level=3,
        )
        dolt.save_entity(location)

        character = create_character(
            universe_id=universe.id,
            name="Test Hero",
            hp_max=20,
            location_id=location.id,
        )
        dolt.save_entity(character)

        lorekeeper = LorekeeperAgent(dolt=dolt, neo4j=neo4j)

        return {
            "lorekeeper": lorekeeper,
            "dolt": dolt,
            "neo4j": neo4j,
            "universe": universe,
            "location": location,
            "character": character,
        }

    @pytest.mark.asyncio
    async def test_handle_context_request(self, setup_lorekeeper):
        world = setup_lorekeeper
        session = Session(
            universe_id=world["universe"].id,
            character_id=world["character"].id,
            location_id=world["location"].id,
        )

        msg = AgentMessage(
            type=MessageType.REQUEST_CONTEXT,
            from_agent=AgentRole.GM,
            payload={"session": session},
        )

        response = await world["lorekeeper"].handle(msg)

        assert response.type == MessageType.CONTEXT_RESPONSE
        assert "context" in response.payload
        context = response.payload["context"]
        assert context.actor.name == "Test Hero"
        assert context.location.name == "Test Location"
        assert context.danger_level == 3

    @pytest.mark.asyncio
    async def test_handle_wrong_message_type(self, setup_lorekeeper):
        world = setup_lorekeeper
        msg = AgentMessage(
            type=MessageType.REQUEST_RESOLUTION,
            from_agent=AgentRole.GM,
        )

        response = await world["lorekeeper"].handle(msg)
        assert response.type == MessageType.ERROR


class TestRulesLawyerAgent:
    """Tests for the Rules Lawyer agent."""

    @pytest.fixture
    def setup_rules_lawyer(self):
        return RulesLawyerAgent()

    @pytest.mark.asyncio
    async def test_handle_resolution_request(self, setup_rules_lawyer):
        rules_lawyer = setup_rules_lawyer

        intent = Intent(
            type=IntentType.ATTACK,
            confidence=1.0,
            target_name="goblin",
            original_input="I attack the goblin",
            reasoning="Attack command detected",
        )
        context = Context(
            actor=EntitySummary(id=uuid4(), name="Hero", type="character", ac=15),
            location=EntitySummary(id=uuid4(), name="Cave", type="location"),
            entities_present=[
                EntitySummary(id=uuid4(), name="Goblin", type="character", ac=13)
            ],
        )

        msg = AgentMessage(
            type=MessageType.REQUEST_RESOLUTION,
            from_agent=AgentRole.GM,
            payload={"intent": intent, "context": context},
        )

        response = await rules_lawyer.handle(msg)

        assert response.type == MessageType.RESOLUTION_RESPONSE
        assert "result" in response.payload
        result = response.payload["result"]
        assert result.roll is not None  # Should have rolled dice

    def test_validate_action_valid_move(self, setup_rules_lawyer):
        rules_lawyer = setup_rules_lawyer

        intent = Intent(
            type=IntentType.MOVE,
            confidence=1.0,
            destination="north",
            original_input="go north",
            reasoning="Movement detected",
        )
        context = Context(
            actor=EntitySummary(id=uuid4(), name="Hero", type="character"),
            location=EntitySummary(id=uuid4(), name="Room", type="location"),
            exits=["north", "south"],
        )

        is_valid, reason = rules_lawyer.validate_action(intent, context)
        assert is_valid

    def test_validate_action_invalid_move(self, setup_rules_lawyer):
        rules_lawyer = setup_rules_lawyer

        intent = Intent(
            type=IntentType.MOVE,
            confidence=1.0,
            destination="west",
            original_input="go west",
            reasoning="Movement detected",
        )
        context = Context(
            actor=EntitySummary(id=uuid4(), name="Hero", type="character"),
            location=EntitySummary(id=uuid4(), name="Room", type="location"),
            exits=["north", "south"],
        )

        is_valid, reason = rules_lawyer.validate_action(intent, context)
        assert not is_valid
        assert "Cannot go west" in reason


class TestGMAgent:
    """Tests for the GM agent."""

    @pytest.fixture
    def setup_gm(self):
        return GMAgent(tone="adventure", verbosity="normal")

    @pytest.mark.asyncio
    async def test_parse_intent(self, setup_gm):
        gm = setup_gm

        intent = await gm.parse_intent("I attack the dragon")

        assert intent.type == IntentType.ATTACK
        assert "dragon" in intent.target_name.lower()

    @pytest.mark.asyncio
    async def test_generate_narrative_from_skill_result(self, setup_gm):
        gm = setup_gm

        intent = Intent(
            type=IntentType.ATTACK,
            confidence=1.0,
            target_name="goblin",
            original_input="attack goblin",
            reasoning="",
        )
        context = Context(
            actor=EntitySummary(id=uuid4(), name="Hero", type="character"),
            location=EntitySummary(id=uuid4(), name="Cave", type="location"),
        )
        from src.engine.models import SkillResult

        skill_results = [
            SkillResult(
                success=True,
                outcome="success",
                roll=18,
                total=22,
                dc=13,
                damage=8,
                description="Hit goblin! Rolled 22 vs AC 13. 8 damage.",
            )
        ]

        narrative = await gm.generate_narrative(intent, context, skill_results)

        assert "Hit goblin" in narrative
        assert "8 damage" in narrative


class TestAgentOrchestrator:
    """Tests for the agent orchestrator."""

    @pytest.fixture
    def setup_orchestrator(self):
        dolt = InMemoryDoltRepository()
        neo4j = InMemoryNeo4jRepository()

        universe = create_prime_material()
        dolt.save_universe(universe)

        location = create_location(
            universe_id=universe.id,
            name="Town Square",
            danger_level=0,
        )
        dolt.save_entity(location)

        character = create_character(
            universe_id=universe.id,
            name="Adventurer",
            hp_max=25,
            location_id=location.id,
        )
        dolt.save_entity(character)

        gm = GMAgent()
        rules_lawyer = RulesLawyerAgent()
        lorekeeper = LorekeeperAgent(dolt=dolt, neo4j=neo4j)

        orchestrator = AgentOrchestrator(
            gm=gm,
            rules_lawyer=rules_lawyer,
            lorekeeper=lorekeeper,
        )

        return {
            "orchestrator": orchestrator,
            "universe": universe,
            "location": location,
            "character": character,
        }

    @pytest.mark.asyncio
    async def test_process_turn_look(self, setup_orchestrator):
        world = setup_orchestrator
        session = Session(
            universe_id=world["universe"].id,
            character_id=world["character"].id,
            location_id=world["location"].id,
        )

        intent, context, skill_results, narrative = await world[
            "orchestrator"
        ].process_turn("I look around", session)

        assert intent.type == IntentType.LOOK
        assert context.location.name == "Town Square"
        assert "Town Square" in narrative

    @pytest.mark.asyncio
    async def test_process_turn_attack(self, setup_orchestrator):
        world = setup_orchestrator
        session = Session(
            universe_id=world["universe"].id,
            character_id=world["character"].id,
            location_id=world["location"].id,
        )

        intent, context, skill_results, narrative = await world[
            "orchestrator"
        ].process_turn("I attack the enemy", session)

        assert intent.type == IntentType.ATTACK
        assert len(skill_results) > 0


class TestGameEngineWithAgents:
    """Tests for GameEngine with agent system enabled."""

    @pytest.mark.asyncio
    async def test_engine_with_agents_enabled(self):
        dolt = InMemoryDoltRepository()
        neo4j = InMemoryNeo4jRepository()

        universe = create_prime_material()
        dolt.save_universe(universe)

        location = create_location(
            universe_id=universe.id,
            name="Forest Path",
        )
        dolt.save_entity(location)

        character = create_character(
            universe_id=universe.id,
            name="Ranger",
            location_id=location.id,
        )
        dolt.save_entity(character)

        # Create engine with agents enabled
        engine = GameEngine(dolt=dolt, neo4j=neo4j, use_agents=True)

        session = await engine.start_session(
            universe_id=universe.id,
            character_id=character.id,
            location_id=location.id,
        )

        result = await engine.process_turn("I look around", session.id)

        assert result.narrative
        assert "Forest Path" in result.narrative or result.narrative

    @pytest.mark.asyncio
    async def test_engine_agents_attack(self):
        dolt = InMemoryDoltRepository()
        neo4j = InMemoryNeo4jRepository()

        universe = create_prime_material()
        dolt.save_universe(universe)

        location = create_location(universe_id=universe.id, name="Arena")
        dolt.save_entity(location)

        character = create_character(
            universe_id=universe.id, name="Fighter", hp_max=30, location_id=location.id
        )
        dolt.save_entity(character)

        engine = GameEngine(dolt=dolt, neo4j=neo4j, use_agents=True)
        session = await engine.start_session(
            universe_id=universe.id,
            character_id=character.id,
            location_id=location.id,
        )

        result = await engine.process_turn("I attack the monster", session.id)

        # Should have made a roll
        assert len(result.rolls) > 0 or result.narrative
