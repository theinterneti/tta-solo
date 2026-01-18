"""
Quest models for TTA-Solo.

Defines the data structures for procedural quests including
objectives, rewards, and quest state tracking.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class QuestStatus(str, Enum):
    """Status of a quest in the player's journal."""

    AVAILABLE = "available"  # Can be discovered/accepted
    ACTIVE = "active"  # Player has accepted and is working on it
    COMPLETED = "completed"  # Successfully finished
    FAILED = "failed"  # Cannot be completed (e.g., NPC died)
    ABANDONED = "abandoned"  # Player gave up


class QuestType(str, Enum):
    """Types of quests that can be generated."""

    FETCH = "fetch"  # Retrieve an item from somewhere
    ESCORT = "escort"  # Protect an NPC to a destination
    HUNT = "hunt"  # Defeat specific enemies
    INVESTIGATE = "investigate"  # Discover information
    DELIVER = "deliver"  # Bring an item to an NPC
    EXPLORE = "explore"  # Reach a location
    TALK = "talk"  # Have a conversation with an NPC


class ObjectiveType(str, Enum):
    """Types of quest objectives."""

    REACH_LOCATION = "reach_location"  # Go to a specific place
    DEFEAT_ENEMY = "defeat_enemy"  # Kill/defeat an entity
    COLLECT_ITEM = "collect_item"  # Pick up an item
    DELIVER_ITEM = "deliver_item"  # Give item to NPC
    TALK_TO_NPC = "talk_to_npc"  # Have conversation
    ESCORT_NPC = "escort_npc"  # Protect NPC to location
    DISCOVER_SECRET = "discover_secret"  # Find hidden information
    SURVIVE = "survive"  # Stay alive for duration/event


class QuestObjective(BaseModel):
    """
    A single objective within a quest.

    Quests can have multiple objectives that must be completed
    in sequence or in parallel.
    """

    id: UUID = Field(default_factory=uuid4)
    description: str
    """Human-readable description: "Retrieve the ancient tome" """

    objective_type: ObjectiveType
    """What kind of action is required."""

    # Target references (at least one should be set)
    target_entity_id: UUID | None = None
    """Entity to interact with (NPC, item, enemy)."""

    target_location_id: UUID | None = None
    """Location to reach or search."""

    target_entity_name: str | None = None
    """Name of target for display purposes."""

    # Progress tracking
    quantity_required: int = 1
    """For objectives like "defeat 3 goblins"."""

    quantity_current: int = 0
    """Current progress toward quantity_required."""

    is_complete: bool = False
    """Whether this objective has been satisfied."""

    is_optional: bool = False
    """Optional objectives give bonus rewards."""

    is_hidden: bool = False
    """Hidden until discovered (e.g., secret objectives)."""

    @property
    def progress_percent(self) -> float:
        """Progress as a percentage (0.0 to 1.0)."""
        if self.quantity_required == 0:
            return 1.0 if self.is_complete else 0.0
        return min(1.0, self.quantity_current / self.quantity_required)

    def check_completion(self) -> bool:
        """Check if objective is complete based on progress."""
        if self.quantity_current >= self.quantity_required:
            self.is_complete = True
        return self.is_complete

    def increment_progress(self, amount: int = 1) -> bool:
        """
        Increment progress and check completion.

        Returns True if objective was just completed.
        """
        was_complete = self.is_complete
        self.quantity_current = min(
            self.quantity_current + amount,
            self.quantity_required,
        )
        self.check_completion()
        return self.is_complete and not was_complete


class QuestReward(BaseModel):
    """Rewards granted upon quest completion."""

    gold: int = 0
    """Gold pieces awarded."""

    experience: int = 0
    """Experience points awarded."""

    item_ids: list[UUID] = Field(default_factory=list)
    """Item entity IDs to give to player."""

    reputation_changes: dict[UUID, int] = Field(default_factory=dict)
    """NPC ID -> reputation change amount."""

    unlocks_location_id: UUID | None = None
    """Location that becomes accessible."""

    unlocks_quest_id: UUID | None = None
    """Follow-up quest that becomes available."""

    special_reward: str | None = None
    """Description of any special/unique reward."""


class Quest(BaseModel):
    """
    A quest that can be discovered, accepted, and completed.

    Quests are procedurally generated based on context and
    provide objectives and rewards for the player.
    """

    id: UUID = Field(default_factory=uuid4)
    universe_id: UUID
    """Universe this quest belongs to."""

    name: str
    """Display name: "The Lost Heirloom" """

    description: str
    """Full description of the quest and its stakes."""

    quest_type: QuestType
    """Category of quest for generation/tracking."""

    status: QuestStatus = QuestStatus.AVAILABLE

    # Quest giver
    giver_id: UUID | None = None
    """NPC who gave this quest (None for self-discovered)."""

    giver_name: str | None = None
    """Display name of quest giver."""

    # Location context
    origin_location_id: UUID | None = None
    """Where the quest was discovered/given."""

    # Objectives
    objectives: Annotated[list[QuestObjective], Field(min_length=1)]
    """List of objectives (at least one required)."""

    current_objective_index: int = 0
    """Index of the active objective (for sequential quests)."""

    is_sequential: bool = True
    """If True, objectives must be completed in order."""

    # Rewards
    rewards: QuestReward = Field(default_factory=QuestReward)

    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    accepted_at: datetime | None = None
    expires_at: datetime | None = None
    completed_at: datetime | None = None

    # Quest chain support
    parent_quest_id: UUID | None = None
    """If this is a sub-quest, the parent quest ID."""

    chain_position: int = 0
    """Position in quest chain (0 = standalone or first)."""

    # Difficulty
    difficulty: Annotated[int, Field(ge=1, le=5)] = 1
    """1 = trivial, 5 = epic."""

    # Tags for filtering/generation
    tags: list[str] = Field(default_factory=list)

    @property
    def current_objective(self) -> QuestObjective | None:
        """Get the current active objective."""
        if 0 <= self.current_objective_index < len(self.objectives):
            return self.objectives[self.current_objective_index]
        return None

    @property
    def is_complete(self) -> bool:
        """Check if all required objectives are complete."""
        required = [o for o in self.objectives if not o.is_optional]
        return all(o.is_complete for o in required)

    @property
    def progress_percent(self) -> float:
        """Overall quest progress as percentage."""
        required = [o for o in self.objectives if not o.is_optional]
        if not required:
            return 1.0 if self.status == QuestStatus.COMPLETED else 0.0
        completed = sum(1 for o in required if o.is_complete)
        return completed / len(required)

    def accept(self) -> None:
        """Mark quest as accepted by player."""
        if self.status == QuestStatus.AVAILABLE:
            self.status = QuestStatus.ACTIVE
            self.accepted_at = datetime.utcnow()

    def complete(self) -> None:
        """Mark quest as completed."""
        if self.status == QuestStatus.ACTIVE and self.is_complete:
            self.status = QuestStatus.COMPLETED
            self.completed_at = datetime.utcnow()

    def fail(self) -> None:
        """Mark quest as failed."""
        if self.status in (QuestStatus.AVAILABLE, QuestStatus.ACTIVE):
            self.status = QuestStatus.FAILED

    def abandon(self) -> None:
        """Mark quest as abandoned by player."""
        if self.status == QuestStatus.ACTIVE:
            self.status = QuestStatus.ABANDONED

    def advance_objective(self) -> QuestObjective | None:
        """
        Move to the next objective if current is complete.

        Returns the new current objective, or None if quest is done.
        """
        if not self.is_sequential:
            return self.current_objective

        current = self.current_objective
        if current and current.is_complete:
            self.current_objective_index += 1
            return self.current_objective

        return current

    def get_incomplete_objectives(self) -> list[QuestObjective]:
        """Get all objectives that aren't complete yet."""
        return [o for o in self.objectives if not o.is_complete]


# =============================================================================
# Quest Templates for Generation
# =============================================================================


class QuestTemplate(BaseModel):
    """
    Template for procedurally generating quests.

    Templates define patterns that are filled with context-specific
    entities to create unique quests.
    """

    quest_type: QuestType
    name_patterns: list[str]
    """Patterns like "The Lost {item}" or "{npc}'s Request" """

    description_patterns: list[str]
    """Full description patterns with placeholders."""

    objective_templates: list[dict]
    """Templates for generating objectives."""

    reward_gold_range: tuple[int, int] = (10, 100)
    """Min/max gold reward."""

    reward_xp_range: tuple[int, int] = (10, 50)
    """Min/max experience reward."""

    suitable_location_types: list[str] = Field(default_factory=list)
    """Location types where this quest makes sense."""

    min_danger_level: int = 0
    max_danger_level: int = 20

    difficulty_range: tuple[int, int] = (1, 3)
    """Min/max difficulty for this template."""

    tags: list[str] = Field(default_factory=list)
    """Tags for categorization."""


# =============================================================================
# Factory Functions
# =============================================================================


def create_quest(
    universe_id: UUID,
    name: str,
    description: str,
    quest_type: QuestType,
    objectives: list[QuestObjective],
    *,
    giver_id: UUID | None = None,
    giver_name: str | None = None,
    rewards: QuestReward | None = None,
    difficulty: int = 1,
    tags: list[str] | None = None,
    is_sequential: bool = True,
) -> Quest:
    """
    Factory function to create a quest with validated data.

    Args:
        universe_id: Universe this quest belongs to
        name: Display name for the quest
        description: Full quest description
        quest_type: Category of quest
        objectives: List of objectives (at least one required)
        giver_id: NPC who gave the quest
        giver_name: Display name of quest giver
        rewards: Rewards for completion
        difficulty: 1-5 difficulty rating
        tags: Optional tags for categorization
        is_sequential: If True, objectives must be completed in order

    Returns:
        A new Quest instance
    """
    return Quest(
        universe_id=universe_id,
        name=name,
        description=description,
        quest_type=quest_type,
        objectives=objectives,
        giver_id=giver_id,
        giver_name=giver_name,
        rewards=rewards or QuestReward(),
        difficulty=difficulty,
        tags=tags or [],
        is_sequential=is_sequential,
    )


def create_objective(
    description: str,
    objective_type: ObjectiveType,
    *,
    target_entity_id: UUID | None = None,
    target_location_id: UUID | None = None,
    target_entity_name: str | None = None,
    quantity: int = 1,
    is_optional: bool = False,
    is_hidden: bool = False,
) -> QuestObjective:
    """
    Factory function to create a quest objective.

    Args:
        description: Human-readable objective description
        objective_type: What kind of action is required
        target_entity_id: Entity to interact with
        target_location_id: Location to reach
        target_entity_name: Name of target for display
        quantity: Required quantity (for defeat X enemies)
        is_optional: Whether this is an optional bonus objective
        is_hidden: Whether objective is hidden until discovered

    Returns:
        A new QuestObjective instance
    """
    return QuestObjective(
        description=description,
        objective_type=objective_type,
        target_entity_id=target_entity_id,
        target_location_id=target_location_id,
        target_entity_name=target_entity_name,
        quantity_required=quantity,
        is_optional=is_optional,
        is_hidden=is_hidden,
    )
