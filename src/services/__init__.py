"""
Service layer for TTA-Solo.

Services orchestrate business logic using database repositories.
"""

from __future__ import annotations

from src.services.multiverse import MultiverseService

__all__ = [
    "MultiverseService",
]
