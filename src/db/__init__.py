"""
Database layer for TTA-Solo.

Provides interfaces and implementations for:
- Dolt: Git-like versioned SQL for truth/event sourcing
- Neo4j: Graph database for relationships and semantic search

Implementations:
- InMemory*: For testing (no external dependencies)
- Real drivers: For production (requires running databases)
"""

from __future__ import annotations

# Real database implementations (require running databases)
from src.db.dolt import (
    DoltConnection,
    DoltRepository,
    init_dolt_schema,
)
from src.db.interfaces import (
    DoltRepository as DoltRepositoryProtocol,
)
from src.db.interfaces import (
    Neo4jRepository as Neo4jRepositoryProtocol,
)
from src.db.memory import (
    InMemoryDoltRepository,
    InMemoryNeo4jRepository,
)
from src.db.neo4j_driver import (
    Neo4jConnection,
    Neo4jRepository,
    init_neo4j_schema,
)

__all__ = [
    # Protocol interfaces
    "DoltRepositoryProtocol",
    "Neo4jRepositoryProtocol",
    # In-memory implementations (for testing)
    "InMemoryDoltRepository",
    "InMemoryNeo4jRepository",
    # Real database implementations
    "DoltConnection",
    "DoltRepository",
    "init_dolt_schema",
    "Neo4jConnection",
    "Neo4jRepository",
    "init_neo4j_schema",
]
