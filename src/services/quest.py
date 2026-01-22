"""
Quest Generation Service for TTA-Solo.

Generates procedural quests based on context (location, NPCs, danger level)
using templates and optional LLM enhancement.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, Field

from src.db.interfaces import DoltRepository, Neo4jRepository
from src.models.entity import Entity, EntityType
from src.models.quest import (
    ObjectiveType,
    Quest,
    QuestObjective,
    QuestReward,
    QuestStatus,
    QuestType,
    create_objective,
    create_quest,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.services.llm import LLMService


# =============================================================================
# Constants
# =============================================================================

# Danger level system
MAX_DANGER_LEVEL = 20
DANGER_TO_DIFFICULTY_DIVISOR = 4  # Converts danger (0-20) to difficulty (1-5)

# Enemy quantity ranges for hunt quests
MIN_ENEMY_QUANTITY = 2
MAX_ENEMY_QUANTITY = 5


# =============================================================================
# Result Models
# =============================================================================


class QuestGenerationResult(BaseModel):
    """Result of generating a quest."""

    success: bool
    quest: Quest | None = None
    error: str | None = None
    used_fallback: bool = False  # True if LLM failed and template used


class QuestProgressResult(BaseModel):
    """Result of updating quest progress."""

    quest_id: UUID
    objective_updated: bool = False
    objective_completed: bool = False
    quest_completed: bool = False
    rewards_granted: QuestReward | None = None
    narrative: str = ""


# =============================================================================
# Quest Templates by Type and Context
# =============================================================================


@dataclass
class QuestTemplateData:
    """Template data for procedural quest generation."""

    quest_type: QuestType
    name_patterns: list[str]
    description_patterns: list[str]
    objective_patterns: list[tuple[ObjectiveType, str]]
    reward_gold_range: tuple[int, int] = (10, 100)
    reward_xp_range: tuple[int, int] = (10, 50)
    difficulty_range: tuple[int, int] = (1, 3)
    tags: list[str] = field(default_factory=list)


# Templates organized by location type and quest type
_QUEST_TEMPLATES: dict[str, list[QuestTemplateData]] = {
    "tavern": [
        QuestTemplateData(
            quest_type=QuestType.DELIVER,
            name_patterns=[
                "A Message for {npc}",
                "{npc}'s Request",
                "The Urgent Delivery",
            ],
            description_patterns=[
                "{giver} needs a message delivered to {npc} as soon as possible. They seem nervous about something.",
                "A sealed letter must reach {npc}. {giver} will pay well for discretion.",
            ],
            objective_patterns=[
                (ObjectiveType.COLLECT_ITEM, "Receive the sealed letter from {giver}"),
                (ObjectiveType.REACH_LOCATION, "Travel to {location}"),
                (ObjectiveType.DELIVER_ITEM, "Deliver the letter to {npc}"),
            ],
            reward_gold_range=(15, 40),
            tags=["social", "delivery"],
        ),
        QuestTemplateData(
            quest_type=QuestType.INVESTIGATE,
            name_patterns=[
                "The Hooded Stranger",
                "Whispers in the Tavern",
                "A Suspicious Character",
            ],
            description_patterns=[
                "A mysterious figure has been asking questions around the tavern. {giver} wants to know who they are and what they want.",
                "Strange rumors are circulating. {giver} asks you to find the source.",
            ],
            objective_patterns=[
                (ObjectiveType.TALK_TO_NPC, "Question the locals about the stranger"),
                (ObjectiveType.DISCOVER_SECRET, "Uncover the stranger's purpose"),
            ],
            reward_gold_range=(20, 50),
            reward_xp_range=(15, 40),
            tags=["mystery", "social"],
        ),
        QuestTemplateData(
            quest_type=QuestType.ESCORT,
            name_patterns=[
                "Safe Passage",
                "Escort to {location}",
                "A Dangerous Journey",
            ],
            description_patterns=[
                "{giver} needs to reach {location} safely but fears the roads. Will you accompany them?",
                "Travel has become dangerous. {giver} needs an escort to {location}.",
            ],
            objective_patterns=[
                (ObjectiveType.ESCORT_NPC, "Escort {giver} to {location}"),
                (ObjectiveType.SURVIVE, "Ensure {giver} arrives safely"),
            ],
            reward_gold_range=(30, 60),
            tags=["escort", "travel"],
        ),
    ],
    "market": [
        QuestTemplateData(
            quest_type=QuestType.FETCH,
            name_patterns=[
                "The Missing Shipment",
                "Rare Goods",
                "{npc}'s Special Order",
            ],
            description_patterns=[
                "A valuable shipment never arrived. {giver} suspects foul play and needs someone to track it down.",
                "{giver} is looking for a rare {item}. They'll pay handsomely if you can find one.",
            ],
            objective_patterns=[
                (ObjectiveType.COLLECT_ITEM, "Find the missing {item}"),
                (ObjectiveType.DELIVER_ITEM, "Return the {item} to {giver}"),
            ],
            reward_gold_range=(25, 75),
            tags=["fetch", "merchant"],
        ),
        QuestTemplateData(
            quest_type=QuestType.DELIVER,
            name_patterns=[
                "Rush Order",
                "Time-Sensitive Delivery",
                "The Impatient Customer",
            ],
            description_patterns=[
                "{giver} has a customer waiting for an important delivery. Time is of the essence.",
                "A package must reach {npc} before sundown. {giver} is counting on you.",
            ],
            objective_patterns=[
                (ObjectiveType.COLLECT_ITEM, "Collect the package from {giver}"),
                (ObjectiveType.DELIVER_ITEM, "Deliver to {npc} quickly"),
            ],
            reward_gold_range=(20, 45),
            tags=["delivery", "urgent"],
        ),
    ],
    "dungeon": [
        QuestTemplateData(
            quest_type=QuestType.FETCH,
            name_patterns=[
                "The Lost Heirloom",
                "Treasure of the Depths",
                "Recovery Mission",
            ],
            description_patterns=[
                "{giver} lost something precious in these depths. They need it back but dare not venture further themselves.",
                "An ancient {item} is said to lie within. {giver} will reward whoever retrieves it.",
            ],
            objective_patterns=[
                (ObjectiveType.REACH_LOCATION, "Delve deeper into the dungeon"),
                (ObjectiveType.COLLECT_ITEM, "Find the {item}"),
                (ObjectiveType.REACH_LOCATION, "Return to safety"),
            ],
            reward_gold_range=(40, 100),
            reward_xp_range=(25, 60),
            difficulty_range=(2, 4),
            tags=["dungeon", "treasure"],
        ),
        QuestTemplateData(
            quest_type=QuestType.HUNT,
            name_patterns=[
                "Pest Control",
                "Clear the Depths",
                "Monster Bounty",
            ],
            description_patterns=[
                "Dangerous creatures have made their lair here. {giver} offers a bounty for clearing them out.",
                "The dungeon is overrun. Eliminate the threat and claim your reward.",
            ],
            objective_patterns=[
                (ObjectiveType.DEFEAT_ENEMY, "Defeat {quantity} enemies"),
            ],
            reward_gold_range=(30, 80),
            reward_xp_range=(30, 70),
            difficulty_range=(2, 4),
            tags=["combat", "bounty"],
        ),
        QuestTemplateData(
            quest_type=QuestType.INVESTIGATE,
            name_patterns=[
                "The Missing Expedition",
                "What Lies Beneath",
                "Secrets of the Ancients",
            ],
            description_patterns=[
                "An expedition vanished in these halls. {giver} wants to know their fate.",
                "Ancient secrets are hidden here. {giver} seeks knowledge of the past.",
            ],
            objective_patterns=[
                (ObjectiveType.REACH_LOCATION, "Explore the dungeon depths"),
                (ObjectiveType.DISCOVER_SECRET, "Find evidence of what happened"),
            ],
            reward_gold_range=(35, 70),
            reward_xp_range=(30, 60),
            difficulty_range=(2, 5),
            tags=["mystery", "exploration"],
        ),
    ],
    "forest": [
        QuestTemplateData(
            quest_type=QuestType.HUNT,
            name_patterns=[
                "The Beast of {location}",
                "Hunting Party",
                "Predator Problem",
            ],
            description_patterns=[
                "A dangerous creature has been terrorizing travelers. {giver} wants it dealt with.",
                "Wildlife has become aggressive. Track down the source of the problem.",
            ],
            objective_patterns=[
                (ObjectiveType.REACH_LOCATION, "Track the creature to its lair"),
                (ObjectiveType.DEFEAT_ENEMY, "Defeat the creature"),
            ],
            reward_gold_range=(25, 60),
            reward_xp_range=(20, 50),
            difficulty_range=(2, 3),
            tags=["hunt", "wilderness"],
        ),
        QuestTemplateData(
            quest_type=QuestType.EXPLORE,
            name_patterns=[
                "The Hidden Grove",
                "Lost Paths",
                "Mapping the Wilderness",
            ],
            description_patterns=[
                "{giver} has heard rumors of a hidden place in the forest. Find it and report back.",
                "The forest holds secrets. {giver} wants you to explore and document what you find.",
            ],
            objective_patterns=[
                (ObjectiveType.REACH_LOCATION, "Explore the forest"),
                (ObjectiveType.DISCOVER_SECRET, "Find the hidden location"),
            ],
            reward_gold_range=(15, 40),
            reward_xp_range=(25, 55),
            tags=["exploration", "wilderness"],
        ),
        QuestTemplateData(
            quest_type=QuestType.FETCH,
            name_patterns=[
                "Rare Herbs",
                "Forest Bounty",
                "The Herbalist's Request",
            ],
            description_patterns=[
                "{giver} needs rare herbs that only grow deep in the forest. Be careful of the dangers within.",
                "Medicinal plants are needed urgently. {giver} will pay well for them.",
            ],
            objective_patterns=[
                (ObjectiveType.COLLECT_ITEM, "Gather the required herbs"),
                (ObjectiveType.REACH_LOCATION, "Return to {giver}"),
            ],
            reward_gold_range=(20, 45),
            tags=["gathering", "wilderness"],
        ),
    ],
    "crypt": [
        QuestTemplateData(
            quest_type=QuestType.HUNT,
            name_patterns=[
                "Restless Dead",
                "The Haunting",
                "Unholy Ground",
            ],
            description_patterns=[
                "The dead do not rest here. {giver} begs you to put them to peace.",
                "Unnatural creatures stir in the crypt. They must be destroyed.",
            ],
            objective_patterns=[
                (ObjectiveType.DEFEAT_ENEMY, "Destroy {quantity} undead"),
                (ObjectiveType.DISCOVER_SECRET, "Find the source of the curse"),
            ],
            reward_gold_range=(35, 80),
            reward_xp_range=(30, 70),
            difficulty_range=(3, 5),
            tags=["undead", "combat"],
        ),
        QuestTemplateData(
            quest_type=QuestType.INVESTIGATE,
            name_patterns=[
                "The Sealed Tomb",
                "Family Secrets",
                "The Inheritance",
            ],
            description_patterns=[
                "{giver}'s ancestor was buried with something important. They need someone brave enough to retrieve it.",
                "Ancient tombs hold forgotten knowledge. {giver} seeks answers about the past.",
            ],
            objective_patterns=[
                (ObjectiveType.REACH_LOCATION, "Find the tomb"),
                (ObjectiveType.COLLECT_ITEM, "Retrieve {item}"),
                (ObjectiveType.SURVIVE, "Escape the crypt"),
            ],
            reward_gold_range=(40, 90),
            reward_xp_range=(25, 60),
            difficulty_range=(3, 5),
            tags=["tomb", "treasure"],
        ),
    ],
}

# Default templates for unknown location types
_DEFAULT_TEMPLATES: list[QuestTemplateData] = [
    QuestTemplateData(
        quest_type=QuestType.TALK,
        name_patterns=[
            "A Simple Request",
            "Information Needed",
            "The Messenger",
        ],
        description_patterns=[
            "{giver} needs someone to speak with {npc} about an important matter.",
            "A message needs to be delivered. {giver} is counting on you.",
        ],
        objective_patterns=[
            (ObjectiveType.TALK_TO_NPC, "Speak with {npc}"),
        ],
        reward_gold_range=(10, 30),
        tags=["simple", "social"],
    ),
    QuestTemplateData(
        quest_type=QuestType.FETCH,
        name_patterns=[
            "Lost and Found",
            "The Missing Item",
            "A Simple Errand",
        ],
        description_patterns=[
            "{giver} has lost something important. Can you help find it?",
            "Something valuable has gone missing. {giver} needs it back.",
        ],
        objective_patterns=[
            (ObjectiveType.COLLECT_ITEM, "Find the lost {item}"),
            (ObjectiveType.DELIVER_ITEM, "Return to {giver}"),
        ],
        reward_gold_range=(15, 35),
        tags=["fetch", "simple"],
    ),
]


# =============================================================================
# Quest Generation Context
# =============================================================================


class QuestContext(BaseModel):
    """Context for generating a quest."""

    universe_id: UUID
    location_id: UUID
    location_type: str = "unknown"
    location_name: str = "Unknown Location"
    danger_level: int = 5

    # Available entities to reference
    npcs_present: list[Entity] = Field(default_factory=list)
    items_available: list[Entity] = Field(default_factory=list)
    connected_locations: list[Entity] = Field(default_factory=list)

    # Quest giver (if triggered by NPC)
    giver_id: UUID | None = None
    giver_name: str | None = None

    # Player info for scaling
    player_level: int = 1

    model_config = {"arbitrary_types_allowed": True}


# =============================================================================
# Quest Service
# =============================================================================


@dataclass
class QuestService:
    """
    Service for quest generation and tracking.

    Uses template-based generation with optional LLM enhancement
    for richer descriptions.
    """

    dolt: DoltRepository
    neo4j: Neo4jRepository
    llm: LLMService | None = field(default=None)

    def set_llm_service(self, llm: LLMService) -> None:
        """Set the LLM service for enhanced generation."""
        self.llm = llm

    async def generate_quest(
        self,
        context: QuestContext,
        quest_type: QuestType | None = None,
    ) -> QuestGenerationResult:
        """
        Generate a contextually appropriate quest.

        Args:
            context: Information about current game state
            quest_type: Optional specific quest type to generate

        Returns:
            Generated quest or error
        """
        try:
            # Select appropriate template
            template = self._select_template(context, quest_type)

            # Fill template with context
            quest = self._fill_template(template, context)

            # Try LLM enhancement
            if self.llm is not None:
                try:
                    enhanced = await self._enhance_with_llm(quest, context)
                    if enhanced:
                        quest = enhanced
                except Exception as e:
                    logger.warning(f"LLM enhancement failed, using template: {e}")

            # Persist the quest
            self._persist_quest(quest)

            return QuestGenerationResult(
                success=True,
                quest=quest,
                used_fallback=self.llm is None,
            )

        except Exception as e:
            logger.error(f"Quest generation failed: {e}")
            return QuestGenerationResult(
                success=False,
                error=str(e),
            )

    def _select_template(
        self,
        context: QuestContext,
        quest_type: QuestType | None = None,
    ) -> QuestTemplateData:
        """Select an appropriate template based on context."""
        # Get templates for this location type
        templates = _QUEST_TEMPLATES.get(context.location_type, _DEFAULT_TEMPLATES)

        # Filter by quest type if specified
        if quest_type:
            typed_templates = [t for t in templates if t.quest_type == quest_type]
            if typed_templates:
                templates = typed_templates

        # Filter by difficulty based on danger level
        suitable = []
        for t in templates:
            min_diff, max_diff = t.difficulty_range
            # Map danger level (0-20) to difficulty (1-5)
            expected_diff = max(1, min(5, context.danger_level // DANGER_TO_DIFFICULTY_DIVISOR + 1))
            if min_diff <= expected_diff <= max_diff:
                suitable.append(t)

        if not suitable:
            suitable = templates  # Fallback to all if none match

        return random.choice(suitable)

    def _fill_template(
        self,
        template: QuestTemplateData,
        context: QuestContext,
    ) -> Quest:
        """Fill a template with context data to create a quest."""
        # Prepare substitution data
        subs: dict[str, str] = {
            "location": context.location_name,
        }

        # Quest giver
        if context.giver_name:
            subs["giver"] = context.giver_name
        elif context.npcs_present:
            giver = random.choice(context.npcs_present)
            subs["giver"] = giver.name
            context.giver_id = giver.id
            context.giver_name = giver.name
        else:
            subs["giver"] = "a local"

        # Target NPC (different from giver)
        available_npcs = [n for n in context.npcs_present if n.id != context.giver_id]
        if available_npcs:
            target_npc = random.choice(available_npcs)
            subs["npc"] = target_npc.name
        else:
            subs["npc"] = "someone"

        # Item
        if context.items_available:
            item = random.choice(context.items_available)
            subs["item"] = item.name
        else:
            subs["item"] = "the object"

        # Enemy quantity
        subs["quantity"] = str(random.randint(MIN_ENEMY_QUANTITY, MAX_ENEMY_QUANTITY))

        # Generate name and description
        name_pattern = random.choice(template.name_patterns)
        desc_pattern = random.choice(template.description_patterns)

        name = self._substitute(name_pattern, subs)
        description = self._substitute(desc_pattern, subs)

        # Generate objectives
        objectives: list[QuestObjective] = []
        for obj_type, obj_pattern in template.objective_patterns:
            obj_desc = self._substitute(obj_pattern, subs)

            # Find target entity for objective
            target_entity_id: UUID | None = None
            target_location_id: UUID | None = None
            target_name: str | None = None
            quantity = 1

            if obj_type == ObjectiveType.TALK_TO_NPC or obj_type == ObjectiveType.DELIVER_ITEM:
                if available_npcs:
                    target = random.choice(available_npcs)
                    target_entity_id = target.id
                    target_name = target.name
            elif obj_type == ObjectiveType.DEFEAT_ENEMY:
                quantity = int(subs.get("quantity", "3"))
            elif obj_type == ObjectiveType.REACH_LOCATION and context.connected_locations:
                target = random.choice(context.connected_locations)
                target_location_id = target.id
                target_name = target.name

            objectives.append(
                create_objective(
                    description=obj_desc,
                    objective_type=obj_type,
                    target_entity_id=target_entity_id,
                    target_location_id=target_location_id,
                    target_entity_name=target_name,
                    quantity=quantity,
                )
            )

        # Calculate rewards
        min_gold, max_gold = template.reward_gold_range
        min_xp, max_xp = template.reward_xp_range

        # Scale by difficulty/danger
        difficulty_mult = 1.0 + (context.danger_level / MAX_DANGER_LEVEL)
        gold = int(random.randint(min_gold, max_gold) * difficulty_mult)
        xp = int(random.randint(min_xp, max_xp) * difficulty_mult)

        rewards = QuestReward(
            gold=gold,
            experience=xp,
        )

        # Calculate difficulty
        min_diff, max_diff = template.difficulty_range
        difficulty = min(5, max(1, context.danger_level // DANGER_TO_DIFFICULTY_DIVISOR + 1))
        difficulty = max(min_diff, min(max_diff, difficulty))

        return create_quest(
            universe_id=context.universe_id,
            name=name,
            description=description,
            quest_type=template.quest_type,
            objectives=objectives,
            giver_id=context.giver_id,
            giver_name=context.giver_name,
            rewards=rewards,
            difficulty=difficulty,
            tags=template.tags.copy(),
        )

    def _substitute(self, pattern: str, subs: dict[str, str]) -> str:
        """Substitute placeholders in a pattern."""
        result = pattern
        for key, value in subs.items():
            result = result.replace(f"{{{key}}}", value)
        return result

    async def _enhance_with_llm(
        self,
        quest: Quest,
        context: QuestContext,
    ) -> Quest | None:
        """
        Use LLM to enhance quest description.

        Returns enhanced quest or None if enhancement fails.
        """
        if self.llm is None or not self.llm.is_available:
            return None

        # Build prompt
        system_prompt = (
            "You are a fantasy RPG quest writer. Enhance quest descriptions to be "
            "more evocative and engaging while keeping the same core objectives."
        )
        user_prompt = f"""Enhance this quest description for a fantasy RPG. Keep the same structure but make it more evocative and engaging.

Quest Name: {quest.name}
Quest Type: {quest.quest_type.value}
Location: {context.location_name} (danger level {context.danger_level}/20)
Quest Giver: {quest.giver_name or "Unknown"}

Current Description:
{quest.description}

Objectives:
"""
        for i, obj in enumerate(quest.objectives, 1):
            user_prompt += f"{i}. {obj.description}\n"

        user_prompt += """
Write an enhanced description (2-3 sentences) that:
- Maintains the same core quest
- Adds sensory details or emotional hooks
- Fits the fantasy setting

Return ONLY the enhanced description text, nothing else."""

        try:
            response = await self.llm.provider.complete(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=200,
            )
            if response and len(response) > 20:
                quest.description = response.strip()
                return quest
        except Exception as e:
            logger.warning(f"LLM enhancement failed: {e}")

        return None

    def _persist_quest(self, quest: Quest) -> None:
        """Save quest to the database."""
        self.dolt.save_quest(quest)

    def get_quest(self, quest_id: UUID) -> Quest | None:
        """Retrieve a quest by ID."""
        return self.dolt.get_quest(quest_id)

    def get_active_quests(self, universe_id: UUID) -> list[Quest]:
        """Get all active quests in a universe."""
        return self.dolt.get_quests_by_status(universe_id, QuestStatus.ACTIVE)

    def get_available_quests(self, universe_id: UUID) -> list[Quest]:
        """Get all available (not yet accepted) quests."""
        return self.dolt.get_quests_by_status(universe_id, QuestStatus.AVAILABLE)

    def accept_quest(self, quest_id: UUID) -> bool:
        """Mark a quest as accepted by the player."""
        quest = self.get_quest(quest_id)
        if quest and quest.status == QuestStatus.AVAILABLE:
            quest.accept()
            self.dolt.save_quest(quest)
            return True
        return False

    def update_objective_progress(
        self,
        quest_id: UUID,
        objective_type: ObjectiveType,
        target_id: UUID | None = None,
        amount: int = 1,
    ) -> QuestProgressResult:
        """
        Update progress on quest objectives.

        Called when player completes relevant actions
        (defeats enemy, reaches location, etc.)
        """
        quest = self.get_quest(quest_id)
        if not quest or quest.status != QuestStatus.ACTIVE:
            return QuestProgressResult(
                quest_id=quest_id,
                narrative="Quest not found or not active.",
            )

        objective_updated = False
        objective_completed = False
        narrative_parts: list[str] = []

        # Check each objective
        for obj in quest.objectives:
            if obj.is_complete:
                continue

            # Match by type and optionally by target
            if obj.objective_type != objective_type:
                continue

            # If a target is specified, check if it matches
            if target_id:
                entity_matches = obj.target_entity_id == target_id
                location_matches = obj.target_location_id == target_id
                # Skip if objective has entity target that doesn't match and no location match
                if (
                    obj.target_entity_id
                    and not entity_matches
                    and (not obj.target_location_id or not location_matches)
                ):
                    continue

            # Update progress
            was_just_completed = obj.increment_progress(amount)
            objective_updated = True

            if was_just_completed:
                objective_completed = True
                narrative_parts.append(f"Objective completed: {obj.description}")

                # Advance to next objective if sequential
                if quest.is_sequential:
                    next_obj = quest.advance_objective()
                    if next_obj:
                        narrative_parts.append(f"New objective: {next_obj.description}")

        # Check if quest is complete
        quest_completed = False
        rewards_granted: QuestReward | None = None

        if quest.is_complete:
            quest.complete()
            quest_completed = True
            rewards_granted = quest.rewards
            narrative_parts.append(f"Quest completed: {quest.name}!")
            if rewards_granted.gold > 0:
                narrative_parts.append(f"Received {rewards_granted.gold} gold.")
            if rewards_granted.experience > 0:
                narrative_parts.append(f"Gained {rewards_granted.experience} XP.")

        # Persist changes
        if objective_updated:
            self.dolt.save_quest(quest)

        return QuestProgressResult(
            quest_id=quest_id,
            objective_updated=objective_updated,
            objective_completed=objective_completed,
            quest_completed=quest_completed,
            rewards_granted=rewards_granted,
            narrative=" ".join(narrative_parts),
        )

    def check_location_objectives(
        self,
        universe_id: UUID,
        location_id: UUID,
    ) -> list[QuestProgressResult]:
        """
        Check if reaching a location completes any objectives.

        Called when player enters a new location.
        """
        results: list[QuestProgressResult] = []
        active_quests = self.get_active_quests(universe_id)

        for quest in active_quests:
            result = self.update_objective_progress(
                quest_id=quest.id,
                objective_type=ObjectiveType.REACH_LOCATION,
                target_id=location_id,
            )
            if result.objective_updated:
                results.append(result)

        return results

    def check_defeat_objectives(
        self,
        universe_id: UUID,
        enemy_id: UUID | None = None,
    ) -> list[QuestProgressResult]:
        """
        Check if defeating an enemy completes any objectives.

        Called when player defeats an enemy.
        """
        results: list[QuestProgressResult] = []
        active_quests = self.get_active_quests(universe_id)

        for quest in active_quests:
            result = self.update_objective_progress(
                quest_id=quest.id,
                objective_type=ObjectiveType.DEFEAT_ENEMY,
                target_id=enemy_id,
            )
            if result.objective_updated:
                results.append(result)

        return results

    def check_dialogue_objectives(
        self,
        universe_id: UUID,
        npc_id: UUID,
    ) -> list[QuestProgressResult]:
        """
        Check if talking to an NPC completes any objectives.

        Called when player has dialogue with an NPC.
        """
        results: list[QuestProgressResult] = []
        active_quests = self.get_active_quests(universe_id)

        for quest in active_quests:
            result = self.update_objective_progress(
                quest_id=quest.id,
                objective_type=ObjectiveType.TALK_TO_NPC,
                target_id=npc_id,
            )
            if result.objective_updated:
                results.append(result)

        return results

    def fail_quest(self, quest_id: UUID, reason: str = "") -> bool:
        """Mark a quest as failed."""
        quest = self.get_quest(quest_id)
        if quest and quest.status in (QuestStatus.AVAILABLE, QuestStatus.ACTIVE):
            quest.fail()
            self.dolt.save_quest(quest)
            logger.info(f"Quest {quest.name} failed: {reason}")
            return True
        return False

    def abandon_quest(self, quest_id: UUID) -> bool:
        """Mark a quest as abandoned by the player."""
        quest = self.get_quest(quest_id)
        if quest and quest.status == QuestStatus.ACTIVE:
            quest.abandon()
            self.dolt.save_quest(quest)
            return True
        return False

    def build_quest_context(
        self,
        universe_id: UUID,
        location_id: UUID,
        giver_id: UUID | None = None,
    ) -> QuestContext:
        """
        Build a QuestContext from current game state.

        Gathers relevant entities and location info for quest generation.
        """
        # Get location info
        location = self.dolt.get_entity(location_id, universe_id)
        location_type = "unknown"
        location_name = "Unknown"
        danger_level = 5

        if location:
            location_name = location.name
            if location.location_properties:
                location_type = location.location_properties.location_type
                danger_level = location.location_properties.danger_level

        # Get NPCs at location
        npcs_present: list[Entity] = []
        npc_rels = self.neo4j.get_relationships(
            location_id,
            universe_id,
            relationship_type="LOCATED_IN",
        )
        for rel in npc_rels:
            entity = self.dolt.get_entity(rel.from_entity_id, universe_id)
            if entity and entity.type == EntityType.CHARACTER:
                npcs_present.append(entity)

        # Get connected locations
        connected_locations: list[Entity] = []
        conn_rels = self.neo4j.get_relationships(
            location_id,
            universe_id,
            relationship_type="CONNECTED_TO",
        )
        for rel in conn_rels:
            entity = self.dolt.get_entity(rel.to_entity_id, universe_id)
            if entity and entity.type == EntityType.LOCATION:
                connected_locations.append(entity)

        # Get giver name if provided
        giver_name: str | None = None
        if giver_id:
            giver = self.dolt.get_entity(giver_id, universe_id)
            if giver:
                giver_name = giver.name

        return QuestContext(
            universe_id=universe_id,
            location_id=location_id,
            location_type=location_type,
            location_name=location_name,
            danger_level=danger_level,
            npcs_present=npcs_present,
            connected_locations=connected_locations,
            giver_id=giver_id,
            giver_name=giver_name,
        )
