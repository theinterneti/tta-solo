"""
NPC AI Models for TTA-Solo.

Defines personality traits, motivations, and profiles that drive NPC behavior.
Based on the Big Five personality model for consistent, believable characters.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class PersonalityTraits(BaseModel):
    """
    Big Five personality model for NPCs.

    Each trait is scored 0-100:
    - 0-30: Low (trait is weak or absent)
    - 31-70: Average (trait is moderate)
    - 71-100: High (trait is strong or dominant)
    """

    openness: Annotated[int, Field(ge=0, le=100)] = 50
    """High: Creative, curious, open to new ideas. Low: Practical, conventional, prefers routine."""

    conscientiousness: Annotated[int, Field(ge=0, le=100)] = 50
    """High: Organized, disciplined, reliable. Low: Spontaneous, flexible, careless."""

    extraversion: Annotated[int, Field(ge=0, le=100)] = 50
    """High: Outgoing, energetic, talkative. Low: Reserved, solitary, quiet."""

    agreeableness: Annotated[int, Field(ge=0, le=100)] = 50
    """High: Friendly, compassionate, cooperative. Low: Competitive, suspicious, antagonistic."""

    neuroticism: Annotated[int, Field(ge=0, le=100)] = 50
    """High: Anxious, moody, easily stressed. Low: Calm, stable, resilient."""

    def get_speech_verbosity(self) -> str:
        """Derive speech verbosity from extraversion."""
        if self.extraversion < 30:
            return "terse"
        elif self.extraversion > 70:
            return "verbose"
        return "normal"

    def get_formality(self) -> str:
        """Derive formality from conscientiousness."""
        if self.conscientiousness < 30:
            return "casual"
        elif self.conscientiousness > 70:
            return "formal"
        return "neutral"

    def get_risk_tolerance(self) -> float:
        """
        Calculate risk tolerance (0.0-1.0).

        High neuroticism = risk averse, high openness = risk seeking.
        """
        base = 0.5
        base -= (self.neuroticism - 50) / 200  # -0.25 to +0.25
        base += (self.openness - 50) / 200  # -0.25 to +0.25
        return max(0.0, min(1.0, base))


class Motivation(str, Enum):
    """
    What drives an NPC's behavior and goals.

    NPCs have 1-3 motivations, ranked by priority.
    """

    # Self-preservation
    SURVIVAL = "survival"
    SAFETY = "safety"

    # Material
    WEALTH = "wealth"
    POWER = "power"
    COMFORT = "comfort"

    # Social
    LOVE = "love"
    BELONGING = "belonging"
    RESPECT = "respect"
    FAME = "fame"

    # Higher purpose
    KNOWLEDGE = "knowledge"
    JUSTICE = "justice"
    DUTY = "duty"
    FAITH = "faith"
    REVENGE = "revenge"

    # Creative
    ARTISTRY = "artistry"
    LEGACY = "legacy"


class NPCProfile(BaseModel):
    """
    Complete NPC personality and motivation profile.

    This is the core data that drives NPC decision-making and dialogue.
    """

    entity_id: UUID
    """The entity this profile belongs to."""

    # Personality
    traits: PersonalityTraits = Field(default_factory=PersonalityTraits)
    """Big Five personality traits."""

    # Motivations (ordered by priority)
    motivations: Annotated[list[Motivation], Field(max_length=3)] = Field(
        default_factory=lambda: [Motivation.SURVIVAL]
    )
    """Up to 3 motivations, ordered by priority."""

    # Behavioral quirks (free-form for LLM)
    quirks: list[str] = Field(default_factory=list)
    """Unique behavioral quirks, e.g., "speaks in third person", "obsessed with cleanliness"."""

    # Speech patterns
    speech_style: str = "neutral"
    """Speech style hint for dialogue generation: "formal", "crude", "poetic", "terse", etc."""

    # Alignment tendency (soft guidance, not strict)
    lawful_chaotic: Annotated[int, Field(ge=-100, le=100)] = 0
    """-100 = chaotic, +100 = lawful. Affects rule-following behavior."""

    good_evil: Annotated[int, Field(ge=-100, le=100)] = 0
    """-100 = evil, +100 = good. Affects moral decision-making."""

    def get_primary_motivation(self) -> Motivation:
        """Get the NPC's primary motivation."""
        return self.motivations[0] if self.motivations else Motivation.SURVIVAL

    def is_lawful(self) -> bool:
        """Check if NPC tends toward lawful behavior."""
        return self.lawful_chaotic > 30

    def is_chaotic(self) -> bool:
        """Check if NPC tends toward chaotic behavior."""
        return self.lawful_chaotic < -30

    def is_good(self) -> bool:
        """Check if NPC tends toward good behavior."""
        return self.good_evil > 30

    def is_evil(self) -> bool:
        """Check if NPC tends toward evil behavior."""
        return self.good_evil < -30

    def get_alignment_description(self) -> str:
        """Get a human-readable alignment description."""
        # Law/Chaos axis
        if self.lawful_chaotic > 30:
            lc = "Lawful"
        elif self.lawful_chaotic < -30:
            lc = "Chaotic"
        else:
            lc = "Neutral"

        # Good/Evil axis
        if self.good_evil > 30:
            ge = "Good"
        elif self.good_evil < -30:
            ge = "Evil"
        else:
            ge = "Neutral"

        # Combine
        if lc == "Neutral" and ge == "Neutral":
            return "True Neutral"
        return f"{lc} {ge}"


class MemoryType(str, Enum):
    """Types of memories NPCs can form."""

    ENCOUNTER = "encounter"
    """Met this entity."""

    DIALOGUE = "dialogue"
    """What was said."""

    ACTION = "action"
    """What someone did."""

    OBSERVATION = "observation"
    """What they witnessed."""

    RUMOR = "rumor"
    """Heard from others."""

    EMOTION = "emotion"
    """How they felt."""


class NPCMemory(BaseModel):
    """
    A single memory held by an NPC.

    Memories influence NPC behavior and are retrieved based on
    relevance, recency, importance, and emotional intensity.
    """

    id: UUID = Field(default_factory=uuid4)
    """Unique identifier for this memory."""

    npc_id: UUID
    """The NPC who holds this memory."""

    memory_type: MemoryType
    """What kind of memory this is."""

    # What happened
    subject_id: UUID | None = None
    """Entity this memory is about (if applicable)."""

    description: str
    """Brief description of the memory."""

    # Emotional impact
    emotional_valence: Annotated[float, Field(ge=-1.0, le=1.0)] = 0.0
    """-1.0 = very negative, +1.0 = very positive."""

    importance: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5
    """0.0 = trivial, 1.0 = life-changing."""

    # Temporal
    event_id: UUID | None = None
    """Linked event if applicable."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    """When this memory was formed."""

    # Decay tracking
    times_recalled: int = 0
    """Number of times this memory has been accessed."""

    last_recalled: datetime | None = None
    """When this memory was last accessed."""

    def recall(self) -> None:
        """Mark this memory as recalled, updating decay tracking."""
        self.times_recalled += 1
        self.last_recalled = datetime.now(UTC)

    def calculate_retrieval_score(
        self,
        relevance: float = 0.5,
        recency_weight: float = 0.25,
        importance_weight: float = 0.25,
        emotion_weight: float = 0.25,
        relevance_weight: float = 0.25,
    ) -> float:
        """
        Calculate how likely this memory is to be retrieved.

        Higher scores mean the memory is more accessible.

        Args:
            relevance: Semantic similarity to current context (0-1)
            recency_weight: How much recency affects retrieval
            importance_weight: How much importance affects retrieval
            emotion_weight: How much emotional intensity affects retrieval
            relevance_weight: How much semantic relevance affects retrieval

        Returns:
            Retrieval score (higher = more likely to retrieve)
        """
        now = datetime.now(UTC)
        age_hours = (now - self.timestamp).total_seconds() / 3600

        # Recency decay: memories fade over time
        # Half-life of ~24 hours for unimportant memories
        recency = 1.0 / (1.0 + age_hours / 24.0)

        # Emotional intensity (absolute value)
        emotion_intensity = abs(self.emotional_valence)

        # Weighted sum
        score = (
            recency * recency_weight
            + self.importance * importance_weight
            + emotion_intensity * emotion_weight
            + relevance * relevance_weight
        )

        # Boost for frequently recalled memories (rehearsal effect)
        rehearsal_bonus = min(0.2, self.times_recalled * 0.02)
        score += rehearsal_bonus

        return min(1.0, score)


# =============================================================================
# Factory Functions
# =============================================================================


def create_npc_profile(
    entity_id: UUID,
    *,
    openness: int = 50,
    conscientiousness: int = 50,
    extraversion: int = 50,
    agreeableness: int = 50,
    neuroticism: int = 50,
    motivations: list[Motivation] | None = None,
    quirks: list[str] | None = None,
    speech_style: str = "neutral",
    lawful_chaotic: int = 0,
    good_evil: int = 0,
) -> NPCProfile:
    """
    Create an NPC profile with the given traits.

    Args:
        entity_id: The entity this profile belongs to
        openness: Openness to experience (0-100)
        conscientiousness: Organization and discipline (0-100)
        extraversion: Sociability and energy (0-100)
        agreeableness: Cooperation and friendliness (0-100)
        neuroticism: Anxiety and emotional instability (0-100)
        motivations: Up to 3 motivations, in priority order
        quirks: Behavioral quirks for dialogue generation
        speech_style: How the NPC speaks
        lawful_chaotic: -100 (chaotic) to +100 (lawful)
        good_evil: -100 (evil) to +100 (good)

    Returns:
        A new NPCProfile instance
    """
    return NPCProfile(
        entity_id=entity_id,
        traits=PersonalityTraits(
            openness=openness,
            conscientiousness=conscientiousness,
            extraversion=extraversion,
            agreeableness=agreeableness,
            neuroticism=neuroticism,
        ),
        motivations=motivations or [Motivation.SURVIVAL],
        quirks=quirks or [],
        speech_style=speech_style,
        lawful_chaotic=lawful_chaotic,
        good_evil=good_evil,
    )


def create_memory(
    npc_id: UUID,
    memory_type: MemoryType,
    description: str,
    *,
    subject_id: UUID | None = None,
    emotional_valence: float = 0.0,
    importance: float = 0.5,
    event_id: UUID | None = None,
) -> NPCMemory:
    """
    Create a new NPC memory.

    Args:
        npc_id: The NPC who holds this memory
        memory_type: What kind of memory this is
        description: Brief description of the memory
        subject_id: Entity this memory is about
        emotional_valence: -1.0 (negative) to +1.0 (positive)
        importance: 0.0 (trivial) to 1.0 (life-changing)
        event_id: Linked event if applicable

    Returns:
        A new NPCMemory instance
    """
    return NPCMemory(
        npc_id=npc_id,
        memory_type=memory_type,
        description=description,
        subject_id=subject_id,
        emotional_valence=emotional_valence,
        importance=importance,
        event_id=event_id,
    )


# =============================================================================
# Decision Making Models (Phase 2)
# =============================================================================


class EntitySummary(BaseModel):
    """
    Lightweight summary of an entity for NPC decision context.

    Used to provide relevant info without loading full entity data.
    """

    id: UUID
    name: str
    entity_type: str  # "character", "location", "item", "faction"
    description: str = ""
    is_player: bool = False

    # For characters
    hp_percentage: float | None = None  # 0.0 to 1.0
    apparent_threat: float = Field(
        default=0.5, ge=0.0, le=1.0, description="How threatening this entity appears"
    )


class RelationshipSummary(BaseModel):
    """
    Lightweight summary of a relationship for NPC decision context.
    """

    target_id: UUID
    target_name: str
    relationship_type: str  # e.g., "ALLIED_WITH", "HOSTILE_TO"
    strength: float = Field(ge=0.0, le=1.0, default=1.0)
    trust: float = Field(ge=-1.0, le=1.0, default=0.0)


class ActionType(str, Enum):
    """Types of actions an NPC can take."""

    # Combat
    ATTACK = "attack"
    DEFEND = "defend"
    FLEE = "flee"
    HIDE = "hide"
    SURRENDER = "surrender"

    # Social
    NEGOTIATE = "negotiate"
    THREATEN = "threaten"
    DECEIVE = "deceive"
    PERSUADE = "persuade"
    INTIMIDATE = "intimidate"

    # Helpful
    HELP = "help"
    HEAL = "heal"
    SHARE = "share"
    WARN = "warn"
    PROTECT = "protect"

    # Neutral
    OBSERVE = "observe"
    WAIT = "wait"
    IGNORE = "ignore"

    # Movement
    APPROACH = "approach"
    RETREAT = "retreat"
    FOLLOW = "follow"


class ActionOption(BaseModel):
    """
    A potential action an NPC can take.

    The symbolic layer calculates scores, and the highest-scoring
    action is typically selected (with some randomness based on personality).
    """

    # Action scoring weights - these control how different factors influence decisions
    # Motivation is weighted highest because NPCs should primarily act on their goals
    WEIGHT_MOTIVATION: float = 0.35  # How well the action serves NPC's goals
    WEIGHT_RELATIONSHIP: float = 0.25  # Impact on relationships
    WEIGHT_PERSONALITY: float = 0.25  # Consistency with personality traits
    WEIGHT_RISK: float = 0.15  # Risk aversion (inverted in calculation)

    action_type: ActionType
    target_id: UUID | None = None
    description: str

    # Scores (calculated by symbolic layer)
    motivation_score: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    """How well does this serve the NPC's goals?"""

    relationship_score: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    """How does this affect relationships?"""

    personality_score: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    """How consistent with personality?"""

    risk_score: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    """How dangerous is this? (higher = more risky)"""

    @property
    def total_score(self) -> float:
        """
        Combined score for action selection.

        Uses class-level weight constants. Risk is inverted so lower risk = better.
        """
        return (
            self.motivation_score * self.WEIGHT_MOTIVATION
            + self.relationship_score * self.WEIGHT_RELATIONSHIP
            + self.personality_score * self.WEIGHT_PERSONALITY
            + (1.0 - self.risk_score) * self.WEIGHT_RISK
        )


class NPCDecisionContext(BaseModel):
    """
    Everything an NPC knows when making a decision.

    This is the input to the decision-making system.
    """

    # Self
    npc_id: UUID
    npc_profile: NPCProfile
    hp_percentage: float = Field(ge=0.0, le=1.0, default=1.0)
    resources_available: float = Field(
        ge=0.0, le=1.0, default=1.0, description="Spell slots, abilities, etc."
    )

    # Environment
    location_name: str = ""
    danger_level: int = Field(ge=0, le=20, default=0)
    entities_present: list[EntitySummary] = Field(default_factory=list)
    escape_routes: int = Field(ge=0, default=1)

    # Social
    relationships: list[RelationshipSummary] = Field(default_factory=list)
    relevant_memories: list[NPCMemory] = Field(default_factory=list)

    # Situation
    current_events: list[str] = Field(
        default_factory=list, description="What's happening right now"
    )
    player_action: str | None = None  # Natural language description


# =============================================================================
# Combat AI Models
# =============================================================================


class CombatState(str, Enum):
    """NPC combat behavior states."""

    AGGRESSIVE = "aggressive"  # Attack strongest threat
    DEFENSIVE = "defensive"  # Protect self, counterattack only
    TACTICAL = "tactical"  # Use positioning and abilities strategically
    SUPPORTIVE = "supportive"  # Help allies, heal, buff
    FLEEING = "fleeing"  # Trying to escape
    SURRENDERING = "surrendering"  # Giving up


class CombatEvaluation(BaseModel):
    """NPC's assessment of the current combat situation."""

    # Self assessment
    hp_percentage: Annotated[float, Field(ge=0.0, le=1.0)]
    resources_remaining: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0
    escape_routes: int = Field(ge=0, default=1)

    # Threat assessment
    enemies_count: int = Field(ge=0, default=0)
    strongest_enemy_threat: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    total_enemy_threat: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0

    # Ally assessment
    allies_count: int = Field(ge=0, default=0)
    ally_health_average: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0

    @property
    def should_flee(self) -> bool:
        """Determine if NPC should attempt to flee."""
        return (
            self.hp_percentage < 0.25
            and self.total_enemy_threat > 0.5
            and self.escape_routes > 0
        )

    @property
    def should_surrender(self) -> bool:
        """Determine if NPC should surrender."""
        return (
            self.hp_percentage < 0.1
            and self.escape_routes == 0
            and self.allies_count == 0
        )


def get_combat_state(
    npc_profile: NPCProfile,
    evaluation: CombatEvaluation,
) -> CombatState:
    """
    Determine combat behavior based on personality and situation.

    Args:
        npc_profile: The NPC's personality profile
        evaluation: Current combat situation assessment

    Returns:
        The recommended combat state
    """
    # Cowardly NPCs flee earlier (high neuroticism = lower threshold)
    flee_threshold = 0.25 + (npc_profile.traits.neuroticism / 200)

    # Check surrender first (most desperate)
    if evaluation.should_surrender:
        return CombatState.SURRENDERING

    # Check flee conditions
    if evaluation.hp_percentage < flee_threshold:
        if evaluation.escape_routes > 0:
            return CombatState.FLEEING
        return CombatState.SURRENDERING

    # Aggressive NPCs (low agreeableness) attack more
    if npc_profile.traits.agreeableness < 30:
        return CombatState.AGGRESSIVE

    # Protective NPCs (high agreeableness) support allies
    if evaluation.allies_count > 0 and npc_profile.traits.agreeableness > 70:
        return CombatState.SUPPORTIVE

    # Default to tactical
    return CombatState.TACTICAL


# =============================================================================
# Dialogue Generation Models
# =============================================================================


class DialogueConstraints(BaseModel):
    """
    Constraints for LLM dialogue generation.

    The symbolic layer builds these constraints, then the neural layer
    uses them to generate personality-consistent dialogue.
    """

    # From personality
    speech_style: str = "neutral"
    verbosity: str = "normal"  # "terse", "normal", "verbose"
    formality: str = "neutral"  # "casual", "neutral", "formal"

    # From relationship
    attitude_toward_player: str = "neutral"  # "friendly", "neutral", "hostile"
    trust_level: str = "guarded"  # "trusting", "guarded", "suspicious"

    # From situation
    emotional_state: str = "calm"  # "calm", "angry", "afraid", "happy"
    urgency: str = "normal"  # "relaxed", "normal", "urgent"

    # Content constraints
    topics_to_mention: list[str] = Field(default_factory=list)
    topics_to_avoid: list[str] = Field(default_factory=list)
    secrets_known: list[str] = Field(default_factory=list)
    lies_to_tell: list[str] = Field(default_factory=list)

    @classmethod
    def from_context(
        cls,
        profile: NPCProfile,
        player_trust: float = 0.0,
        emotional_valence: float = 0.0,
        in_combat: bool = False,
    ) -> DialogueConstraints:
        """
        Build dialogue constraints from NPC profile and context.

        Args:
            profile: The NPC's personality profile
            player_trust: Trust level toward player (-1 to 1)
            emotional_valence: Current emotional state (-1 to 1)
            in_combat: Whether currently in combat

        Returns:
            DialogueConstraints for LLM prompting
        """
        # Derive verbosity from extraversion
        verbosity = profile.traits.get_speech_verbosity()

        # Derive formality from conscientiousness
        formality = profile.traits.get_formality()

        # Derive attitude from trust
        if player_trust > 0.5:
            attitude = "friendly"
        elif player_trust < -0.5:
            attitude = "hostile"
        else:
            attitude = "neutral"

        # Derive trust level
        if player_trust > 0.3:
            trust_level = "trusting"
        elif player_trust < -0.3:
            trust_level = "suspicious"
        else:
            trust_level = "guarded"

        # Derive emotional state
        if in_combat and emotional_valence < 0:
            emotional_state = "angry"
        elif emotional_valence > 0.5:
            emotional_state = "happy"
        elif emotional_valence < -0.5:
            emotional_state = "afraid" if profile.traits.neuroticism > 50 else "angry"
        else:
            emotional_state = "calm"

        # Urgency based on combat
        urgency = "urgent" if in_combat else "normal"

        return cls(
            speech_style=profile.speech_style,
            verbosity=verbosity,
            formality=formality,
            attitude_toward_player=attitude,
            trust_level=trust_level,
            emotional_state=emotional_state,
            urgency=urgency,
        )
