"""
Real Dolt database implementation for TTA-Solo.

Uses mysql-connector-python to connect to a Dolt SQL server.
Dolt provides Git-like branching for timeline forks.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import mysql.connector
from mysql.connector.cursor import MySQLCursor

from src.models import Entity, EntityType, Event, EventOutcome, EventType, Universe, UniverseStatus


class DoltConnection:
    """
    Connection manager for Dolt database.

    Handles connection pooling and provides cursor context manager.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        database: str = "tta_solo",
    ) -> None:
        self.config = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
            "autocommit": True,
        }
        self._connection: Any = None

    def get_connection(self) -> Any:
        """Get or create a database connection."""
        if self._connection is None or not self._connection.is_connected():
            self._connection = mysql.connector.connect(**self.config)
        return self._connection

    def close(self) -> None:
        """Close the database connection."""
        if self._connection and self._connection.is_connected():
            self._connection.close()
            self._connection = None


class DoltRepository:
    """
    Real Dolt implementation of the DoltRepository interface.

    Uses Dolt's Git-like branching for timeline management.
    """

    def __init__(self, connection: DoltConnection) -> None:
        self._conn = connection

    def _execute(
        self,
        query: str,
        params: tuple[Any, ...] | None = None,
        fetch: bool = True,
    ) -> list[dict[str, Any]]:
        """Execute a query and return results as list of dicts."""
        conn = self._conn.get_connection()
        cursor: MySQLCursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(query, params or ())
            if fetch:
                results = cursor.fetchall()
                # Cast to list of dicts (cursor with dictionary=True returns dicts)
                return [dict(row) for row in results]  # type: ignore[arg-type]
            return []
        finally:
            cursor.close()

    def _execute_proc(self, proc_name: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Execute a Dolt stored procedure."""
        conn = self._conn.get_connection()
        cursor: MySQLCursor = conn.cursor(dictionary=True)
        try:
            cursor.callproc(proc_name, args)
            # Fetch results from stored procedures
            results = []
            for result in cursor.stored_results():
                results.extend(result.fetchall())
            return results
        finally:
            cursor.close()

    # =========================================================================
    # Branch Operations
    # =========================================================================

    def get_current_branch(self) -> str:
        """Get the name of the current Dolt branch."""
        result = self._execute("SELECT active_branch() as branch")
        return result[0]["branch"] if result else "main"

    def create_branch(self, branch_name: str, from_branch: str = "main") -> None:
        """Create a new branch from an existing branch."""
        # First checkout the source branch
        current = self.get_current_branch()
        if current != from_branch:
            self._execute_proc("dolt_checkout", (from_branch,))

        # Create the new branch
        self._execute_proc("dolt_branch", (branch_name,))

        # Return to original branch if needed
        if current != from_branch:
            self._execute_proc("dolt_checkout", (current,))

    def checkout_branch(self, branch_name: str) -> None:
        """Switch to a different branch."""
        self._execute_proc("dolt_checkout", (branch_name,))

    def branch_exists(self, branch_name: str) -> bool:
        """Check if a branch exists."""
        result = self._execute(
            "SELECT name FROM dolt_branches WHERE name = %s",
            (branch_name,),
        )
        return len(result) > 0

    def delete_branch(self, branch_name: str) -> None:
        """Delete a branch."""
        if branch_name == "main":
            raise ValueError("Cannot delete main branch")
        if branch_name == self.get_current_branch():
            raise ValueError("Cannot delete the current branch")

        self._execute_proc("dolt_branch", ("-D", branch_name))

    # =========================================================================
    # Universe Operations
    # =========================================================================

    def save_universe(self, universe: Universe) -> None:
        """Insert or update a universe record."""
        query = """
            INSERT INTO universes (
                id, name, description, dolt_branch, status, depth,
                parent_universe_id, owner_id, fork_point_event_id,
                is_shared, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                description = VALUES(description),
                status = VALUES(status),
                updated_at = VALUES(updated_at)
        """
        self._execute(
            query,
            (
                str(universe.id),
                universe.name,
                universe.description,
                universe.dolt_branch,
                universe.status.value,
                universe.depth,
                str(universe.parent_universe_id) if universe.parent_universe_id else None,
                str(universe.owner_id) if universe.owner_id else None,
                str(universe.fork_point_event_id) if universe.fork_point_event_id else None,
                universe.is_shared,
                universe.created_at,
                universe.updated_at,
            ),
            fetch=False,
        )
        # Commit changes
        self._execute_proc("dolt_commit", ("-am", f"Save universe {universe.name}"))

    def get_universe(self, universe_id: UUID) -> Universe | None:
        """Get a universe by ID."""
        result = self._execute(
            "SELECT * FROM universes WHERE id = %s",
            (str(universe_id),),
        )
        if not result:
            return None
        return self._row_to_universe(result[0])

    def get_universe_by_branch(self, branch_name: str) -> Universe | None:
        """Get a universe by its Dolt branch name."""
        result = self._execute(
            "SELECT * FROM universes WHERE dolt_branch = %s",
            (branch_name,),
        )
        if not result:
            return None
        return self._row_to_universe(result[0])

    def _row_to_universe(self, row: dict[str, Any]) -> Universe:
        """Convert a database row to a Universe object."""
        return Universe(
            id=UUID(row["id"]),
            name=row["name"],
            description=row["description"] or "",
            dolt_branch=row["dolt_branch"],
            status=UniverseStatus(row["status"]),
            depth=row["depth"],
            parent_universe_id=UUID(row["parent_universe_id"])
            if row["parent_universe_id"]
            else None,
            owner_id=UUID(row["owner_id"]) if row["owner_id"] else None,
            fork_point_event_id=UUID(row["fork_point_event_id"])
            if row["fork_point_event_id"]
            else None,
            is_shared=row.get("is_shared", False),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # =========================================================================
    # Entity Operations
    # =========================================================================

    def save_entity(self, entity: Entity) -> None:
        """Insert or update an entity record."""
        query = """
            INSERT INTO entities (
                id, universe_id, type, name, description, tags,
                stats, faction_properties, location_properties, item_properties,
                current_location_id, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                description = VALUES(description),
                tags = VALUES(tags),
                stats = VALUES(stats),
                faction_properties = VALUES(faction_properties),
                location_properties = VALUES(location_properties),
                item_properties = VALUES(item_properties),
                current_location_id = VALUES(current_location_id),
                updated_at = VALUES(updated_at)
        """
        self._execute(
            query,
            (
                str(entity.id),
                str(entity.universe_id),
                entity.type.value,
                entity.name,
                entity.description,
                json.dumps(entity.tags),
                entity.stats.model_dump_json() if entity.stats else None,
                entity.faction_properties.model_dump_json() if entity.faction_properties else None,
                entity.location_properties.model_dump_json()
                if entity.location_properties
                else None,
                entity.item_properties.model_dump_json() if entity.item_properties else None,
                str(entity.current_location_id) if entity.current_location_id else None,
                entity.created_at,
                entity.updated_at,
            ),
            fetch=False,
        )
        self._execute_proc("dolt_commit", ("-am", f"Save entity {entity.name}"))

    def get_entity(self, entity_id: UUID, universe_id: UUID) -> Entity | None:
        """Get an entity by ID within a specific universe."""
        result = self._execute(
            "SELECT * FROM entities WHERE id = %s AND universe_id = %s",
            (str(entity_id), str(universe_id)),
        )
        if not result:
            return None
        return self._row_to_entity(result[0])

    def get_entity_by_name(self, name: str, universe_id: UUID) -> Entity | None:
        """Get an entity by name within a specific universe."""
        result = self._execute(
            "SELECT * FROM entities WHERE name = %s AND universe_id = %s",
            (name, str(universe_id)),
        )
        if not result:
            return None
        return self._row_to_entity(result[0])

    def get_entities_by_type(self, entity_type: str, universe_id: UUID) -> list[Entity]:
        """Get all entities of a given type in a universe."""
        result = self._execute(
            "SELECT * FROM entities WHERE type = %s AND universe_id = %s",
            (entity_type, str(universe_id)),
        )
        return [self._row_to_entity(row) for row in result]

    def _row_to_entity(self, row: dict[str, Any]) -> Entity:
        """Convert a database row to an Entity object."""
        from src.models import EntityStats, FactionProperties, ItemProperties, LocationProperties

        return Entity(
            id=UUID(row["id"]),
            universe_id=UUID(row["universe_id"]),
            type=EntityType(row["type"]),
            name=row["name"],
            description=row["description"] or "",
            tags=json.loads(row["tags"]) if row["tags"] else [],
            stats=EntityStats.model_validate_json(row["stats"]) if row["stats"] else None,
            faction_properties=(
                FactionProperties.model_validate_json(row["faction_properties"])
                if row.get("faction_properties")
                else None
            ),
            location_properties=(
                LocationProperties.model_validate_json(row["location_properties"])
                if row.get("location_properties")
                else None
            ),
            item_properties=(
                ItemProperties.model_validate_json(row["item_properties"])
                if row.get("item_properties")
                else None
            ),
            current_location_id=(
                UUID(row["current_location_id"]) if row.get("current_location_id") else None
            ),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # =========================================================================
    # Event Operations
    # =========================================================================

    def append_event(self, event: Event) -> None:
        """Append an event to the immutable event log."""
        query = """
            INSERT INTO events (
                id, universe_id, event_type, timestamp, real_timestamp,
                actor_id, target_id, location_id, outcome, roll,
                payload, narrative_summary, caused_by_event_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """
        self._execute(
            query,
            (
                str(event.id),
                str(event.universe_id),
                event.event_type.value,
                event.timestamp,
                event.real_timestamp,
                str(event.actor_id),
                str(event.target_id) if event.target_id else None,
                str(event.location_id) if event.location_id else None,
                event.outcome.value,
                event.roll,
                json.dumps(event.payload),
                event.narrative_summary,
                str(event.caused_by_event_id) if event.caused_by_event_id else None,
            ),
            fetch=False,
        )
        self._execute_proc("dolt_commit", ("-am", f"Event: {event.event_type.value}"))

    def get_events(
        self,
        universe_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Event]:
        """Get events for a universe, ordered by timestamp."""
        result = self._execute(
            """
            SELECT * FROM events
            WHERE universe_id = %s
            ORDER BY timestamp ASC
            LIMIT %s OFFSET %s
            """,
            (str(universe_id), limit, offset),
        )
        return [self._row_to_event(row) for row in result]

    def get_event(self, event_id: UUID) -> Event | None:
        """Get a specific event by ID."""
        result = self._execute(
            "SELECT * FROM events WHERE id = %s",
            (str(event_id),),
        )
        if not result:
            return None
        return self._row_to_event(result[0])

    def get_events_since(self, universe_id: UUID, since_event_id: UUID) -> list[Event]:
        """Get all events after a specific event."""
        # First get the timestamp of the since event
        since_event = self.get_event(since_event_id)
        if not since_event:
            return []

        result = self._execute(
            """
            SELECT * FROM events
            WHERE universe_id = %s AND timestamp > %s
            ORDER BY timestamp ASC
            """,
            (str(universe_id), since_event.timestamp),
        )
        return [self._row_to_event(row) for row in result]

    def get_events_at_location(
        self,
        universe_id: UUID,
        location_id: UUID,
        limit: int = 100,
    ) -> list[Event]:
        """Get events that occurred at a specific location."""
        result = self._execute(
            """
            SELECT * FROM events
            WHERE universe_id = %s AND location_id = %s
            ORDER BY timestamp DESC
            LIMIT %s
            """,
            (str(universe_id), str(location_id), limit),
        )
        return [self._row_to_event(row) for row in result]

    def _row_to_event(self, row: dict[str, Any]) -> Event:
        """Convert a database row to an Event object."""
        return Event(
            id=UUID(row["id"]),
            universe_id=UUID(row["universe_id"]),
            event_type=EventType(row["event_type"]),
            timestamp=row["timestamp"],
            real_timestamp=row["real_timestamp"],
            actor_id=UUID(row["actor_id"]),
            target_id=UUID(row["target_id"]) if row["target_id"] else None,
            location_id=UUID(row["location_id"]) if row["location_id"] else None,
            outcome=EventOutcome(row["outcome"]),
            roll=row["roll"],
            payload=json.loads(row["payload"]) if row["payload"] else {},
            narrative_summary=row["narrative_summary"] or "",
            caused_by_event_id=UUID(row["caused_by_event_id"])
            if row["caused_by_event_id"]
            else None,
        )


# SQL schema for initializing the database
DOLT_SCHEMA = """
-- Universes table
CREATE TABLE IF NOT EXISTS universes (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    dolt_branch VARCHAR(255) NOT NULL UNIQUE,
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    depth INT NOT NULL DEFAULT 0,
    parent_universe_id VARCHAR(36),
    owner_id VARCHAR(36),
    fork_point_event_id VARCHAR(36),
    is_shared BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    INDEX idx_dolt_branch (dolt_branch),
    INDEX idx_parent (parent_universe_id)
);

-- Entities table
CREATE TABLE IF NOT EXISTS entities (
    id VARCHAR(36) PRIMARY KEY,
    universe_id VARCHAR(36) NOT NULL,
    type VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    tags JSON,
    stats JSON,
    faction_properties JSON,
    location_properties JSON,
    item_properties JSON,
    current_location_id VARCHAR(36),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    INDEX idx_universe (universe_id),
    INDEX idx_type (type),
    INDEX idx_name (name),
    UNIQUE KEY uk_name_universe (name, universe_id)
);

-- Events table (append-only log)
CREATE TABLE IF NOT EXISTS events (
    id VARCHAR(36) PRIMARY KEY,
    universe_id VARCHAR(36) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    timestamp DATETIME NOT NULL,
    real_timestamp DATETIME NOT NULL,
    actor_id VARCHAR(36) NOT NULL,
    target_id VARCHAR(36),
    location_id VARCHAR(36),
    outcome VARCHAR(50) NOT NULL,
    roll INT,
    payload JSON,
    narrative_summary TEXT,
    caused_by_event_id VARCHAR(36),
    INDEX idx_universe_time (universe_id, timestamp),
    INDEX idx_location (location_id),
    INDEX idx_actor (actor_id)
);

-- NPC profiles (extends entities with personality data)
CREATE TABLE IF NOT EXISTS npc_profiles (
    entity_id VARCHAR(36) PRIMARY KEY,
    traits JSON NOT NULL,
    motivations JSON NOT NULL,
    speech_style VARCHAR(50),
    quirks JSON,
    lawful_chaotic INT DEFAULT 0,
    good_evil INT DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (entity_id) REFERENCES entities(id)
);

-- NPC memories (for persistence, Neo4j handles search)
CREATE TABLE IF NOT EXISTS npc_memories (
    id VARCHAR(36) PRIMARY KEY,
    npc_id VARCHAR(36) NOT NULL,
    memory_type VARCHAR(50) NOT NULL,
    subject_id VARCHAR(36),
    description TEXT NOT NULL,
    emotional_valence FLOAT DEFAULT 0,
    importance FLOAT DEFAULT 0.5,
    event_id VARCHAR(36),
    timestamp DATETIME NOT NULL,
    times_recalled INT DEFAULT 0,
    last_recalled DATETIME,
    INDEX idx_npc (npc_id),
    INDEX idx_subject (subject_id),
    INDEX idx_event (event_id),
    FOREIGN KEY (npc_id) REFERENCES entities(id)
);
"""


def init_dolt_schema(connection: DoltConnection) -> None:
    """Initialize the Dolt database schema."""
    conn = connection.get_connection()
    cursor = conn.cursor()
    try:
        for statement in DOLT_SCHEMA.split(";"):
            statement = statement.strip()
            if statement:
                cursor.execute(statement)
        conn.commit()
    finally:
        cursor.close()
