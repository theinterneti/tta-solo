"""
Tests for the Move Executor service.

Tests that GM moves actually create entities and modify world state.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.engine.models import Context, EntitySummary, Session
from src.engine.pbta import GMMove, GMMoveType
from src.services.move_executor import (
    MoveExecutionResult,
    MoveExecutor,
    NPCGenerationParams,
    NPC_TEMPLATES,
)
from src.services.npc import NPCService


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def dolt():
    """Create an in-memory Dolt repository."""
    return InMemoryDoltRepository()


@pytest.fixture
def neo4j():
    """Create an in-memory Neo4j repository."""
    return InMemoryNeo4jRepository()


@pytest.fixture
def npc_service(dolt, neo4j):
    """Create an NPC service with in-memory repositories."""
    return NPCService(dolt=dolt, neo4j=neo4j)


@pytest.fixture
def executor(dolt, neo4j, npc_service):
    """Create a MoveExecutor with in-memory repositories."""
    return MoveExecutor(
        dolt=dolt,
        neo4j=neo4j,
        npc_service=npc_service,
        llm=None,  # Use templates
    )


@pytest.fixture
def session():
    """Create a basic game session."""
    universe_id = uuid4()
    location_id = uuid4()
    character_id = uuid4()
    return Session(
        universe_id=universe_id,
        location_id=location_id,
        character_ids=[character_id],
        active_character_id=character_id,
    )


@pytest.fixture
def basic_context(session):
    """Create a basic game context."""
    return Context(
        actor=EntitySummary(
            id=session.character_id,
            name="Hero",
            type="character",
        ),
        actor_inventory=[],
        location=EntitySummary(
            id=session.location_id,
            name="The Rusty Tavern",
            type="location",
            description="A smoky tavern filled with rough-looking patrons.",
        ),
        entities_present=[],
        exits=["north", "south"],
        known_entities=[],
        recent_events=[],
        mood=None,
        danger_level=3,
    )


@pytest.fixture
def dungeon_context(session):
    """Create a dungeon context for testing."""
    return Context(
        actor=EntitySummary(
            id=session.character_id,
            name="Hero",
            type="character",
        ),
        actor_inventory=[
            EntitySummary(id=uuid4(), name="Torch", type="item"),
            EntitySummary(id=uuid4(), name="Sword", type="item"),
        ],
        location=EntitySummary(
            id=session.location_id,
            name="Dark Dungeon",
            type="location",
            description="A damp, dark dungeon corridor.",
        ),
        entities_present=[],
        exits=["east"],
        known_entities=[],
        recent_events=[],
        mood="ominous",
        danger_level=12,
    )


# =============================================================================
# Basic Execution Tests
# =============================================================================


class TestMoveExecutorBasics:
    """Basic tests for MoveExecutor functionality."""

    @pytest.mark.asyncio
    async def test_narrative_only_move_returns_description(self, executor, basic_context, session):
        """Narrative-only moves should just return the description."""
        move = GMMove(
            type=GMMoveType.SHOW_DANGER,
            is_hard=False,
            description="Something dangerous lurks nearby...",
        )

        result = await executor.execute(move, basic_context, session)

        assert result.success
        assert result.narrative == "Something dangerous lurks nearby..."
        assert len(result.entities_created) == 0

    @pytest.mark.asyncio
    async def test_executor_returns_result_type(self, executor, basic_context, session):
        """Executor should always return MoveExecutionResult."""
        move = GMMove(
            type=GMMoveType.INTRODUCE_NPC,
            is_hard=False,
            description="Someone appears...",
        )

        result = await executor.execute(move, basic_context, session)

        assert isinstance(result, MoveExecutionResult)


# =============================================================================
# INTRODUCE_NPC Tests
# =============================================================================


class TestIntroduceNPC:
    """Tests for the INTRODUCE_NPC move execution."""

    @pytest.mark.asyncio
    async def test_introduce_npc_creates_entity(self, executor, dolt, basic_context, session):
        """INTRODUCE_NPC should create an entity in Dolt."""
        move = GMMove(
            type=GMMoveType.INTRODUCE_NPC,
            is_hard=False,
            description="Someone appears...",
        )

        result = await executor.execute(move, basic_context, session)

        assert result.success
        assert len(result.entities_created) == 1

        # Verify entity was saved
        entity_id = result.entities_created[0]
        entity = dolt.get_entity(entity_id, session.universe_id)
        assert entity is not None
        assert entity.name  # Has a name

    @pytest.mark.asyncio
    async def test_introduce_npc_creates_profile(
        self, executor, npc_service, basic_context, session
    ):
        """INTRODUCE_NPC should create an NPC profile."""
        move = GMMove(
            type=GMMoveType.INTRODUCE_NPC,
            is_hard=False,
            description="Someone appears...",
        )

        result = await executor.execute(move, basic_context, session)

        # Get the created entity
        entity_id = result.entities_created[0]

        # Verify profile was created
        profile = npc_service.get_profile(entity_id)
        assert profile is not None
        assert 0 <= profile.traits.openness <= 100
        assert 0 <= profile.traits.extraversion <= 100

    @pytest.mark.asyncio
    async def test_introduce_npc_creates_located_in_relationship(
        self, executor, neo4j, basic_context, session
    ):
        """INTRODUCE_NPC should create LOCATED_IN relationship."""
        move = GMMove(
            type=GMMoveType.INTRODUCE_NPC,
            is_hard=False,
            description="Someone appears...",
        )

        result = await executor.execute(move, basic_context, session)

        assert len(result.relationships_created) == 1

        # Verify relationship was created
        entity_id = result.entities_created[0]
        relationships = neo4j.get_relationships(
            session.location_id,
            session.universe_id,
            relationship_type="LOCATED_IN",
        )

        # Find the relationship for our NPC
        npc_rel = [r for r in relationships if r.from_entity_id == entity_id]
        assert len(npc_rel) == 1

    @pytest.mark.asyncio
    async def test_introduce_npc_generates_narrative(self, executor, basic_context, session):
        """INTRODUCE_NPC should generate a narrative."""
        move = GMMove(
            type=GMMoveType.INTRODUCE_NPC,
            is_hard=False,
            description="Someone appears...",
        )

        result = await executor.execute(move, basic_context, session)

        assert result.narrative
        assert len(result.narrative) > 20  # Not just empty

    @pytest.mark.asyncio
    async def test_introduce_npc_uses_tavern_templates_for_tavern(
        self, executor, basic_context, session
    ):
        """Tavern context should use tavern NPC templates."""
        move = GMMove(
            type=GMMoveType.INTRODUCE_NPC,
            is_hard=False,
            description="Someone appears...",
        )

        # Run multiple times to verify template usage
        tavern_names = set()
        for template in NPC_TEMPLATES.get("tavern", []):
            tavern_names.update(template.names)

        found_tavern_npc = False
        for _ in range(10):
            result = await executor.execute(move, basic_context, session)
            entity_id = result.entities_created[0]
            entity = executor.dolt.get_entity(entity_id, session.universe_id)
            if entity and entity.name in tavern_names:
                found_tavern_npc = True
                break

        assert found_tavern_npc, "Should use tavern templates for tavern location"

    @pytest.mark.asyncio
    async def test_introduce_npc_uses_dungeon_templates_for_dungeon(
        self, executor, dungeon_context, session
    ):
        """Dungeon context should use dungeon NPC templates."""
        move = GMMove(
            type=GMMoveType.INTRODUCE_NPC,
            is_hard=False,
            description="Someone appears...",
        )

        dungeon_names = set()
        for template in NPC_TEMPLATES.get("dungeon", []):
            dungeon_names.update(template.names)

        found_dungeon_npc = False
        for _ in range(10):
            result = await executor.execute(move, dungeon_context, session)
            entity_id = result.entities_created[0]
            entity = executor.dolt.get_entity(entity_id, session.universe_id)
            if entity and entity.name in dungeon_names:
                found_dungeon_npc = True
                break

        assert found_dungeon_npc, "Should use dungeon templates for dungeon location"


# =============================================================================
# CHANGE_ENVIRONMENT Tests
# =============================================================================


class TestChangeEnvironment:
    """Tests for the CHANGE_ENVIRONMENT move execution."""

    @pytest.mark.asyncio
    async def test_change_environment_low_danger_returns_atmosphere(
        self, executor, basic_context, session
    ):
        """Low danger should change atmosphere (narrative only)."""
        # basic_context has danger_level=3
        move = GMMove(
            type=GMMoveType.CHANGE_ENVIRONMENT,
            is_hard=False,
            description="The environment shifts...",
        )

        result = await executor.execute(move, basic_context, session)

        assert result.success
        assert result.narrative
        # Low danger = atmosphere change (no entities)
        assert len(result.entities_created) == 0

    @pytest.mark.asyncio
    async def test_change_environment_high_danger_creates_feature(
        self, executor, dungeon_context, session
    ):
        """High danger should create a location feature."""
        # dungeon_context has danger_level=12
        move = GMMove(
            type=GMMoveType.CHANGE_ENVIRONMENT,
            is_hard=False,
            description="The environment shifts...",
        )

        result = await executor.execute(move, dungeon_context, session)

        assert result.success
        # High danger = creates feature entity
        assert len(result.entities_created) == 1
        assert len(result.relationships_created) == 1


# =============================================================================
# TAKE_AWAY Tests
# =============================================================================


class TestTakeAway:
    """Tests for the TAKE_AWAY move execution."""

    @pytest.mark.asyncio
    async def test_take_away_with_no_inventory_returns_narrative(
        self, executor, basic_context, session
    ):
        """TAKE_AWAY with no inventory should return special narrative."""
        move = GMMove(
            type=GMMoveType.TAKE_AWAY,
            is_hard=True,
            description="Something is lost!",
        )

        result = await executor.execute(move, basic_context, session)

        assert result.success
        assert "nothing to lose" in result.narrative.lower()

    @pytest.mark.asyncio
    async def test_take_away_with_inventory_mentions_item(self, executor, dungeon_context, session):
        """TAKE_AWAY with inventory should mention the lost item."""
        move = GMMove(
            type=GMMoveType.TAKE_AWAY,
            is_hard=True,
            description="Something is lost!",
        )

        result = await executor.execute(move, dungeon_context, session)

        assert result.success
        # Should mention one of the items (Torch or Sword)
        assert "torch" in result.narrative.lower() or "sword" in result.narrative.lower()

    @pytest.mark.asyncio
    async def test_take_away_marks_item_inactive(self, dolt, neo4j, npc_service, session):
        """TAKE_AWAY should mark the item as inactive in Dolt."""
        from src.models import create_item

        # Create an item that exists in Dolt
        item = create_item(
            universe_id=session.universe_id,
            name="Magic Sword",
            description="A gleaming blade",
        )
        dolt.save_entity(item)

        # Create context with the item in inventory
        context = Context(
            actor=EntitySummary(
                id=session.character_id,
                name="Hero",
                type="character",
            ),
            actor_inventory=[
                EntitySummary(id=item.id, name=item.name, type="item"),
            ],
            location=EntitySummary(
                id=session.location_id,
                name="Test Location",
                type="location",
            ),
            entities_present=[],
            exits=[],
            known_entities=[],
            recent_events=[],
            mood=None,
            danger_level=5,
        )

        executor = MoveExecutor(
            dolt=dolt,
            neo4j=neo4j,
            npc_service=npc_service,
            llm=None,
        )

        move = GMMove(
            type=GMMoveType.TAKE_AWAY,
            is_hard=True,
            description="Something is lost!",
        )

        result = await executor.execute(move, context, session)

        assert result.success
        assert "magic sword" in result.narrative.lower()

        # Verify item was marked inactive
        updated_item = dolt.get_entity(item.id, session.universe_id)
        assert updated_item is not None
        assert updated_item.is_active is False
        assert "[Lost]" in updated_item.description


# =============================================================================
# CAPTURE Tests
# =============================================================================


class TestCapture:
    """Tests for the CAPTURE move execution."""

    @pytest.mark.asyncio
    async def test_capture_creates_trap_location(self, executor, dolt, basic_context, session):
        """CAPTURE should create a trap location."""
        move = GMMove(
            type=GMMoveType.CAPTURE,
            is_hard=True,
            description="You're trapped!",
        )

        result = await executor.execute(move, basic_context, session)

        assert result.success
        assert len(result.entities_created) == 1

        # Verify it's a location
        trap_id = result.entities_created[0]
        trap = dolt.get_entity(trap_id, session.universe_id)
        assert trap is not None
        assert (
            "trap" in trap.name.lower()
            or "cell" in trap.name.lower()
            or "pit" in trap.name.lower()
            or "sealed" in trap.name.lower()
            or "collapsed" in trap.name.lower()
        )

    @pytest.mark.asyncio
    async def test_capture_creates_relationships(self, executor, neo4j, basic_context, session):
        """CAPTURE should create LOCATED_IN and TRAPPED_IN relationships."""
        move = GMMove(
            type=GMMoveType.CAPTURE,
            is_hard=True,
            description="You're trapped!",
        )

        result = await executor.execute(move, basic_context, session)

        # Creates 2 relationships: LOCATED_IN and TRAPPED_IN
        assert len(result.relationships_created) == 2

    @pytest.mark.asyncio
    async def test_capture_narrative_mentions_trapped(self, executor, basic_context, session):
        """CAPTURE narrative should mention being trapped."""
        move = GMMove(
            type=GMMoveType.CAPTURE,
            is_hard=True,
            description="You're trapped!",
        )

        result = await executor.execute(move, basic_context, session)

        assert "trap" in result.narrative.lower()

    @pytest.mark.asyncio
    async def test_capture_updates_session_location(self, executor, basic_context, session):
        """CAPTURE should update the session location to the trap."""
        original_location = session.location_id

        move = GMMove(
            type=GMMoveType.CAPTURE,
            is_hard=True,
            description="You're trapped!",
        )

        result = await executor.execute(move, basic_context, session)

        assert result.success
        # Session location should be updated to the trap
        assert session.location_id != original_location
        assert session.location_id == result.entities_created[0]

    @pytest.mark.asyncio
    async def test_capture_creates_trapped_in_relationship(self, executor, neo4j, basic_context, session):
        """CAPTURE should create a TRAPPED_IN relationship."""
        move = GMMove(
            type=GMMoveType.CAPTURE,
            is_hard=True,
            description="You're trapped!",
        )

        result = await executor.execute(move, basic_context, session)

        assert result.success
        # Should have 2 relationships: LOCATED_IN and TRAPPED_IN
        assert len(result.relationships_created) == 2

        # Check for TRAPPED_IN relationship
        trap_id = result.entities_created[0]
        relationships = neo4j.get_relationships(
            trap_id,
            session.universe_id,
            relationship_type="TRAPPED_IN",
        )
        trapped_rel = [r for r in relationships if r.from_entity_id == session.character_id]
        assert len(trapped_rel) == 1


# =============================================================================
# REVEAL_UNWELCOME_TRUTH Tests
# =============================================================================


class TestRevealTruth:
    """Tests for the REVEAL_UNWELCOME_TRUTH move execution."""

    @pytest.mark.asyncio
    async def test_reveal_truth_returns_narrative(self, executor, basic_context, session):
        """REVEAL_UNWELCOME_TRUTH should return a troubling narrative."""
        move = GMMove(
            type=GMMoveType.REVEAL_UNWELCOME_TRUTH,
            is_hard=False,
            description="You realize something...",
        )

        result = await executor.execute(move, basic_context, session)

        assert result.success
        assert result.narrative
        assert len(result.narrative) > 20


# =============================================================================
# Template Generation Tests
# =============================================================================


class TestNPCTemplateGeneration:
    """Tests for NPC template-based generation."""

    def test_template_npc_parameters_returns_valid_params(self, executor, basic_context):
        """Template generation should return valid NPCGenerationParams."""
        params = executor._template_npc_parameters(basic_context)

        assert isinstance(params, NPCGenerationParams)
        assert params.name
        assert params.description
        assert 0 <= params.openness <= 100
        assert 0 <= params.conscientiousness <= 100
        assert 0 <= params.extraversion <= 100
        assert 0 <= params.agreeableness <= 100
        assert 0 <= params.neuroticism <= 100

    def test_get_location_type_tavern(self, executor, basic_context):
        """Should identify tavern location type."""
        location_type = executor._get_location_type(basic_context)
        assert location_type == "tavern"

    def test_get_location_type_dungeon(self, executor, dungeon_context):
        """Should identify dungeon location type."""
        location_type = executor._get_location_type(dungeon_context)
        assert location_type == "dungeon"

    def test_get_location_type_default(self, executor, session):
        """Unknown location should return default."""
        context = Context(
            actor=EntitySummary(id=session.character_id, name="Hero", type="character"),
            actor_inventory=[],
            location=EntitySummary(
                id=session.location_id,
                name="Strange Place",
                type="location",
            ),
            entities_present=[],
            exits=[],
            known_entities=[],
            recent_events=[],
            mood=None,
            danger_level=5,
        )

        location_type = executor._get_location_type(context)
        assert location_type == "default"


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling and graceful degradation."""

    @pytest.mark.asyncio
    async def test_unknown_move_type_returns_description(self, executor, basic_context, session):
        """Unknown move types should return description as narrative."""
        # USE_MONSTER_MOVE is not in generators, so it's narrative-only
        move = GMMove(
            type=GMMoveType.USE_MONSTER_MOVE,
            is_hard=True,
            description="The creature attacks!",
        )

        result = await executor.execute(move, basic_context, session)

        assert result.success
        assert result.narrative == "The creature attacks!"
        assert len(result.entities_created) == 0

    @pytest.mark.asyncio
    async def test_executor_handles_minimal_context_location(self, executor, session):
        """Executor should handle minimal location gracefully."""
        context = Context(
            actor=EntitySummary(id=session.character_id, name="Hero", type="character"),
            actor_inventory=[],
            location=EntitySummary(
                id=session.location_id,
                name="",  # Empty name
                type="location",
            ),
            entities_present=[],
            exits=[],
            known_entities=[],
            recent_events=[],
            mood=None,
            danger_level=5,
        )

        move = GMMove(
            type=GMMoveType.INTRODUCE_NPC,
            is_hard=False,
            description="Someone appears...",
        )

        # Should use default templates, not crash
        result = await executor.execute(move, context, session)
        assert result.success


# =============================================================================
# LLM NPC Generation Tests
# =============================================================================


class TestLLMNPCGeneration:
    """Tests for LLM-powered NPC generation."""

    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM service."""
        from unittest.mock import AsyncMock, MagicMock

        llm = MagicMock()
        llm.is_available = True
        llm.provider = MagicMock()
        llm.provider.complete = AsyncMock()
        return llm

    @pytest.fixture
    def llm_executor(self, dolt, neo4j, npc_service, mock_llm):
        """Create a MoveExecutor with mock LLM."""
        return MoveExecutor(
            dolt=dolt,
            neo4j=neo4j,
            npc_service=npc_service,
            llm=mock_llm,
        )

    @pytest.mark.asyncio
    async def test_llm_npc_generation_parses_valid_json(
        self, llm_executor, mock_llm, basic_context, session
    ):
        """LLM NPC generation should parse valid JSON response."""
        mock_llm.provider.complete.return_value = """{
            "name": "Grizzled Bartender",
            "description": "A scarred veteran with one eye, polishing glasses endlessly.",
            "role": "merchant",
            "traits": {
                "openness": 45,
                "conscientiousness": 70,
                "extraversion": 65,
                "agreeableness": 40,
                "neuroticism": 30
            },
            "motivations": ["wealth", "safety"],
            "speech_style": "gruff",
            "quirks": ["Always polishing something"],
            "initial_attitude": "neutral"
        }"""

        move = GMMove(
            type=GMMoveType.INTRODUCE_NPC,
            is_hard=False,
            description="Someone appears...",
        )

        result = await llm_executor.execute(move, basic_context, session)

        assert result.success
        assert "Grizzled Bartender" in result.narrative
        assert mock_llm.provider.complete.called

    @pytest.mark.asyncio
    async def test_llm_npc_generation_handles_markdown_code_blocks(
        self, llm_executor, mock_llm, basic_context, session
    ):
        """Should handle JSON wrapped in markdown code blocks."""
        mock_llm.provider.complete.return_value = """```json
{
    "name": "Hooded Figure",
    "description": "A mysterious stranger in dark robes.",
    "role": "stranger",
    "traits": {"openness": 30},
    "motivations": ["knowledge"],
    "speech_style": "mysterious"
}
```"""

        move = GMMove(
            type=GMMoveType.INTRODUCE_NPC,
            is_hard=False,
            description="Someone appears...",
        )

        result = await llm_executor.execute(move, basic_context, session)

        assert result.success
        assert "Hooded Figure" in result.narrative

    @pytest.mark.asyncio
    async def test_llm_npc_generation_falls_back_on_invalid_json(
        self, llm_executor, mock_llm, basic_context, session
    ):
        """Invalid JSON should fall back to templates."""
        mock_llm.provider.complete.return_value = "This is not valid JSON at all!"

        move = GMMove(
            type=GMMoveType.INTRODUCE_NPC,
            is_hard=False,
            description="Someone appears...",
        )

        result = await llm_executor.execute(move, basic_context, session)

        # Should still succeed via template fallback
        assert result.success
        assert len(result.entities_created) == 1

    @pytest.mark.asyncio
    async def test_llm_npc_generation_falls_back_on_exception(
        self, llm_executor, mock_llm, basic_context, session
    ):
        """LLM exceptions should fall back to templates."""
        mock_llm.provider.complete.side_effect = RuntimeError("API error")

        move = GMMove(
            type=GMMoveType.INTRODUCE_NPC,
            is_hard=False,
            description="Someone appears...",
        )

        result = await llm_executor.execute(move, basic_context, session)

        # Should still succeed via template fallback
        assert result.success
        assert len(result.entities_created) == 1

    @pytest.mark.asyncio
    async def test_llm_npc_generation_clamps_trait_values(
        self, llm_executor, mock_llm, basic_context, session
    ):
        """Trait values outside 0-100 should be clamped."""
        mock_llm.provider.complete.return_value = """{
            "name": "Extreme Personality",
            "description": "Someone with extreme traits.",
            "role": "stranger",
            "traits": {
                "openness": 150,
                "conscientiousness": -50,
                "extraversion": 200,
                "agreeableness": 50,
                "neuroticism": null
            },
            "motivations": ["power"],
            "speech_style": "intense"
        }"""

        params = await llm_executor._llm_generate_npc(basic_context, session, "miss")

        assert params.openness == 100  # Clamped from 150
        assert params.conscientiousness == 0  # Clamped from -50
        assert params.extraversion == 100  # Clamped from 200
        assert params.agreeableness == 50  # Normal
        assert params.neuroticism == 50  # Default for null

    @pytest.mark.asyncio
    async def test_llm_npc_generation_handles_unknown_motivations(
        self, llm_executor, mock_llm, basic_context, session
    ):
        """Unknown motivation strings should be skipped."""
        mock_llm.provider.complete.return_value = """{
            "name": "Weird Motives",
            "description": "Someone with strange goals.",
            "role": "stranger",
            "traits": {},
            "motivations": ["unknown_motivation", "power", "also_unknown"],
            "speech_style": "odd"
        }"""

        params = await llm_executor._llm_generate_npc(basic_context, session, "miss")

        # Only 'power' should be parsed, unknown ones skipped
        from src.models.npc import Motivation

        assert Motivation.POWER in params.motivations
        assert len(params.motivations) >= 1  # At least power

    def test_parse_npc_response_extracts_json_from_text(self, llm_executor, basic_context):
        """Should extract JSON from surrounding text."""
        response = """Here's an NPC for you:
        {"name": "Embedded NPC", "description": "test", "role": "test"}
        Hope you like it!"""

        params = llm_executor._parse_npc_response(response, basic_context)
        assert params.name == "Embedded NPC"

    def test_build_npc_generation_prompt_includes_context(self, llm_executor, basic_context):
        """Prompt should include location and context information."""
        prompt = llm_executor._build_npc_generation_prompt(basic_context, "miss")

        assert "Rusty Tavern" in prompt
        assert "Danger Level: 3/20" in prompt
        assert "miss" in prompt

    def test_clamp_trait_handles_edge_cases(self, llm_executor):
        """Trait clamping should handle various input types."""
        assert llm_executor._clamp_trait(150) == 100
        assert llm_executor._clamp_trait(-10) == 0
        assert llm_executor._clamp_trait(50) == 50
        assert llm_executor._clamp_trait(None) == 50
        assert llm_executor._clamp_trait(50.7) == 50  # Float to int
