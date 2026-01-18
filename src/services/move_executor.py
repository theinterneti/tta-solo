"""
Move Executor for TTA-Solo.

Executes PbtA GM moves, transforming them from narrative-only text
into generative actions that create entities and modify world state.

This is the bridge between move selection (pbta.py) and world generation.
"""

from __future__ import annotations

import json
import logging
import random
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.db.interfaces import DoltRepository, Neo4jRepository
from src.engine.pbta import GMMove, GMMoveType
from src.models.entity import create_character, create_item, create_location
from src.models.npc import Motivation, create_npc_profile
from src.models.relationships import Relationship, RelationshipType

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.engine.models import Context, Session
    from src.services.llm import LLMService
    from src.services.npc import NPCService
    from src.services.quest import QuestService


# =============================================================================
# Result Models
# =============================================================================


class MoveExecutionResult(BaseModel):
    """Result of executing a GM move."""

    success: bool
    narrative: str  # Generated or template narrative

    # Entities created/modified
    entities_created: list[UUID] = Field(default_factory=list)
    entities_modified: list[UUID] = Field(default_factory=list)
    relationships_created: list[UUID] = Field(default_factory=list)

    # State changes for display
    state_changes: list[str] = Field(default_factory=list)

    # Error tracking
    error: str | None = None
    used_fallback: bool = False  # True if LLM failed and template used


class NPCGenerationParams(BaseModel):
    """Parameters for generating a new NPC."""

    name: str
    description: str
    role: str  # merchant, guard, traveler, etc.

    # Personality traits (0-100)
    openness: int = 50
    conscientiousness: int = 50
    extraversion: int = 50
    agreeableness: int = 50
    neuroticism: int = 50

    motivations: list[Motivation] = Field(default_factory=list)
    speech_style: str = "neutral"
    quirks: list[str] = Field(default_factory=list)

    # Combat stats
    hp_max: int = 10
    ac: int = 10

    # Initial disposition
    initial_attitude: str = "neutral"  # friendly, neutral, hostile


class EnvironmentFeatureParams(BaseModel):
    """Parameters for generating an environment feature."""

    name: str
    description: str
    feature_type: str = "discovery"  # passage, hazard, discovery, hideout, obstacle
    is_dangerous: bool = False
    interaction_hint: str | None = None


# =============================================================================
# Constants
# =============================================================================

# Probability of generating a quest when OFFER_OPPORTUNITY is triggered
_QUEST_OPPORTUNITY_CHANCE = 0.4


# =============================================================================
# NPC Templates by Location Type
# =============================================================================


@dataclass
class NPCTemplate:
    """Template for generating NPCs by location type."""

    names: list[str]
    roles: list[str]
    descriptions: list[str]
    trait_ranges: dict[str, tuple[int, int]] = field(default_factory=dict)
    speech_styles: list[str] = field(default_factory=lambda: ["neutral"])
    motivations: list[Motivation] = field(default_factory=list)


_NPC_TEMPLATES: dict[str, list[NPCTemplate]] = {
    "tavern": [
        NPCTemplate(
            names=["Greta", "Old Tom", "Bron", "Mira the Red", "Stumpy Pete"],
            roles=["barkeeper", "patron", "bard", "gambler", "server"],
            descriptions=[
                "a weathered face that's seen too many bar fights",
                "nursing a drink and watching the door nervously",
                "humming a tune while polishing a mug",
                "shuffling a worn deck of cards",
            ],
            trait_ranges={
                "extraversion": (50, 85),
                "agreeableness": (40, 75),
                "neuroticism": (20, 50),
            },
            speech_styles=["warm", "gruff", "chatty", "suspicious"],
            motivations=[Motivation.WEALTH, Motivation.SAFETY, Motivation.BELONGING],
        ),
    ],
    "dungeon": [
        NPCTemplate(
            names=["The Prisoner", "Whisper", "Lost One", "Broken Guard", "The Survivor"],
            roles=["prisoner", "survivor", "lost_soul", "former_guard"],
            descriptions=[
                "shackled to the wall, eyes hollow with despair",
                "huddled in a corner, barely alive",
                "muttering to themselves in the darkness",
                "wounded and delirious, armor rusted",
            ],
            trait_ranges={
                "neuroticism": (65, 95),
                "extraversion": (10, 35),
                "agreeableness": (30, 70),
            },
            speech_styles=["fearful", "desperate", "resigned", "paranoid"],
            motivations=[Motivation.SURVIVAL, Motivation.SAFETY],
        ),
    ],
    "market": [
        NPCTemplate(
            names=["Merchant Finn", "Silverhand", "Madame Vera", "Quick Nick", "Honest Hal"],
            roles=["merchant", "pickpocket", "fortune_teller", "hawker", "fence"],
            descriptions=[
                "gesturing enthusiastically at their wares",
                "eyes darting through the crowd",
                "draped in colorful scarves and jingling jewelry",
                "calling out prices in a practiced sing-song",
            ],
            trait_ranges={
                "extraversion": (65, 95),
                "conscientiousness": (25, 70),
                "agreeableness": (20, 60),
            },
            speech_styles=["persuasive", "shifty", "mysterious", "boisterous"],
            motivations=[Motivation.WEALTH, Motivation.FAME, Motivation.SURVIVAL],
        ),
    ],
    "forest": [
        NPCTemplate(
            names=["The Hermit", "Ranger Thorne", "Wild Child", "The Wanderer"],
            roles=["hermit", "ranger", "druid", "traveler"],
            descriptions=[
                "dressed in furs and leaves, eyes sharp as a hawk",
                "moving silently despite their gear",
                "covered in mud but seemingly at peace",
                "carrying a staff carved with strange symbols",
            ],
            trait_ranges={
                "openness": (60, 90),
                "extraversion": (15, 45),
                "neuroticism": (20, 50),
            },
            speech_styles=["cryptic", "terse", "gentle", "wary"],
            motivations=[Motivation.KNOWLEDGE, Motivation.SAFETY, Motivation.DUTY],
        ),
    ],
    "castle": [
        NPCTemplate(
            names=["Sir Aldric", "Lady Maren", "Steward Bern", "Guard Captain Vex"],
            roles=["knight", "noble", "servant", "guard"],
            descriptions=[
                "standing at rigid attention in polished armor",
                "surveying the room with practiced aristocratic disdain",
                "hovering nearby, awaiting orders",
                "hand resting casually on their weapon",
            ],
            trait_ranges={
                "conscientiousness": (60, 90),
                "agreeableness": (30, 60),
                "extraversion": (40, 70),
            },
            speech_styles=["formal", "cold", "deferential", "military"],
            motivations=[Motivation.DUTY, Motivation.POWER, Motivation.RESPECT],
        ),
    ],
    "default": [
        NPCTemplate(
            names=["Stranger", "Traveler", "Local", "Passerby", "The Figure"],
            roles=["traveler", "commoner", "wanderer", "worker"],
            descriptions=[
                "watching you with guarded curiosity",
                "going about their business",
                "pausing to observe the newcomer",
                "neither friendly nor hostile, just... there",
            ],
            trait_ranges={},  # Use defaults (50)
            speech_styles=["neutral", "cautious", "curious"],
            motivations=[Motivation.SURVIVAL, Motivation.SAFETY],
        ),
    ],
}


# =============================================================================
# LLM Generation Prompts
# =============================================================================

_NPC_GENERATION_SYSTEM_PROMPT = """You are an NPC generator for a tabletop RPG. Generate a contextually appropriate NPC.

Output ONLY valid JSON with this exact structure (no markdown, no explanation):
{
    "name": "string (fantasy-appropriate name)",
    "description": "1-2 sentence physical/behavioral description",
    "role": "merchant|guard|traveler|criminal|noble|peasant|adventurer|scholar|priest|artisan|entertainer",
    "traits": {
        "openness": 0-100,
        "conscientiousness": 0-100,
        "extraversion": 0-100,
        "agreeableness": 0-100,
        "neuroticism": 0-100
    },
    "motivations": ["survival"|"wealth"|"power"|"knowledge"|"duty"|"vengeance"|"love"|"fame"|"safety"|"belonging"|"respect"],
    "speech_style": "formal|crude|poetic|terse|warm|cold|nervous|mysterious|boisterous",
    "quirks": ["optional behavioral quirk"],
    "initial_attitude": "friendly|neutral|hostile"
}

Guidelines:
- Match the NPC to the location type and danger level
- Higher danger = more desperate/dangerous NPCs
- Traits should reflect the role and situation
- Include 1-3 motivations
- Keep descriptions vivid but concise
- Make names memorable and fantasy-appropriate"""


_ENVIRONMENT_GENERATION_SYSTEM_PROMPT = """You are an environment feature generator for a tabletop RPG. Generate contextually appropriate location features that add mystery, danger, or opportunity.

Output ONLY valid JSON with this exact structure (no markdown, no explanation):
{
    "name": "string (short, evocative name for the feature)",
    "description": "1-2 sentence atmospheric description",
    "feature_type": "passage|hazard|discovery|hideout|obstacle",
    "is_dangerous": true|false,
    "interaction_hint": "optional hint about what players might do with it"
}

Guidelines:
- Match the feature to the location type and danger level
- Higher danger = more ominous/threatening features
- Features should feel discoverable and interactive
- Keep names short (1-3 words)
- Descriptions should be atmospheric and evocative"""


# Environment feature templates
_ENVIRONMENT_FEATURES: dict[str, list[tuple[str, str]]] = {
    "dungeon": [
        ("Hidden Passage", "A section of wall that slides aside, revealing darkness beyond..."),
        ("Collapsed Tunnel", "Rubble blocks what was once a passage, though gaps remain..."),
        ("Underground Stream", "Water trickles through a crack, pooling in a small basin..."),
        ("Ancient Inscription", "Faded writing covers this section of wall..."),
    ],
    "tavern": [
        ("Back Room", "A door you hadn't noticed leads to a private area..."),
        ("Loose Floorboard", "A board creaks oddly, suggesting a hollow beneath..."),
        ("Secret Cellar", "Behind the bar, a trapdoor leads down..."),
    ],
    "forest": [
        ("Animal Trail", "A narrow path through the undergrowth, recently used..."),
        ("Hollow Tree", "An ancient oak with a dark cavity in its trunk..."),
        ("Hidden Clearing", "The trees part to reveal a small glade..."),
        ("Overgrown Ruins", "Stone foundations barely visible through the growth..."),
    ],
    "default": [
        ("Shadowy Corner", "An area the light doesn't quite reach..."),
        ("Strange Mark", "An unfamiliar symbol scratched into the surface..."),
        ("Hidden Alcove", "A small recess, easy to miss at first glance..."),
    ],
}


# =============================================================================
# Move Executor Service
# =============================================================================


@dataclass
class MoveExecutor:
    """
    Executes GM moves, creating entities and modifying world state.

    The bridge between move selection (pbta.py) and world generation.
    Supports LLM-powered generation with template fallbacks.
    """

    dolt: DoltRepository
    neo4j: Neo4jRepository
    npc_service: NPCService
    llm: LLMService | None = None
    quest_service: QuestService | None = None

    # Generator registry - maps move types to executor methods
    _generators: dict[
        GMMoveType,
        Callable[[GMMove, Context, Session, str], Coroutine[Any, Any, MoveExecutionResult]],
    ] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize the generator registry."""
        self._generators = {
            # Generative moves (create entities/relationships)
            GMMoveType.INTRODUCE_NPC: self._execute_introduce_npc,
            GMMoveType.CHANGE_ENVIRONMENT: self._execute_change_environment,
            GMMoveType.CAPTURE: self._execute_capture,
            GMMoveType.OFFER_OPPORTUNITY: self._execute_offer_opportunity,
            # Effect moves (modify state)
            GMMoveType.TAKE_AWAY: self._execute_take_away,
            GMMoveType.DEAL_DAMAGE: self._execute_deal_damage,
            GMMoveType.SEPARATE_THEM: self._execute_separate_them,
            GMMoveType.ADVANCE_TIME: self._execute_advance_time,
            # Narrative moves (atmosphere/warnings)
            GMMoveType.REVEAL_UNWELCOME_TRUTH: self._execute_reveal_truth,
            GMMoveType.SHOW_DANGER: self._execute_show_danger,
        }

    async def execute(
        self,
        move: GMMove,
        context: Context,
        session: Session,
        trigger_reason: str = "miss",
    ) -> MoveExecutionResult:
        """
        Execute a GM move, potentially creating entities.

        Args:
            move: The GM move to execute
            context: Current game context
            session: Active session
            trigger_reason: Why this move was triggered ("miss", "weak_hit", "proactive")

        Returns:
            MoveExecutionResult with created entities and narrative
        """
        generator = self._generators.get(move.type)

        if generator is None:
            # Narrative-only move - just return description
            return MoveExecutionResult(
                success=True,
                narrative=move.description,
            )

        try:
            return await generator(move, context, session, trigger_reason)
        except Exception as e:
            # Graceful degradation - return narrative only, but log the error
            logger.error(
                "Move executor failed for %s, falling back to narrative: %s",
                move.type.value,
                e,
                exc_info=True,
            )
            return MoveExecutionResult(
                success=True,
                narrative=move.description,
                error=f"Generation failed, using template: {e}",
                used_fallback=True,
            )

    # =========================================================================
    # Generative Move Executors
    # =========================================================================

    async def _execute_introduce_npc(
        self,
        move: GMMove,
        context: Context,
        session: Session,
        trigger_reason: str,
    ) -> MoveExecutionResult:
        """
        Generate and create a new NPC appropriate for the context.

        Uses LLM to generate contextually appropriate NPC, falls back
        to templates if LLM unavailable or fails.
        """
        # Generate NPC parameters (LLM or template)
        npc_params = await self._generate_npc_parameters(context, session, trigger_reason)

        # Create character entity
        npc_entity = create_character(
            universe_id=session.universe_id,
            name=npc_params.name,
            description=npc_params.description,
            hp_max=npc_params.hp_max,
            ac=npc_params.ac,
            location_id=session.location_id,
        )
        self.dolt.save_entity(npc_entity)

        # Create NPC profile with personality
        npc_profile = create_npc_profile(
            entity_id=npc_entity.id,
            openness=npc_params.openness,
            conscientiousness=npc_params.conscientiousness,
            extraversion=npc_params.extraversion,
            agreeableness=npc_params.agreeableness,
            neuroticism=npc_params.neuroticism,
            motivations=npc_params.motivations if npc_params.motivations else None,
            speech_style=npc_params.speech_style,
            quirks=npc_params.quirks if npc_params.quirks else None,
        )
        self.npc_service.save_profile(npc_profile)

        # Create LOCATED_IN relationship
        located_in = Relationship(
            universe_id=session.universe_id,
            from_entity_id=npc_entity.id,
            to_entity_id=session.location_id,
            relationship_type=RelationshipType.LOCATED_IN,
        )
        self.neo4j.create_relationship(located_in)

        # Generate narrative
        narrative = self._narrate_npc_introduction(
            npc_entity.name, npc_params.description, npc_params.role, trigger_reason
        )

        return MoveExecutionResult(
            success=True,
            narrative=narrative,
            entities_created=[npc_entity.id],
            relationships_created=[located_in.id],
            state_changes=[f"New NPC: {npc_entity.name}"],
        )

    async def _execute_change_environment(
        self,
        move: GMMove,
        context: Context,
        session: Session,
        trigger_reason: str,
    ) -> MoveExecutionResult:
        """
        Modify or extend the current location.

        Can add new features, create connected sub-locations, or change atmosphere.
        """
        # Determine what type of change based on danger level
        if context.danger_level < 5:
            return await self._add_atmosphere(context, session)
        elif context.danger_level < 12:
            return await self._add_location_feature(context, session)
        else:
            return await self._add_location_feature(context, session, is_hazard=True)

    async def _execute_take_away(
        self,
        move: GMMove,
        context: Context,
        session: Session,
        trigger_reason: str,
    ) -> MoveExecutionResult:
        """
        Remove an item from the actor's inventory.

        Actually marks the item as inactive in Dolt and removes
        the CARRIES/WIELDS/WEARS relationship from Neo4j.
        """
        # Find an item to take (prefer equipped items)
        if not context.actor_inventory:
            return MoveExecutionResult(
                success=True,
                narrative="You have nothing to lose... this time.",
            )

        # Select a random item
        item_summary = random.choice(context.actor_inventory)

        # Get the actual entity from Dolt
        item_entity = self.dolt.get_entity(item_summary.id, session.universe_id)
        if item_entity is None:
            # Item doesn't exist in DB, just return narrative
            return MoveExecutionResult(
                success=True,
                narrative=f"Your {item_summary.name} slips from your grasp and is lost!",
                state_changes=[f"Lost: {item_summary.name}"],
            )

        # Mark item as inactive
        item_entity.is_active = False
        item_entity.description = f"{item_entity.description} [Lost]"
        self.dolt.save_entity(item_entity)

        # Remove inventory relationships (CARRIES, WIELDS, WEARS)
        relationships_removed = []
        for rel_type in ["CARRIES", "WIELDS", "WEARS"]:
            rel = self.neo4j.get_relationship_between(
                from_entity_id=context.actor.id,
                to_entity_id=item_summary.id,
                universe_id=session.universe_id,
                relationship_type=rel_type,
            )
            if rel is not None:
                self.neo4j.delete_relationship(rel.id)
                relationships_removed.append(rel.id)

        # Generate narrative based on how it was lost
        narratives = [
            f"Your {item_summary.name} slips from your grasp and is lost to the darkness!",
            f"In the chaos, your {item_summary.name} is knocked away and lost!",
            f"With a sickening crunch, your {item_summary.name} is destroyed!",
            f"Your {item_summary.name} shatters into pieces!",
        ]
        narrative = random.choice(narratives)

        return MoveExecutionResult(
            success=True,
            narrative=narrative,
            entities_modified=[item_summary.id],
            state_changes=[f"Lost: {item_summary.name}"],
        )

    async def _execute_capture(
        self,
        move: GMMove,
        context: Context,
        session: Session,
        trigger_reason: str,
    ) -> MoveExecutionResult:
        """
        Trap the actor in a location.

        Creates a new trap location, moves the character there,
        updates the session, and creates a TRAPPED_IN relationship
        to indicate they cannot easily leave.
        """
        # Create a trap location
        trap_names = ["Holding Cell", "Pit Trap", "Collapsed Chamber", "Sealed Room"]
        trap_descriptions = [
            "A cramped, dark cell with iron bars.",
            "A deep pit with smooth walls, impossible to climb.",
            "Rubble seals the way you came - you're cut off.",
            "The door slams shut behind you with terrible finality.",
        ]
        trap_idx = random.randrange(len(trap_names))
        trap_name = trap_names[trap_idx]
        trap_desc = trap_descriptions[trap_idx]

        trap_location = create_location(
            universe_id=session.universe_id,
            name=trap_name,
            description=trap_desc,
            danger_level=context.danger_level,
        )
        self.dolt.save_entity(trap_location)

        relationships_created = []

        # Remove old LOCATED_IN relationship
        old_location_rel = self.neo4j.get_relationship_between(
            from_entity_id=session.character_id,
            to_entity_id=session.location_id,
            universe_id=session.universe_id,
            relationship_type="LOCATED_IN",
        )
        if old_location_rel is not None:
            self.neo4j.delete_relationship(old_location_rel.id)

        # Create new LOCATED_IN relationship to trap
        new_location_rel = Relationship(
            universe_id=session.universe_id,
            from_entity_id=session.character_id,
            to_entity_id=trap_location.id,
            relationship_type=RelationshipType.LOCATED_IN,
        )
        self.neo4j.create_relationship(new_location_rel)
        relationships_created.append(new_location_rel.id)

        # Create TRAPPED_IN relationship to indicate they cannot easily leave
        trapped_rel = Relationship(
            universe_id=session.universe_id,
            from_entity_id=session.character_id,
            to_entity_id=trap_location.id,
            relationship_type=RelationshipType.TRAPPED_IN,
            description="Cannot leave without help or effort",
        )
        self.neo4j.create_relationship(trapped_rel)
        relationships_created.append(trapped_rel.id)

        # Update session location
        session.location_id = trap_location.id

        narrative = f"You find yourself trapped in a {trap_name.lower()}! {trap_desc}"

        return MoveExecutionResult(
            success=True,
            narrative=narrative,
            entities_created=[trap_location.id],
            relationships_created=relationships_created,
            state_changes=["Trapped!", f"Location: {trap_name}"],
        )

    async def _execute_reveal_truth(
        self,
        move: GMMove,
        context: Context,
        session: Session,
        trigger_reason: str,
    ) -> MoveExecutionResult:
        """Reveal an unwelcome truth about the situation."""
        # Generate a troubling revelation based on context
        revelations = [
            "You realize the path you came from has vanished...",
            "A cold certainty settles over you - you're being watched.",
            "The symbols on the wall... you've seen them before, in nightmares.",
            "Something about this place feels deeply, fundamentally wrong.",
            "You notice tracks in the dust - something has been following you.",
        ]

        narrative = random.choice(revelations)

        return MoveExecutionResult(
            success=True,
            narrative=narrative,
            state_changes=["Unsettling revelation"],
        )

    async def _execute_show_danger(
        self,
        move: GMMove,
        context: Context,
        session: Session,
        trigger_reason: str,
    ) -> MoveExecutionResult:
        """
        Show signs of impending danger.

        This is a soft move - a warning that telegraphs something bad
        without immediately causing consequences.
        """
        danger_signs = [
            "You hear ominous sounds in the distance...",
            "The air grows heavy with a sense of menace.",
            "Something shifts in the shadows nearby.",
            "A chill runs down your spine - danger is close.",
            "Your instincts scream at you to be careful.",
            "The ground trembles slightly beneath your feet.",
            "An unnatural silence falls over the area.",
        ]

        narrative = random.choice(danger_signs)

        # Could add HAS_ATMOSPHERE relationship for persistent mood
        return MoveExecutionResult(
            success=True,
            narrative=narrative,
            state_changes=["Danger sensed"],
        )

    async def _execute_offer_opportunity(
        self,
        move: GMMove,
        context: Context,
        session: Session,
        trigger_reason: str,
    ) -> MoveExecutionResult:
        """
        Offer an opportunity with a cost or complication.

        Can create either:
        - A quest hook (if quest_service available and NPCs present)
        - An interactive element that the player might use
        """
        # 40% chance to generate a quest if conditions are right
        if self.quest_service is not None and random.random() < _QUEST_OPPORTUNITY_CHANCE:
            quest_result = await self._try_generate_quest_opportunity(context, session)
            if quest_result is not None:
                return quest_result

        # Fall back to creating an interactive feature
        opportunities = [
            (
                "Hidden Lever",
                "A lever protrudes from the wall. It could open a way forward... or trigger something worse.",
            ),
            (
                "Abandoned Supplies",
                "You spot a discarded pack. Useful items, perhaps, but why was it abandoned here?",
            ),
            (
                "Strange Device",
                "An odd mechanism sits here, humming with energy. It looks operational.",
            ),
            (
                "Cracked Wall",
                "A section of wall looks weakened. You might be able to break through.",
            ),
            (
                "Glowing Runes",
                "Arcane symbols pulse with light. They seem to react to your presence.",
            ),
        ]

        name, description = random.choice(opportunities)

        # Create an interactive feature
        feature_entity = create_item(
            universe_id=session.universe_id,
            name=name,
            description=description,
            tags=["opportunity", "interactive"],
            location_id=session.location_id,
        )
        self.dolt.save_entity(feature_entity)

        # Link to location
        contains_rel = Relationship(
            universe_id=session.universe_id,
            from_entity_id=session.location_id,
            to_entity_id=feature_entity.id,
            relationship_type=RelationshipType.CONTAINS,
        )
        self.neo4j.create_relationship(contains_rel)

        narrative = f"An opportunity presents itself: {description}"

        return MoveExecutionResult(
            success=True,
            narrative=narrative,
            entities_created=[feature_entity.id],
            relationships_created=[contains_rel.id],
            state_changes=[f"Opportunity: {name}"],
        )

    async def _try_generate_quest_opportunity(
        self,
        context: Context,
        session: Session,
    ) -> MoveExecutionResult | None:
        """
        Try to generate a quest as an opportunity.

        Returns None if quest generation isn't possible or fails.
        """
        if self.quest_service is None:
            return None

        # Build quest context
        quest_context = self.quest_service.build_quest_context(
            universe_id=session.universe_id,
            location_id=session.location_id,
        )

        # If no NPCs present, skip quest generation
        if not quest_context.npcs_present:
            return None

        # Pick a random NPC as the quest giver
        giver = random.choice(quest_context.npcs_present)
        quest_context.giver_id = giver.id
        quest_context.giver_name = giver.name

        # Generate the quest
        result = await self.quest_service.generate_quest(quest_context)

        if not result.success or result.quest is None:
            return None

        quest = result.quest

        # Build narrative
        narrative = (
            f"{quest.giver_name} catches your attention. "
            f'"{quest.description}" '
            f"(New quest available: {quest.name})"
        )

        return MoveExecutionResult(
            success=True,
            narrative=narrative,
            state_changes=[f"Quest available: {quest.name}"],
        )

    async def _execute_deal_damage(
        self,
        move: GMMove,
        context: Context,
        session: Session,
        trigger_reason: str,
    ) -> MoveExecutionResult:
        """
        Deal damage to the actor.

        The damage amount is typically set on the GMMove by the router.
        This method handles the narrative and could apply the damage
        to the character entity.
        """
        damage = move.damage or 0

        if damage > 0:
            # Get the actor entity and apply damage
            actor_entity = self.dolt.get_entity(context.actor.id, session.universe_id)
            if actor_entity and actor_entity.stats:
                new_hp = max(0, actor_entity.stats.hp_current - damage)
                actor_entity.stats.hp_current = new_hp
                self.dolt.save_entity(actor_entity)

            damage_sources = [
                f"You take {damage} damage from the blow!",
                f"Pain shoots through you as you suffer {damage} damage!",
                f"The attack connects, dealing {damage} damage!",
                f"You cry out as {damage} damage tears into you!",
            ]
            narrative = random.choice(damage_sources)

            return MoveExecutionResult(
                success=True,
                narrative=narrative,
                entities_modified=[context.actor.id],
                state_changes=[f"Took {damage} damage"],
            )

        # No damage specified - just narrative
        return MoveExecutionResult(
            success=True,
            narrative="You narrowly avoid the worst of it, but you know you won't be so lucky next time.",
        )

    async def _execute_separate_them(
        self,
        move: GMMove,
        context: Context,
        session: Session,
        trigger_reason: str,
    ) -> MoveExecutionResult:
        """
        Separate party members (for multi-character sessions).

        In a solo game with one character, this becomes a narrative
        moment about isolation or losing track of an NPC ally.
        """
        # Check if there are NPCs present who could be separated
        npcs_present = [e for e in context.entities_present if e.type == "character"]

        if npcs_present:
            # Separate an NPC from the party
            separated_npc = random.choice(npcs_present)

            # Remove their LOCATED_IN relationship
            old_rel = self.neo4j.get_relationship_between(
                from_entity_id=separated_npc.id,
                to_entity_id=session.location_id,
                universe_id=session.universe_id,
                relationship_type="LOCATED_IN",
            )
            if old_rel:
                self.neo4j.delete_relationship(old_rel.id)

            narrative = f"{separated_npc.name} vanishes from sight! You've been separated!"

            return MoveExecutionResult(
                success=True,
                narrative=narrative,
                entities_modified=[separated_npc.id],
                state_changes=[f"Separated from {separated_npc.name}"],
            )

        # No one to separate - just isolation narrative
        isolation_narratives = [
            "The path behind you collapses - you're on your own now.",
            "The fog rolls in thick, cutting you off from any allies.",
            "You realize with a start that you've become completely turned around.",
        ]

        return MoveExecutionResult(
            success=True,
            narrative=random.choice(isolation_narratives),
            state_changes=["Isolated"],
        )

    async def _execute_advance_time(
        self,
        move: GMMove,
        context: Context,
        session: Session,
        trigger_reason: str,
    ) -> MoveExecutionResult:
        """
        Advance time, potentially triggering consequences.

        Could affect temporary conditions, wandering monsters,
        or time-sensitive events.
        """
        time_passages = [
            "Time passes... the shadows grow longer.",
            "Hours slip by as you struggle with your situation.",
            "When you finally recover your bearings, significant time has passed.",
            "The passage of time weighs on you as you continue.",
        ]

        narrative = random.choice(time_passages)

        # Could trigger additional effects:
        # - Heal 1 HP if resting
        # - Check for wandering encounters
        # - Advance quest timers
        # For now, just narrative

        return MoveExecutionResult(
            success=True,
            narrative=narrative,
            state_changes=["Time passed"],
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def _generate_npc_parameters(
        self,
        context: Context,
        session: Session,
        trigger_reason: str,
    ) -> NPCGenerationParams:
        """
        Generate NPC parameters using LLM or templates.

        Falls back to templates if LLM is unavailable or fails.
        """
        # Try LLM generation if available
        if self.llm is not None and self.llm.is_available:
            try:
                return await self._llm_generate_npc(context, session, trigger_reason)
            except (ValueError, RuntimeError, json.JSONDecodeError) as e:
                logger.warning("LLM NPC generation failed, using templates: %s", e)

        # Fallback to templates
        return self._template_npc_parameters(context)

    async def _llm_generate_npc(
        self,
        context: Context,
        session: Session,
        trigger_reason: str,
    ) -> NPCGenerationParams:
        """
        Generate NPC parameters using LLM.

        Raises:
            ValueError: If LLM response cannot be parsed
            RuntimeError: If LLM is not available
        """
        if self.llm is None:
            raise RuntimeError("LLM service not available")

        # Build context-aware prompt
        prompt = self._build_npc_generation_prompt(context, trigger_reason)

        # Generate with LLM
        response = await self.llm.provider.complete(
            messages=[
                {"role": "system", "content": _NPC_GENERATION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=512,
            temperature=0.8,
        )

        # Parse JSON response
        return self._parse_npc_response(response, context)

    def _build_npc_generation_prompt(self, context: Context, trigger_reason: str) -> str:
        """Build the user prompt for NPC generation."""
        # Get existing character names to avoid duplicates
        existing_names = [e.name for e in context.entities_present]

        # Get recent events for context
        recent_events = context.recent_events[:3] if context.recent_events else []

        location_name = context.location.name if context.location else "Unknown"
        location_desc = context.location.description if context.location else ""

        prompt = f"""Current Location: {location_name}
Location Description: {location_desc}
Danger Level: {context.danger_level}/20
Existing Characters: {", ".join(existing_names) if existing_names else "None"}
Recent Events: {"; ".join(recent_events) if recent_events else "None"}
Trigger: {trigger_reason}

Generate a NEW character who fits this scene. Avoid names similar to existing characters.
Output JSON only, no other text."""

        return prompt

    def _parse_npc_response(self, response: str, context: Context) -> NPCGenerationParams:
        """
        Parse LLM response into NPCGenerationParams.

        Handles both clean JSON and JSON wrapped in markdown code blocks.
        """
        # Clean up response - handle markdown code blocks
        cleaned = response.strip()
        if cleaned.startswith("```"):
            # Remove markdown code block markers
            lines = cleaned.split("\n")
            # Find the actual JSON content
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```"):
                    in_block = not in_block
                    continue
                if in_block or not line.startswith("```"):
                    json_lines.append(line)
            cleaned = "\n".join(json_lines).strip()

        # Try to extract JSON if there's surrounding text
        if not cleaned.startswith("{"):
            # Look for JSON object in the response
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            if start != -1 and end > start:
                cleaned = cleaned[start:end]

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse NPC JSON: {e}") from e

        # Parse traits with defaults
        traits = data.get("traits", {})

        # Parse motivations from strings to Motivation enum
        motivation_strs = data.get("motivations", [])
        motivations = []
        for m_str in motivation_strs[:3]:  # Max 3 motivations
            try:
                motivations.append(Motivation(m_str.lower()))
            except ValueError:
                logger.warning(
                    "Unknown NPC motivation %r in LLM response; skipping. Known: %s",
                    m_str,
                    [m.value for m in Motivation],
                )

        # Default to SURVIVAL if no valid motivations
        if not motivations:
            motivations = [Motivation.SURVIVAL]

        return NPCGenerationParams(
            name=data.get("name", "Mysterious Stranger"),
            description=data.get("description", "A figure of unknown origin."),
            role=data.get("role", "stranger"),
            openness=self._clamp_trait(traits.get("openness", 50)),
            conscientiousness=self._clamp_trait(traits.get("conscientiousness", 50)),
            extraversion=self._clamp_trait(traits.get("extraversion", 50)),
            agreeableness=self._clamp_trait(traits.get("agreeableness", 50)),
            neuroticism=self._clamp_trait(traits.get("neuroticism", 50)),
            motivations=motivations,
            speech_style=data.get("speech_style", "neutral"),
            quirks=data.get("quirks", [])[:2],  # Max 2 quirks
            hp_max=10 + context.danger_level,
            ac=10 + (context.danger_level // 5),
            initial_attitude=data.get("initial_attitude", "neutral"),
        )

    def _clamp_trait(self, value: int | float | None) -> int:
        """Clamp a trait value to valid range 0-100."""
        if value is None:
            return 50
        return max(0, min(100, int(value)))

    def _template_npc_parameters(self, context: Context) -> NPCGenerationParams:
        """Generate NPC parameters from templates based on location."""
        # Determine location type from context
        location_type = self._get_location_type(context)

        # Get templates for this location type
        templates = _NPC_TEMPLATES.get(location_type, _NPC_TEMPLATES["default"])
        template = random.choice(templates)

        # Generate parameters from template
        name = random.choice(template.names)
        role = random.choice(template.roles)
        description = random.choice(template.descriptions)
        speech_style = random.choice(template.speech_styles)

        # Generate traits within ranges
        def get_trait(trait_name: str) -> int:
            if trait_name in template.trait_ranges:
                low, high = template.trait_ranges[trait_name]
                return random.randint(low, high)
            return random.randint(40, 60)  # Default range

        # Select 1-2 motivations
        motivations = []
        if template.motivations:
            num_motivations = random.randint(1, min(2, len(template.motivations)))
            motivations = random.sample(template.motivations, num_motivations)

        return NPCGenerationParams(
            name=name,
            description=description,
            role=role,
            openness=get_trait("openness"),
            conscientiousness=get_trait("conscientiousness"),
            extraversion=get_trait("extraversion"),
            agreeableness=get_trait("agreeableness"),
            neuroticism=get_trait("neuroticism"),
            motivations=motivations,
            speech_style=speech_style,
            quirks=[],
            hp_max=10 + context.danger_level,
            ac=10 + (context.danger_level // 5),
            initial_attitude="neutral",
        )

    def _get_location_type(self, context: Context) -> str:
        """Determine location type from context for template selection."""
        if context.location is None:
            return "default"

        location_name = context.location.name.lower()
        location_desc = (context.location.description or "").lower()
        combined = f"{location_name} {location_desc}"

        # Simple keyword matching
        if any(word in combined for word in ["tavern", "inn", "bar", "pub"]):
            return "tavern"
        if any(word in combined for word in ["dungeon", "cave", "crypt", "tomb", "prison"]):
            return "dungeon"
        if any(word in combined for word in ["market", "bazaar", "shop", "store", "square"]):
            return "market"
        if any(word in combined for word in ["forest", "wood", "grove", "jungle"]):
            return "forest"
        if any(word in combined for word in ["castle", "palace", "manor", "throne", "court"]):
            return "castle"

        return "default"

    def _narrate_npc_introduction(
        self,
        name: str,
        description: str,
        role: str,
        trigger_reason: str,
    ) -> str:
        """Generate narrative for NPC introduction."""
        intros = [
            f"A figure emerges from the shadows - {name}, {description}.",
            f"You notice someone you hadn't seen before: {name}, {description}.",
            f"{name} appears, {description}.",
            f"From nearby, {name} catches your attention - {description}.",
        ]
        return random.choice(intros)

    async def _add_location_feature(
        self,
        context: Context,
        session: Session,
        is_hazard: bool = False,
    ) -> MoveExecutionResult:
        """
        Add a new feature to the current location.

        Uses LLM to generate contextually appropriate features,
        falls back to templates if LLM unavailable or fails.
        """
        # Generate feature parameters (LLM or template)
        feature_params = await self._generate_environment_feature(context, is_hazard)

        # Create feature entity using create_item (proper factory for location features)
        feature_entity = create_item(
            universe_id=session.universe_id,
            name=feature_params.name,
            description=feature_params.description,
            tags=["location_feature", feature_params.feature_type],
            location_id=session.location_id,
        )
        self.dolt.save_entity(feature_entity)

        # Link to location via CONTAINS relationship
        contains_rel = Relationship(
            universe_id=session.universe_id,
            from_entity_id=session.location_id,
            to_entity_id=feature_entity.id,
            relationship_type=RelationshipType.CONTAINS,
        )
        self.neo4j.create_relationship(contains_rel)

        narrative = f"The environment shifts... {feature_params.description}"

        return MoveExecutionResult(
            success=True,
            narrative=narrative,
            entities_created=[feature_entity.id],
            relationships_created=[contains_rel.id],
            state_changes=[f"New feature: {feature_params.name}"],
        )

    async def _generate_environment_feature(
        self,
        context: Context,
        is_hazard: bool,
    ) -> EnvironmentFeatureParams:
        """
        Generate environment feature parameters using LLM or templates.

        Falls back to templates if LLM is unavailable or fails.
        """
        # Try LLM generation if available
        if self.llm is not None and self.llm.is_available:
            try:
                return await self._llm_generate_environment_feature(context, is_hazard)
            except (ValueError, RuntimeError, json.JSONDecodeError) as e:
                logger.warning("LLM environment generation failed, using templates: %s", e)

        # Fallback to templates
        return self._template_environment_feature(context, is_hazard)

    async def _llm_generate_environment_feature(
        self,
        context: Context,
        is_hazard: bool,
    ) -> EnvironmentFeatureParams:
        """
        Generate environment feature using LLM.

        Raises:
            ValueError: If LLM response cannot be parsed
            RuntimeError: If LLM is not available
        """
        if self.llm is None:
            raise RuntimeError("LLM service not available")

        # Build prompt
        prompt = self._build_environment_generation_prompt(context, is_hazard)

        # Generate with LLM
        response = await self.llm.provider.complete(
            messages=[
                {"role": "system", "content": _ENVIRONMENT_GENERATION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=256,
            temperature=0.8,
        )

        # Parse JSON response
        return self._parse_environment_response(response, is_hazard)

    def _build_environment_generation_prompt(self, context: Context, is_hazard: bool) -> str:
        """Build the user prompt for environment feature generation."""
        location_name = context.location.name if context.location else "Unknown"
        location_desc = context.location.description if context.location else ""

        hazard_instruction = "The feature should be DANGEROUS or threatening." if is_hazard else ""

        prompt = f"""Current Location: {location_name}
Location Description: {location_desc}
Danger Level: {context.danger_level}/20
Mood: {context.mood or "neutral"}
{hazard_instruction}

Generate an environment feature that fits this location.
Output JSON only, no other text."""

        return prompt

    def _parse_environment_response(
        self, response: str, is_hazard: bool
    ) -> EnvironmentFeatureParams:
        """Parse LLM response into EnvironmentFeatureParams."""
        # Clean up response - handle markdown code blocks
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.startswith("```"):
                    in_block = not in_block
                    continue
                if in_block or not line.startswith("```"):
                    json_lines.append(line)
            cleaned = "\n".join(json_lines).strip()

        # Try to extract JSON if there's surrounding text
        if not cleaned.startswith("{"):
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            if start != -1 and end > start:
                cleaned = cleaned[start:end]

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse environment JSON: {e}") from e

        return EnvironmentFeatureParams(
            name=data.get("name", "Strange Feature"),
            description=data.get("description", "Something catches your eye..."),
            feature_type=data.get("feature_type", "discovery"),
            is_dangerous=data.get("is_dangerous", is_hazard),
            interaction_hint=data.get("interaction_hint"),
        )

    def _template_environment_feature(
        self, context: Context, is_hazard: bool
    ) -> EnvironmentFeatureParams:
        """Generate environment feature from templates."""
        location_type = self._get_location_type(context)
        features = _ENVIRONMENT_FEATURES.get(location_type, _ENVIRONMENT_FEATURES["default"])

        feature_name, feature_desc = random.choice(features)

        if is_hazard:
            feature_desc = feature_desc.rstrip(".") + ", and it looks dangerous."

        return EnvironmentFeatureParams(
            name=feature_name,
            description=feature_desc,
            feature_type="hazard" if is_hazard else "discovery",
            is_dangerous=is_hazard,
        )

    async def _add_atmosphere(
        self,
        context: Context,
        session: Session,
    ) -> MoveExecutionResult:
        """Change the atmosphere of the current location."""
        atmospheres = [
            "An eerie silence falls over the area...",
            "The air grows thick with tension...",
            "Shadows seem to deepen around you...",
            "A strange smell wafts through the air...",
            "The temperature drops noticeably...",
        ]

        narrative = random.choice(atmospheres)

        return MoveExecutionResult(
            success=True,
            narrative=narrative,
            state_changes=["Atmosphere changed"],
        )
