"""Tests for in-memory database implementations."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.models import (
    Event,
    EventOutcome,
    EventType,
    create_character,
    create_knows_relationship,
    create_prime_material,
)

# --- InMemoryDoltRepository Tests ---


class TestInMemoryDoltBranching:
    """Tests for Dolt branching operations."""

    def test_default_branch_is_main(self):
        repo = InMemoryDoltRepository()
        assert repo.get_current_branch() == "main"

    def test_create_branch(self):
        repo = InMemoryDoltRepository()
        repo.create_branch("feature/test")
        assert repo.branch_exists("feature/test")
        assert repo.branch_exists("main")

    def test_create_branch_from_nonexistent_fails(self):
        repo = InMemoryDoltRepository()
        with pytest.raises(ValueError, match="does not exist"):
            repo.create_branch("new-branch", from_branch="nonexistent")

    def test_create_duplicate_branch_fails(self):
        repo = InMemoryDoltRepository()
        repo.create_branch("feature/test")
        with pytest.raises(ValueError, match="already exists"):
            repo.create_branch("feature/test")

    def test_checkout_branch(self):
        repo = InMemoryDoltRepository()
        repo.create_branch("feature/test")
        repo.checkout_branch("feature/test")
        assert repo.get_current_branch() == "feature/test"

    def test_checkout_nonexistent_fails(self):
        repo = InMemoryDoltRepository()
        with pytest.raises(ValueError, match="does not exist"):
            repo.checkout_branch("nonexistent")

    def test_delete_branch(self):
        repo = InMemoryDoltRepository()
        repo.create_branch("feature/test")
        repo.delete_branch("feature/test")
        assert not repo.branch_exists("feature/test")

    def test_cannot_delete_main(self):
        repo = InMemoryDoltRepository()
        with pytest.raises(ValueError, match="Cannot delete main"):
            repo.delete_branch("main")

    def test_cannot_delete_current_branch(self):
        repo = InMemoryDoltRepository()
        repo.create_branch("feature/test")
        repo.checkout_branch("feature/test")
        with pytest.raises(ValueError, match="Cannot delete the current branch"):
            repo.delete_branch("feature/test")

    def test_branch_isolation(self):
        """Data on one branch doesn't affect another."""
        repo = InMemoryDoltRepository()

        # Create data on main
        prime = create_prime_material()
        repo.save_universe(prime)

        # Create branch and switch
        repo.create_branch("fork/test")
        repo.checkout_branch("fork/test")

        # Modify on fork
        prime_fork = repo.get_universe(prime.id)
        assert prime_fork is not None
        prime_fork.name = "Modified Prime"
        repo.save_universe(prime_fork)

        # Check main is unchanged
        repo.checkout_branch("main")
        original = repo.get_universe(prime.id)
        assert original is not None
        assert original.name == "Prime Material"


class TestInMemoryDoltUniverse:
    """Tests for universe operations."""

    def test_save_and_get_universe(self):
        repo = InMemoryDoltRepository()
        prime = create_prime_material()
        repo.save_universe(prime)

        retrieved = repo.get_universe(prime.id)
        assert retrieved is not None
        assert retrieved.name == prime.name
        assert retrieved.id == prime.id

    def test_get_nonexistent_universe(self):
        repo = InMemoryDoltRepository()
        result = repo.get_universe(uuid4())
        assert result is None

    def test_get_universe_by_branch(self):
        repo = InMemoryDoltRepository()
        prime = create_prime_material()
        repo.save_universe(prime)

        retrieved = repo.get_universe_by_branch("main")
        assert retrieved is not None
        assert retrieved.id == prime.id


class TestInMemoryDoltEntity:
    """Tests for entity operations."""

    def test_save_and_get_entity(self):
        repo = InMemoryDoltRepository()
        universe_id = uuid4()
        char = create_character(universe_id=universe_id, name="Hero")
        repo.save_entity(char)

        retrieved = repo.get_entity(char.id, universe_id)
        assert retrieved is not None
        assert retrieved.name == "Hero"

    def test_get_entity_wrong_universe(self):
        repo = InMemoryDoltRepository()
        universe_id = uuid4()
        char = create_character(universe_id=universe_id, name="Hero")
        repo.save_entity(char)

        # Try to get from different universe
        result = repo.get_entity(char.id, uuid4())
        assert result is None

    def test_get_entities_by_type(self):
        repo = InMemoryDoltRepository()
        universe_id = uuid4()

        # Create multiple characters
        char1 = create_character(universe_id=universe_id, name="Hero")
        char2 = create_character(universe_id=universe_id, name="Villain")
        repo.save_entity(char1)
        repo.save_entity(char2)

        characters = repo.get_entities_by_type("character", universe_id)
        assert len(characters) == 2
        names = {c.name for c in characters}
        assert names == {"Hero", "Villain"}


class TestInMemoryDoltEvent:
    """Tests for event operations."""

    def test_append_and_get_events(self):
        repo = InMemoryDoltRepository()
        universe_id = uuid4()
        actor_id = uuid4()

        event = Event(
            universe_id=universe_id,
            event_type=EventType.DIALOGUE,
            actor_id=actor_id,
            outcome=EventOutcome.SUCCESS,
        )
        repo.append_event(event)

        events = repo.get_events(universe_id)
        assert len(events) == 1
        assert events[0].id == event.id

    def test_get_event_by_id(self):
        repo = InMemoryDoltRepository()
        universe_id = uuid4()

        event = Event(
            universe_id=universe_id,
            event_type=EventType.TRAVEL,
            actor_id=uuid4(),
        )
        repo.append_event(event)

        retrieved = repo.get_event(event.id)
        assert retrieved is not None
        assert retrieved.event_type == EventType.TRAVEL

    def test_events_are_ordered_by_timestamp(self):
        repo = InMemoryDoltRepository()
        universe_id = uuid4()

        # Create events with different timestamps
        from datetime import datetime

        event1 = Event(
            universe_id=universe_id,
            event_type=EventType.DIALOGUE,
            actor_id=uuid4(),
            timestamp=datetime(2024, 1, 1),
        )
        event2 = Event(
            universe_id=universe_id,
            event_type=EventType.TRAVEL,
            actor_id=uuid4(),
            timestamp=datetime(2024, 1, 2),
        )
        # Add in reverse order
        repo.append_event(event2)
        repo.append_event(event1)

        events = repo.get_events(universe_id)
        assert events[0].id == event1.id  # Earlier timestamp first
        assert events[1].id == event2.id


# --- InMemoryNeo4jRepository Tests ---


class TestInMemoryNeo4jRelationships:
    """Tests for Neo4j relationship operations."""

    def test_create_and_get_relationship(self):
        repo = InMemoryNeo4jRepository()
        universe_id = uuid4()
        char1_id = uuid4()
        char2_id = uuid4()

        rel = create_knows_relationship(
            universe_id=universe_id,
            from_id=char1_id,
            to_id=char2_id,
            trust=0.8,
        )
        repo.create_relationship(rel)

        rels = repo.get_relationships(char1_id, universe_id)
        assert len(rels) == 1
        assert rels[0].trust == 0.8

    def test_get_relationships_by_type(self):
        repo = InMemoryNeo4jRepository()
        universe_id = uuid4()
        char_id = uuid4()

        # Create KNOWS relationship
        knows = create_knows_relationship(
            universe_id=universe_id,
            from_id=char_id,
            to_id=uuid4(),
        )
        repo.create_relationship(knows)

        # Filter by type
        knows_rels = repo.get_relationships(char_id, universe_id, relationship_type="KNOWS")
        assert len(knows_rels) == 1

        # Non-matching type
        fears_rels = repo.get_relationships(char_id, universe_id, relationship_type="FEARS")
        assert len(fears_rels) == 0

    def test_delete_relationship(self):
        repo = InMemoryNeo4jRepository()
        universe_id = uuid4()

        rel = create_knows_relationship(
            universe_id=universe_id,
            from_id=uuid4(),
            to_id=uuid4(),
        )
        repo.create_relationship(rel)
        repo.delete_relationship(rel.id)

        rels = repo.get_relationships(rel.from_entity_id, universe_id)
        assert len(rels) == 0


class TestInMemoryNeo4jVariants:
    """Tests for Neo4j variant node operations."""

    def test_create_variant_node(self):
        repo = InMemoryNeo4jRepository()
        original_id = uuid4()
        variant_id = uuid4()
        universe_id = uuid4()

        repo.create_variant_node(
            original_entity_id=original_id,
            variant_entity_id=variant_id,
            variant_universe_id=universe_id,
            changes={"is_dead": "true"},
        )

        assert repo.has_variant(original_id, universe_id)

    def test_no_variant_returns_false(self):
        repo = InMemoryNeo4jRepository()
        assert not repo.has_variant(uuid4(), uuid4())

    def test_get_entity_in_universe_with_variant(self):
        repo = InMemoryNeo4jRepository()
        original_id = uuid4()
        variant_id = uuid4()
        universe_id = uuid4()

        # Register original entity
        repo.register_entity(original_id, "King", "character", None)

        # Create variant
        repo.create_variant_node(
            original_entity_id=original_id,
            variant_entity_id=variant_id,
            variant_universe_id=universe_id,
            changes={"is_dead": "true"},
        )

        # Should return variant in this universe
        result = repo.get_entity_in_universe("King", universe_id, "character")
        assert result == variant_id


class TestInMemoryNeo4jGraph:
    """Tests for Neo4j graph traversal."""

    def test_find_connected_entities(self):
        repo = InMemoryNeo4jRepository()
        universe_id = uuid4()
        entity_a = uuid4()
        entity_b = uuid4()
        entity_c = uuid4()

        # A knows B, B knows C
        rel1 = create_knows_relationship(universe_id, entity_a, entity_b)
        rel2 = create_knows_relationship(universe_id, entity_b, entity_c)
        repo.create_relationship(rel1)
        repo.create_relationship(rel2)

        # Find entities connected to A within 2 hops
        connected = repo.find_connected_entities(entity_a, universe_id, max_depth=2)
        assert entity_b in connected
        assert entity_c in connected

    def test_find_path_exists(self):
        repo = InMemoryNeo4jRepository()
        universe_id = uuid4()
        entity_a = uuid4()
        entity_b = uuid4()
        entity_c = uuid4()

        rel1 = create_knows_relationship(universe_id, entity_a, entity_b)
        rel2 = create_knows_relationship(universe_id, entity_b, entity_c)
        repo.create_relationship(rel1)
        repo.create_relationship(rel2)

        path = repo.find_path(entity_a, entity_c, universe_id)
        assert path is not None
        assert path[0] == entity_a
        assert path[-1] == entity_c

    def test_find_path_not_exists(self):
        repo = InMemoryNeo4jRepository()
        universe_id = uuid4()
        entity_a = uuid4()
        entity_b = uuid4()

        # No relationship between A and B
        path = repo.find_path(entity_a, entity_b, universe_id)
        assert path is None


class TestInMemoryNeo4jVectorSearch:
    """Tests for Neo4j vector similarity search."""

    def test_similarity_search(self):
        repo = InMemoryNeo4jRepository()
        universe_id = uuid4()

        entity1 = uuid4()
        entity2 = uuid4()

        repo.register_entity(entity1, "Dragon", "character", universe_id)
        repo.register_entity(entity2, "Goblin", "character", universe_id)

        # Set embeddings (similar vectors)
        repo.set_embedding(entity1, [1.0, 0.0, 0.0])
        repo.set_embedding(entity2, [0.9, 0.1, 0.0])

        # Search with query similar to entity1
        results = repo.similarity_search([1.0, 0.0, 0.0], universe_id)
        assert len(results) == 2
        assert results[0][0] == entity1  # Most similar first
        assert results[0][1] > results[1][1]  # Higher similarity score
