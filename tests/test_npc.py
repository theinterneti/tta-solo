"""Tests for NPC AI models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.models import (
    MemoryType,
    Motivation,
    NPCMemory,
    NPCProfile,
    PersonalityTraits,
    create_memory,
    create_npc_profile,
)


class TestPersonalityTraits:
    """Tests for the PersonalityTraits model."""

    def test_default_values(self) -> None:
        """Test that default values are 50 (average)."""
        traits = PersonalityTraits()
        assert traits.openness == 50
        assert traits.conscientiousness == 50
        assert traits.extraversion == 50
        assert traits.agreeableness == 50
        assert traits.neuroticism == 50

    def test_custom_values(self) -> None:
        """Test setting custom trait values."""
        traits = PersonalityTraits(
            openness=80,
            conscientiousness=20,
            extraversion=90,
            agreeableness=10,
            neuroticism=70,
        )
        assert traits.openness == 80
        assert traits.conscientiousness == 20
        assert traits.extraversion == 90
        assert traits.agreeableness == 10
        assert traits.neuroticism == 70

    def test_trait_bounds(self) -> None:
        """Test that traits must be 0-100."""
        with pytest.raises(ValueError):
            PersonalityTraits(openness=-1)
        with pytest.raises(ValueError):
            PersonalityTraits(openness=101)

    def test_speech_verbosity_terse(self) -> None:
        """Test that low extraversion gives terse speech."""
        traits = PersonalityTraits(extraversion=20)
        assert traits.get_speech_verbosity() == "terse"

    def test_speech_verbosity_verbose(self) -> None:
        """Test that high extraversion gives verbose speech."""
        traits = PersonalityTraits(extraversion=80)
        assert traits.get_speech_verbosity() == "verbose"

    def test_speech_verbosity_normal(self) -> None:
        """Test that average extraversion gives normal speech."""
        traits = PersonalityTraits(extraversion=50)
        assert traits.get_speech_verbosity() == "normal"

    def test_formality_casual(self) -> None:
        """Test that low conscientiousness gives casual formality."""
        traits = PersonalityTraits(conscientiousness=20)
        assert traits.get_formality() == "casual"

    def test_formality_formal(self) -> None:
        """Test that high conscientiousness gives formal speech."""
        traits = PersonalityTraits(conscientiousness=80)
        assert traits.get_formality() == "formal"

    def test_formality_neutral(self) -> None:
        """Test that average conscientiousness gives neutral formality."""
        traits = PersonalityTraits(conscientiousness=50)
        assert traits.get_formality() == "neutral"

    def test_risk_tolerance_default(self) -> None:
        """Test default risk tolerance is 0.5."""
        traits = PersonalityTraits()
        assert traits.get_risk_tolerance() == 0.5

    def test_risk_tolerance_high_neuroticism(self) -> None:
        """Test that high neuroticism decreases risk tolerance."""
        traits = PersonalityTraits(neuroticism=100, openness=50)
        assert traits.get_risk_tolerance() < 0.5

    def test_risk_tolerance_high_openness(self) -> None:
        """Test that high openness increases risk tolerance."""
        traits = PersonalityTraits(openness=100, neuroticism=50)
        assert traits.get_risk_tolerance() > 0.5

    def test_risk_tolerance_clamped(self) -> None:
        """Test that risk tolerance is clamped to 0-1."""
        # Extreme values
        traits = PersonalityTraits(openness=100, neuroticism=0)
        assert 0.0 <= traits.get_risk_tolerance() <= 1.0

        traits = PersonalityTraits(openness=0, neuroticism=100)
        assert 0.0 <= traits.get_risk_tolerance() <= 1.0


class TestMotivation:
    """Tests for the Motivation enum."""

    def test_all_motivations_exist(self) -> None:
        """Test that all expected motivations are defined."""
        expected = [
            "survival",
            "safety",  # Self-preservation
            "wealth",
            "power",
            "comfort",  # Material
            "love",
            "belonging",
            "respect",
            "fame",  # Social
            "knowledge",
            "justice",
            "duty",
            "faith",
            "revenge",  # Higher purpose
            "artistry",
            "legacy",  # Creative
        ]
        actual = [m.value for m in Motivation]
        assert set(expected) == set(actual)

    def test_motivation_is_string(self) -> None:
        """Test that motivations can be used as strings."""
        # StrEnum comparison works with == but str() returns the full name
        assert Motivation.SURVIVAL == "survival"
        assert Motivation.WEALTH.value == "wealth"


class TestNPCProfile:
    """Tests for the NPCProfile model."""

    def test_create_profile(self) -> None:
        """Test creating a basic profile."""
        entity_id = uuid4()
        profile = NPCProfile(entity_id=entity_id)

        assert profile.entity_id == entity_id
        assert isinstance(profile.traits, PersonalityTraits)
        assert profile.motivations == [Motivation.SURVIVAL]
        assert profile.quirks == []
        assert profile.speech_style == "neutral"
        assert profile.lawful_chaotic == 0
        assert profile.good_evil == 0

    def test_create_profile_with_traits(self) -> None:
        """Test creating a profile with custom traits."""
        entity_id = uuid4()
        traits = PersonalityTraits(openness=80, agreeableness=20)
        profile = NPCProfile(
            entity_id=entity_id,
            traits=traits,
            motivations=[Motivation.POWER, Motivation.WEALTH],
            quirks=["speaks in riddles"],
            speech_style="cryptic",
            lawful_chaotic=-50,
            good_evil=-30,
        )

        assert profile.traits.openness == 80
        assert profile.traits.agreeableness == 20
        assert profile.motivations == [Motivation.POWER, Motivation.WEALTH]
        assert "speaks in riddles" in profile.quirks
        assert profile.speech_style == "cryptic"
        assert profile.lawful_chaotic == -50
        assert profile.good_evil == -30

    def test_max_motivations(self) -> None:
        """Test that motivations are limited to 3."""
        entity_id = uuid4()
        with pytest.raises(ValueError):
            NPCProfile(
                entity_id=entity_id,
                motivations=[
                    Motivation.POWER,
                    Motivation.WEALTH,
                    Motivation.FAME,
                    Motivation.LEGACY,
                ],
            )

    def test_alignment_bounds(self) -> None:
        """Test that alignment values are bounded."""
        entity_id = uuid4()
        with pytest.raises(ValueError):
            NPCProfile(entity_id=entity_id, lawful_chaotic=101)
        with pytest.raises(ValueError):
            NPCProfile(entity_id=entity_id, good_evil=-101)

    def test_get_primary_motivation(self) -> None:
        """Test getting the primary motivation."""
        entity_id = uuid4()
        profile = NPCProfile(
            entity_id=entity_id,
            motivations=[Motivation.KNOWLEDGE, Motivation.LEGACY],
        )
        assert profile.get_primary_motivation() == Motivation.KNOWLEDGE

    def test_get_primary_motivation_empty(self) -> None:
        """Test getting primary motivation when empty defaults to SURVIVAL."""
        entity_id = uuid4()
        # Need to bypass validation by using model_construct
        profile = NPCProfile.model_construct(
            entity_id=entity_id,
            traits=PersonalityTraits(),
            motivations=[],
        )
        assert profile.get_primary_motivation() == Motivation.SURVIVAL

    def test_is_lawful(self) -> None:
        """Test lawful detection."""
        entity_id = uuid4()
        profile = NPCProfile(entity_id=entity_id, lawful_chaotic=50)
        assert profile.is_lawful() is True
        assert profile.is_chaotic() is False

    def test_is_chaotic(self) -> None:
        """Test chaotic detection."""
        entity_id = uuid4()
        profile = NPCProfile(entity_id=entity_id, lawful_chaotic=-50)
        assert profile.is_chaotic() is True
        assert profile.is_lawful() is False

    def test_is_good(self) -> None:
        """Test good detection."""
        entity_id = uuid4()
        profile = NPCProfile(entity_id=entity_id, good_evil=50)
        assert profile.is_good() is True
        assert profile.is_evil() is False

    def test_is_evil(self) -> None:
        """Test evil detection."""
        entity_id = uuid4()
        profile = NPCProfile(entity_id=entity_id, good_evil=-50)
        assert profile.is_evil() is True
        assert profile.is_good() is False

    def test_alignment_description_lawful_good(self) -> None:
        """Test alignment description for lawful good."""
        profile = NPCProfile(
            entity_id=uuid4(),
            lawful_chaotic=80,
            good_evil=80,
        )
        assert profile.get_alignment_description() == "Lawful Good"

    def test_alignment_description_chaotic_evil(self) -> None:
        """Test alignment description for chaotic evil."""
        profile = NPCProfile(
            entity_id=uuid4(),
            lawful_chaotic=-80,
            good_evil=-80,
        )
        assert profile.get_alignment_description() == "Chaotic Evil"

    def test_alignment_description_true_neutral(self) -> None:
        """Test alignment description for true neutral."""
        profile = NPCProfile(
            entity_id=uuid4(),
            lawful_chaotic=0,
            good_evil=0,
        )
        assert profile.get_alignment_description() == "True Neutral"

    def test_alignment_description_neutral_good(self) -> None:
        """Test alignment description for neutral good."""
        profile = NPCProfile(
            entity_id=uuid4(),
            lawful_chaotic=0,
            good_evil=80,
        )
        assert profile.get_alignment_description() == "Neutral Good"


class TestNPCMemory:
    """Tests for the NPCMemory model."""

    def test_create_memory(self) -> None:
        """Test creating a basic memory."""
        npc_id = uuid4()
        memory = NPCMemory(
            npc_id=npc_id,
            memory_type=MemoryType.ENCOUNTER,
            description="Met a friendly merchant",
        )

        assert memory.npc_id == npc_id
        assert memory.memory_type == MemoryType.ENCOUNTER
        assert memory.description == "Met a friendly merchant"
        assert memory.emotional_valence == 0.0
        assert memory.importance == 0.5
        assert memory.times_recalled == 0
        assert memory.last_recalled is None

    def test_memory_valence_bounds(self) -> None:
        """Test that emotional valence is bounded."""
        with pytest.raises(ValueError):
            NPCMemory(
                npc_id=uuid4(),
                memory_type=MemoryType.EMOTION,
                description="test",
                emotional_valence=1.5,
            )
        with pytest.raises(ValueError):
            NPCMemory(
                npc_id=uuid4(),
                memory_type=MemoryType.EMOTION,
                description="test",
                emotional_valence=-1.5,
            )

    def test_memory_importance_bounds(self) -> None:
        """Test that importance is bounded."""
        with pytest.raises(ValueError):
            NPCMemory(
                npc_id=uuid4(),
                memory_type=MemoryType.ACTION,
                description="test",
                importance=1.5,
            )
        with pytest.raises(ValueError):
            NPCMemory(
                npc_id=uuid4(),
                memory_type=MemoryType.ACTION,
                description="test",
                importance=-0.1,
            )

    def test_recall_updates_tracking(self) -> None:
        """Test that recall() updates tracking fields."""
        memory = NPCMemory(
            npc_id=uuid4(),
            memory_type=MemoryType.DIALOGUE,
            description="Had a conversation",
        )

        assert memory.times_recalled == 0
        assert memory.last_recalled is None

        memory.recall()

        assert memory.times_recalled == 1
        assert memory.last_recalled is not None

        memory.recall()
        assert memory.times_recalled == 2

    def test_retrieval_score_recent_important(self) -> None:
        """Test that recent, important memories have high retrieval scores."""
        memory = NPCMemory(
            npc_id=uuid4(),
            memory_type=MemoryType.ACTION,
            description="Life-changing event",
            importance=1.0,
            emotional_valence=1.0,
        )

        score = memory.calculate_retrieval_score(relevance=1.0)
        assert score > 0.8

    def test_retrieval_score_old_trivial(self) -> None:
        """Test that old, trivial memories have low retrieval scores."""
        npc_id = uuid4()
        memory = NPCMemory(
            npc_id=npc_id,
            memory_type=MemoryType.OBSERVATION,
            description="Saw a rock",
            importance=0.0,
            emotional_valence=0.0,
            timestamp=datetime.now(UTC) - timedelta(days=7),
        )

        score = memory.calculate_retrieval_score(relevance=0.0)
        assert score < 0.2

    def test_retrieval_score_with_rehearsal(self) -> None:
        """Test that frequently recalled memories get a bonus."""
        memory = NPCMemory(
            npc_id=uuid4(),
            memory_type=MemoryType.ENCOUNTER,
            description="Memorable meeting",
            importance=0.5,
        )

        base_score = memory.calculate_retrieval_score(relevance=0.5)

        # Recall several times
        for _ in range(5):
            memory.recall()

        boosted_score = memory.calculate_retrieval_score(relevance=0.5)
        assert boosted_score > base_score


class TestMemoryType:
    """Tests for the MemoryType enum."""

    def test_all_memory_types_exist(self) -> None:
        """Test that all expected memory types are defined."""
        expected = ["encounter", "dialogue", "action", "observation", "rumor", "emotion"]
        actual = [m.value for m in MemoryType]
        assert set(expected) == set(actual)


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_npc_profile(self) -> None:
        """Test the create_npc_profile factory function."""
        entity_id = uuid4()
        profile = create_npc_profile(
            entity_id,
            openness=70,
            conscientiousness=30,
            extraversion=80,
            agreeableness=60,
            neuroticism=40,
            motivations=[Motivation.FAME, Motivation.LOVE],
            quirks=["always winking"],
            speech_style="flirtatious",
            lawful_chaotic=-20,
            good_evil=40,
        )

        assert profile.entity_id == entity_id
        assert profile.traits.openness == 70
        assert profile.traits.conscientiousness == 30
        assert profile.motivations == [Motivation.FAME, Motivation.LOVE]
        assert "always winking" in profile.quirks
        assert profile.speech_style == "flirtatious"
        assert profile.lawful_chaotic == -20
        assert profile.good_evil == 40

    def test_create_npc_profile_defaults(self) -> None:
        """Test create_npc_profile with defaults."""
        entity_id = uuid4()
        profile = create_npc_profile(entity_id)

        assert profile.entity_id == entity_id
        assert profile.traits.openness == 50
        assert profile.motivations == [Motivation.SURVIVAL]

    def test_create_memory(self) -> None:
        """Test the create_memory factory function."""
        npc_id = uuid4()
        subject_id = uuid4()
        event_id = uuid4()

        memory = create_memory(
            npc_id,
            MemoryType.ACTION,
            "Saved the village",
            subject_id=subject_id,
            emotional_valence=0.9,
            importance=0.8,
            event_id=event_id,
        )

        assert memory.npc_id == npc_id
        assert memory.memory_type == MemoryType.ACTION
        assert memory.description == "Saved the village"
        assert memory.subject_id == subject_id
        assert memory.emotional_valence == 0.9
        assert memory.importance == 0.8
        assert memory.event_id == event_id

    def test_create_memory_defaults(self) -> None:
        """Test create_memory with defaults."""
        npc_id = uuid4()
        memory = create_memory(npc_id, MemoryType.RUMOR, "Heard about treasure")

        assert memory.npc_id == npc_id
        assert memory.memory_type == MemoryType.RUMOR
        assert memory.description == "Heard about treasure"
        assert memory.subject_id is None
        assert memory.emotional_valence == 0.0
        assert memory.importance == 0.5
