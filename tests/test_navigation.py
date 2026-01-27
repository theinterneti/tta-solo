"""
Tests for the navigation system.
"""

from __future__ import annotations

import pytest

from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.engine import GameEngine
from src.engine.models import EngineConfig
from src.models.entity import create_character, create_location
from src.models.relationships import Relationship, RelationshipType
from src.models.universe import Universe


@pytest.fixture
def test_world():
    """Create a test world with connected locations."""
    # Create fresh repositories for each test
    dolt = InMemoryDoltRepository()
    neo4j = InMemoryNeo4jRepository()
    engine = GameEngine(dolt=dolt, neo4j=neo4j, config=EngineConfig())

    # Create universe
    universe = Universe(name="Test World")
    dolt.save_universe(universe)

    # Create locations
    tavern = create_location(
        universe_id=universe.id,
        name="Rusty Dragon Inn",
        description="A cozy tavern",
        location_type="tavern",
    )
    dolt.save_entity(tavern)

    market = create_location(
        universe_id=universe.id,
        name="Market Square",
        description="A busy marketplace",
        location_type="market",
    )
    dolt.save_entity(market)

    gate = create_location(
        universe_id=universe.id,
        name="Town Gate",
        description="The main entrance to town",
        location_type="gate",
    )
    dolt.save_entity(gate)

    # Create connections
    # Tavern -> Market (via "north")
    neo4j.create_relationship(
        Relationship(
            universe_id=universe.id,
            from_entity_id=tavern.id,
            to_entity_id=market.id,
            relationship_type=RelationshipType.CONNECTED_TO,
            description="north",
        )
    )

    # Market -> Tavern (via "south")
    neo4j.create_relationship(
        Relationship(
            universe_id=universe.id,
            from_entity_id=market.id,
            to_entity_id=tavern.id,
            relationship_type=RelationshipType.CONNECTED_TO,
            description="south",
        )
    )

    # Market -> Gate (via "east")
    neo4j.create_relationship(
        Relationship(
            universe_id=universe.id,
            from_entity_id=market.id,
            to_entity_id=gate.id,
            relationship_type=RelationshipType.CONNECTED_TO,
            description="east",
        )
    )

    # Create player
    player = create_character(
        universe_id=universe.id,
        name="Test Player",
        description="The player character",
        hp_max=30,
        location_id=tavern.id,
    )
    dolt.save_entity(player)

    return {
        "dolt": dolt,
        "neo4j": neo4j,
        "engine": engine,
        "universe": universe,
        "tavern": tavern,
        "market": market,
        "gate": gate,
        "player": player,
    }


class TestNavigationHelpers:
    """Tests for navigation helper functions."""

    def test_get_location_exits(self, test_world):
        """_get_location_exits should return connected locations."""
        from dataclasses import dataclass
        from uuid import UUID

        @dataclass
        class MockState:
            engine: GameEngine
            location_id: UUID
            universe_id: UUID

        state = MockState(
            engine=test_world["engine"],
            location_id=test_world["tavern"].id,
            universe_id=test_world["universe"].id,
        )

        # Import the REPL to test the method
        from src.cli.repl import GameREPL

        repl = GameREPL()
        exits = repl._get_location_exits(state)

        assert len(exits) == 1
        assert "north" in exits
        assert exits["north"]["name"] == "Market Square"

    def test_get_location_exits_multiple(self, test_world):
        """_get_location_exits should return all connected locations."""
        from dataclasses import dataclass
        from uuid import UUID

        @dataclass
        class MockState:
            engine: GameEngine
            location_id: UUID
            universe_id: UUID

        state = MockState(
            engine=test_world["engine"],
            location_id=test_world["market"].id,
            universe_id=test_world["universe"].id,
        )

        from src.cli.repl import GameREPL

        repl = GameREPL()
        exits = repl._get_location_exits(state)

        assert len(exits) == 2
        assert "south" in exits
        assert "east" in exits

    def test_match_exit_exact(self, test_world):
        """_match_exit should match exact exit names."""
        from src.cli.repl import GameREPL

        repl = GameREPL()

        exits = {
            "north": {"id": test_world["market"].id, "name": "Market Square"},
            "south": {"id": test_world["tavern"].id, "name": "Rusty Dragon Inn"},
        }

        assert repl._match_exit("north", exits) == "north"
        assert repl._match_exit("south", exits) == "south"

    def test_match_exit_partial(self, test_world):
        """_match_exit should match partial destination names."""
        from src.cli.repl import GameREPL

        repl = GameREPL()

        exits = {
            "north": {"id": test_world["market"].id, "name": "Market Square"},
            "south": {"id": test_world["tavern"].id, "name": "Rusty Dragon Inn"},
        }

        # Match by destination name
        assert repl._match_exit("market", exits) == "north"
        assert repl._match_exit("rusty", exits) == "south"

    def test_match_exit_no_match(self, test_world):
        """_match_exit should return None for no matches."""
        from src.cli.repl import GameREPL

        repl = GameREPL()

        exits = {
            "north": {"id": test_world["market"].id, "name": "Market Square"},
        }

        assert repl._match_exit("west", exits) is None
        assert repl._match_exit("castle", exits) is None

    def test_match_exit_ambiguous(self, test_world):
        """_match_exit should return None for ambiguous matches."""
        from src.cli.repl import GameREPL

        repl = GameREPL()

        # Both exits start with "north" - typing "north" is ambiguous
        exits = {
            "north": {"id": test_world["market"].id, "name": "Market Square"},
            "northeast": {"id": test_world["gate"].id, "name": "Town Gate"},
        }

        # "n" matches both "north" and "northeast" (prefix match) - ambiguous
        assert repl._match_exit("n", exits) is None

        # But exact match should still work
        assert repl._match_exit("north", exits) == "north"
        assert repl._match_exit("northeast", exits) == "northeast"

        # "northe" only matches "northeast" (prefix) - not ambiguous
        assert repl._match_exit("northe", exits) == "northeast"


class TestGoCommand:
    """Tests for /go command."""

    def test_go_no_args_shows_exits(self, test_world):
        """_cmd_go with no args should show available exits."""
        from dataclasses import dataclass
        from uuid import UUID

        from src.models.entity import Entity

        @dataclass
        class MockState:
            engine: GameEngine
            character_id: UUID
            universe_id: UUID
            location_id: UUID
            session_id: UUID | None = None
            pending_talk_npc: Entity | None = None

        state = MockState(
            engine=test_world["engine"],
            character_id=test_world["player"].id,
            universe_id=test_world["universe"].id,
            location_id=test_world["tavern"].id,
        )

        from src.cli.repl import GameREPL

        repl = GameREPL()
        result = repl._cmd_go(state, [])

        assert "Where do you want to go?" in result
        assert "north" in result

    def test_go_invalid_destination(self, test_world):
        """_cmd_go with invalid destination should show error."""
        from dataclasses import dataclass
        from uuid import UUID

        from src.models.entity import Entity

        @dataclass
        class MockState:
            engine: GameEngine
            character_id: UUID
            universe_id: UUID
            location_id: UUID
            session_id: UUID | None = None
            pending_talk_npc: Entity | None = None

        state = MockState(
            engine=test_world["engine"],
            character_id=test_world["player"].id,
            universe_id=test_world["universe"].id,
            location_id=test_world["tavern"].id,
        )

        from src.cli.repl import GameREPL

        repl = GameREPL()
        result = repl._cmd_go(state, ["west"])

        assert "Can't go" in result
        assert "north" in result  # Shows available exits

    def test_go_valid_destination(self, test_world):
        """_cmd_go with valid destination should update location."""
        from dataclasses import dataclass
        from uuid import UUID

        from src.models.entity import Entity

        @dataclass
        class MockState:
            engine: GameEngine
            character_id: UUID
            universe_id: UUID
            location_id: UUID
            session_id: UUID | None = None
            pending_talk_npc: Entity | None = None

        state = MockState(
            engine=test_world["engine"],
            character_id=test_world["player"].id,
            universe_id=test_world["universe"].id,
            location_id=test_world["tavern"].id,
        )

        from src.cli.repl import GameREPL

        repl = GameREPL()
        result = repl._cmd_go(state, ["north"])

        assert "Market Square" in result
        assert state.location_id == test_world["market"].id

        # Verify Dolt entity was updated
        updated_player = test_world["dolt"].get_entity(
            test_world["player"].id, test_world["universe"].id
        )
        assert updated_player.current_location_id == test_world["market"].id

        # Verify Neo4j LOCATED_IN relationship was updated
        located_in_rels = test_world["neo4j"].get_relationships(
            test_world["player"].id,
            test_world["universe"].id,
            relationship_type="LOCATED_IN",
        )
        # Should have a relationship to the new location
        new_location_rels = [
            r for r in located_in_rels if r.to_entity_id == test_world["market"].id
        ]
        assert len(new_location_rels) == 1


class TestExitsCommand:
    """Tests for /exits command."""

    def test_exits_shows_available(self, test_world):
        """_cmd_exits should show all available exits."""
        from dataclasses import dataclass
        from uuid import UUID

        from src.models.entity import Entity

        @dataclass
        class MockState:
            engine: GameEngine
            character_id: UUID
            universe_id: UUID
            location_id: UUID
            session_id: UUID | None = None
            pending_talk_npc: Entity | None = None

        state = MockState(
            engine=test_world["engine"],
            character_id=test_world["player"].id,
            universe_id=test_world["universe"].id,
            location_id=test_world["market"].id,
        )

        from src.cli.repl import GameREPL

        repl = GameREPL()
        result = repl._cmd_exits(state, [])

        assert "Available exits" in result
        assert "south" in result
        assert "east" in result
        assert "Rusty Dragon" in result
        assert "Town Gate" in result

    def test_exits_no_exits(self, test_world):
        """_cmd_exits should handle locations with no exits."""
        from dataclasses import dataclass
        from uuid import UUID

        from src.models.entity import Entity

        @dataclass
        class MockState:
            engine: GameEngine
            character_id: UUID
            universe_id: UUID
            location_id: UUID
            session_id: UUID | None = None
            pending_talk_npc: Entity | None = None

        # Gate has no outgoing connections
        state = MockState(
            engine=test_world["engine"],
            character_id=test_world["player"].id,
            universe_id=test_world["universe"].id,
            location_id=test_world["gate"].id,
        )

        from src.cli.repl import GameREPL

        repl = GameREPL()
        result = repl._cmd_exits(state, [])

        assert "no obvious exits" in result.lower()
