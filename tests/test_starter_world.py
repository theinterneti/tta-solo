"""
Tests for the starter world content.
"""

from __future__ import annotations

import pytest

from src.content import create_starter_world
from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.services.npc import NPCService


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


class TestStarterWorld:
    """Tests for starter world creation."""

    def test_create_starter_world_returns_result(self, dolt, neo4j, npc_service):
        """create_starter_world should return a complete result."""
        result = create_starter_world(dolt, neo4j, npc_service)

        assert result.universe is not None
        assert result.starting_location_id is not None
        assert result.player_character_id is not None

    def test_creates_universe(self, dolt, neo4j, npc_service):
        """Should create a universe named Eldoria."""
        result = create_starter_world(dolt, neo4j, npc_service)

        assert result.universe.name == "Eldoria"
        universe = dolt.get_universe(result.universe.id)
        assert universe is not None

    def test_creates_multiple_locations(self, dolt, neo4j, npc_service):
        """Should create multiple connected locations."""
        result = create_starter_world(dolt, neo4j, npc_service)

        assert len(result.locations) >= 5
        assert "tavern" in result.locations
        assert "market" in result.locations
        assert "crypt" in result.locations

    def test_locations_have_different_danger_levels(self, dolt, neo4j, npc_service):
        """Locations should have varying danger levels."""
        result = create_starter_world(dolt, neo4j, npc_service)

        tavern = dolt.get_entity(result.locations["tavern"], result.universe.id)
        crypt = dolt.get_entity(result.locations["crypt"], result.universe.id)

        assert tavern.location_properties.danger_level < 5  # Safe
        assert crypt.location_properties.danger_level >= 10  # Dangerous

    def test_creates_npcs_with_profiles(self, dolt, neo4j, npc_service):
        """Should create NPCs with personality profiles."""
        result = create_starter_world(dolt, neo4j, npc_service)

        assert len(result.npcs) >= 4
        assert "ameiko" in result.npcs

        # Check NPC has profile
        ameiko_profile = npc_service.get_profile(result.npcs["ameiko"])
        assert ameiko_profile is not None
        assert ameiko_profile.traits.extraversion > 50  # She's extraverted

    def test_npcs_have_located_in_relationships(self, dolt, neo4j, npc_service):
        """NPCs should have LOCATED_IN relationships."""
        result = create_starter_world(dolt, neo4j, npc_service)

        # Check bartender is in tavern
        rels = neo4j.get_relationships(
            result.locations["tavern"],
            result.universe.id,
            relationship_type="LOCATED_IN",
        )
        npc_ids = [r.from_entity_id for r in rels]
        assert result.npcs["ameiko"] in npc_ids

    def test_creates_starter_items(self, dolt, neo4j, npc_service):
        """Should create starter items."""
        result = create_starter_world(dolt, neo4j, npc_service)

        assert len(result.items) >= 4
        assert "sword" in result.items
        assert "potion" in result.items
        assert "torch" in result.items

    def test_player_has_inventory(self, dolt, neo4j, npc_service):
        """Player should have items in inventory."""
        result = create_starter_world(dolt, neo4j, npc_service)

        # Check CARRIES relationships
        rels = neo4j.get_relationships(
            result.player_character_id,
            result.universe.id,
            relationship_type="CARRIES",
        )
        carried_ids = [r.to_entity_id for r in rels]

        assert result.items["sword"] in carried_ids
        assert result.items["potion"] in carried_ids

    def test_locations_are_connected(self, dolt, neo4j, npc_service):
        """Locations should be connected via relationships."""
        result = create_starter_world(dolt, neo4j, npc_service)

        # Check tavern connects to market
        rels = neo4j.get_relationships(
            result.locations["tavern"],
            result.universe.id,
            relationship_type="CONNECTED_TO",
        )
        connected_to = [r.to_entity_id for r in rels]
        assert result.locations["market"] in connected_to

    def test_custom_player_name(self, dolt, neo4j, npc_service):
        """Should use custom player name."""
        result = create_starter_world(
            dolt,
            neo4j,
            npc_service,
            player_name="Sir Lancelot",
        )

        player = dolt.get_entity(result.player_character_id, result.universe.id)
        assert player.name == "Sir Lancelot"
