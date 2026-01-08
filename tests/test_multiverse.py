"""Tests for the MultiverseService."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.models import (
    EventType,
    UniverseStatus,
    create_character,
)
from src.services.multiverse import MultiverseService


@pytest.fixture
def multiverse_service() -> MultiverseService:
    """Create a MultiverseService with in-memory repositories."""
    dolt = InMemoryDoltRepository()
    neo4j = InMemoryNeo4jRepository()
    return MultiverseService(dolt=dolt, neo4j=neo4j)


class TestInitializePrimeMaterial:
    """Tests for Prime Material initialization."""

    def test_creates_prime_universe(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        assert prime.name == "Prime Material"
        assert prime.is_prime_material()
        assert prime.dolt_branch == "main"

    def test_custom_name(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material(name="Custom Prime")
        assert prime.name == "Custom Prime"

    def test_prime_is_persisted(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        retrieved = multiverse_service.dolt.get_universe(prime.id)
        assert retrieved is not None
        assert retrieved.id == prime.id


class TestForkUniverse:
    """Tests for universe forking."""

    def test_fork_creates_new_universe(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="What If Timeline",
            fork_reason="Testing alternate outcome",
        )

        assert result.success
        assert result.universe is not None
        assert result.universe.name == "What If Timeline"
        assert result.universe.parent_universe_id == prime.id
        assert result.universe.depth == 1

    def test_fork_creates_dolt_branch(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Branch Test",
            fork_reason="Testing branching",
        )

        assert result.success
        assert multiverse_service.dolt.branch_exists(result.universe.dolt_branch)

    def test_fork_records_event(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Event Test",
            fork_reason="Testing event",
        )

        assert result.fork_event is not None
        assert result.fork_event.event_type == EventType.FORK
        assert result.fork_event.payload["fork_reason"] == "Testing event"

    def test_fork_with_player_id(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()
        player_id = uuid4()

        result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Player Branch",
            fork_reason="Player choice",
            player_id=player_id,
        )

        assert result.success
        assert result.universe.owner_id == player_id
        assert f"user/{player_id}" in result.universe.dolt_branch

    def test_fork_nonexistent_parent_fails(self, multiverse_service: MultiverseService):
        result = multiverse_service.fork_universe(
            parent_universe_id=uuid4(),
            new_universe_name="Orphan",
            fork_reason="No parent",
        )

        assert not result.success
        assert "not found" in result.error

    def test_fork_archived_parent_fails(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        # Archive the prime (shouldn't normally do this, but for testing)
        prime.status = UniverseStatus.ARCHIVED
        multiverse_service.dolt.save_universe(prime)

        result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="From Archived",
            fork_reason="Testing",
        )

        assert not result.success
        assert "inactive" in result.error.lower()

    def test_nested_forks(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        # First fork
        result1 = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Fork 1",
            fork_reason="First fork",
        )
        assert result1.success

        # Need to switch to fork1's branch to save it properly
        # Then switch back to main to fork again from there
        multiverse_service.dolt.checkout_branch("main")
        multiverse_service.dolt.save_universe(result1.universe)

        # Second fork from first fork
        result2 = multiverse_service.fork_universe(
            parent_universe_id=result1.universe.id,
            new_universe_name="Fork 2",
            fork_reason="Second fork",
        )

        assert result2.success
        assert result2.universe.depth == 2
        assert result2.universe.parent_universe_id == result1.universe.id


class TestTravelBetweenWorlds:
    """Tests for cross-world travel."""

    def test_travel_copies_character(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        # Create character in prime
        hero = create_character(
            universe_id=prime.id,
            name="World Walker",
            hp_max=50,
        )
        multiverse_service.dolt.save_entity(hero)

        # Fork to create destination
        fork_result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Destination",
            fork_reason="Travel destination",
        )

        # Save destination universe to main branch for lookup
        multiverse_service.dolt.checkout_branch("main")
        multiverse_service.dolt.save_universe(fork_result.universe)

        # Travel to destination
        travel_result = multiverse_service.travel_between_worlds(
            traveler_id=hero.id,
            source_universe_id=prime.id,
            destination_universe_id=fork_result.universe.id,
        )

        assert travel_result.success
        assert travel_result.traveler_copy_id is not None
        assert travel_result.traveler_copy_id != hero.id  # Different ID

    def test_travel_creates_variant_node(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        hero = create_character(universe_id=prime.id, name="Traveler")
        multiverse_service.dolt.save_entity(hero)

        fork_result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Destination",
            fork_reason="Travel",
        )

        # Save destination universe to main branch for lookup
        multiverse_service.dolt.checkout_branch("main")
        multiverse_service.dolt.save_universe(fork_result.universe)

        travel_result = multiverse_service.travel_between_worlds(
            traveler_id=hero.id,
            source_universe_id=prime.id,
            destination_universe_id=fork_result.universe.id,
        )

        assert travel_result.success
        # Check variant was created
        has_variant = multiverse_service.neo4j.has_variant(hero.id, fork_result.universe.id)
        assert has_variant

    def test_travel_records_event(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        hero = create_character(universe_id=prime.id, name="Traveler")
        multiverse_service.dolt.save_entity(hero)

        fork_result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Destination",
            fork_reason="Travel",
        )

        # Save destination universe to main branch for lookup
        multiverse_service.dolt.checkout_branch("main")
        multiverse_service.dolt.save_universe(fork_result.universe)

        travel_result = multiverse_service.travel_between_worlds(
            traveler_id=hero.id,
            source_universe_id=prime.id,
            destination_universe_id=fork_result.universe.id,
            travel_method="portal",
        )

        assert travel_result.travel_event is not None
        assert travel_result.travel_event.event_type == EventType.TRAVEL
        assert travel_result.travel_event.payload["travel_method"] == "portal"

    def test_travel_nonexistent_source_fails(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        result = multiverse_service.travel_between_worlds(
            traveler_id=uuid4(),
            source_universe_id=uuid4(),
            destination_universe_id=prime.id,
        )

        assert not result.success
        assert "Source universe" in result.error

    def test_travel_nonexistent_destination_fails(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        hero = create_character(universe_id=prime.id, name="Traveler")
        multiverse_service.dolt.save_entity(hero)

        result = multiverse_service.travel_between_worlds(
            traveler_id=hero.id,
            source_universe_id=prime.id,
            destination_universe_id=uuid4(),
        )

        assert not result.success
        assert "Destination universe" in result.error

    def test_travel_nonexistent_traveler_fails(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        fork_result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Destination",
            fork_reason="Travel",
        )

        multiverse_service.dolt.checkout_branch("main")
        result = multiverse_service.travel_between_worlds(
            traveler_id=uuid4(),
            source_universe_id=prime.id,
            destination_universe_id=fork_result.universe.id,
        )

        assert not result.success
        assert "not found" in result.error


class TestArchiveUniverse:
    """Tests for archiving universes."""

    def test_archive_sets_status(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        fork_result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="To Archive",
            fork_reason="Testing archive",
        )

        success = multiverse_service.archive_universe(fork_result.universe.id)
        assert success

        # Check status was updated
        multiverse_service.dolt.checkout_branch(fork_result.universe.dolt_branch)
        archived = multiverse_service.dolt.get_universe(fork_result.universe.id)
        assert archived.status == UniverseStatus.ARCHIVED

    def test_cannot_archive_prime(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        success = multiverse_service.archive_universe(prime.id)
        assert not success

    def test_archive_nonexistent_fails(self, multiverse_service: MultiverseService):
        success = multiverse_service.archive_universe(uuid4())
        assert not success


class TestUniverseLineage:
    """Tests for universe lineage tracking."""

    def test_prime_has_single_element_lineage(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        lineage = multiverse_service.get_universe_lineage(prime.id)
        assert len(lineage) == 1
        assert lineage[0].id == prime.id

    def test_fork_lineage_includes_parent(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        fork_result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Child",
            fork_reason="Testing lineage",
        )

        # Need to save fork universe to main branch for lineage lookup
        multiverse_service.dolt.checkout_branch("main")
        multiverse_service.dolt.save_universe(fork_result.universe)

        lineage = multiverse_service.get_universe_lineage(fork_result.universe.id)
        assert len(lineage) == 2
        assert lineage[0].id == prime.id  # Prime first
        assert lineage[1].id == fork_result.universe.id  # Child second

    def test_deep_lineage(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        # Create chain of forks
        current_id = prime.id
        for i in range(3):
            result = multiverse_service.fork_universe(
                parent_universe_id=current_id,
                new_universe_name=f"Fork {i + 1}",
                fork_reason=f"Depth {i + 1}",
            )
            # Save to main for lineage lookup
            multiverse_service.dolt.checkout_branch("main")
            multiverse_service.dolt.save_universe(result.universe)
            current_id = result.universe.id

        lineage = multiverse_service.get_universe_lineage(current_id)
        assert len(lineage) == 4  # Prime + 3 forks
        assert lineage[0].is_prime_material()
        assert lineage[-1].depth == 3
