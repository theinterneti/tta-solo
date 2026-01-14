"""
NPC Service for TTA-Solo.

Orchestrates NPC decision-making, memory formation, and behavior.
This is the symbolic layer that drives NPC intelligence.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
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
    MemoryType,
    Motivation,
    NPCDecisionContext,
    NPCMemory,
    NPCProfile,
    RelationshipSummary,
    create_memory,
    get_combat_state,
)
from src.models.relationships import RelationshipType

if TYPE_CHECKING:
    pass


# =============================================================================
# Text Relevance Helpers
# =============================================================================

# Common stop words to exclude from keyword extraction
_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "need", "dare",
    "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by",
    "from", "as", "into", "through", "during", "before", "after", "above",
    "below", "between", "under", "again", "further", "then", "once", "here",
    "there", "when", "where", "why", "how", "all", "each", "few", "more",
    "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "just", "and", "but", "if", "or",
    "because", "until", "while", "this", "that", "these", "those", "i",
    "you", "he", "she", "it", "we", "they", "what", "which", "who", "whom",
})


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
    # Boost: any overlap is significant
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
    enemies = [e for e in context.entities_present if e.apparent_threat > 0.5]
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
    """

    dolt: DoltRepository
    neo4j: Neo4jRepository

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
            motivation = _score_motivation(
                action_type, context.npc_profile.motivations
            )
            relationship = _score_relationship(
                action_type, context.relationships, target_id
            )
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
        # High neuroticism = more erratic choices (20% chance to pick second-best)
        if (
            context.npc_profile.traits.neuroticism > 70
            and len(options) > 1
            and random.random() < 0.2
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
            threats = [e for e in entities if e.apparent_threat > 0.5 and not e.is_player]
            if threats:
                threats.sort(key=lambda x: x.apparent_threat, reverse=True)
                return threats[0].id
            # Or target player if no other threats
            players = [e for e in entities if e.is_player]
            if players:
                return players[0].id

        if action_type in [ActionType.HELP, ActionType.HEAL, ActionType.PROTECT]:
            # Target injured allies
            allies = [
                e for e in entities
                if e.hp_percentage is not None and e.hp_percentage < 1.0
            ]
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
        if event.outcome == EventOutcome.CRITICAL_SUCCESS or event.outcome == EventOutcome.CRITICAL_FAILURE:
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
    ) -> RelationshipDelta:
        """
        Update NPC's relationship based on an event.

        Args:
            npc_id: The NPC whose relationship is updated
            target_id: The entity the relationship is with
            event: The event affecting the relationship

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

        return RelationshipDelta(
            target_id=target_id,
            trust_change=trust_change,
            strength_change=strength_change,
        )

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
                limit=limit * 3,  # Fetch more to allow scoring
            )
        else:
            memories = self.neo4j.get_memories_for_npc(
                npc_id=npc_id,
                limit=limit * 3,
            )

        if not memories:
            return []

        # Score each memory
        scored_memories: list[tuple[NPCMemory, float]] = []
        context_keywords = _extract_keywords(context_description)

        for memory in memories:
            # Calculate keyword-based relevance (future: vector similarity)
            relevance = _calculate_keyword_relevance(
                memory.description, context_keywords
            )

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
