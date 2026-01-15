"""
NPC Service for TTA-Solo.

Orchestrates NPC decision-making, memory formation, and behavior.
This is the symbolic layer that drives NPC intelligence.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, Field

from src.db.interfaces import DoltRepository, Neo4jRepository
from src.models.event import Event, EventOutcome, EventType
from src.models.npc import (
    ActionOption,
    ActionType,
    CombatEvaluation,
    CombatState,
    DialogueConstraints,
    EntitySummary,
    MemoryType,
    Motivation,
    NPCDecisionContext,
    NPCMemory,
    NPCProfile,
    RelationshipSummary,
    create_memory,
    create_npc_profile,
    get_combat_state,
)
from src.models.relationships import RelationshipType

if TYPE_CHECKING:
    from src.services.llm import LLMService


# =============================================================================
# Constants
# =============================================================================

# Decision-making thresholds
ERRATIC_NEUROTICISM_THRESHOLD = 70  # NPCs above this are more unpredictable
ERRATIC_CHOICE_PROBABILITY = 0.2  # Chance for erratic NPC to pick suboptimal action
THREAT_THRESHOLD = 0.5  # Entities above this apparent_threat are considered threatening

# Memory retrieval
MEMORY_PREFETCH_MULTIPLIER = 3  # Fetch this many times the limit for scoring/filtering


# =============================================================================
# Text Relevance Helpers
# =============================================================================

# Common stop words to exclude from keyword extraction
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        "need",
        "dare",
        "ought",
        "used",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "and",
        "but",
        "if",
        "or",
        "because",
        "until",
        "while",
        "this",
        "that",
        "these",
        "those",
        "i",
        "you",
        "he",
        "she",
        "it",
        "we",
        "they",
        "what",
        "which",
        "who",
        "whom",
    }
)


def _extract_keywords(text: str) -> set[str]:
    """
    Extract meaningful keywords from text for relevance matching.

    Args:
        text: Text to extract keywords from

    Returns:
        Set of lowercase keywords (excluding stop words)
    """
    # Simple tokenization: split on non-alphanumeric, lowercase
    words = set()
    current_word = []

    for char in text.lower():
        if char.isalnum():
            current_word.append(char)
        elif current_word:
            word = "".join(current_word)
            if len(word) > 2 and word not in _STOP_WORDS:
                words.add(word)
            current_word = []

    # Don't forget the last word
    if current_word:
        word = "".join(current_word)
        if len(word) > 2 and word not in _STOP_WORDS:
            words.add(word)

    return words


def _calculate_keyword_relevance(
    memory_description: str,
    context_keywords: set[str],
) -> float:
    """
    Calculate relevance score based on keyword overlap.

    This is a simple heuristic for relevance scoring.
    Future: Replace with vector similarity using embeddings.

    Args:
        memory_description: The memory's description text
        context_keywords: Keywords extracted from current context

    Returns:
        Relevance score from 0.0 to 1.0
    """
    if not context_keywords:
        return 0.5  # Neutral relevance if no context

    memory_keywords = _extract_keywords(memory_description)

    if not memory_keywords:
        return 0.3  # Low relevance for empty memories

    # Jaccard-inspired overlap scoring
    overlap = len(memory_keywords & context_keywords)
    union = len(memory_keywords | context_keywords)

    if union == 0:
        return 0.3

    # Scale to 0.0-1.0 range with a boost for any overlap
    base_score = overlap / union

    # Boost: any overlap is significant.
    # - base_score is a Jaccard-like overlap in [0.0, 1.0].
    # - For overlap == 0 we keep the score at or below 0.3 (see early returns).
    # - For overlap > 0 we map base_score into [0.3, 1.0] via 0.3 + 0.7 * base_score,
    #   so any overlapping memory is guaranteed at least 0.3 relevance while still
    #   preserving the relative strength of the overlap in the upper part of the range.
    if overlap > 0:
        base_score = 0.3 + (0.7 * base_score)

    return min(1.0, base_score)


# =============================================================================
# Result Models
# =============================================================================


class DecisionResult(BaseModel):
    """Result of an NPC decision."""

    action: ActionOption
    reasoning: str = ""
    alternatives_considered: int = 0


class MemoryFormationResult(BaseModel):
    """Result of attempting to form a memory."""

    formed: bool
    memory: NPCMemory | None = None
    reason: str = ""


class RelationshipDelta(BaseModel):
    """Change in a relationship after an event."""

    target_id: UUID
    trust_change: float = Field(ge=-1.0, le=1.0, default=0.0)
    strength_change: float = Field(ge=-1.0, le=1.0, default=0.0)
    new_relationship_type: RelationshipType | None = None


class CombatTurnResult(BaseModel):
    """Result of determining an NPC's combat turn action."""

    combat_state: CombatState
    """The NPC's current combat behavior state."""

    action: ActionType
    """The specific action to take this turn."""

    target_id: UUID | None = None
    """Target of the action, if applicable."""

    description: str = ""
    """Brief description of the action."""

    should_use_ability: bool = False
    """Whether the NPC should use a special ability/spell."""

    ability_name: str | None = None
    """Name of ability to use, if should_use_ability is True."""


# =============================================================================
# Action Scoring Helpers
# =============================================================================


# Maps motivations to preferred action types
MOTIVATION_ACTION_PREFERENCES: dict[Motivation, list[ActionType]] = {
    # Self-preservation
    Motivation.SURVIVAL: [ActionType.FLEE, ActionType.DEFEND, ActionType.HIDE],
    Motivation.SAFETY: [ActionType.RETREAT, ActionType.DEFEND, ActionType.OBSERVE],
    # Material
    Motivation.WEALTH: [ActionType.NEGOTIATE, ActionType.DECEIVE, ActionType.SHARE],
    Motivation.POWER: [ActionType.ATTACK, ActionType.INTIMIDATE, ActionType.THREATEN],
    Motivation.COMFORT: [ActionType.IGNORE, ActionType.WAIT, ActionType.RETREAT],
    # Social
    Motivation.LOVE: [ActionType.HELP, ActionType.PROTECT, ActionType.SHARE],
    Motivation.BELONGING: [ActionType.HELP, ActionType.FOLLOW, ActionType.SHARE],
    Motivation.RESPECT: [ActionType.NEGOTIATE, ActionType.PERSUADE, ActionType.HELP],
    Motivation.FAME: [ActionType.ATTACK, ActionType.PROTECT, ActionType.PERSUADE],
    # Higher purpose
    Motivation.KNOWLEDGE: [ActionType.OBSERVE, ActionType.NEGOTIATE, ActionType.APPROACH],
    Motivation.JUSTICE: [ActionType.ATTACK, ActionType.PROTECT, ActionType.WARN],
    Motivation.DUTY: [ActionType.PROTECT, ActionType.DEFEND, ActionType.FOLLOW],
    Motivation.FAITH: [ActionType.HELP, ActionType.HEAL, ActionType.PROTECT],
    Motivation.REVENGE: [ActionType.ATTACK, ActionType.THREATEN, ActionType.INTIMIDATE],
    # Creative
    Motivation.ARTISTRY: [ActionType.OBSERVE, ActionType.SHARE, ActionType.APPROACH],
    Motivation.LEGACY: [ActionType.PROTECT, ActionType.HELP, ActionType.WARN],
}

# Maps relationship types to preferred action types
RELATIONSHIP_ACTION_MODIFIERS: dict[RelationshipType, tuple[list[ActionType], list[ActionType]]] = {
    # (favored actions, avoided actions)
    RelationshipType.ALLIED_WITH: (
        [ActionType.HELP, ActionType.DEFEND, ActionType.SHARE, ActionType.WARN, ActionType.PROTECT],
        [ActionType.ATTACK, ActionType.DECEIVE, ActionType.THREATEN],
    ),
    RelationshipType.HOSTILE_TO: (
        [ActionType.ATTACK, ActionType.THREATEN, ActionType.DECEIVE, ActionType.FLEE],
        [ActionType.HELP, ActionType.SHARE, ActionType.PROTECT],
    ),
    RelationshipType.FEARS: (
        [ActionType.FLEE, ActionType.HIDE, ActionType.SURRENDER, ActionType.RETREAT],
        [ActionType.ATTACK, ActionType.APPROACH, ActionType.THREATEN],
    ),
    RelationshipType.RESPECTS: (
        [ActionType.OBSERVE, ActionType.HELP, ActionType.FOLLOW, ActionType.NEGOTIATE],
        [ActionType.IGNORE, ActionType.THREATEN, ActionType.DECEIVE],
    ),
    RelationshipType.DISTRUSTS: (
        [ActionType.OBSERVE, ActionType.RETREAT, ActionType.DECEIVE],
        [ActionType.SHARE, ActionType.HELP, ActionType.FOLLOW],
    ),
}


def _score_motivation(
    action: ActionType,
    motivations: list[Motivation],
) -> float:
    """
    Score how well an action serves the NPC's motivations.

    Args:
        action: The action to score
        motivations: NPC's motivations in priority order

    Returns:
        Score from 0.0 to 1.0
    """
    score = 0.0
    for i, motivation in enumerate(motivations):
        # Higher priority motivations have more weight
        weight = 1.0 / (i + 1)  # 1.0, 0.5, 0.33...
        preferred = MOTIVATION_ACTION_PREFERENCES.get(motivation, [])
        if action in preferred:
            # Higher bonus for actions at the start of the preference list
            position = preferred.index(action)
            position_bonus = 1.0 - (position * 0.2)  # 1.0, 0.8, 0.6
            score += weight * position_bonus

    # Normalize to 0-1 range
    return min(1.0, score)


def _score_relationship(
    action: ActionType,
    relationships: list[RelationshipSummary],
    target_id: UUID | None,
) -> float:
    """
    Score how well an action aligns with relationships.

    Args:
        action: The action to score
        relationships: NPC's relationships
        target_id: Target of the action (if any)

    Returns:
        Score from 0.0 to 1.0
    """
    if not target_id or not relationships:
        return 0.5  # Neutral score for no target

    # Find relationship with target
    target_rel = None
    for rel in relationships:
        if rel.target_id == target_id:
            target_rel = rel
            break

    if not target_rel:
        return 0.5  # No relationship = neutral

    # Get relationship type enum
    try:
        rel_type = RelationshipType(target_rel.relationship_type)
    except ValueError:
        return 0.5

    # Check modifiers
    modifiers = RELATIONSHIP_ACTION_MODIFIERS.get(rel_type)
    if not modifiers:
        return 0.5

    favored, avoided = modifiers

    if action in favored:
        # Boost based on relationship strength
        return 0.5 + (0.5 * target_rel.strength)
    elif action in avoided:
        # Penalty based on relationship strength
        return 0.5 - (0.4 * target_rel.strength)

    return 0.5


def _score_personality(
    action: ActionType,
    profile: NPCProfile,
) -> float:
    """
    Score how consistent an action is with personality.

    Args:
        action: The action to score
        profile: NPC's personality profile

    Returns:
        Score from 0.0 to 1.0
    """
    traits = profile.traits
    score = 0.5  # Start neutral

    # High extraversion favors social actions
    if action in [ActionType.NEGOTIATE, ActionType.PERSUADE, ActionType.APPROACH]:
        score += (traits.extraversion - 50) / 200  # -0.25 to +0.25

    # Low extraversion favors solitary actions
    if action in [ActionType.HIDE, ActionType.OBSERVE, ActionType.RETREAT]:
        score += (50 - traits.extraversion) / 200

    # High agreeableness favors helpful actions
    if action in [ActionType.HELP, ActionType.SHARE, ActionType.HEAL, ActionType.PROTECT]:
        score += (traits.agreeableness - 50) / 200

    # Low agreeableness favors competitive actions
    if action in [ActionType.ATTACK, ActionType.THREATEN, ActionType.INTIMIDATE]:
        score += (50 - traits.agreeableness) / 200

    # High conscientiousness favors cautious actions
    if action in [ActionType.OBSERVE, ActionType.DEFEND, ActionType.WAIT]:
        score += (traits.conscientiousness - 50) / 200

    # High neuroticism favors avoidant actions
    if action in [ActionType.FLEE, ActionType.HIDE, ActionType.SURRENDER]:
        score += (traits.neuroticism - 50) / 200

    # High openness favors exploration
    if action in [ActionType.APPROACH, ActionType.OBSERVE, ActionType.NEGOTIATE]:
        score += (traits.openness - 50) / 200

    return max(0.0, min(1.0, score))


def _assess_risk(
    action: ActionType,
    context: NPCDecisionContext,
) -> float:
    """
    Assess the risk of an action.

    Args:
        action: The action to assess
        context: Current decision context

    Returns:
        Risk score from 0.0 (safe) to 1.0 (very dangerous)
    """
    base_risk = 0.0

    # Combat actions are inherently risky
    if action in [ActionType.ATTACK, ActionType.THREATEN, ActionType.INTIMIDATE]:
        base_risk = 0.5

    # Defensive actions have medium risk
    if action in [ActionType.DEFEND, ActionType.PROTECT]:
        base_risk = 0.3

    # Avoidant actions are low risk
    if action in [ActionType.FLEE, ActionType.HIDE, ActionType.SURRENDER]:
        base_risk = 0.1

    # Social actions have variable risk based on relationships
    if action in [ActionType.NEGOTIATE, ActionType.PERSUADE, ActionType.DECEIVE]:
        base_risk = 0.2

    # Adjust for context
    # Low HP = higher risk for aggressive actions
    if context.hp_percentage < 0.5 and action == ActionType.ATTACK:
        base_risk += 0.3

    # High danger level increases all risks
    base_risk += context.danger_level / 40  # 0-0.5 bonus

    # Many enemies increases risk
    enemies = [e for e in context.entities_present if e.apparent_threat > THREAT_THRESHOLD]
    if len(enemies) > 1:
        base_risk += 0.1 * len(enemies)

    # No escape routes makes fleeing impossible
    if context.escape_routes == 0 and action == ActionType.FLEE:
        base_risk = 1.0  # Can't flee!

    return max(0.0, min(1.0, base_risk))


# =============================================================================
# NPC Service
# =============================================================================


@dataclass
class NPCService:
    """
    Service for NPC AI operations.

    Handles decision-making, memory formation, and behavior generation
    using the neuro-symbolic approach.

    The service uses a hybrid approach:
    - Symbolic layer: Personality, relationships, decision scoring
    - Neural layer: LLM-powered dialogue generation (optional)
    """

    dolt: DoltRepository
    neo4j: Neo4jRepository
    llm: LLMService | None = field(default=None)

    def get_profile(self, entity_id: UUID) -> NPCProfile | None:
        """
        Load an NPC profile from the database.

        Args:
            entity_id: The entity to get the profile for

        Returns:
            NPCProfile if found, None otherwise
        """
        from src.models.npc import PersonalityTraits

        profile_data = self.dolt.get_npc_profile(entity_id)
        if not profile_data:
            return None

        traits_data = profile_data.get("traits", {})
        traits = PersonalityTraits(
            openness=traits_data.get("openness", 50),
            conscientiousness=traits_data.get("conscientiousness", 50),
            extraversion=traits_data.get("extraversion", 50),
            agreeableness=traits_data.get("agreeableness", 50),
            neuroticism=traits_data.get("neuroticism", 50),
        )

        motivations_raw = profile_data.get("motivations", ["survival"])
        motivations = [Motivation(m) for m in motivations_raw]

        return NPCProfile(
            entity_id=entity_id,
            traits=traits,
            motivations=motivations,
            quirks=profile_data.get("quirks", []),
            speech_style=profile_data.get("speech_style", "neutral"),
            lawful_chaotic=profile_data.get("lawful_chaotic", 0),
            good_evil=profile_data.get("good_evil", 0),
        )

    def save_profile(self, profile: NPCProfile) -> None:
        """
        Save an NPC profile to the database.

        Args:
            profile: The profile to save
        """
        self.dolt.save_npc_profile(
            entity_id=profile.entity_id,
            traits={
                "openness": profile.traits.openness,
                "conscientiousness": profile.traits.conscientiousness,
                "extraversion": profile.traits.extraversion,
                "agreeableness": profile.traits.agreeableness,
                "neuroticism": profile.traits.neuroticism,
            },
            motivations=[m.value for m in profile.motivations],
            speech_style=profile.speech_style,
            quirks=profile.quirks,
            lawful_chaotic=profile.lawful_chaotic,
            good_evil=profile.good_evil,
        )

    def get_or_create_profile(
        self,
        entity_id: UUID,
        default_traits: dict[str, int] | None = None,
    ) -> NPCProfile:
        """
        Get an existing profile or create a default one.

        Note: Default profiles created by this method are NOT automatically
        persisted to the database. Call save_profile() explicitly if you
        want to persist a newly created profile.

        Args:
            entity_id: The entity to get/create profile for
            default_traits: Optional default trait values (openness, conscientiousness, etc.)

        Returns:
            The loaded or newly created profile
        """
        profile = self.get_profile(entity_id)
        if profile:
            return profile

        # Create default profile
        traits = default_traits or {}
        profile = create_npc_profile(
            entity_id,
            openness=traits.get("openness", 50),
            conscientiousness=traits.get("conscientiousness", 50),
            extraversion=traits.get("extraversion", 50),
            agreeableness=traits.get("agreeableness", 50),
            neuroticism=traits.get("neuroticism", 50),
        )

        # Don't persist default profiles - let them be created explicitly
        return profile

    def decide_action(
        self,
        context: NPCDecisionContext,
        available_actions: list[ActionType] | None = None,
    ) -> DecisionResult:
        """
        Determine what action an NPC should take.

        Uses weighted scoring across motivation, relationship, personality,
        and risk factors to select the best action.

        Args:
            context: Everything the NPC knows about the current situation
            available_actions: Optional filter for available actions

        Returns:
            The selected action with scoring details
        """
        # Default to all actions if not specified
        if available_actions is None:
            available_actions = list(ActionType)

        # Generate action options
        options: list[ActionOption] = []

        for action_type in available_actions:
            # Determine target (use first hostile for attacks, first ally for help)
            target_id = self._select_target(action_type, context)

            # Score the action
            motivation = _score_motivation(action_type, context.npc_profile.motivations)
            relationship = _score_relationship(action_type, context.relationships, target_id)
            personality = _score_personality(action_type, context.npc_profile)
            risk = _assess_risk(action_type, context)

            option = ActionOption(
                action_type=action_type,
                target_id=target_id,
                description=f"{action_type.value}",
                motivation_score=motivation,
                relationship_score=relationship,
                personality_score=personality,
                risk_score=risk,
            )
            options.append(option)

        # Sort by total score
        options.sort(key=lambda x: x.total_score, reverse=True)

        # Add some randomness based on personality
        # High neuroticism = more erratic choices
        if (
            context.npc_profile.traits.neuroticism > ERRATIC_NEUROTICISM_THRESHOLD
            and len(options) > 1
            and random.random() < ERRATIC_CHOICE_PROBABILITY
        ):
            options[0], options[1] = options[1], options[0]

        best = options[0]
        return DecisionResult(
            action=best,
            reasoning=self._explain_decision(best, context),
            alternatives_considered=len(options),
        )

    def _select_target(
        self,
        action_type: ActionType,
        context: NPCDecisionContext,
    ) -> UUID | None:
        """Select an appropriate target for the action."""
        entities = context.entities_present

        if action_type in [ActionType.ATTACK, ActionType.THREATEN, ActionType.INTIMIDATE]:
            # Target most threatening entity
            threats = [
                e for e in entities if e.apparent_threat > THREAT_THRESHOLD and not e.is_player
            ]
            if threats:
                threats.sort(key=lambda x: x.apparent_threat, reverse=True)
                return threats[0].id
            # Or target player if no other threats
            players = [e for e in entities if e.is_player]
            if players:
                return players[0].id

        if action_type in [ActionType.HELP, ActionType.HEAL, ActionType.PROTECT]:
            # Target injured allies
            allies = [e for e in entities if e.hp_percentage is not None and e.hp_percentage < 1.0]
            if allies:
                allies.sort(key=lambda x: x.hp_percentage or 1.0)
                return allies[0].id

        if action_type in [ActionType.NEGOTIATE, ActionType.PERSUADE, ActionType.DECEIVE]:
            # Target player or first entity
            players = [e for e in entities if e.is_player]
            if players:
                return players[0].id
            if entities:
                return entities[0].id

        return None

    def _explain_decision(
        self,
        action: ActionOption,
        context: NPCDecisionContext,
    ) -> str:
        """Generate a brief explanation for the decision."""
        parts = []

        # Motivation explanation
        if action.motivation_score > 0.6:
            motivation = context.npc_profile.get_primary_motivation()
            parts.append(f"aligns with {motivation.value}")

        # Personality explanation
        if action.personality_score > 0.6:
            parts.append("fits personality")

        # Risk explanation
        if action.risk_score > 0.7:
            parts.append("despite high risk")
        elif action.risk_score < 0.2:
            parts.append("low risk")

        if parts:
            return f"Chose {action.action_type.value}: {', '.join(parts)}"
        return f"Chose {action.action_type.value}"

    def form_memory(
        self,
        npc_id: UUID,
        event: Event,
        emotional_valence: float | None = None,
    ) -> MemoryFormationResult:
        """
        Create a memory from an event if significant enough.

        Args:
            npc_id: The NPC forming the memory
            event: The event to potentially remember
            emotional_valence: Override emotional valence (-1 to 1)

        Returns:
            Result indicating if memory was formed
        """
        # Calculate importance based on event type
        importance = self._calculate_importance(event, npc_id)

        # Skip trivial events
        if importance < 0.3:
            return MemoryFormationResult(
                formed=False,
                reason="Event not significant enough to remember",
            )

        # Determine memory type
        memory_type = self._event_to_memory_type(event)

        # Calculate emotional valence if not provided
        if emotional_valence is None:
            emotional_valence = self._calculate_emotional_valence(event, npc_id)

        # Create memory
        memory = create_memory(
            npc_id=npc_id,
            memory_type=memory_type,
            description=event.narrative_summary or f"{event.event_type.value} event",
            subject_id=event.actor_id if event.actor_id != npc_id else event.target_id,
            emotional_valence=emotional_valence,
            importance=importance,
            event_id=event.id,
        )

        return MemoryFormationResult(
            formed=True,
            memory=memory,
            reason=f"Formed {memory_type.value} memory with importance {importance:.2f}",
        )

    def _calculate_importance(self, event: Event, npc_id: UUID) -> float:
        """Calculate how important an event is to an NPC."""
        importance = 0.5

        # Events targeting the NPC are more important
        if event.target_id == npc_id:
            importance += 0.3

        # Combat events are highly important
        if event.event_type in [
            EventType.ATTACK,
            EventType.DAMAGE,
            EventType.DEATH,
            EventType.COMBAT_START,
        ]:
            importance += 0.3

        # Social events matter
        if event.event_type in [EventType.DIALOGUE, EventType.PERSUASION, EventType.INTIMIDATION]:
            importance += 0.2

        # Outcome affects importance
        if (
            event.outcome == EventOutcome.CRITICAL_SUCCESS
            or event.outcome == EventOutcome.CRITICAL_FAILURE
        ):
            importance += 0.2

        return min(1.0, importance)

    def _event_to_memory_type(self, event: Event) -> MemoryType:
        """Map event type to memory type."""
        mapping = {
            EventType.DIALOGUE: MemoryType.DIALOGUE,
            EventType.ATTACK: MemoryType.ACTION,
            EventType.DAMAGE: MemoryType.ACTION,
            EventType.DEATH: MemoryType.OBSERVATION,
            EventType.SKILL_CHECK: MemoryType.OBSERVATION,
            EventType.TRAVEL: MemoryType.OBSERVATION,
            EventType.PERSUASION: MemoryType.DIALOGUE,
            EventType.INTIMIDATION: MemoryType.EMOTION,
        }
        return mapping.get(event.event_type, MemoryType.OBSERVATION)

    def _calculate_emotional_valence(self, event: Event, npc_id: UUID) -> float:
        """Calculate emotional response to an event."""
        valence = 0.0

        # Positive outcomes feel good, negative feel bad
        if event.outcome == EventOutcome.SUCCESS:
            valence = 0.3
        elif event.outcome == EventOutcome.CRITICAL_SUCCESS:
            valence = 0.7
        elif event.outcome == EventOutcome.FAILURE:
            valence = -0.3
        elif event.outcome == EventOutcome.CRITICAL_FAILURE:
            valence = -0.7

        # Being the target of damage is negative
        if event.target_id == npc_id and event.event_type == EventType.DAMAGE:
            valence = min(-0.5, valence - 0.5)

        # Being helped is positive
        if event.target_id == npc_id and event.event_type == EventType.HEAL:
            valence = max(0.5, valence + 0.5)

        return max(-1.0, min(1.0, valence))

    def update_relationship(
        self,
        npc_id: UUID,
        target_id: UUID,
        event: Event,
        persist: bool = True,
    ) -> RelationshipDelta:
        """
        Update NPC's relationship based on an event.

        Calculates relationship changes and optionally persists them to Neo4j.
        If no relationship exists, creates a KNOWS relationship.

        Args:
            npc_id: The NPC whose relationship is updated
            target_id: The entity the relationship is with
            event: The event affecting the relationship
            persist: Whether to persist changes to Neo4j

        Returns:
            The change in relationship metrics
        """
        trust_change = 0.0
        strength_change = 0.0

        # Actions targeting the NPC affect trust
        if event.target_id == npc_id:
            if event.event_type == EventType.DAMAGE:
                trust_change = -0.2
                strength_change = 0.1  # Relationship becomes more intense
            elif event.event_type == EventType.HEAL:
                trust_change = 0.2
                strength_change = 0.1

        # Witnessing actions affects trust less
        elif event.actor_id == target_id:
            if event.event_type == EventType.DAMAGE:
                trust_change = -0.1
            elif event.event_type == EventType.HEAL:
                trust_change = 0.1

        # Dialogue affects relationships
        if event.event_type == EventType.DIALOGUE:
            strength_change = 0.05

        # Social skill checks affect trust
        if event.event_type == EventType.PERSUASION:
            if event.outcome in [EventOutcome.SUCCESS, EventOutcome.CRITICAL_SUCCESS]:
                trust_change += 0.1
            else:
                trust_change -= 0.05
        elif event.event_type == EventType.INTIMIDATION:
            if event.outcome in [EventOutcome.SUCCESS, EventOutcome.CRITICAL_SUCCESS]:
                trust_change -= 0.15  # Intimidation hurts trust even when successful
                strength_change += 0.1
        elif event.event_type == EventType.DECEPTION:
            # If deception is discovered later, this would change
            pass

        delta = RelationshipDelta(
            target_id=target_id,
            trust_change=trust_change,
            strength_change=strength_change,
        )

        # Persist changes if requested
        if persist and (trust_change != 0.0 or strength_change != 0.0):
            self._apply_relationship_delta(npc_id, target_id, event.universe_id, delta)

        return delta

    def _apply_relationship_delta(
        self,
        npc_id: UUID,
        target_id: UUID,
        universe_id: UUID,
        delta: RelationshipDelta,
    ) -> None:
        """
        Apply a relationship delta to the database.

        Creates a KNOWS relationship if none exists.
        """
        from src.models.relationships import Relationship

        # Try to find existing relationship
        existing = self.neo4j.get_relationship_between(
            from_entity_id=npc_id,
            to_entity_id=target_id,
            universe_id=universe_id,
        )

        if existing:
            # Update existing relationship
            new_trust = (existing.trust or 0.0) + delta.trust_change
            new_strength = existing.strength + delta.strength_change

            # Clamp values
            existing.trust = max(-1.0, min(1.0, new_trust))
            existing.strength = max(0.0, min(1.0, new_strength))

            self.neo4j.update_relationship(existing)
        else:
            # Create new KNOWS relationship
            new_rel = Relationship(
                universe_id=universe_id,
                from_entity_id=npc_id,
                to_entity_id=target_id,
                relationship_type=RelationshipType.KNOWS,
                strength=max(0.0, min(1.0, 0.5 + delta.strength_change)),
                trust=max(-1.0, min(1.0, delta.trust_change)),
            )
            self.neo4j.create_relationship(new_rel)

    def get_combat_action(
        self,
        npc_profile: NPCProfile,
        evaluation: CombatEvaluation,
    ) -> CombatState:
        """
        Determine NPC's combat behavior state.

        Pure symbolic - no LLM needed.

        Args:
            npc_profile: The NPC's personality profile
            evaluation: Current combat situation

        Returns:
            The recommended combat state
        """
        return get_combat_state(npc_profile, evaluation)

    def build_combat_evaluation(
        self,
        npc_id: UUID,
        npc_hp_percentage: float,
        entities_present: list[EntitySummary],
        relationships: list[RelationshipSummary],
        escape_routes: int = 1,
        resources_remaining: float = 1.0,
    ) -> CombatEvaluation:
        """
        Build a combat evaluation from current game state.

        Analyzes entities present to determine threat levels and ally status
        based on the NPC's relationships.

        Args:
            npc_id: The NPC evaluating the combat situation
            npc_hp_percentage: NPC's current HP as 0.0-1.0
            entities_present: Entities in the combat area
            relationships: NPC's relationships with other entities
            escape_routes: Number of available escape routes
            resources_remaining: NPC's remaining resources (spell slots, etc.)

        Returns:
            CombatEvaluation with threat and ally assessments
        """
        # Build relationship lookup for quick access
        rel_lookup: dict[UUID, RelationshipSummary] = {r.target_id: r for r in relationships}

        # Categorize entities as enemies or allies
        enemies: list[EntitySummary] = []
        allies: list[EntitySummary] = []

        for entity in entities_present:
            if entity.id == npc_id:
                continue  # Skip self

            rel = rel_lookup.get(entity.id)

            # Determine if enemy or ally based on relationship
            if rel:
                if rel.relationship_type in ["HOSTILE_TO", "FEARS"]:
                    enemies.append(entity)
                elif rel.relationship_type in ["ALLIED_WITH", "RESPECTS"]:
                    allies.append(entity)
                elif rel.trust < -0.3:
                    # Distrusted entities are treated as potential enemies
                    enemies.append(entity)
                elif rel.trust > 0.3:
                    allies.append(entity)
                else:
                    # Neutral - treat as potential threat if they appear threatening
                    if entity.apparent_threat > THREAT_THRESHOLD:
                        enemies.append(entity)
            else:
                # No relationship - use apparent threat
                if entity.apparent_threat > THREAT_THRESHOLD:
                    enemies.append(entity)

        # Calculate threat metrics
        strongest_threat = 0.0
        total_threat = 0.0
        for enemy in enemies:
            threat = enemy.apparent_threat
            strongest_threat = max(strongest_threat, threat)
            total_threat += threat

        # Normalize total threat to 0-1 range (cap at 1.0)
        total_threat = min(1.0, total_threat)

        # Calculate ally health average
        ally_health_avg = 1.0
        if allies:
            ally_health_sum = sum(a.hp_percentage or 1.0 for a in allies)
            ally_health_avg = ally_health_sum / len(allies)

        return CombatEvaluation(
            hp_percentage=npc_hp_percentage,
            resources_remaining=resources_remaining,
            escape_routes=escape_routes,
            enemies_count=len(enemies),
            strongest_enemy_threat=strongest_threat,
            total_enemy_threat=total_threat,
            allies_count=len(allies),
            ally_health_average=ally_health_avg,
        )

    def get_npc_combat_turn(
        self,
        npc_id: UUID,
        npc_profile: NPCProfile,
        evaluation: CombatEvaluation,
        entities_present: list[EntitySummary],
        relationships: list[RelationshipSummary],
    ) -> CombatTurnResult:
        """
        Determine the NPC's action for this combat turn.

        Translates the high-level CombatState into a concrete action
        with target selection based on the tactical situation.

        Args:
            npc_id: The NPC taking the turn
            npc_profile: NPC's personality profile
            evaluation: Current combat evaluation
            entities_present: Entities in the combat area
            relationships: NPC's relationships

        Returns:
            CombatTurnResult with action and target
        """
        # Get combat state from personality + evaluation
        combat_state = self.get_combat_action(npc_profile, evaluation)

        # Build relationship lookup
        rel_lookup: dict[UUID, RelationshipSummary] = {r.target_id: r for r in relationships}

        # Identify enemies and allies from entities
        enemies: list[EntitySummary] = []
        allies: list[EntitySummary] = []
        injured_allies: list[EntitySummary] = []

        for entity in entities_present:
            if entity.id == npc_id:
                continue

            rel = rel_lookup.get(entity.id)
            is_enemy = False
            is_ally = False

            if rel:
                if rel.relationship_type in ["HOSTILE_TO", "FEARS"] or rel.trust < -0.3:
                    is_enemy = True
                elif rel.relationship_type in ["ALLIED_WITH", "RESPECTS"] or rel.trust > 0.3:
                    is_ally = True
            elif entity.apparent_threat > THREAT_THRESHOLD:
                is_enemy = True

            if is_enemy:
                enemies.append(entity)
            elif is_ally:
                allies.append(entity)
                if entity.hp_percentage is not None and entity.hp_percentage < 0.5:
                    injured_allies.append(entity)

        # Translate combat state to action
        action: ActionType
        target_id: UUID | None = None
        description: str
        should_use_ability = False
        ability_name: str | None = None

        if combat_state == CombatState.AGGRESSIVE:
            action = ActionType.ATTACK
            # Target the strongest threat
            if enemies:
                enemies.sort(key=lambda e: e.apparent_threat, reverse=True)
                target_id = enemies[0].id
                description = f"Attacks {enemies[0].name} aggressively"
            else:
                # No enemies visible, look for targets
                action = ActionType.APPROACH
                description = "Looks for threats to engage"

        elif combat_state == CombatState.DEFENSIVE:
            # Counterattack if enemies present, otherwise defend
            if enemies and evaluation.hp_percentage > 0.3:
                action = ActionType.ATTACK
                # Target the closest/weakest threat for safer engagement
                enemies.sort(key=lambda e: e.hp_percentage or 1.0)
                target_id = enemies[0].id
                description = f"Cautiously attacks {enemies[0].name}"
            else:
                action = ActionType.DEFEND
                description = "Takes a defensive stance"

        elif combat_state == CombatState.TACTICAL:
            # Use abilities if available, otherwise position strategically
            if evaluation.resources_remaining > 0.3 and enemies:
                # Attempt to use an ability
                should_use_ability = True
                ability_name = "tactical_ability"  # Placeholder for actual ability selection
                action = ActionType.ATTACK
                enemies.sort(key=lambda e: e.apparent_threat, reverse=True)
                target_id = enemies[0].id
                description = f"Uses tactical approach against {enemies[0].name}"
            else:
                action = ActionType.DEFEND
                description = "Repositions tactically"

        elif combat_state == CombatState.SUPPORTIVE:
            # Prioritize helping injured allies
            if injured_allies:
                action = ActionType.HEAL
                injured_allies.sort(key=lambda a: a.hp_percentage or 1.0)
                target_id = injured_allies[0].id
                description = f"Moves to help {injured_allies[0].name}"
                should_use_ability = True
                ability_name = "healing"
            elif allies:
                action = ActionType.PROTECT
                # Protect the weakest ally
                allies.sort(key=lambda a: a.hp_percentage or 1.0)
                target_id = allies[0].id
                description = f"Protects {allies[0].name}"
            else:
                # No allies, fall back to defensive
                action = ActionType.DEFEND
                description = "Takes a defensive stance"

        elif combat_state == CombatState.FLEEING:
            action = ActionType.FLEE
            description = "Attempts to escape"

        elif combat_state == CombatState.SURRENDERING:
            action = ActionType.SURRENDER
            description = "Surrenders"

        else:
            # Default fallback
            action = ActionType.DEFEND
            description = "Takes a defensive stance"

        return CombatTurnResult(
            combat_state=combat_state,
            action=action,
            target_id=target_id,
            description=description,
            should_use_ability=should_use_ability,
            ability_name=ability_name,
        )

    def build_dialogue_constraints(
        self,
        profile: NPCProfile,
        relationships: list[RelationshipSummary],
        memories: list[NPCMemory],
        in_combat: bool = False,
    ) -> DialogueConstraints:
        """
        Build constraints for LLM dialogue generation.

        Args:
            profile: NPC's personality profile
            relationships: Relevant relationships
            memories: Relevant memories
            in_combat: Whether currently in combat

        Returns:
            Constraints for prompting the LLM
        """
        # Calculate trust toward player
        player_trust = 0.0
        for rel in relationships:
            if rel.relationship_type in ["ALLIED_WITH", "RESPECTS"]:
                player_trust = max(player_trust, rel.trust)
            elif rel.relationship_type in ["HOSTILE_TO", "FEARS"]:
                player_trust = min(player_trust, -rel.trust)

        # Calculate emotional valence from recent memories
        emotional_valence = 0.0
        if memories:
            recent_emotions = [m.emotional_valence for m in memories[-5:]]
            emotional_valence = sum(recent_emotions) / len(recent_emotions)

        # Build constraints
        constraints = DialogueConstraints.from_context(
            profile=profile,
            player_trust=player_trust,
            emotional_valence=emotional_valence,
            in_combat=in_combat,
        )

        # Add topics from memories
        for memory in memories:
            if memory.importance > 0.7:
                constraints.topics_to_mention.append(memory.description[:50])

        return constraints

    def retrieve_memories(
        self,
        npc_id: UUID,
        context_description: str,
        limit: int = 5,
        subject_id: UUID | None = None,
    ) -> list[NPCMemory]:
        """
        Retrieve relevant memories for the current context.

        Scores memories by:
        - Relevance: Keyword overlap with context (future: vector similarity)
        - Recency: More recent memories score higher
        - Importance: Life-changing events score higher
        - Emotional intensity: Strong emotions are more memorable

        Args:
            npc_id: The NPC to retrieve memories for
            context_description: Description of current context
            limit: Maximum memories to return
            subject_id: Optional entity to filter memories about

        Returns:
            Relevant memories sorted by retrieval score
        """
        # Get memories from Neo4j
        if subject_id:
            memories = self.neo4j.get_memories_about_entity(
                npc_id=npc_id,
                subject_id=subject_id,
                limit=limit * MEMORY_PREFETCH_MULTIPLIER,  # Fetch more to allow scoring
            )
        else:
            memories = self.neo4j.get_memories_for_npc(
                npc_id=npc_id,
                limit=limit * MEMORY_PREFETCH_MULTIPLIER,
            )

        if not memories:
            return []

        # Score each memory
        scored_memories: list[tuple[NPCMemory, float]] = []
        context_keywords = _extract_keywords(context_description)

        for memory in memories:
            # Calculate keyword-based relevance (future: vector similarity)
            relevance = _calculate_keyword_relevance(memory.description, context_keywords)

            # Use the model's retrieval score calculation
            score = memory.calculate_retrieval_score(relevance=relevance)
            scored_memories.append((memory, score))

        # Sort by score descending
        scored_memories.sort(key=lambda x: x[1], reverse=True)

        # Return top N and mark them as recalled
        result = []
        for memory, _score in scored_memories[:limit]:
            memory.recall()
            self.neo4j.update_memory_recall(memory.id)
            result.append(memory)

        return result

    async def generate_dialogue(
        self,
        npc_id: UUID,
        player_input: str,
        profile: NPCProfile,
        relationships: list[RelationshipSummary],
        situation: str,
        in_combat: bool = False,
    ) -> str:
        """
        Generate NPC dialogue response using LLM.

        Uses personality constraints to guide the LLM output,
        ensuring responses are consistent with the NPC's character.

        Args:
            npc_id: The NPC generating dialogue
            player_input: What the player said
            profile: NPC's personality profile
            relationships: Relevant relationships
            situation: Description of current situation
            in_combat: Whether currently in combat

        Returns:
            Generated dialogue response, or fallback if LLM unavailable
        """
        # Retrieve relevant memories
        memories = self.retrieve_memories(npc_id, player_input, limit=5)

        # Build dialogue constraints
        constraints = self.build_dialogue_constraints(
            profile=profile,
            relationships=relationships,
            memories=memories,
            in_combat=in_combat,
        )

        # If no LLM available, use fallback
        if self.llm is None or not self.llm.is_available:
            return self._fallback_dialogue(profile, constraints, player_input)

        # Get NPC name (would need entity lookup in real implementation)
        npc_name = f"NPC-{str(npc_id)[:8]}"
        npc_description = f"a {constraints.speech_style} character"

        # Format memories for prompt
        memory_strings = [m.description for m in memories]

        # Format constraints
        constraint_strings = []
        if constraints.topics_to_mention:
            constraint_strings.append(
                f"Try to mention: {', '.join(constraints.topics_to_mention[:3])}"
            )
        if constraints.topics_to_avoid:
            constraint_strings.append(
                f"Avoid mentioning: {', '.join(constraints.topics_to_avoid[:3])}"
            )

        try:
            return await self.llm.generate_dialogue(
                npc_name=npc_name,
                npc_description=npc_description,
                speech_style=constraints.speech_style,
                verbosity=constraints.verbosity,
                formality=constraints.formality,
                attitude=constraints.attitude_toward_player,
                trust_level=constraints.trust_level,
                emotional_state=constraints.emotional_state,
                urgency=constraints.urgency,
                memories=memory_strings,
                player_input=player_input,
                situation=situation,
                constraints=constraint_strings if constraint_strings else None,
            )
        except Exception:
            # Fallback on any error
            return self._fallback_dialogue(profile, constraints, player_input)

    def _fallback_dialogue(
        self,
        profile: NPCProfile,
        constraints: DialogueConstraints,
        player_input: str,
    ) -> str:
        """
        Generate template-based dialogue when LLM is unavailable.

        Args:
            profile: NPC's personality profile
            constraints: Dialogue constraints
            player_input: What the player said

        Returns:
            Simple template-based response
        """
        # Detect greeting
        greetings = ["hello", "hi", "greetings", "hey", "good morning", "good evening"]
        if any(g in player_input.lower() for g in greetings):
            if constraints.attitude_toward_player == "friendly":
                return "Well met, friend!"
            elif constraints.attitude_toward_player == "hostile":
                return "*glares* What do you want?"
            else:
                return "Hello, traveler."

        # Detect question
        if "?" in player_input or player_input.lower().startswith(
            ("who", "what", "where", "when", "why", "how")
        ):
            if constraints.trust_level == "suspicious":
                return "I don't know anything about that. And even if I did, why would I tell you?"
            elif constraints.trust_level == "trusting":
                return "Hmm, let me think about that..."
            else:
                return "I'm not sure I can help you with that."

        # Detect threat/intimidation
        if any(t in player_input.lower() for t in ["threat", "kill", "hurt", "attack"]):
            if profile.traits.agreeableness > 60:
                return "Please, there's no need for violence!"
            elif profile.traits.neuroticism > 60:
                return "*backs away nervously* L-leave me alone!"
            else:
                return "*stands firm* You don't scare me."

        # Default response based on attitude
        if constraints.attitude_toward_player == "friendly":
            return "Interesting. Tell me more."
        elif constraints.attitude_toward_player == "hostile":
            return "*grunts dismissively*"
        else:
            return "I see."
