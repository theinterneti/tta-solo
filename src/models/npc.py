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
