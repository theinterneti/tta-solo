"""
Multiverse Service for TTA-Solo.

Orchestrates timeline forking, cross-world travel, and universe management.
Implements the "Git for Fiction" concept from the multiverse spec.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
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


class MergeProposalStatus(str, Enum):
    """Status of a merge proposal."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MERGED = "merged"
    CONFLICT = "conflict"


class MergeProposal(BaseModel):
    """
    A proposal to merge content back to canon.

    This is the "Pull Request" for fiction - allowing player-created
    content (locations, NPCs, lore) to be proposed for the Prime Material.
    """

    id: UUID = Field(default_factory=uuid4)
    source_universe_id: UUID = Field(description="Universe containing the content")
    target_universe_id: UUID = Field(description="Universe to merge into (usually Prime)")
    entity_ids: list[UUID] = Field(
        default_factory=list,
        description="Specific entities to merge",
    )
    title: str = Field(default="", description="Short title for the proposal")
    description: str = Field(description="Why this content should be merged")

    # Review workflow
    status: MergeProposalStatus = MergeProposalStatus.PENDING
    submitter_id: UUID | None = Field(default=None, description="Who submitted this")
    reviewer_id: UUID | None = Field(default=None, description="Who reviewed this")
    review_notes: str = Field(default="", description="Notes from the reviewer")

    # Validation
    conflicts: list[str] = Field(
        default_factory=list,
        description="Any conflicts detected during validation",
    )
    validation_passed: bool = Field(default=False)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_at: datetime | None = None
    merged_at: datetime | None = None


class MergeResult(BaseModel):
    """Result of a merge operation."""

    success: bool
    proposal_id: UUID | None = None
    entities_merged: int = 0
    entities_skipped: int = 0
    error: str | None = None
    narrative: str = Field(default="", description="Narrative description of the merge")


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

    # =========================================================================
    # Phase 5: Merge/PR System for Canon
    # =========================================================================

    # In-memory storage for proposals (would be persisted in production)
    _proposals: dict[UUID, MergeProposal] = field(default_factory=dict)

    def propose_merge(
        self,
        source_universe_id: UUID,
        target_universe_id: UUID,
        entity_ids: list[UUID],
        title: str,
        description: str,
        submitter_id: UUID | None = None,
    ) -> MergeProposal:
        """
        Create a proposal to merge content from one universe to another.

        This is the "Pull Request" for fiction - proposing that player-created
        content be added to the canonical Prime Material.

        Args:
            source_universe_id: Universe containing the content to merge
            target_universe_id: Universe to merge into (usually Prime Material)
            entity_ids: Specific entities to include in the merge
            title: Short title for the proposal
            description: Why this content should be merged
            submitter_id: UUID of the player submitting

        Returns:
            MergeProposal with validation status
        """
        proposal = MergeProposal(
            source_universe_id=source_universe_id,
            target_universe_id=target_universe_id,
            entity_ids=entity_ids,
            title=title,
            description=description,
            submitter_id=submitter_id,
        )

        # Validate the proposal
        conflicts = self.validate_merge(proposal)
        proposal.conflicts = conflicts
        proposal.validation_passed = len(conflicts) == 0

        if conflicts:
            proposal.status = MergeProposalStatus.CONFLICT

        # Store the proposal
        self._proposals[proposal.id] = proposal

        return proposal

    def validate_merge(self, proposal: MergeProposal) -> list[str]:
        """
        Validate a merge proposal for conflicts.

        Checks:
        1. Source and target universes exist
        2. Entities exist in source universe
        3. No name conflicts in target universe
        4. Target is an ancestor of source (can merge up the tree)

        Args:
            proposal: The merge proposal to validate

        Returns:
            List of conflict descriptions (empty if valid)
        """
        conflicts: list[str] = []

        # Check source universe exists
        source = self.dolt.get_universe(proposal.source_universe_id)
        if source is None:
            conflicts.append(f"Source universe {proposal.source_universe_id} not found")
            return conflicts

        # Check target universe exists
        target = self.dolt.get_universe(proposal.target_universe_id)
        if target is None:
            conflicts.append(f"Target universe {proposal.target_universe_id} not found")
            return conflicts

        # Check target is active
        if not target.is_active():
            conflicts.append(f"Target universe is not active (status: {target.status})")

        # Check source and target are not the same
        if proposal.source_universe_id == proposal.target_universe_id:
            conflicts.append("Cannot merge a universe into itself")

        # Check target is an ancestor of source (can only merge up the tree)
        lineage = self.get_universe_lineage(proposal.source_universe_id)
        target_ids = [u.id for u in lineage]
        if proposal.target_universe_id not in target_ids:
            conflicts.append(
                f"Target universe must be an ancestor of source universe. "
                f"Can only merge up the fork tree."
            )

        # Verify entities exist in source
        self.dolt.checkout_branch(source.dolt_branch)
        for entity_id in proposal.entity_ids:
            entity = self.dolt.get_entity(entity_id, proposal.source_universe_id)
            if entity is None:
                conflicts.append(f"Entity {entity_id} not found in source universe")
            else:
                # Check for name conflicts in target
                self.dolt.checkout_branch(target.dolt_branch)
                # In a real implementation, we'd check if an entity with the
                # same name already exists in the target
                existing = self.dolt.get_entity(entity_id, proposal.target_universe_id)
                if existing is not None:
                    conflicts.append(
                        f"Entity '{entity.name}' already exists in target universe"
                    )
                self.dolt.checkout_branch(source.dolt_branch)

        return conflicts

    def review_proposal(
        self,
        proposal_id: UUID,
        approved: bool,
        reviewer_id: UUID,
        review_notes: str = "",
    ) -> MergeProposal | None:
        """
        Review a merge proposal, approving or rejecting it.

        Args:
            proposal_id: ID of the proposal to review
            approved: Whether to approve the proposal
            reviewer_id: UUID of the reviewer
            review_notes: Notes explaining the decision

        Returns:
            Updated MergeProposal, or None if not found
        """
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            return None

        proposal.reviewer_id = reviewer_id
        proposal.review_notes = review_notes
        proposal.reviewed_at = datetime.utcnow()

        if approved:
            if proposal.validation_passed:
                proposal.status = MergeProposalStatus.APPROVED
            else:
                # Can't approve with conflicts
                proposal.status = MergeProposalStatus.CONFLICT
        else:
            proposal.status = MergeProposalStatus.REJECTED

        return proposal

    def execute_merge(self, proposal_id: UUID) -> MergeResult:
        """
        Execute an approved merge proposal.

        Copies entities from the source universe to the target universe,
        creating appropriate events and Neo4j relationships.

        Args:
            proposal_id: ID of the approved proposal to execute

        Returns:
            MergeResult with outcome details
        """
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            return MergeResult(
                success=False,
                error=f"Proposal {proposal_id} not found",
            )

        if proposal.status != MergeProposalStatus.APPROVED:
            return MergeResult(
                success=False,
                proposal_id=proposal_id,
                error=f"Proposal is not approved (status: {proposal.status.value})",
            )

        # Get universes
        source = self.dolt.get_universe(proposal.source_universe_id)
        target = self.dolt.get_universe(proposal.target_universe_id)

        if source is None or target is None:
            return MergeResult(
                success=False,
                proposal_id=proposal_id,
                error="Source or target universe not found",
            )

        entities_merged = 0
        entities_skipped = 0
        merged_names: list[str] = []

        # Copy each entity to the target
        for entity_id in proposal.entity_ids:
            self.dolt.checkout_branch(source.dolt_branch)
            entity = self.dolt.get_entity(entity_id, proposal.source_universe_id)

            if entity is None:
                entities_skipped += 1
                continue

            # Create a copy for the target universe
            merged_entity = entity.model_copy(deep=True)
            merged_entity.id = uuid4()  # New ID in target
            merged_entity.universe_id = proposal.target_universe_id
            merged_entity.created_at = datetime.utcnow()
            merged_entity.updated_at = datetime.utcnow()

            # Save to target
            self.dolt.checkout_branch(target.dolt_branch)
            self.dolt.save_entity(merged_entity)

            # Create Neo4j variant relationship (tracks origin)
            self.neo4j.create_variant_node(
                original_entity_id=entity_id,
                variant_entity_id=merged_entity.id,
                variant_universe_id=proposal.target_universe_id,
                changes={"merged_from": str(proposal.source_universe_id)},
            )

            entities_merged += 1
            merged_names.append(entity.name)

        # Record the merge event
        merge_event = Event(
            universe_id=proposal.target_universe_id,
            event_type=EventType.MERGE,
            actor_id=proposal.submitter_id or uuid4(),
            outcome=EventOutcome.SUCCESS,
            payload={
                "proposal_id": str(proposal_id),
                "source_universe_id": str(proposal.source_universe_id),
                "entities_merged": entities_merged,
                "entity_names": merged_names,
            },
            narrative_summary=f"Content merged from alternate timeline: {', '.join(merged_names)}",
        )
        self.dolt.append_event(merge_event)

        # Update proposal status
        proposal.status = MergeProposalStatus.MERGED
        proposal.merged_at = datetime.utcnow()

        return MergeResult(
            success=True,
            proposal_id=proposal_id,
            entities_merged=entities_merged,
            entities_skipped=entities_skipped,
            narrative=f"Successfully merged {entities_merged} entities to canon: {', '.join(merged_names)}",
        )

    def get_pending_proposals(
        self,
        target_universe_id: UUID | None = None,
    ) -> list[MergeProposal]:
        """
        Get all pending merge proposals.

        Args:
            target_universe_id: Filter by target universe (optional)

        Returns:
            List of pending MergeProposal objects
        """
        pending = [
            p for p in self._proposals.values()
            if p.status == MergeProposalStatus.PENDING
        ]

        if target_universe_id is not None:
            pending = [p for p in pending if p.target_universe_id == target_universe_id]

        return pending

    def get_proposal(self, proposal_id: UUID) -> MergeProposal | None:
        """Get a specific merge proposal by ID."""
        return self._proposals.get(proposal_id)
