"""Tests for the MultiverseService."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.models import (
    EventType,
    UniverseStatus,
    create_character,
    create_location,
)
from src.services.multiverse import (
    MergeProposalStatus,
    MultiverseService,
)


@pytest.fixture
def multiverse_service() -> MultiverseService:
    """Create a MultiverseService with in-memory repositories."""
    dolt = InMemoryDoltRepository()
    neo4j = InMemoryNeo4jRepository()
    return MultiverseService(dolt=dolt, neo4j=neo4j)


class TestInitializePrimeMaterial:
    """Tests for Prime Material initialization."""

    def test_creates_prime_universe(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        assert prime.name == "Prime Material"
        assert prime.is_prime_material()
        assert prime.dolt_branch == "main"

    def test_custom_name(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material(name="Custom Prime")
        assert prime.name == "Custom Prime"

    def test_prime_is_persisted(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        retrieved = multiverse_service.dolt.get_universe(prime.id)
        assert retrieved is not None
        assert retrieved.id == prime.id


class TestForkUniverse:
    """Tests for universe forking."""

    def test_fork_creates_new_universe(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="What If Timeline",
            fork_reason="Testing alternate outcome",
        )

        assert result.success
        assert result.universe is not None
        assert result.universe.name == "What If Timeline"
        assert result.universe.parent_universe_id == prime.id
        assert result.universe.depth == 1

    def test_fork_creates_dolt_branch(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Branch Test",
            fork_reason="Testing branching",
        )

        assert result.success
        assert multiverse_service.dolt.branch_exists(result.universe.dolt_branch)

    def test_fork_records_event(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Event Test",
            fork_reason="Testing event",
        )

        assert result.fork_event is not None
        assert result.fork_event.event_type == EventType.FORK
        assert result.fork_event.payload["fork_reason"] == "Testing event"

    def test_fork_with_player_id(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()
        player_id = uuid4()

        result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Player Branch",
            fork_reason="Player choice",
            player_id=player_id,
        )

        assert result.success
        assert result.universe.owner_id == player_id
        assert f"user/{player_id}" in result.universe.dolt_branch

    def test_fork_nonexistent_parent_fails(self, multiverse_service: MultiverseService):
        result = multiverse_service.fork_universe(
            parent_universe_id=uuid4(),
            new_universe_name="Orphan",
            fork_reason="No parent",
        )

        assert not result.success
        assert "not found" in result.error

    def test_fork_archived_parent_fails(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        # Archive the prime (shouldn't normally do this, but for testing)
        prime.status = UniverseStatus.ARCHIVED
        multiverse_service.dolt.save_universe(prime)

        result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="From Archived",
            fork_reason="Testing",
        )

        assert not result.success
        assert "inactive" in result.error.lower()

    def test_nested_forks(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        # First fork
        result1 = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Fork 1",
            fork_reason="First fork",
        )
        assert result1.success

        # Need to switch to fork1's branch to save it properly
        # Then switch back to main to fork again from there
        multiverse_service.dolt.checkout_branch("main")
        multiverse_service.dolt.save_universe(result1.universe)

        # Second fork from first fork
        result2 = multiverse_service.fork_universe(
            parent_universe_id=result1.universe.id,
            new_universe_name="Fork 2",
            fork_reason="Second fork",
        )

        assert result2.success
        assert result2.universe.depth == 2
        assert result2.universe.parent_universe_id == result1.universe.id


class TestTravelBetweenWorlds:
    """Tests for cross-world travel."""

    def test_travel_copies_character(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        # Create character in prime
        hero = create_character(
            universe_id=prime.id,
            name="World Walker",
            hp_max=50,
        )
        multiverse_service.dolt.save_entity(hero)

        # Fork to create destination
        fork_result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Destination",
            fork_reason="Travel destination",
        )

        # Save destination universe to main branch for lookup
        multiverse_service.dolt.checkout_branch("main")
        multiverse_service.dolt.save_universe(fork_result.universe)

        # Travel to destination
        travel_result = multiverse_service.travel_between_worlds(
            traveler_id=hero.id,
            source_universe_id=prime.id,
            destination_universe_id=fork_result.universe.id,
        )

        assert travel_result.success
        assert travel_result.traveler_copy_id is not None
        assert travel_result.traveler_copy_id != hero.id  # Different ID

    def test_travel_creates_variant_node(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        hero = create_character(universe_id=prime.id, name="Traveler")
        multiverse_service.dolt.save_entity(hero)

        fork_result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Destination",
            fork_reason="Travel",
        )

        # Save destination universe to main branch for lookup
        multiverse_service.dolt.checkout_branch("main")
        multiverse_service.dolt.save_universe(fork_result.universe)

        travel_result = multiverse_service.travel_between_worlds(
            traveler_id=hero.id,
            source_universe_id=prime.id,
            destination_universe_id=fork_result.universe.id,
        )

        assert travel_result.success
        # Check variant was created
        has_variant = multiverse_service.neo4j.has_variant(hero.id, fork_result.universe.id)
        assert has_variant

    def test_travel_records_event(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        hero = create_character(universe_id=prime.id, name="Traveler")
        multiverse_service.dolt.save_entity(hero)

        fork_result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Destination",
            fork_reason="Travel",
        )

        # Save destination universe to main branch for lookup
        multiverse_service.dolt.checkout_branch("main")
        multiverse_service.dolt.save_universe(fork_result.universe)

        travel_result = multiverse_service.travel_between_worlds(
            traveler_id=hero.id,
            source_universe_id=prime.id,
            destination_universe_id=fork_result.universe.id,
            travel_method="portal",
        )

        assert travel_result.travel_event is not None
        assert travel_result.travel_event.event_type == EventType.TRAVEL
        assert travel_result.travel_event.payload["travel_method"] == "portal"

    def test_travel_nonexistent_source_fails(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        result = multiverse_service.travel_between_worlds(
            traveler_id=uuid4(),
            source_universe_id=uuid4(),
            destination_universe_id=prime.id,
        )

        assert not result.success
        assert "Source universe" in result.error

    def test_travel_nonexistent_destination_fails(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        hero = create_character(universe_id=prime.id, name="Traveler")
        multiverse_service.dolt.save_entity(hero)

        result = multiverse_service.travel_between_worlds(
            traveler_id=hero.id,
            source_universe_id=prime.id,
            destination_universe_id=uuid4(),
        )

        assert not result.success
        assert "Destination universe" in result.error

    def test_travel_nonexistent_traveler_fails(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        fork_result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Destination",
            fork_reason="Travel",
        )

        multiverse_service.dolt.checkout_branch("main")
        result = multiverse_service.travel_between_worlds(
            traveler_id=uuid4(),
            source_universe_id=prime.id,
            destination_universe_id=fork_result.universe.id,
        )

        assert not result.success
        assert "not found" in result.error


class TestArchiveUniverse:
    """Tests for archiving universes."""

    def test_archive_sets_status(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        fork_result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="To Archive",
            fork_reason="Testing archive",
        )

        success = multiverse_service.archive_universe(fork_result.universe.id)
        assert success

        # Check status was updated
        multiverse_service.dolt.checkout_branch(fork_result.universe.dolt_branch)
        archived = multiverse_service.dolt.get_universe(fork_result.universe.id)
        assert archived.status == UniverseStatus.ARCHIVED

    def test_cannot_archive_prime(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        success = multiverse_service.archive_universe(prime.id)
        assert not success

    def test_archive_nonexistent_fails(self, multiverse_service: MultiverseService):
        success = multiverse_service.archive_universe(uuid4())
        assert not success


class TestUniverseLineage:
    """Tests for universe lineage tracking."""

    def test_prime_has_single_element_lineage(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        lineage = multiverse_service.get_universe_lineage(prime.id)
        assert len(lineage) == 1
        assert lineage[0].id == prime.id

    def test_fork_lineage_includes_parent(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        fork_result = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Child",
            fork_reason="Testing lineage",
        )

        # Need to save fork universe to main branch for lineage lookup
        multiverse_service.dolt.checkout_branch("main")
        multiverse_service.dolt.save_universe(fork_result.universe)

        lineage = multiverse_service.get_universe_lineage(fork_result.universe.id)
        assert len(lineage) == 2
        assert lineage[0].id == prime.id  # Prime first
        assert lineage[1].id == fork_result.universe.id  # Child second

    def test_deep_lineage(self, multiverse_service: MultiverseService):
        prime = multiverse_service.initialize_prime_material()

        # Create chain of forks
        current_id = prime.id
        for i in range(3):
            result = multiverse_service.fork_universe(
                parent_universe_id=current_id,
                new_universe_name=f"Fork {i + 1}",
                fork_reason=f"Depth {i + 1}",
            )
            # Save to main for lineage lookup
            multiverse_service.dolt.checkout_branch("main")
            multiverse_service.dolt.save_universe(result.universe)
            current_id = result.universe.id

        lineage = multiverse_service.get_universe_lineage(current_id)
        assert len(lineage) == 4  # Prime + 3 forks
        assert lineage[0].is_prime_material()
        assert lineage[-1].depth == 3


class TestMergeProposals:
    """Tests for the merge/PR system (Phase 5)."""

    def test_propose_merge_creates_proposal(self, multiverse_service: MultiverseService):
        """Creating a merge proposal should store it."""
        prime = multiverse_service.initialize_prime_material()

        # Create a fork with some content
        fork = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Player Branch",
            fork_reason="Adding new content",
        )
        multiverse_service.dolt.checkout_branch("main")
        multiverse_service.dolt.save_universe(fork.universe)

        # Create an NPC in the fork
        npc = create_character(universe_id=fork.universe.id, name="Cool NPC")
        multiverse_service.dolt.checkout_branch(fork.universe.dolt_branch)
        multiverse_service.dolt.save_entity(npc)

        # Propose merging the NPC to prime
        proposal = multiverse_service.propose_merge(
            source_universe_id=fork.universe.id,
            target_universe_id=prime.id,
            entity_ids=[npc.id],
            title="Add Cool NPC",
            description="This NPC adds great value to the world",
            submitter_id=uuid4(),
        )

        assert proposal is not None
        assert proposal.status == MergeProposalStatus.PENDING
        assert proposal.validation_passed
        assert len(proposal.conflicts) == 0

    def test_propose_merge_detects_missing_source(self, multiverse_service: MultiverseService):
        """Proposal should fail if source universe doesn't exist."""
        prime = multiverse_service.initialize_prime_material()

        proposal = multiverse_service.propose_merge(
            source_universe_id=uuid4(),  # Non-existent
            target_universe_id=prime.id,
            entity_ids=[uuid4()],
            title="Bad Proposal",
            description="This should fail",
        )

        assert proposal.status == MergeProposalStatus.CONFLICT
        assert not proposal.validation_passed
        assert len(proposal.conflicts) > 0

    def test_propose_merge_detects_missing_entity(self, multiverse_service: MultiverseService):
        """Proposal should detect missing entities in source."""
        prime = multiverse_service.initialize_prime_material()

        fork = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Empty Fork",
            fork_reason="Testing",
        )
        multiverse_service.dolt.checkout_branch("main")
        multiverse_service.dolt.save_universe(fork.universe)

        # Propose merging a non-existent entity
        proposal = multiverse_service.propose_merge(
            source_universe_id=fork.universe.id,
            target_universe_id=prime.id,
            entity_ids=[uuid4()],  # Doesn't exist
            title="Missing Entity",
            description="This should have conflicts",
        )

        assert proposal.status == MergeProposalStatus.CONFLICT
        assert "not found in source universe" in proposal.conflicts[0]

    def test_review_proposal_approves(self, multiverse_service: MultiverseService):
        """Reviewing and approving a valid proposal should work."""
        prime = multiverse_service.initialize_prime_material()

        fork = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Player Branch",
            fork_reason="Adding content",
        )
        multiverse_service.dolt.checkout_branch("main")
        multiverse_service.dolt.save_universe(fork.universe)

        location = create_location(universe_id=fork.universe.id, name="New Tavern")
        multiverse_service.dolt.checkout_branch(fork.universe.dolt_branch)
        multiverse_service.dolt.save_entity(location)

        proposal = multiverse_service.propose_merge(
            source_universe_id=fork.universe.id,
            target_universe_id=prime.id,
            entity_ids=[location.id],
            title="Add Tavern",
            description="Great location",
        )

        reviewer_id = uuid4()
        reviewed = multiverse_service.review_proposal(
            proposal_id=proposal.id,
            approved=True,
            reviewer_id=reviewer_id,
            review_notes="Looks good!",
        )

        assert reviewed is not None
        assert reviewed.status == MergeProposalStatus.APPROVED
        assert reviewed.reviewer_id == reviewer_id
        assert reviewed.review_notes == "Looks good!"
        assert reviewed.reviewed_at is not None

    def test_review_proposal_rejects(self, multiverse_service: MultiverseService):
        """Rejecting a proposal should set status to rejected."""
        prime = multiverse_service.initialize_prime_material()

        fork = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Player Branch",
            fork_reason="Testing",
        )
        multiverse_service.dolt.checkout_branch("main")
        multiverse_service.dolt.save_universe(fork.universe)

        npc = create_character(universe_id=fork.universe.id, name="Bad NPC")
        multiverse_service.dolt.checkout_branch(fork.universe.dolt_branch)
        multiverse_service.dolt.save_entity(npc)

        proposal = multiverse_service.propose_merge(
            source_universe_id=fork.universe.id,
            target_universe_id=prime.id,
            entity_ids=[npc.id],
            title="Bad Content",
            description="Not good",
        )

        reviewed = multiverse_service.review_proposal(
            proposal_id=proposal.id,
            approved=False,
            reviewer_id=uuid4(),
            review_notes="Does not fit the world",
        )

        assert reviewed.status == MergeProposalStatus.REJECTED

    def test_execute_merge_copies_entities(self, multiverse_service: MultiverseService):
        """Executing a merge should copy entities to target."""
        prime = multiverse_service.initialize_prime_material()

        fork = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Player Branch",
            fork_reason="Adding content",
        )
        multiverse_service.dolt.checkout_branch("main")
        multiverse_service.dolt.save_universe(fork.universe)

        # Create content in fork
        npc = create_character(universe_id=fork.universe.id, name="Merged NPC")
        multiverse_service.dolt.checkout_branch(fork.universe.dolt_branch)
        multiverse_service.dolt.save_entity(npc)

        # Propose and approve
        proposal = multiverse_service.propose_merge(
            source_universe_id=fork.universe.id,
            target_universe_id=prime.id,
            entity_ids=[npc.id],
            title="Add NPC",
            description="Great NPC",
        )

        multiverse_service.review_proposal(
            proposal_id=proposal.id,
            approved=True,
            reviewer_id=uuid4(),
        )

        # Execute the merge
        result = multiverse_service.execute_merge(proposal.id)

        assert result.success
        assert result.entities_merged == 1
        assert "Merged NPC" in result.narrative

        # Verify the proposal is now merged
        updated = multiverse_service.get_proposal(proposal.id)
        assert updated.status == MergeProposalStatus.MERGED
        assert updated.merged_at is not None

    def test_execute_merge_not_approved_fails(self, multiverse_service: MultiverseService):
        """Cannot execute a merge that isn't approved."""
        prime = multiverse_service.initialize_prime_material()

        fork = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Player Branch",
            fork_reason="Testing",
        )
        multiverse_service.dolt.checkout_branch("main")
        multiverse_service.dolt.save_universe(fork.universe)

        npc = create_character(universe_id=fork.universe.id, name="Test NPC")
        multiverse_service.dolt.checkout_branch(fork.universe.dolt_branch)
        multiverse_service.dolt.save_entity(npc)

        proposal = multiverse_service.propose_merge(
            source_universe_id=fork.universe.id,
            target_universe_id=prime.id,
            entity_ids=[npc.id],
            title="Not Approved",
            description="Testing",
        )

        # Try to execute without approval
        result = multiverse_service.execute_merge(proposal.id)

        assert not result.success
        assert "not approved" in result.error

    def test_execute_merge_success_outcome_when_all_entities_merge(
        self, multiverse_service: MultiverseService
    ):
        """Merge event outcome should be SUCCESS when all entities merge successfully."""
        from src.models import EventOutcome

        prime = multiverse_service.initialize_prime_material()

        fork = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Player Branch",
            fork_reason="Testing outcome",
        )
        multiverse_service.dolt.checkout_branch("main")
        multiverse_service.dolt.save_universe(fork.universe)

        # Create entities in fork
        npc = create_character(universe_id=fork.universe.id, name="Test NPC")
        multiverse_service.dolt.checkout_branch(fork.universe.dolt_branch)
        multiverse_service.dolt.save_entity(npc)

        # Create and approve proposal
        proposal = multiverse_service.propose_merge(
            source_universe_id=fork.universe.id,
            target_universe_id=prime.id,
            entity_ids=[npc.id],
            title="Test Merge",
            description="Testing SUCCESS outcome",
        )

        multiverse_service.review_proposal(
            proposal_id=proposal.id,
            approved=True,
            reviewer_id=uuid4(),
        )

        # Execute the merge
        result = multiverse_service.execute_merge(proposal.id)

        assert result.success
        assert result.entities_merged == 1
        assert result.entities_skipped == 0

        # Check the merge event has SUCCESS outcome since all entities merged
        events = multiverse_service.dolt.get_events(prime.id)
        merge_events = [e for e in events if e.event_type == EventType.MERGE]
        assert len(merge_events) == 1
        merge_event = merge_events[0]
        assert merge_event.outcome == EventOutcome.SUCCESS
        assert merge_event.payload["entities_merged"] == 1
        assert merge_event.payload["entities_skipped"] == 0

    def test_get_pending_proposals(self, multiverse_service: MultiverseService):
        """Should return all pending proposals."""
        prime = multiverse_service.initialize_prime_material()

        fork = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Player Branch",
            fork_reason="Testing",
        )
        multiverse_service.dolt.checkout_branch("main")
        multiverse_service.dolt.save_universe(fork.universe)

        # Create two proposals
        npc1 = create_character(universe_id=fork.universe.id, name="NPC 1")
        npc2 = create_character(universe_id=fork.universe.id, name="NPC 2")
        multiverse_service.dolt.checkout_branch(fork.universe.dolt_branch)
        multiverse_service.dolt.save_entity(npc1)
        multiverse_service.dolt.save_entity(npc2)

        multiverse_service.propose_merge(
            source_universe_id=fork.universe.id,
            target_universe_id=prime.id,
            entity_ids=[npc1.id],
            title="Proposal 1",
            description="First",
        )

        multiverse_service.propose_merge(
            source_universe_id=fork.universe.id,
            target_universe_id=prime.id,
            entity_ids=[npc2.id],
            title="Proposal 2",
            description="Second",
        )

        pending = multiverse_service.get_pending_proposals()
        assert len(pending) == 2

        # Filter by target
        pending_prime = multiverse_service.get_pending_proposals(target_universe_id=prime.id)
        assert len(pending_prime) == 2

    def test_full_merge_workflow(self, multiverse_service: MultiverseService):
        """Test complete workflow: create, review, merge."""
        # Setup prime material
        prime = multiverse_service.initialize_prime_material()

        # Player forks and creates content
        fork = multiverse_service.fork_universe(
            parent_universe_id=prime.id,
            new_universe_name="Player Campaign",
            fork_reason="Personal adventure",
            player_id=uuid4(),
        )
        multiverse_service.dolt.checkout_branch("main")
        multiverse_service.dolt.save_universe(fork.universe)

        # Player creates a cool location
        tavern = create_location(
            universe_id=fork.universe.id,
            name="The Rusty Dragon Inn",
        )
        multiverse_service.dolt.checkout_branch(fork.universe.dolt_branch)
        multiverse_service.dolt.save_entity(tavern)

        # Player submits for canon
        proposal = multiverse_service.propose_merge(
            source_universe_id=fork.universe.id,
            target_universe_id=prime.id,
            entity_ids=[tavern.id],
            title="Add The Rusty Dragon Inn",
            description="A beloved tavern that should be in the main world",
            submitter_id=uuid4(),
        )
        assert proposal.validation_passed

        # Admin reviews and approves
        multiverse_service.review_proposal(
            proposal_id=proposal.id,
            approved=True,
            reviewer_id=uuid4(),
            review_notes="Great addition to the world!",
        )

        # Execute the merge
        result = multiverse_service.execute_merge(proposal.id)

        assert result.success
        assert result.entities_merged == 1
        assert "Rusty Dragon" in result.narrative

        # Verify it's no longer pending
        pending = multiverse_service.get_pending_proposals()
        assert len(pending) == 0
