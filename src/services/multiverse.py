"""
Multiverse Service for TTA-Solo.

Orchestrates timeline forking, cross-world travel, and universe management.
Implements the "Git for Fiction" concept from the multiverse spec.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.db.interfaces import DoltRepository, Neo4jRepository
from src.models import (
    Event,
    EventOutcome,
    EventType,
    Universe,
    UniverseStatus,
    create_fork,
    create_fork_event,
    create_prime_material,
)


class ForkResult(BaseModel):
    """Result of a universe fork operation."""

    success: bool
    universe: Universe | None = None
    fork_event: Event | None = None
    error: str | None = None


class TravelResult(BaseModel):
    """Result of a cross-world travel operation."""

    success: bool
    traveler_copy_id: UUID | None = None
    destination_universe_id: UUID | None = None
    travel_event: Event | None = None
    error: str | None = None


class MergeProposal(BaseModel):
    """A proposal to merge content back to canon."""

    id: UUID = Field(default_factory=uuid4)
    source_universe_id: UUID
    target_universe_id: UUID
    entity_ids: list[UUID] = Field(default_factory=list)
    description: str
    status: str = "pending"  # pending, approved, rejected, merged
    created_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_at: datetime | None = None


@dataclass
class MultiverseService:
    """
    Service for managing the multiverse.

    Handles timeline forking, cross-world travel, and content merging.
    Uses repository interfaces for database access.
    """

    dolt: DoltRepository
    neo4j: Neo4jRepository

    def initialize_prime_material(self, name: str = "Prime Material") -> Universe:
        """
        Initialize the Prime Material universe.

        Should be called once during system setup.

        Args:
            name: Name for the prime universe (default: "Prime Material")

        Returns:
            The created Prime Material universe
        """
        prime = create_prime_material(name=name)
        self.dolt.save_universe(prime)
        return prime

    def fork_universe(
        self,
        parent_universe_id: UUID,
        new_universe_name: str,
        fork_reason: str,
        player_id: UUID | None = None,
        fork_point_event_id: UUID | None = None,
    ) -> ForkResult:
        """
        Create a new timeline branch from a parent universe.

        This is the core "what if" operation - creating an alternate timeline
        where events can diverge from the parent.

        Args:
            parent_universe_id: UUID of the universe to fork from
            new_universe_name: Name for the new universe
            fork_reason: Why this fork is being created
            player_id: UUID of the player creating the fork (optional)
            fork_point_event_id: Event ID where the fork occurs (optional)

        Returns:
            ForkResult with the new universe and fork event, or error
        """
        # Get the parent universe
        parent = self.dolt.get_universe(parent_universe_id)
        if parent is None:
            return ForkResult(
                success=False,
                error=f"Parent universe {parent_universe_id} not found",
            )

        # Check parent is active
        if not parent.is_active():
            return ForkResult(
                success=False,
                error=f"Cannot fork from inactive universe (status: {parent.status})",
            )

        # Create the new universe record
        new_universe = create_fork(
            parent=parent,
            name=new_universe_name,
            owner_id=player_id,
            fork_reason=fork_reason,
            fork_point_event_id=fork_point_event_id,
        )

        # Create Dolt branch
        if not self.dolt.branch_exists(parent.dolt_branch):
            return ForkResult(
                success=False,
                error=f"Parent Dolt branch '{parent.dolt_branch}' does not exist",
            )

        try:
            self.dolt.create_branch(
                branch_name=new_universe.dolt_branch,
                from_branch=parent.dolt_branch,
            )
        except ValueError as e:
            return ForkResult(success=False, error=str(e))

        # Switch to the new branch and save the universe
        self.dolt.checkout_branch(new_universe.dolt_branch)
        self.dolt.save_universe(new_universe)

        # Create and record the fork event
        # Use a system actor ID if no player specified
        actor_id = player_id or uuid4()
        fork_event = create_fork_event(
            parent_universe_id=parent_universe_id,
            child_universe_id=new_universe.id,
            actor_id=actor_id,
            fork_reason=fork_reason,
            fork_point_event_id=fork_point_event_id,
        )
        self.dolt.append_event(fork_event)

        return ForkResult(
            success=True,
            universe=new_universe,
            fork_event=fork_event,
        )

    def travel_between_worlds(
        self,
        traveler_id: UUID,
        source_universe_id: UUID,
        destination_universe_id: UUID,
        travel_method: str = "portal",
    ) -> TravelResult:
        """
        Move a character between universes.

        The character is COPIED to the destination - the original remains
        in the source universe (possibly dormant).

        Args:
            traveler_id: UUID of the entity traveling
            source_universe_id: UUID of the source universe
            destination_universe_id: UUID of the destination universe
            travel_method: How the travel occurs (portal, spell, artifact)

        Returns:
            TravelResult with the new entity copy and travel event, or error
        """
        # Validate source and destination universes
        source = self.dolt.get_universe(source_universe_id)
        if source is None:
            return TravelResult(
                success=False,
                error=f"Source universe {source_universe_id} not found",
            )

        destination = self.dolt.get_universe(destination_universe_id)
        if destination is None:
            return TravelResult(
                success=False,
                error=f"Destination universe {destination_universe_id} not found",
            )

        # Get the traveler from source universe
        self.dolt.checkout_branch(source.dolt_branch)
        traveler = self.dolt.get_entity(traveler_id, source_universe_id)
        if traveler is None:
            return TravelResult(
                success=False,
                error=f"Traveler {traveler_id} not found in source universe",
            )

        if not traveler.is_character():
            return TravelResult(
                success=False,
                error="Only characters can travel between worlds",
            )

        # Create a copy of the traveler in the destination universe
        traveler_copy = traveler.model_copy(deep=True)
        traveler_copy.id = uuid4()
        traveler_copy.universe_id = destination_universe_id
        traveler_copy.current_location_id = None  # Must find new location
        traveler_copy.created_at = datetime.utcnow()
        traveler_copy.updated_at = datetime.utcnow()

        # Save the copy in the destination
        self.dolt.checkout_branch(destination.dolt_branch)
        self.dolt.save_entity(traveler_copy)

        # Create Neo4j variant relationship
        self.neo4j.create_variant_node(
            original_entity_id=traveler_id,
            variant_entity_id=traveler_copy.id,
            variant_universe_id=destination_universe_id,
            changes={"travel_origin": str(source_universe_id)},
        )

        # Record the travel event
        travel_event = Event(
            universe_id=destination_universe_id,
            event_type=EventType.TRAVEL,
            actor_id=traveler_copy.id,
            outcome=EventOutcome.SUCCESS,
            payload={
                "original_entity_id": str(traveler_id),
                "from_universe_id": str(source_universe_id),
                "to_universe_id": str(destination_universe_id),
                "travel_method": travel_method,
            },
            narrative_summary=f"{traveler.name} traveled from another world via {travel_method}.",
        )
        self.dolt.append_event(travel_event)

        return TravelResult(
            success=True,
            traveler_copy_id=traveler_copy.id,
            destination_universe_id=destination_universe_id,
            travel_event=travel_event,
        )

    def archive_universe(self, universe_id: UUID) -> bool:
        """
        Archive a universe, making it read-only.

        Archived universes can be viewed but not modified.

        Args:
            universe_id: UUID of the universe to archive

        Returns:
            True if successful, False otherwise
        """
        universe = self.dolt.get_universe(universe_id)
        if universe is None:
            return False

        if universe.is_prime_material():
            return False  # Cannot archive Prime Material

        universe.status = UniverseStatus.ARCHIVED
        universe.updated_at = datetime.utcnow()

        self.dolt.checkout_branch(universe.dolt_branch)
        self.dolt.save_universe(universe)
        return True

    def get_universe_lineage(self, universe_id: UUID) -> list[Universe]:
        """
        Get the ancestry of a universe back to Prime Material.

        Args:
            universe_id: UUID of the universe to trace

        Returns:
            List of universes from Prime Material to the target
        """
        lineage: list[Universe] = []
        current_id: UUID | None = universe_id

        while current_id is not None:
            universe = self.dolt.get_universe(current_id)
            if universe is None:
                break
            lineage.append(universe)
            current_id = universe.parent_universe_id

        lineage.reverse()  # Prime Material first
        return lineage

    def get_fork_children(self, universe_id: UUID) -> list[Universe]:
        """
        Get all universes that were forked from this one.

        Note: This is a simplified implementation. A real implementation
        would query the database for universes with this parent_id.

        Args:
            universe_id: UUID of the parent universe

        Returns:
            List of child universes
        """
        # This would need a proper query in a real implementation
        # For now, we return an empty list as a placeholder
        return []
