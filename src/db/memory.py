"""
In-memory implementations of database interfaces for testing.

These implementations store everything in dictionaries, making tests
fast and isolated from actual database infrastructure.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from uuid import UUID

from src.models import Entity, Event, Relationship, Universe
from src.models.npc import NPCMemory
from src.models.quest import Quest, QuestStatus


class InMemoryDoltRepository:
    """
    In-memory implementation of DoltRepository for testing.

    Simulates Dolt's branching model with nested dictionaries.
    """

    def __init__(self) -> None:
        self._current_branch = "main"
        self._branches: set[str] = {"main"}

        # Data stored per-branch: branch_name -> {table_name -> {id -> record}}
        self._universes: dict[str, dict[UUID, Universe]] = {"main": {}}
        self._entities: dict[str, dict[UUID, Entity]] = {"main": {}}
        self._events: dict[str, list[Event]] = {"main": []}

        # NPC profiles (not branched - global across timelines)
        self._npc_profiles: dict[UUID, dict] = {}

        # Quests stored by ID (not branched for now)
        self._quests: dict[UUID, Quest] = {}

    def get_current_branch(self) -> str:
        """Get the name of the current Dolt branch."""
        return self._current_branch

    def create_branch(self, branch_name: str, from_branch: str = "main") -> None:
        """Create a new branch from an existing branch."""
        if from_branch not in self._branches:
            raise ValueError(f"Source branch '{from_branch}' does not exist")
        if branch_name in self._branches:
            raise ValueError(f"Branch '{branch_name}' already exists")

        self._branches.add(branch_name)
        # Deep copy data from source branch
        self._universes[branch_name] = deepcopy(self._universes.get(from_branch, {}))
        self._entities[branch_name] = deepcopy(self._entities.get(from_branch, {}))
        self._events[branch_name] = deepcopy(self._events.get(from_branch, []))

    def checkout_branch(self, branch_name: str) -> None:
        """Switch to a different branch."""
        if branch_name not in self._branches:
            raise ValueError(f"Branch '{branch_name}' does not exist")
        self._current_branch = branch_name

    def branch_exists(self, branch_name: str) -> bool:
        """Check if a branch exists."""
        return branch_name in self._branches

    def delete_branch(self, branch_name: str) -> None:
        """Delete a branch."""
        if branch_name == "main":
            raise ValueError("Cannot delete main branch")
        if branch_name not in self._branches:
            raise ValueError(f"Branch '{branch_name}' does not exist")
        if branch_name == self._current_branch:
            raise ValueError("Cannot delete the current branch")

        self._branches.discard(branch_name)
        self._universes.pop(branch_name, None)
        self._entities.pop(branch_name, None)
        self._events.pop(branch_name, None)

    # Universe operations
    def save_universe(self, universe: Universe) -> None:
        """Insert or update a universe record."""
        branch_data = self._universes.setdefault(self._current_branch, {})
        universe.updated_at = datetime.utcnow()
        branch_data[universe.id] = deepcopy(universe)

    def get_universe(self, universe_id: UUID) -> Universe | None:
        """Get a universe by ID."""
        branch_data = self._universes.get(self._current_branch, {})
        universe = branch_data.get(universe_id)
        return deepcopy(universe) if universe else None

    def get_universe_by_branch(self, branch_name: str) -> Universe | None:
        """Get a universe by its Dolt branch name."""
        branch_data = self._universes.get(self._current_branch, {})
        for universe in branch_data.values():
            if universe.branch_name == branch_name:
                return deepcopy(universe)
        return None

    # Entity operations
    def save_entity(self, entity: Entity) -> None:
        """Insert or update an entity record."""
        branch_data = self._entities.setdefault(self._current_branch, {})
        entity.updated_at = datetime.utcnow()
        branch_data[entity.id] = deepcopy(entity)

    def get_entity(self, entity_id: UUID, universe_id: UUID) -> Entity | None:
        """Get an entity by ID within a specific universe."""
        branch_data = self._entities.get(self._current_branch, {})
        entity = branch_data.get(entity_id)
        if entity and entity.universe_id == universe_id:
            return deepcopy(entity)
        return None

    def get_entity_by_name(self, name: str, universe_id: UUID) -> Entity | None:
        """Get an entity by name within a specific universe."""
        branch_data = self._entities.get(self._current_branch, {})
        for entity in branch_data.values():
            if entity.name == name and entity.universe_id == universe_id:
                return deepcopy(entity)
        return None

    def get_entities_by_type(self, entity_type: str, universe_id: UUID) -> list[Entity]:
        """Get all entities of a given type in a universe."""
        branch_data = self._entities.get(self._current_branch, {})
        return [
            deepcopy(e)
            for e in branch_data.values()
            if e.type.value == entity_type and e.universe_id == universe_id
        ]

    # Event operations
    def append_event(self, event: Event) -> None:
        """Append an event to the immutable event log."""
        branch_events = self._events.setdefault(self._current_branch, [])
        branch_events.append(deepcopy(event))

    def get_events(
        self,
        universe_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Event]:
        """Get events for a universe, ordered by timestamp."""
        branch_events = self._events.get(self._current_branch, [])
        universe_events = [e for e in branch_events if e.universe_id == universe_id]
        universe_events.sort(key=lambda e: e.timestamp)
        return [deepcopy(e) for e in universe_events[offset : offset + limit]]

    def get_event(self, event_id: UUID) -> Event | None:
        """Get a specific event by ID."""
        branch_events = self._events.get(self._current_branch, [])
        for event in branch_events:
            if event.id == event_id:
                return deepcopy(event)
        return None

    def get_events_since(self, universe_id: UUID, since_event_id: UUID) -> list[Event]:
        """Get all events after a specific event."""
        branch_events = self._events.get(self._current_branch, [])
        universe_events = [e for e in branch_events if e.universe_id == universe_id]
        universe_events.sort(key=lambda e: e.timestamp)

        # Find the index of the since_event
        since_index = None
        for i, event in enumerate(universe_events):
            if event.id == since_event_id:
                since_index = i
                break

        if since_index is None:
            return []

        return [deepcopy(e) for e in universe_events[since_index + 1 :]]

    def get_events_at_location(
        self,
        universe_id: UUID,
        location_id: UUID,
        limit: int = 100,
    ) -> list[Event]:
        """Get events that occurred at a specific location."""
        branch_events = self._events.get(self._current_branch, [])
        location_events = [
            e
            for e in branch_events
            if e.universe_id == universe_id and e.location_id == location_id
        ]
        location_events.sort(key=lambda e: e.timestamp, reverse=True)
        return [deepcopy(e) for e in location_events[:limit]]

    # NPC Profile operations
    def get_npc_profile(self, entity_id: UUID) -> dict | None:
        """Get an NPC profile by entity ID."""
        return deepcopy(self._npc_profiles.get(entity_id))

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
        self._npc_profiles[entity_id] = {
            "entity_id": entity_id,
            "traits": deepcopy(traits),
            "motivations": list(motivations),
            "speech_style": speech_style,
            "quirks": list(quirks) if quirks else [],
            "lawful_chaotic": lawful_chaotic,
            "good_evil": good_evil,
        }

    # Quest operations
    def save_quest(self, quest: Quest) -> None:
        """Save or update a quest."""
        self._quests[quest.id] = deepcopy(quest)

    def get_quest(self, quest_id: UUID) -> Quest | None:
        """Get a quest by ID."""
        quest = self._quests.get(quest_id)
        return deepcopy(quest) if quest else None

    def get_quests_by_status(self, universe_id: UUID, status: QuestStatus) -> list[Quest]:
        """Get all quests in a universe with a specific status."""
        return [
            deepcopy(q)
            for q in self._quests.values()
            if q.universe_id == universe_id and q.status == status
        ]

    def get_quests_for_universe(self, universe_id: UUID) -> list[Quest]:
        """Get all quests in a universe."""
        return [deepcopy(q) for q in self._quests.values() if q.universe_id == universe_id]


class InMemoryNeo4jRepository:
    """
    In-memory implementation of Neo4jRepository for testing.

    Simulates Neo4j's graph model with dictionaries.
    """

    def __init__(self) -> None:
        # Relationships stored by ID
        self._relationships: dict[UUID, Relationship] = {}

        # Variant tracking: (original_id, universe_id) -> variant_id
        self._variants: dict[tuple[UUID, UUID], UUID] = {}

        # Entity metadata for lookups: entity_id -> {name, type, universe_id}
        self._entity_metadata: dict[UUID, dict] = {}

        # Mock embeddings for similarity search
        self._embeddings: dict[UUID, list[float]] = {}

        # NPC memories stored by ID
        self._memories: dict[UUID, NPCMemory] = {}

    def create_relationship(self, relationship: Relationship) -> None:
        """Create a relationship between two entities."""
        self._relationships[relationship.id] = deepcopy(relationship)

    def get_relationships(
        self,
        entity_id: UUID,
        universe_id: UUID,
        relationship_type: str | None = None,
    ) -> list[Relationship]:
        """Get all relationships for an entity in a universe."""
        results = []
        for rel in self._relationships.values():
            if rel.universe_id != universe_id:
                continue
            if rel.from_entity_id != entity_id and rel.to_entity_id != entity_id:
                continue
            if relationship_type and rel.relationship_type.value != relationship_type:
                continue
            results.append(deepcopy(rel))
        return results

    def get_relationship_between(
        self,
        from_entity_id: UUID,
        to_entity_id: UUID,
        universe_id: UUID,
        relationship_type: str | None = None,
    ) -> Relationship | None:
        """Get a specific relationship between two entities."""
        for rel in self._relationships.values():
            if rel.universe_id != universe_id:
                continue
            if rel.from_entity_id != from_entity_id or rel.to_entity_id != to_entity_id:
                continue
            if relationship_type and rel.relationship_type.value != relationship_type:
                continue
            return deepcopy(rel)
        return None

    def update_relationship(self, relationship: Relationship) -> None:
        """Update an existing relationship."""
        if relationship.id not in self._relationships:
            raise ValueError(f"Relationship {relationship.id} not found")
        self._relationships[relationship.id] = deepcopy(relationship)

    def delete_relationship(self, relationship_id: UUID) -> None:
        """Delete a relationship."""
        self._relationships.pop(relationship_id, None)

    # Variant operations
    def create_variant_node(
        self,
        original_entity_id: UUID,
        variant_entity_id: UUID,
        variant_universe_id: UUID,
        changes: dict[str, str],
    ) -> None:
        """Create a variant of an entity for a forked universe."""
        key = (original_entity_id, variant_universe_id)
        self._variants[key] = variant_entity_id

        # Copy metadata if original exists
        if original_entity_id in self._entity_metadata:
            original_meta = self._entity_metadata[original_entity_id]
            self._entity_metadata[variant_entity_id] = {
                "name": original_meta.get("name"),
                "type": original_meta.get("type"),
                "universe_id": variant_universe_id,
                "changes": changes,
            }

    def register_entity(
        self, entity_id: UUID, name: str, entity_type: str, universe_id: UUID
    ) -> None:
        """Register entity metadata for lookups (helper for testing)."""
        self._entity_metadata[entity_id] = {
            "name": name,
            "type": entity_type,
            "universe_id": universe_id,
        }

    def get_entity_in_universe(
        self,
        entity_name: str,
        universe_id: UUID,
        entity_type: str | None = None,
    ) -> UUID | None:
        """Get an entity in a specific universe, considering variants."""
        # First, look for direct match in this universe
        for entity_id, meta in self._entity_metadata.items():
            name_match = meta.get("name") == entity_name
            universe_match = meta.get("universe_id") == universe_id
            type_match = entity_type is None or meta.get("type") == entity_type
            if name_match and universe_match and type_match:
                return entity_id

        # If not found, look for variant of a Prime entity
        for entity_id, meta in self._entity_metadata.items():
            name_match = meta.get("name") == entity_name
            type_match = entity_type is None or meta.get("type") == entity_type
            if name_match and type_match:
                # Check if there's a variant for this universe
                key = (entity_id, universe_id)
                if key in self._variants:
                    return self._variants[key]
                # If no variant, return original (if from Prime)
                if meta.get("universe_id") is None:
                    return entity_id

        return None

    def has_variant(self, original_entity_id: UUID, universe_id: UUID) -> bool:
        """Check if an entity has a variant in a specific universe."""
        return (original_entity_id, universe_id) in self._variants

    # Graph queries
    def find_connected_entities(
        self,
        entity_id: UUID,
        universe_id: UUID,
        max_depth: int = 2,
    ) -> list[UUID]:
        """Find entities connected to a given entity within N hops."""
        visited: set[UUID] = set()
        to_visit: list[tuple[UUID, int]] = [(entity_id, 0)]

        while to_visit:
            current_id, depth = to_visit.pop(0)
            if current_id in visited or depth > max_depth:
                continue
            visited.add(current_id)

            # Find connected entities through relationships
            for rel in self._relationships.values():
                if rel.universe_id != universe_id:
                    continue
                if rel.from_entity_id == current_id:
                    to_visit.append((rel.to_entity_id, depth + 1))
                elif rel.to_entity_id == current_id:
                    to_visit.append((rel.from_entity_id, depth + 1))

        visited.discard(entity_id)  # Don't include the starting entity
        return list(visited)

    def find_path(
        self,
        from_entity_id: UUID,
        to_entity_id: UUID,
        universe_id: UUID,
    ) -> list[UUID] | None:
        """Find a path between two entities if one exists."""
        if from_entity_id == to_entity_id:
            return [from_entity_id]

        visited: set[UUID] = set()
        queue: list[list[UUID]] = [[from_entity_id]]

        while queue:
            path = queue.pop(0)
            current = path[-1]

            if current in visited:
                continue
            visited.add(current)

            for rel in self._relationships.values():
                if rel.universe_id != universe_id:
                    continue

                next_entity = None
                if rel.from_entity_id == current:
                    next_entity = rel.to_entity_id
                elif rel.to_entity_id == current:
                    next_entity = rel.from_entity_id

                if next_entity and next_entity not in visited:
                    new_path = path + [next_entity]
                    if next_entity == to_entity_id:
                        return new_path
                    queue.append(new_path)

        return None

    # Vector search
    def set_embedding(self, entity_id: UUID, embedding: list[float]) -> None:
        """Set an embedding for an entity (helper for testing)."""
        self._embeddings[entity_id] = embedding

    def similarity_search(
        self,
        query_embedding: list[float],
        universe_id: UUID,
        limit: int = 10,
    ) -> list[tuple[UUID, float]]:
        """Search for similar entities using vector embeddings."""
        results: list[tuple[UUID, float]] = []

        for entity_id, embedding in self._embeddings.items():
            # Filter by universe
            meta = self._entity_metadata.get(entity_id, {})
            if meta.get("universe_id") != universe_id:
                continue

            # Cosine similarity
            similarity = self._cosine_similarity(query_embedding, embedding)
            results.append((entity_id, similarity))

        # Sort by similarity descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(a) != len(b):
            return 0.0

        dot_product = sum(x * y for x, y in zip(a, b, strict=True))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    # NPC Memory operations
    def create_memory(self, memory: NPCMemory) -> None:
        """Create a new NPC memory node."""
        self._memories[memory.id] = deepcopy(memory)

    def get_memories_for_npc(
        self,
        npc_id: UUID,
        limit: int = 20,
    ) -> list[NPCMemory]:
        """Get all memories for an NPC, ordered by timestamp (newest first)."""
        memories = [deepcopy(m) for m in self._memories.values() if m.npc_id == npc_id]
        memories.sort(key=lambda m: m.timestamp, reverse=True)
        return memories[:limit]

    def get_memories_about_entity(
        self,
        npc_id: UUID,
        subject_id: UUID,
        limit: int = 10,
    ) -> list[NPCMemory]:
        """Get an NPC's memories about a specific entity."""
        memories = [
            deepcopy(m)
            for m in self._memories.values()
            if m.npc_id == npc_id and m.subject_id == subject_id
        ]
        memories.sort(key=lambda m: m.timestamp, reverse=True)
        return memories[:limit]

    def update_memory_recall(self, memory_id: UUID) -> None:
        """Update the recall tracking for a memory."""
        if memory_id in self._memories:
            self._memories[memory_id].recall()

    def delete_memory(self, memory_id: UUID) -> None:
        """Delete a memory."""
        self._memories.pop(memory_id, None)

    def get_owned_items(self, character_id: UUID) -> list[Entity]:
        """Get all items owned by a character via OWNS or CARRIES relationships."""
        raise NotImplementedError(
            "InMemoryNeo4jRepository.get_owned_items requires access to the Dolt "
            "entity store and is not implemented for the in-memory test repository. "
            "Use get_relationships() with CARRIES/OWNS relationship types instead."
        )

    def get_entities_at_location(
        self, location_id: UUID, universe_id: UUID, entity_type: str | None = None
    ) -> list[Entity]:
        """Get all entities at a specific location via LOCATED_IN relationships."""
        raise NotImplementedError(
            "InMemoryNeo4jRepository.get_entities_at_location requires access to the "
            "Dolt entity store and is not implemented for the in-memory test "
            "repository. Use get_relationships() with LOCATED_IN relationship type instead."
        )
