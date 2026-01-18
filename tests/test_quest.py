"""
Tests for the quest system.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.models.entity import create_character, create_location
from src.models.quest import (
    ObjectiveType,
    QuestReward,
    QuestStatus,
    QuestType,
    create_objective,
    create_quest,
)
from src.models.relationships import Relationship, RelationshipType
from src.services.quest import QuestContext, QuestService


@pytest.fixture
def universe_id():
    """A universe ID for testing."""
    return uuid4()


@pytest.fixture
def dolt():
    """In-memory Dolt repository."""
    return InMemoryDoltRepository()


@pytest.fixture
def neo4j():
    """In-memory Neo4j repository."""
    return InMemoryNeo4jRepository()


@pytest.fixture
def quest_service(dolt, neo4j):
    """Quest service for testing."""
    return QuestService(dolt=dolt, neo4j=neo4j)


# =============================================================================
# Quest Model Tests
# =============================================================================


class TestQuestObjective:
    """Tests for QuestObjective model."""

    def test_create_objective(self):
        """create_objective creates an objective with correct defaults."""
        obj = create_objective(
            description="Defeat the dragon",
            objective_type=ObjectiveType.DEFEAT_ENEMY,
            quantity=1,
        )

        assert obj.description == "Defeat the dragon"
        assert obj.objective_type == ObjectiveType.DEFEAT_ENEMY
        assert obj.quantity_required == 1
        assert obj.quantity_current == 0
        assert obj.is_complete is False

    def test_progress_percent_with_quantity(self):
        """progress_percent calculates correctly for multi-quantity objectives."""
        obj = create_objective(
            description="Defeat 5 goblins",
            objective_type=ObjectiveType.DEFEAT_ENEMY,
            quantity=5,
        )

        assert obj.progress_percent == 0.0
        obj.quantity_current = 2
        assert obj.progress_percent == 0.4
        obj.quantity_current = 5
        assert obj.progress_percent == 1.0

    def test_increment_progress(self):
        """increment_progress updates current and checks completion."""
        obj = create_objective(
            description="Defeat 3 enemies",
            objective_type=ObjectiveType.DEFEAT_ENEMY,
            quantity=3,
        )

        # First increment - not complete
        result = obj.increment_progress(1)
        assert result is False
        assert obj.quantity_current == 1
        assert obj.is_complete is False

        # Second increment - still not complete
        result = obj.increment_progress(1)
        assert result is False
        assert obj.quantity_current == 2

        # Third increment - now complete
        result = obj.increment_progress(1)
        assert result is True  # Just completed
        assert obj.quantity_current == 3
        assert obj.is_complete is True

    def test_increment_progress_caps_at_required(self):
        """increment_progress doesn't exceed required quantity."""
        obj = create_objective(
            description="Defeat 2 enemies",
            objective_type=ObjectiveType.DEFEAT_ENEMY,
            quantity=2,
        )

        obj.increment_progress(10)  # Overshoot
        assert obj.quantity_current == 2
        assert obj.is_complete is True


class TestQuest:
    """Tests for Quest model."""

    def test_create_quest(self, universe_id):
        """create_quest creates a quest with correct defaults."""
        objectives = [
            create_objective("Go to the cave", ObjectiveType.REACH_LOCATION),
            create_objective("Defeat the boss", ObjectiveType.DEFEAT_ENEMY),
        ]

        quest = create_quest(
            universe_id=universe_id,
            name="The Hero's Journey",
            description="A classic quest",
            quest_type=QuestType.HUNT,
            objectives=objectives,
        )

        assert quest.name == "The Hero's Journey"
        assert quest.quest_type == QuestType.HUNT
        assert quest.status == QuestStatus.AVAILABLE
        assert len(quest.objectives) == 2

    def test_quest_accept(self, universe_id):
        """accept() changes status to ACTIVE."""
        quest = create_quest(
            universe_id=universe_id,
            name="Test Quest",
            description="Testing",
            quest_type=QuestType.FETCH,
            objectives=[create_objective("Get item", ObjectiveType.COLLECT_ITEM)],
        )

        assert quest.status == QuestStatus.AVAILABLE
        assert quest.accepted_at is None

        quest.accept()

        assert quest.status == QuestStatus.ACTIVE
        assert quest.accepted_at is not None

    def test_quest_complete(self, universe_id):
        """complete() changes status when all objectives done."""
        obj = create_objective("Talk to NPC", ObjectiveType.TALK_TO_NPC)
        obj.is_complete = True

        quest = create_quest(
            universe_id=universe_id,
            name="Test Quest",
            description="Testing",
            quest_type=QuestType.TALK,
            objectives=[obj],
        )
        quest.accept()

        assert quest.is_complete is True
        quest.complete()

        assert quest.status == QuestStatus.COMPLETED
        assert quest.completed_at is not None

    def test_quest_fail(self, universe_id):
        """fail() changes status to FAILED."""
        quest = create_quest(
            universe_id=universe_id,
            name="Test Quest",
            description="Testing",
            quest_type=QuestType.ESCORT,
            objectives=[create_objective("Escort NPC", ObjectiveType.ESCORT_NPC)],
        )
        quest.accept()

        quest.fail()
        assert quest.status == QuestStatus.FAILED

    def test_quest_abandon(self, universe_id):
        """abandon() changes status to ABANDONED."""
        quest = create_quest(
            universe_id=universe_id,
            name="Test Quest",
            description="Testing",
            quest_type=QuestType.FETCH,
            objectives=[create_objective("Get item", ObjectiveType.COLLECT_ITEM)],
        )
        quest.accept()

        quest.abandon()
        assert quest.status == QuestStatus.ABANDONED

    def test_quest_progress_percent(self, universe_id):
        """progress_percent calculates based on completed objectives."""
        objectives = [
            create_objective("Obj 1", ObjectiveType.REACH_LOCATION),
            create_objective("Obj 2", ObjectiveType.TALK_TO_NPC),
            create_objective("Obj 3 (optional)", ObjectiveType.COLLECT_ITEM, is_optional=True),
        ]

        quest = create_quest(
            universe_id=universe_id,
            name="Test Quest",
            description="Testing",
            quest_type=QuestType.INVESTIGATE,
            objectives=objectives,
        )

        assert quest.progress_percent == 0.0  # 0/2 required complete

        objectives[0].is_complete = True
        assert quest.progress_percent == 0.5  # 1/2 required complete

        objectives[1].is_complete = True
        assert quest.progress_percent == 1.0  # 2/2 required complete

    def test_quest_advance_objective(self, universe_id):
        """advance_objective moves to next objective when current is complete."""
        objectives = [
            create_objective("Step 1", ObjectiveType.REACH_LOCATION),
            create_objective("Step 2", ObjectiveType.TALK_TO_NPC),
        ]

        quest = create_quest(
            universe_id=universe_id,
            name="Sequential Quest",
            description="Testing",
            quest_type=QuestType.INVESTIGATE,
            objectives=objectives,
            is_sequential=True,
        )

        assert quest.current_objective_index == 0
        assert quest.current_objective == objectives[0]

        # Complete first objective
        objectives[0].is_complete = True
        next_obj = quest.advance_objective()

        assert quest.current_objective_index == 1
        assert next_obj == objectives[1]


# =============================================================================
# Quest Service Tests
# =============================================================================


class TestQuestService:
    """Tests for QuestService."""

    @pytest.mark.asyncio
    async def test_generate_quest_for_tavern(self, quest_service, universe_id, dolt, neo4j):
        """generate_quest creates appropriate quest for tavern location."""
        # Create a tavern location
        location_id = uuid4()
        location = create_location(
            universe_id=universe_id,
            name="The Rusty Tankard",
            description="A cozy tavern",
            location_type="tavern",
            danger_level=2,
        )
        location.id = location_id
        dolt.save_entity(location)

        # Create an NPC at the tavern
        npc_id = uuid4()
        npc = create_character(
            universe_id=universe_id,
            name="Bartender Bob",
            description="A friendly bartender",
        )
        npc.id = npc_id
        dolt.save_entity(npc)

        # Create relationship
        rel = Relationship(
            universe_id=universe_id,
            from_entity_id=npc_id,
            to_entity_id=location_id,
            relationship_type=RelationshipType.LOCATED_IN,
        )
        neo4j.create_relationship(rel)

        # Build context and generate
        context = quest_service.build_quest_context(
            universe_id=universe_id,
            location_id=location_id,
        )

        result = await quest_service.generate_quest(context)

        assert result.success is True
        assert result.quest is not None
        assert result.quest.status == QuestStatus.AVAILABLE
        assert len(result.quest.objectives) >= 1

    @pytest.mark.asyncio
    async def test_generate_quest_for_dungeon(self, quest_service, universe_id, dolt, neo4j):
        """generate_quest creates appropriate quest for dungeon location."""
        # Create a dungeon location
        location_id = uuid4()
        location = create_location(
            universe_id=universe_id,
            name="Dark Crypt",
            description="A dangerous crypt",
            location_type="dungeon",
            danger_level=15,
        )
        location.id = location_id
        dolt.save_entity(location)

        context = quest_service.build_quest_context(
            universe_id=universe_id,
            location_id=location_id,
        )

        result = await quest_service.generate_quest(context)

        assert result.success is True
        assert result.quest is not None
        # Higher danger should give higher rewards
        assert result.quest.rewards.gold > 0 or result.quest.rewards.experience > 0

    @pytest.mark.asyncio
    async def test_generate_specific_quest_type(self, quest_service, universe_id, dolt):
        """generate_quest can create specific quest types."""
        location_id = uuid4()
        location = create_location(
            universe_id=universe_id,
            name="Forest Path",
            description="A forest trail",
            location_type="forest",
            danger_level=8,
        )
        location.id = location_id
        dolt.save_entity(location)

        context = QuestContext(
            universe_id=universe_id,
            location_id=location_id,
            location_type="forest",
            location_name="Forest Path",
            danger_level=8,
        )

        result = await quest_service.generate_quest(context, quest_type=QuestType.HUNT)

        assert result.success is True
        assert result.quest is not None
        assert result.quest.quest_type == QuestType.HUNT

    def test_accept_quest(self, quest_service, universe_id, dolt):
        """accept_quest marks quest as active."""
        # Create and save a quest
        quest = create_quest(
            universe_id=universe_id,
            name="Test Quest",
            description="Testing",
            quest_type=QuestType.FETCH,
            objectives=[create_objective("Get item", ObjectiveType.COLLECT_ITEM)],
        )
        dolt.save_quest(quest)

        assert quest_service.accept_quest(quest.id) is True

        # Verify status changed
        loaded = quest_service.get_quest(quest.id)
        assert loaded is not None
        assert loaded.status == QuestStatus.ACTIVE

    def test_update_objective_progress(self, quest_service, universe_id, dolt):
        """update_objective_progress updates matching objectives."""
        quest = create_quest(
            universe_id=universe_id,
            name="Hunt Quest",
            description="Kill enemies",
            quest_type=QuestType.HUNT,
            objectives=[
                create_objective(
                    "Defeat 3 enemies",
                    ObjectiveType.DEFEAT_ENEMY,
                    quantity=3,
                )
            ],
        )
        quest.accept()
        dolt.save_quest(quest)

        # Update progress
        result = quest_service.update_objective_progress(
            quest_id=quest.id,
            objective_type=ObjectiveType.DEFEAT_ENEMY,
            amount=1,
        )

        assert result.objective_updated is True
        assert result.objective_completed is False

        # Check persisted
        loaded = quest_service.get_quest(quest.id)
        assert loaded.objectives[0].quantity_current == 1

    def test_update_objective_progress_completes_quest(self, quest_service, universe_id, dolt):
        """update_objective_progress can complete quest."""
        quest = create_quest(
            universe_id=universe_id,
            name="Simple Quest",
            description="Talk to someone",
            quest_type=QuestType.TALK,
            objectives=[
                create_objective(
                    "Talk to the merchant",
                    ObjectiveType.TALK_TO_NPC,
                    quantity=1,
                )
            ],
            rewards=QuestReward(gold=50, experience=25),
        )
        quest.accept()
        dolt.save_quest(quest)

        result = quest_service.update_objective_progress(
            quest_id=quest.id,
            objective_type=ObjectiveType.TALK_TO_NPC,
            amount=1,
        )

        assert result.objective_updated is True
        assert result.objective_completed is True
        assert result.quest_completed is True
        assert result.rewards_granted is not None
        assert result.rewards_granted.gold == 50

    def test_check_location_objectives(self, quest_service, universe_id, dolt):
        """check_location_objectives finds matching quests."""
        location_id = uuid4()

        quest = create_quest(
            universe_id=universe_id,
            name="Explore Quest",
            description="Reach the location",
            quest_type=QuestType.EXPLORE,
            objectives=[
                create_objective(
                    "Reach the cave",
                    ObjectiveType.REACH_LOCATION,
                    target_location_id=location_id,
                )
            ],
        )
        quest.accept()
        dolt.save_quest(quest)

        results = quest_service.check_location_objectives(universe_id, location_id)

        assert len(results) == 1
        assert results[0].objective_completed is True
        assert results[0].quest_completed is True

    def test_check_defeat_objectives(self, quest_service, universe_id, dolt):
        """check_defeat_objectives finds matching quests."""
        quest = create_quest(
            universe_id=universe_id,
            name="Hunt Quest",
            description="Kill enemies",
            quest_type=QuestType.HUNT,
            objectives=[
                create_objective(
                    "Defeat 2 enemies",
                    ObjectiveType.DEFEAT_ENEMY,
                    quantity=2,
                )
            ],
        )
        quest.accept()
        dolt.save_quest(quest)

        # First kill
        results = quest_service.check_defeat_objectives(universe_id)
        assert len(results) == 1
        assert results[0].objective_completed is False

        # Second kill
        results = quest_service.check_defeat_objectives(universe_id)
        assert len(results) == 1
        assert results[0].objective_completed is True
        assert results[0].quest_completed is True

    def test_check_dialogue_objectives(self, quest_service, universe_id, dolt):
        """check_dialogue_objectives finds matching quests."""
        npc_id = uuid4()

        quest = create_quest(
            universe_id=universe_id,
            name="Talk Quest",
            description="Talk to the NPC",
            quest_type=QuestType.TALK,
            objectives=[
                create_objective(
                    "Talk to the merchant",
                    ObjectiveType.TALK_TO_NPC,
                    target_entity_id=npc_id,
                )
            ],
        )
        quest.accept()
        dolt.save_quest(quest)

        results = quest_service.check_dialogue_objectives(universe_id, npc_id)

        assert len(results) == 1
        assert results[0].objective_completed is True

    def test_fail_quest(self, quest_service, universe_id, dolt):
        """fail_quest marks quest as failed."""
        quest = create_quest(
            universe_id=universe_id,
            name="Test Quest",
            description="Testing",
            quest_type=QuestType.ESCORT,
            objectives=[create_objective("Escort", ObjectiveType.ESCORT_NPC)],
        )
        quest.accept()
        dolt.save_quest(quest)

        assert quest_service.fail_quest(quest.id, "NPC died") is True

        loaded = quest_service.get_quest(quest.id)
        assert loaded.status == QuestStatus.FAILED

    def test_abandon_quest(self, quest_service, universe_id, dolt):
        """abandon_quest marks quest as abandoned."""
        quest = create_quest(
            universe_id=universe_id,
            name="Test Quest",
            description="Testing",
            quest_type=QuestType.FETCH,
            objectives=[create_objective("Get item", ObjectiveType.COLLECT_ITEM)],
        )
        quest.accept()
        dolt.save_quest(quest)

        assert quest_service.abandon_quest(quest.id) is True

        loaded = quest_service.get_quest(quest.id)
        assert loaded.status == QuestStatus.ABANDONED

    def test_get_active_quests(self, quest_service, universe_id, dolt):
        """get_active_quests returns only active quests."""
        # Create quests with different statuses
        quest1 = create_quest(
            universe_id=universe_id,
            name="Active Quest",
            description="Testing",
            quest_type=QuestType.FETCH,
            objectives=[create_objective("Get item", ObjectiveType.COLLECT_ITEM)],
        )
        quest1.accept()
        dolt.save_quest(quest1)

        quest2 = create_quest(
            universe_id=universe_id,
            name="Available Quest",
            description="Testing",
            quest_type=QuestType.TALK,
            objectives=[create_objective("Talk", ObjectiveType.TALK_TO_NPC)],
        )
        dolt.save_quest(quest2)

        active = quest_service.get_active_quests(universe_id)

        assert len(active) == 1
        assert active[0].name == "Active Quest"

    def test_get_available_quests(self, quest_service, universe_id, dolt):
        """get_available_quests returns only available quests."""
        quest1 = create_quest(
            universe_id=universe_id,
            name="Active Quest",
            description="Testing",
            quest_type=QuestType.FETCH,
            objectives=[create_objective("Get item", ObjectiveType.COLLECT_ITEM)],
        )
        quest1.accept()
        dolt.save_quest(quest1)

        quest2 = create_quest(
            universe_id=universe_id,
            name="Available Quest",
            description="Testing",
            quest_type=QuestType.TALK,
            objectives=[create_objective("Talk", ObjectiveType.TALK_TO_NPC)],
        )
        dolt.save_quest(quest2)

        available = quest_service.get_available_quests(universe_id)

        assert len(available) == 1
        assert available[0].name == "Available Quest"

    def test_build_quest_context(self, quest_service, universe_id, dolt, neo4j):
        """build_quest_context gathers relevant context."""
        # Create location
        location_id = uuid4()
        location = create_location(
            universe_id=universe_id,
            name="Market Square",
            description="A busy market",
            location_type="market",
            danger_level=3,
        )
        location.id = location_id
        dolt.save_entity(location)

        # Create NPC at location
        npc_id = uuid4()
        npc = create_character(
            universe_id=universe_id,
            name="Merchant Mary",
            description="A merchant",
        )
        npc.id = npc_id
        dolt.save_entity(npc)

        rel = Relationship(
            universe_id=universe_id,
            from_entity_id=npc_id,
            to_entity_id=location_id,
            relationship_type=RelationshipType.LOCATED_IN,
        )
        neo4j.create_relationship(rel)

        # Create connected location
        other_location_id = uuid4()
        other_location = create_location(
            universe_id=universe_id,
            name="Dark Alley",
            description="A shadowy alley",
            location_type="alley",
        )
        other_location.id = other_location_id
        dolt.save_entity(other_location)

        conn_rel = Relationship(
            universe_id=universe_id,
            from_entity_id=location_id,
            to_entity_id=other_location_id,
            relationship_type=RelationshipType.CONNECTED_TO,
        )
        neo4j.create_relationship(conn_rel)

        # Build context
        context = quest_service.build_quest_context(
            universe_id=universe_id,
            location_id=location_id,
        )

        assert context.location_type == "market"
        assert context.location_name == "Market Square"
        assert context.danger_level == 3
        assert len(context.npcs_present) == 1
        assert context.npcs_present[0].name == "Merchant Mary"
        assert len(context.connected_locations) == 1
