"""
Real Neo4j database implementation for TTA-Solo.

Uses the official neo4j Python driver for graph operations.
Neo4j stores relationships, context, and vector embeddings.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from neo4j import Driver, GraphDatabase, Query, Session

from src.models import Relationship, RelationshipType
from src.models.npc import MemoryType, NPCMemory


class Neo4jConnection:
    """
    Connection manager for Neo4j database.

    Handles driver lifecycle and provides session access.
    """

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "password",
        database: str = "neo4j",
    ) -> None:
        self.uri = uri
        self.auth = (user, password)
        self.database = database
        self._driver: Driver | None = None

    def get_driver(self) -> Driver:
        """Get or create a database driver."""
        if self._driver is None:
            self._driver = GraphDatabase.driver(self.uri, auth=self.auth)
        return self._driver

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.get_driver().session(database=self.database)

    def close(self) -> None:
        """Close the database driver."""
        if self._driver:
            self._driver.close()
            self._driver = None

    def verify_connectivity(self) -> bool:
        """Verify the database connection is working."""
        try:
            self.get_driver().verify_connectivity()
            return True
        except Exception:
            return False


class Neo4jRepository:
    """
    Real Neo4j implementation of the Neo4jRepository interface.

    Handles graph operations for relationships, variants, and vector search.
    """

    def __init__(self, connection: Neo4jConnection) -> None:
        self._conn = connection

    def _run_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a Cypher query and return results."""
        with self._conn.get_session() as session:
            # Use Query for type safety, cast needed for dynamic strings
            result = session.run(Query(query), parameters or {})  # type: ignore[arg-type]
            return [dict(record) for record in result]

    def _run_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        """Execute a write query."""
        with self._conn.get_session() as session:
            session.run(Query(query), parameters or {})  # type: ignore[arg-type]

    # =========================================================================
    # Relationship Operations
    # =========================================================================

    def create_relationship(self, relationship: Relationship) -> None:
        """Create a relationship between two entities."""
        query = """
        MERGE (from:Entity {id: $from_id})
        MERGE (to:Entity {id: $to_id})
        CREATE (from)-[r:RELATES {
            id: $rel_id,
            type: $rel_type,
            universe_id: $universe_id,
            strength: $strength,
            trust: $trust,
            description: $description,
            established_at: datetime($established_at),
            is_active: $is_active
        }]->(to)
        """
        self._run_write(
            query,
            {
                "from_id": str(relationship.from_entity_id),
                "to_id": str(relationship.to_entity_id),
                "rel_id": str(relationship.id),
                "rel_type": relationship.relationship_type.value,
                "universe_id": str(relationship.universe_id),
                "strength": relationship.strength,
                "trust": relationship.trust,
                "description": relationship.description or "",
                "established_at": relationship.established_at.isoformat(),
                "is_active": relationship.is_active,
            },
        )

    def get_relationships(
        self,
        entity_id: UUID,
        universe_id: UUID,
        relationship_type: str | None = None,
    ) -> list[Relationship]:
        """Get all relationships for an entity in a universe."""
        type_filter = "AND r.type = $rel_type" if relationship_type else ""
        query = f"""
        MATCH (e:Entity {{id: $entity_id}})-[r:RELATES]-(other:Entity)
        WHERE r.universe_id = $universe_id {type_filter}
        RETURN r, e.id as from_id, other.id as to_id
        """
        params: dict[str, Any] = {
            "entity_id": str(entity_id),
            "universe_id": str(universe_id),
        }
        if relationship_type:
            params["rel_type"] = relationship_type

        results = self._run_query(query, params)
        return [self._record_to_relationship(r) for r in results]

    def update_relationship(self, relationship: Relationship) -> None:
        """Update an existing relationship."""
        query = """
        MATCH ()-[r:RELATES {id: $rel_id}]->()
        SET r.strength = $strength,
            r.trust = $trust,
            r.description = $description,
            r.is_active = $is_active
        """
        self._run_write(
            query,
            {
                "rel_id": str(relationship.id),
                "strength": relationship.strength,
                "trust": relationship.trust,
                "description": relationship.description or "",
                "is_active": relationship.is_active,
            },
        )

    def delete_relationship(self, relationship_id: UUID) -> None:
        """Delete a relationship."""
        query = """
        MATCH ()-[r:RELATES {id: $rel_id}]->()
        DELETE r
        """
        self._run_write(query, {"rel_id": str(relationship_id)})

    def _record_to_relationship(self, record: dict[str, Any]) -> Relationship:
        """Convert a Neo4j record to a Relationship object."""
        r = record["r"]
        established_at = r.get("established_at")
        if established_at and hasattr(established_at, "to_native"):
            established_at = established_at.to_native()
        elif established_at is None:
            established_at = datetime.now(UTC)

        return Relationship(
            id=UUID(r["id"]),
            from_entity_id=UUID(record["from_id"]),
            to_entity_id=UUID(record["to_id"]),
            relationship_type=RelationshipType(r["type"]),
            universe_id=UUID(r["universe_id"]),
            strength=r["strength"],
            trust=r.get("trust"),
            description=r.get("description"),
            established_at=established_at,
            is_active=r.get("is_active", True),
        )

    # =========================================================================
    # Variant Operations
    # =========================================================================

    def create_variant_node(
        self,
        original_entity_id: UUID,
        variant_entity_id: UUID,
        variant_universe_id: UUID,
        changes: dict[str, str],
    ) -> None:
        """Create a variant of an entity for a forked universe."""
        query = """
        MERGE (original:Entity {id: $original_id})
        CREATE (variant:Entity {
            id: $variant_id,
            universe_id: $universe_id,
            is_variant: true
        })
        CREATE (variant)-[:VARIANT_OF {changes: $changes}]->(original)
        """
        self._run_write(
            query,
            {
                "original_id": str(original_entity_id),
                "variant_id": str(variant_entity_id),
                "universe_id": str(variant_universe_id),
                "changes": changes,
            },
        )

    def get_entity_in_universe(
        self,
        entity_name: str,
        universe_id: UUID,
        entity_type: str | None = None,
    ) -> UUID | None:
        """Get an entity in a specific universe, considering variants."""
        type_filter = "AND e.type = $entity_type" if entity_type else ""

        # First try to find a direct match in this universe
        query = f"""
        MATCH (e:Entity)
        WHERE e.name = $name AND e.universe_id = $universe_id {type_filter}
        RETURN e.id as id
        LIMIT 1
        """
        params: dict[str, Any] = {
            "name": entity_name,
            "universe_id": str(universe_id),
        }
        if entity_type:
            params["entity_type"] = entity_type

        results = self._run_query(query, params)
        if results:
            return UUID(results[0]["id"])

        # If not found, look for a variant
        query = f"""
        MATCH (variant:Entity)-[:VARIANT_OF]->(original:Entity)
        WHERE original.name = $name AND variant.universe_id = $universe_id {type_filter}
        RETURN variant.id as id
        LIMIT 1
        """
        results = self._run_query(query, params)
        if results:
            return UUID(results[0]["id"])

        # Finally, check if the original exists in Prime (no universe_id or prime)
        query = f"""
        MATCH (e:Entity)
        WHERE e.name = $name
            AND (e.universe_id IS NULL OR e.universe_id = 'prime')
            AND NOT EXISTS {{
                MATCH (v:Entity)-[:VARIANT_OF]->(e)
                WHERE v.universe_id = $universe_id
            }}
            {type_filter}
        RETURN e.id as id
        LIMIT 1
        """
        results = self._run_query(query, params)
        if results:
            return UUID(results[0]["id"])

        return None

    def has_variant(self, original_entity_id: UUID, universe_id: UUID) -> bool:
        """Check if an entity has a variant in a specific universe."""
        query = """
        MATCH (variant:Entity)-[:VARIANT_OF]->(original:Entity {id: $original_id})
        WHERE variant.universe_id = $universe_id
        RETURN count(variant) as count
        """
        results = self._run_query(
            query,
            {
                "original_id": str(original_entity_id),
                "universe_id": str(universe_id),
            },
        )
        return results[0]["count"] > 0 if results else False

    # =========================================================================
    # Graph Queries
    # =========================================================================

    def find_connected_entities(
        self,
        entity_id: UUID,
        universe_id: UUID,
        max_depth: int = 2,
    ) -> list[UUID]:
        """Find entities connected to a given entity within N hops."""
        query = """
        MATCH (start:Entity {id: $entity_id})-[r:RELATES*1..$max_depth]-(connected:Entity)
        WHERE ALL(rel IN r WHERE rel.universe_id = $universe_id)
        RETURN DISTINCT connected.id as id
        """
        results = self._run_query(
            query,
            {
                "entity_id": str(entity_id),
                "universe_id": str(universe_id),
                "max_depth": max_depth,
            },
        )
        return [UUID(r["id"]) for r in results]

    def find_path(
        self,
        from_entity_id: UUID,
        to_entity_id: UUID,
        universe_id: UUID,
    ) -> list[UUID] | None:
        """Find a path between two entities if one exists."""
        query = """
        MATCH path = shortestPath(
            (from:Entity {id: $from_id})-[r:RELATES*]-(to:Entity {id: $to_id})
        )
        WHERE ALL(rel IN r WHERE rel.universe_id = $universe_id)
        RETURN [n IN nodes(path) | n.id] as path
        """
        results = self._run_query(
            query,
            {
                "from_id": str(from_entity_id),
                "to_id": str(to_entity_id),
                "universe_id": str(universe_id),
            },
        )
        if not results:
            return None
        return [UUID(id_str) for id_str in results[0]["path"]]

    # =========================================================================
    # Vector Search
    # =========================================================================

    def set_embedding(self, entity_id: UUID, embedding: list[float]) -> None:
        """Set an embedding vector for an entity."""
        query = """
        MATCH (e:Entity {id: $entity_id})
        SET e.embedding = $embedding
        """
        self._run_write(
            query,
            {
                "entity_id": str(entity_id),
                "embedding": embedding,
            },
        )

    def similarity_search(
        self,
        query_embedding: list[float],
        universe_id: UUID,
        limit: int = 10,
    ) -> list[tuple[UUID, float]]:
        """Search for similar entities using vector embeddings."""
        # Neo4j 5.x with vector index
        query = """
        MATCH (e:Entity)
        WHERE e.universe_id = $universe_id AND e.embedding IS NOT NULL
        WITH e, gds.similarity.cosine(e.embedding, $query_embedding) AS similarity
        WHERE similarity > 0
        RETURN e.id as id, similarity
        ORDER BY similarity DESC
        LIMIT $limit
        """
        results = self._run_query(
            query,
            {
                "universe_id": str(universe_id),
                "query_embedding": query_embedding,
                "limit": limit,
            },
        )
        return [(UUID(r["id"]), r["similarity"]) for r in results]

    # =========================================================================
    # NPC Memory Operations
    # =========================================================================

    def create_memory(self, memory: NPCMemory) -> None:
        """Create a new NPC memory node."""
        query = """
        MERGE (npc:Entity {id: $npc_id})
        CREATE (m:Memory {
            id: $id,
            npc_id: $npc_id,
            type: $memory_type,
            subject_id: $subject_id,
            description: $description,
            emotional_valence: $emotional_valence,
            importance: $importance,
            event_id: $event_id,
            timestamp: datetime($timestamp),
            times_recalled: $times_recalled,
            last_recalled: $last_recalled
        })
        CREATE (npc)-[:REMEMBERS]->(m)
        WITH m
        MATCH (subject:Entity {id: $subject_id})
        WHERE $subject_id IS NOT NULL
        CREATE (m)-[:ABOUT]->(subject)
        """
        self._run_write(
            query,
            {
                "id": str(memory.id),
                "npc_id": str(memory.npc_id),
                "memory_type": memory.memory_type.value,
                "subject_id": str(memory.subject_id) if memory.subject_id else None,
                "description": memory.description,
                "emotional_valence": memory.emotional_valence,
                "importance": memory.importance,
                "event_id": str(memory.event_id) if memory.event_id else None,
                "timestamp": memory.timestamp.isoformat(),
                "times_recalled": memory.times_recalled,
                "last_recalled": memory.last_recalled.isoformat() if memory.last_recalled else None,
            },
        )

    def get_memories_for_npc(
        self,
        npc_id: UUID,
        limit: int = 20,
    ) -> list[NPCMemory]:
        """Get all memories for an NPC, ordered by timestamp (newest first)."""
        query = """
        MATCH (npc:Entity {id: $npc_id})-[:REMEMBERS]->(m:Memory)
        RETURN m
        ORDER BY m.timestamp DESC
        LIMIT $limit
        """
        results = self._run_query(
            query,
            {"npc_id": str(npc_id), "limit": limit},
        )
        return [self._record_to_memory(r["m"]) for r in results]

    def get_memories_about_entity(
        self,
        npc_id: UUID,
        subject_id: UUID,
        limit: int = 10,
    ) -> list[NPCMemory]:
        """Get an NPC's memories about a specific entity."""
        query = """
        MATCH (npc:Entity {id: $npc_id})-[:REMEMBERS]->(m:Memory)-[:ABOUT]->(subject:Entity {id: $subject_id})
        RETURN m
        ORDER BY m.timestamp DESC
        LIMIT $limit
        """
        results = self._run_query(
            query,
            {
                "npc_id": str(npc_id),
                "subject_id": str(subject_id),
                "limit": limit,
            },
        )
        return [self._record_to_memory(r["m"]) for r in results]

    def update_memory_recall(self, memory_id: UUID) -> None:
        """Update the recall tracking for a memory."""
        query = """
        MATCH (m:Memory {id: $memory_id})
        SET m.times_recalled = m.times_recalled + 1,
            m.last_recalled = datetime()
        """
        self._run_write(query, {"memory_id": str(memory_id)})

    def delete_memory(self, memory_id: UUID) -> None:
        """Delete a memory."""
        query = """
        MATCH (m:Memory {id: $memory_id})
        DETACH DELETE m
        """
        self._run_write(query, {"memory_id": str(memory_id)})

    def _record_to_memory(self, record: dict[str, Any]) -> NPCMemory:
        """Convert a Neo4j record to an NPCMemory object."""
        # Parse datetime fields
        timestamp_raw = record.get("timestamp")
        if timestamp_raw is not None and hasattr(timestamp_raw, "to_native"):
            timestamp = timestamp_raw.to_native()
        elif isinstance(timestamp_raw, datetime):
            timestamp = timestamp_raw
        else:
            timestamp = datetime.now(UTC)

        last_recalled_raw = record.get("last_recalled")
        last_recalled: datetime | None = None
        if last_recalled_raw is not None and hasattr(last_recalled_raw, "to_native"):
            last_recalled = last_recalled_raw.to_native()
        elif isinstance(last_recalled_raw, datetime):
            last_recalled = last_recalled_raw

        return NPCMemory(
            id=UUID(record["id"]),
            npc_id=UUID(record["npc_id"]),
            memory_type=MemoryType(record["type"]),
            subject_id=UUID(record["subject_id"]) if record.get("subject_id") else None,
            description=record["description"],
            emotional_valence=record.get("emotional_valence", 0.0),
            importance=record.get("importance", 0.5),
            event_id=UUID(record["event_id"]) if record.get("event_id") else None,
            timestamp=timestamp,
            times_recalled=record.get("times_recalled", 0),
            last_recalled=last_recalled,
        )

    # =========================================================================
    # Entity Registration (for metadata lookups)
    # =========================================================================

    def register_entity(
        self,
        entity_id: UUID,
        name: str,
        entity_type: str,
        universe_id: UUID,
    ) -> None:
        """Register entity metadata for lookups."""
        query = """
        MERGE (e:Entity {id: $entity_id})
        SET e.name = $name,
            e.type = $entity_type,
            e.universe_id = $universe_id
        """
        self._run_write(
            query,
            {
                "entity_id": str(entity_id),
                "name": name,
                "entity_type": entity_type,
                "universe_id": str(universe_id),
            },
        )


# Cypher statements for initializing Neo4j schema/indexes
NEO4J_SCHEMA = [
    # Entity indexes
    "CREATE INDEX entity_id_index IF NOT EXISTS FOR (e:Entity) ON (e.id)",
    "CREATE INDEX entity_name_index IF NOT EXISTS FOR (e:Entity) ON (e.name)",
    "CREATE INDEX entity_universe_index IF NOT EXISTS FOR (e:Entity) ON (e.universe_id)",
    "CREATE INDEX entity_type_index IF NOT EXISTS FOR (e:Entity) ON (e.type)",
    # Memory indexes (for NPC AI)
    "CREATE INDEX memory_id_index IF NOT EXISTS FOR (m:Memory) ON (m.id)",
    "CREATE INDEX memory_npc_index IF NOT EXISTS FOR (m:Memory) ON (m.npc_id)",
    "CREATE INDEX memory_type_index IF NOT EXISTS FOR (m:Memory) ON (m.type)",
    "CREATE INDEX memory_timestamp_index IF NOT EXISTS FOR (m:Memory) ON (m.timestamp)",
    # Relationship indexes
    "CREATE INDEX rel_universe_index IF NOT EXISTS FOR ()-[r:RELATES]-() ON (r.universe_id)",
    "CREATE INDEX rel_type_index IF NOT EXISTS FOR ()-[r:RELATES]-() ON (r.type)",
    # Constraints
    "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT memory_id_unique IF NOT EXISTS FOR (m:Memory) REQUIRE m.id IS UNIQUE",
    # Vector index for similarity search (requires Neo4j 5.11+ with native vector support)
    # Uncomment when vector embeddings are implemented:
    # "CALL db.index.vector.createNodeIndex('entityEmbeddings', 'Entity', 'embedding', 1536, 'cosine')",
]


def init_neo4j_schema(connection: Neo4jConnection) -> None:
    """Initialize the Neo4j database schema and indexes."""
    with connection.get_session() as session:
        for statement in NEO4J_SCHEMA:
            try:
                session.run(Query(statement))  # type: ignore[arg-type]
            except Exception as e:
                # Index may already exist, that's fine
                if "already exists" not in str(e).lower():
                    raise
