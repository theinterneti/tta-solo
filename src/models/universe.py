"""
Universe Models for TTA-Solo.

Universes represent timeline branches in the multiverse.
Each universe is a Dolt branch, allowing Git-like versioning of game state.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class UniverseStatus(StrEnum):
    """Status of a universe/timeline."""

    ACTIVE = "active"  # Currently playable
    ARCHIVED = "archived"  # Preserved but not active
    MERGED = "merged"  # Content merged into parent
    ABANDONED = "abandoned"  # No longer maintained


class Universe(BaseModel):
    """
    A timeline/universe in the multiverse.

    Each universe corresponds to a Dolt branch.
    Forking creates a new branch with zero-cost copy.
    """

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="")

    # Lineage
    parent_universe_id: UUID | None = Field(
        default=None, description="The universe this was forked from"
    )
    fork_point_event_id: UUID | None = Field(
        default=None, description="The event where the fork occurred"
    )
    depth: int = Field(default=0, ge=0, description="How many forks from Prime Material")

    # Ownership
    owner_id: UUID | None = Field(default=None, description="Player who owns this branch")
    is_shared: bool = Field(default=False, description="Whether others can join")

    # Status
    status: UniverseStatus = UniverseStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_event_at: datetime | None = Field(default=None)

    # Dolt integration
    branch_name: str = Field(default="", description="Corresponding Dolt branch name")

    def is_prime_material(self) -> bool:
        """Check if this is the root/canonical universe."""
        return self.parent_universe_id is None and self.depth == 0

    def is_active(self) -> bool:
        """Check if this universe is currently active."""
        return self.status == UniverseStatus.ACTIVE


class UniverseConnection(BaseModel):
    """
    A connection between two universes allowing travel.

    Some universes can be linked, allowing characters to travel between them.
    """

    id: UUID = Field(default_factory=uuid4)
    from_universe_id: UUID
    to_universe_id: UUID
    connection_type: str = Field(
        default="portal", description="How travel occurs: portal, spell, artifact, etc."
    )
    bidirectional: bool = Field(default=True)
    is_active: bool = Field(default=True)
    location_id: UUID | None = Field(
        default=None, description="Where the connection exists in from_universe"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)


def create_prime_material(name: str = "Prime Material", description: str = "") -> Universe:
    """Create the root canonical universe."""
    universe = Universe(
        name=name,
        description=description or "The canonical timeline.",
        parent_universe_id=None,
        depth=0,
        is_shared=True,
    )
    universe.branch_name = "main"
    return universe


def create_fork(
    parent: Universe,
    name: str,
    owner_id: UUID | None = None,
    fork_reason: str = "",
    fork_point_event_id: UUID | None = None,
) -> Universe:
    """
    Create a new universe forked from a parent.

    Args:
        parent: The universe to fork from
        name: Name for the new universe
        owner_id: Player who owns this branch
        fork_reason: Why the fork was created
        fork_point_event_id: The event that triggered the fork

    Returns:
        New Universe instance
    """
    universe = Universe(
        name=name,
        description=fork_reason,
        parent_universe_id=parent.id,
        fork_point_event_id=fork_point_event_id,
        depth=parent.depth + 1,
        owner_id=owner_id,
        is_shared=False,
    )
    # Generate Dolt branch name
    safe_name = name.lower().replace(" ", "_").replace("-", "_")
    if owner_id:
        universe.branch_name = f"user/{owner_id}/{safe_name}"
    else:
        universe.branch_name = f"fork/{universe.id}"
    return universe


def create_shared_adventure(
    parent: Universe,
    name: str,
    description: str = "",
) -> Universe:
    """
    Create a shared adventure that multiple players can fork.

    Like a template that others can branch from.
    """
    universe = Universe(
        name=name,
        description=description,
        parent_universe_id=parent.id,
        depth=parent.depth + 1,
        is_shared=True,
    )
    safe_name = name.lower().replace(" ", "_").replace("-", "_")
    universe.branch_name = f"adventure/{safe_name}"
    return universe
