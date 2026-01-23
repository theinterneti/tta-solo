"""
Database interface definitions for TTA-Solo.

Uses Protocol classes to define the contract for database operations.
Implementations can use real drivers or in-memory mocks for testing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from src.models import Entity, Event, Relationship, Universe
    from src.models.npc import NPCMemory
    from src.models.quest import Quest, QuestStatus


class DoltRepository(Protocol):
    """
    Interface for Dolt database operations.

    Dolt is the "source of truth" - stores entities, events, and universes.
    Supports Git-like branching for timeline forks.
    """

    def get_current_branch(self) -> str:
        """Get the name of the current Dolt branch."""
        ...

    def create_branch(self, branch_name: str, from_branch: str = "main") -> None:
        """Create a new branch from an existing branch."""
        ...

    def checkout_branch(self, branch_name: str) -> None:
        """Switch to a different branch."""
        ...

    def branch_exists(self, branch_name: str) -> bool:
        """Check if a branch exists."""
        ...

    def delete_branch(self, branch_name: str) -> None:
        """Delete a branch."""
        ...

    # Universe operations
    def save_universe(self, universe: Universe) -> None:
        """Insert or update a universe record."""
        ...

    def get_universe(self, universe_id: UUID) -> Universe | None:
        """Get a universe by ID."""
        ...

    def get_universe_by_branch(self, branch_name: str) -> Universe | None:
        """Get a universe by its Dolt branch name."""
        ...

    # Entity operations
    def save_entity(self, entity: Entity) -> None:
        """Insert or update an entity record."""
        ...

    def get_entity(self, entity_id: UUID, universe_id: UUID) -> Entity | None:
        """Get an entity by ID within a specific universe."""
        ...

    def get_entity_by_name(self, name: str, universe_id: UUID) -> Entity | None:
        """Get an entity by name within a specific universe."""
        ...

    def get_entities_by_type(self, entity_type: str, universe_id: UUID) -> list[Entity]:
        """Get all entities of a given type in a universe."""
        ...

    # Event operations
    def append_event(self, event: Event) -> None:
        """Append an event to the immutable event log."""
        ...

    def get_events(
        self,
        universe_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Event]:
        """Get events for a universe, ordered by timestamp."""
        ...

    def get_event(self, event_id: UUID) -> Event | None:
        """Get a specific event by ID."""
        ...

    def get_events_since(self, universe_id: UUID, since_event_id: UUID) -> list[Event]:
        """Get all events after a specific event."""
        ...

    def get_events_at_location(
        self,
        universe_id: UUID,
        location_id: UUID,
        limit: int = 100,
    ) -> list[Event]:
        """Get events that occurred at a specific location."""
        ...

    # NPC Profile operations
    def get_npc_profile(self, entity_id: UUID) -> dict | None:
        """Get an NPC profile by entity ID."""
        ...

    def save_npc_profile(
        self,
        entity_id: UUID,
        traits: dict,
        motivations: list[str],
        speech_style: str | None = None,
        quirks: list[str] | None = None,
        lawful_chaotic: int = 0,
        good_evil: int = 0,
    ) -> None:
        """Save or update an NPC profile."""
        ...

    # Quest operations
    def save_quest(self, quest: Quest) -> None:
        """Save or update a quest."""
        ...

    def get_quest(self, quest_id: UUID) -> Quest | None:
        """Get a quest by ID."""
        ...

    def get_quests_by_status(self, universe_id: UUID, status: QuestStatus) -> list[Quest]:
        """Get all quests in a universe with a specific status."""
        ...

    def get_quests_for_universe(self, universe_id: UUID) -> list[Quest]:
        """Get all quests in a universe."""
        ...


class Neo4jRepository(Protocol):
    """
    Interface for Neo4j database operations.

    Neo4j stores "soft state" - relationships, feelings, and context
    that enhance narrative retrieval. Also handles vector search.
    """

    # Relationship operations
    def create_relationship(self, relationship: Relationship) -> None:
        """Create a relationship between two entities."""
        ...

    def get_relationships(
        self,
        entity_id: UUID,
        universe_id: UUID,
        relationship_type: str | None = None,
    ) -> list[Relationship]:
        """Get all relationships for an entity in a universe."""
        ...

    def get_relationship_between(
        self,
        from_entity_id: UUID,
        to_entity_id: UUID,
        universe_id: UUID,
        relationship_type: str | None = None,
    ) -> Relationship | None:
        """Get a specific relationship between two entities."""
        ...

    def update_relationship(self, relationship: Relationship) -> None:
        """Update an existing relationship."""
        ...

    def delete_relationship(self, relationship_id: UUID) -> None:
        """Delete a relationship."""
        ...

    # Variant operations (for timeline forks)
    def create_variant_node(
        self,
        original_entity_id: UUID,
        variant_entity_id: UUID,
        variant_universe_id: UUID,
        changes: dict[str, str],
    ) -> None:
        """
        Create a variant of an entity for a forked universe.

        This creates a new node with a VARIANT_OF relationship to the original.
        """
        ...

    def get_entity_in_universe(
        self,
        entity_name: str,
        universe_id: UUID,
        entity_type: str | None = None,
    ) -> UUID | None:
        """
        Get an entity in a specific universe, considering variants.

        Returns the variant if one exists, otherwise the original from Prime.
        """
        ...

    def has_variant(self, original_entity_id: UUID, universe_id: UUID) -> bool:
        """Check if an entity has a variant in a specific universe."""
        ...

    # Graph queries
    def find_connected_entities(
        self,
        entity_id: UUID,
        universe_id: UUID,
        max_depth: int = 2,
    ) -> list[UUID]:
        """Find entities connected to a given entity within N hops."""
        ...

    def find_path(
        self,
        from_entity_id: UUID,
        to_entity_id: UUID,
        universe_id: UUID,
    ) -> list[UUID] | None:
        """Find a path between two entities if one exists."""
        ...

    # Vector search
    def similarity_search(
        self,
        query_embedding: list[float],
        universe_id: UUID,
        limit: int = 10,
    ) -> list[tuple[UUID, float]]:
        """
        Search for similar entities using vector embeddings.

        Returns list of (entity_id, similarity_score) tuples.
        """
        ...

    # NPC Memory operations
    def create_memory(self, memory: NPCMemory) -> None:
        """Create a new NPC memory node."""
        ...

    def get_memories_for_npc(
        self,
        npc_id: UUID,
        limit: int = 20,
    ) -> list[NPCMemory]:
        """Get all memories for an NPC, ordered by timestamp (newest first)."""
        ...

    def get_memories_about_entity(
        self,
        npc_id: UUID,
        subject_id: UUID,
        limit: int = 10,
    ) -> list[NPCMemory]:
        """Get an NPC's memories about a specific entity."""
        ...

    def update_memory_recall(self, memory_id: UUID) -> None:
        """Update the recall tracking for a memory (increment times_recalled, update last_recalled)."""
        ...

    def delete_memory(self, memory_id: UUID) -> None:
        """Delete a memory."""
        ...

    # Inventory operations
    def get_owned_items(self, character_id: UUID) -> list[Entity]:
        """Get all items owned by a character via OWNS relationships."""
        ...

    def get_entities_at_location(
        self, location_id: UUID, universe_id: UUID, entity_type: str | None = None
    ) -> list[Entity]:
        """Get all entities at a specific location."""
        ...
