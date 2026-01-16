"""
Integration tests for the Move Executor system.

Tests the MoveExecutor directly to verify it creates entities correctly.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.engine.models import Context, EntitySummary, Session
from src.engine.pbta import GMMove, GMMoveType
from src.models import (
    create_character,
    create_location,
    create_prime_material,
)
from src.services.move_executor import MoveExecutor
from src.services.npc import NPCService


def count_entities(dolt: InMemoryDoltRepository) -> int:
    """Count total entities on the current branch."""
    branch = dolt.get_current_branch()
    return len(dolt._entities.get(branch, {}))


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
    """Create an NPC service."""
    return NPCService(dolt=dolt, neo4j=neo4j)


@pytest.fixture
def move_executor(dolt, neo4j, npc_service):
    """Create a MoveExecutor without LLM (template mode)."""
    return MoveExecutor(
        dolt=dolt,
        neo4j=neo4j,
        npc_service=npc_service,
        llm=None,
    )


@pytest.fixture
def universe(dolt):
    """Create a test universe."""
    universe = create_prime_material()
    dolt.save_universe(universe)
    return universe


@pytest.fixture
def tavern_location(dolt, universe):
    """Create a tavern location."""
    loc = create_location(
        universe_id=universe.id,
        name="The Rusty Tavern",
        description="A smoky tavern filled with rough-looking patrons.",
        danger_level=3,
    )
    dolt.save_entity(loc)
    return loc


@pytest.fixture
def dungeon_location(dolt, universe):
    """Create a dungeon location for high-danger tests."""
    loc = create_location(
        universe_id=universe.id,
        name="Dark Dungeon",
        description="A damp, dark dungeon corridor.",
        danger_level=15,
    )
    dolt.save_entity(loc)
    return loc


@pytest.fixture
def hero(dolt, universe, tavern_location):
    """Create a test hero character."""
    char = create_character(
        universe_id=universe.id,
        name="Test Hero",
        hp_max=20,
        location_id=tavern_location.id,
    )
    dolt.save_entity(char)
    return char


@pytest.fixture
def session(universe, hero, tavern_location):
    """Create a game session."""
    return Session(
        universe_id=universe.id,
        location_id=tavern_location.id,
        character_ids=[hero.id],
        active_character_id=hero.id,
    )


@pytest.fixture
def tavern_context(hero, tavern_location):
    """Create a tavern context."""
    return Context(
        actor=EntitySummary(
            id=hero.id,
            name=hero.name,
            type="character",
        ),
        actor_inventory=[],
        location=EntitySummary(
            id=tavern_location.id,
            name=tavern_location.name,
            type="location",
            description=tavern_location.description,
        ),
        entities_present=[],
        exits=["north", "south"],
        known_entities=[],
        recent_events=[],
        mood=None,
        danger_level=3,
    )


@pytest.fixture
def dungeon_context(hero, dungeon_location):
    """Create a dungeon context for high-danger tests."""
    return Context(
        actor=EntitySummary(
            id=hero.id,
            name=hero.name,
            type="character",
        ),
        actor_inventory=[
            EntitySummary(id=uuid4(), name="Torch", type="item"),
            EntitySummary(id=uuid4(), name="Sword", type="item"),
        ],
        location=EntitySummary(
            id=dungeon_location.id,
            name=dungeon_location.name,
            type="location",
            description=dungeon_location.description,
        ),
        entities_present=[],
        exits=["east"],
        known_entities=[],
        recent_events=[],
        mood="ominous",
        danger_level=15,
    )


@pytest.fixture
def dungeon_session(universe, hero, dungeon_location):
    """Create a dungeon session for high-danger tests."""
    return Session(
        universe_id=universe.id,
        location_id=dungeon_location.id,
        character_ids=[hero.id],
        active_character_id=hero.id,
    )


# =============================================================================
# INTRODUCE_NPC Integration Tests
# =============================================================================


class TestIntroduceNPCIntegration:
    """Integration tests for INTRODUCE_NPC move execution."""

    @pytest.mark.asyncio
    async def test_introduce_npc_creates_entity_in_dolt(
        self, move_executor, dolt, tavern_context, session
    ):
        """INTRODUCE_NPC should create an entity in Dolt."""
        entities_before = count_entities(dolt)

        move = GMMove(
            type=GMMoveType.INTRODUCE_NPC,
            is_hard=False,
            description="A stranger appears...",
        )

        result = await move_executor.execute(move, tavern_context, session)

        entities_after = count_entities(dolt)
        assert result.success
        assert entities_after > entities_before, "Should have created a new entity"
        assert len(result.entities_created) == 1

    @pytest.mark.asyncio
    async def test_introduce_npc_creates_npc_profile(
        self, move_executor, npc_service, tavern_context, session
    ):
        """INTRODUCE_NPC should create an NPC profile with personality traits."""
        move = GMMove(
            type=GMMoveType.INTRODUCE_NPC,
            is_hard=False,
            description="A stranger appears...",
        )

        result = await move_executor.execute(move, tavern_context, session)

        assert result.success
        npc_id = result.entities_created[0]
        profile = npc_service.get_profile(npc_id)

        assert profile is not None, "NPC should have a profile"
        assert 0 <= profile.traits.openness <= 100
        assert 0 <= profile.traits.extraversion <= 100

    @pytest.mark.asyncio
    async def test_introduce_npc_creates_located_in_relationship(
        self, move_executor, neo4j, tavern_context, session
    ):
        """INTRODUCE_NPC should create a LOCATED_IN relationship."""
        move = GMMove(
            type=GMMoveType.INTRODUCE_NPC,
            is_hard=False,
            description="A stranger appears...",
        )

        result = await move_executor.execute(move, tavern_context, session)

        assert result.success
        assert len(result.relationships_created) == 1

        # Verify the relationship exists
        npc_id = result.entities_created[0]
        relationships = neo4j.get_relationships(
            session.location_id,
            session.universe_id,
            relationship_type="LOCATED_IN",
        )

        npc_rel = [r for r in relationships if r.from_entity_id == npc_id]
        assert len(npc_rel) == 1, "NPC should have LOCATED_IN relationship"

    @pytest.mark.asyncio
    async def test_introduce_npc_generates_appropriate_narrative(
        self, move_executor, tavern_context, session
    ):
        """INTRODUCE_NPC should generate a narrative mentioning the NPC."""
        move = GMMove(
            type=GMMoveType.INTRODUCE_NPC,
            is_hard=False,
            description="A stranger appears...",
        )

        result = await move_executor.execute(move, tavern_context, session)

        assert result.success
        assert result.narrative
        assert len(result.narrative) > 20, "Narrative should be substantial"


# =============================================================================
# CHANGE_ENVIRONMENT Integration Tests
# =============================================================================


class TestChangeEnvironmentIntegration:
    """Integration tests for CHANGE_ENVIRONMENT move execution."""

    @pytest.mark.asyncio
    async def test_change_environment_low_danger_no_entity(
        self, move_executor, dolt, tavern_context, session
    ):
        """Low danger CHANGE_ENVIRONMENT should change atmosphere, not create entities."""
        entities_before = count_entities(dolt)

        move = GMMove(
            type=GMMoveType.CHANGE_ENVIRONMENT,
            is_hard=False,
            description="The environment shifts...",
        )

        result = await move_executor.execute(move, tavern_context, session)

        entities_after = count_entities(dolt)
        assert result.success
        # Low danger = atmosphere change, no entity
        assert entities_after == entities_before

    @pytest.mark.asyncio
    async def test_change_environment_high_danger_creates_feature(
        self, move_executor, dolt, dungeon_context, dungeon_session
    ):
        """High danger CHANGE_ENVIRONMENT should create a location feature."""
        entities_before = count_entities(dolt)

        move = GMMove(
            type=GMMoveType.CHANGE_ENVIRONMENT,
            is_hard=False,
            description="The environment shifts...",
        )

        result = await move_executor.execute(move, dungeon_context, dungeon_session)

        entities_after = count_entities(dolt)
        assert result.success
        assert entities_after > entities_before, "High danger should create feature"
        assert len(result.entities_created) == 1


# =============================================================================
# CAPTURE Integration Tests
# =============================================================================


class TestCaptureIntegration:
    """Integration tests for CAPTURE move execution."""

    @pytest.mark.asyncio
    async def test_capture_creates_trap_location(
        self, move_executor, dolt, tavern_context, session
    ):
        """CAPTURE should create a trap location entity."""
        entities_before = count_entities(dolt)

        move = GMMove(
            type=GMMoveType.CAPTURE,
            is_hard=True,
            description="You're trapped!",
        )

        result = await move_executor.execute(move, tavern_context, session)

        entities_after = count_entities(dolt)
        assert result.success
        assert entities_after > entities_before
        assert "trap" in result.narrative.lower()

    @pytest.mark.asyncio
    async def test_capture_creates_relationships(
        self, move_executor, neo4j, tavern_context, session
    ):
        """CAPTURE should create LOCATED_IN and TRAPPED_IN relationships."""
        move = GMMove(
            type=GMMoveType.CAPTURE,
            is_hard=True,
            description="You're trapped!",
        )

        result = await move_executor.execute(move, tavern_context, session)

        assert result.success
        # Creates 2 relationships: LOCATED_IN and TRAPPED_IN
        assert len(result.relationships_created) == 2


# =============================================================================
# Template Fallback Integration Tests
# =============================================================================


class TestTemplateFallback:
    """Integration tests for template-based generation."""

    @pytest.mark.asyncio
    async def test_executor_without_llm_uses_templates(
        self, move_executor, dolt, tavern_context, session
    ):
        """Without LLM, executor should use templates successfully."""
        # Verify no LLM
        assert move_executor.llm is None

        move = GMMove(
            type=GMMoveType.INTRODUCE_NPC,
            is_hard=False,
            description="Someone appears...",
        )

        result = await move_executor.execute(move, tavern_context, session)

        assert result.success
        assert len(result.entities_created) == 1
        assert result.narrative

    @pytest.mark.asyncio
    async def test_tavern_npcs_have_appropriate_names(
        self, move_executor, dolt, tavern_context, session
    ):
        """Tavern NPCs should have tavern-appropriate names from templates."""
        from src.services.move_executor import NPC_TEMPLATES

        tavern_names = set()
        for template in NPC_TEMPLATES.get("tavern", []):
            tavern_names.update(template.names)

        move = GMMove(
            type=GMMoveType.INTRODUCE_NPC,
            is_hard=False,
            description="Someone appears...",
        )

        # Try a few times to verify template selection
        found_tavern_name = False
        for _ in range(10):
            result = await move_executor.execute(move, tavern_context, session)
            npc_id = result.entities_created[0]
            branch = dolt.get_current_branch()
            npc = dolt._entities[branch].get(npc_id)
            if npc and npc.name in tavern_names:
                found_tavern_name = True
                break

        assert found_tavern_name, "Should use tavern NPC templates"
