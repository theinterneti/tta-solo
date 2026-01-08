"""
Database layer for TTA-Solo.

Provides interfaces and implementations for:
- Dolt: Git-like versioned SQL for truth/event sourcing
- Neo4j: Graph database for relationships and semantic search
"""

from __future__ import annotations

from src.db.interfaces import (
    DoltRepository,
    Neo4jRepository,
)
from src.db.memory import (
    InMemoryDoltRepository,
    InMemoryNeo4jRepository,
)

__all__ = [
    "DoltRepository",
    "Neo4jRepository",
    "InMemoryDoltRepository",
    "InMemoryNeo4jRepository",
]
