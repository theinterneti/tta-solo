"""
Tests for NPC AI decision making and memory system.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
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
    create_memory,
    create_npc_profile,
    get_combat_state,
)
from src.services.npc import NPCService

# =============================================================================
# Action Option Tests
# =============================================================================


class TestActionOption:
    """Tests for ActionOption model and scoring."""

    def test_total_score_calculation(self) -> None:
        """Test the weighted score calculation."""
        option = ActionOption(
            action_type=ActionType.ATTACK,
            description="Attack the goblin",
            motivation_score=1.0,
            relationship_score=0.5,
            personality_score=0.5,
            risk_score=0.0,  # Low risk
        )
        # 1.0 * 0.35 + 0.5 * 0.25 + 0.5 * 0.25 + (1.0 - 0.0) * 0.15
        # = 0.35 + 0.125 + 0.125 + 0.15 = 0.75
        assert option.total_score == pytest.approx(0.75)

    def test_total_score_high_risk_penalty(self) -> None:
        """Test that high risk reduces the score."""
        low_risk = ActionOption(
            action_type=ActionType.ATTACK,
            description="Attack",
            motivation_score=0.5,
            relationship_score=0.5,
            personality_score=0.5,
            risk_score=0.0,
        )
        high_risk = ActionOption(
            action_type=ActionType.ATTACK,
            description="Attack",
            motivation_score=0.5,
            relationship_score=0.5,
            personality_score=0.5,
            risk_score=1.0,
        )
        assert low_risk.total_score > high_risk.total_score

    def test_total_score_motivation_weight(self) -> None:
        """Test that motivation has the highest weight."""
        high_motivation = ActionOption(
            action_type=ActionType.ATTACK,
            description="Attack",
            motivation_score=1.0,
            relationship_score=0.0,
            personality_score=0.0,
            risk_score=0.5,
        )
        high_relationship = ActionOption(
            action_type=ActionType.ATTACK,
            description="Attack",
            motivation_score=0.0,
            relationship_score=1.0,
            personality_score=0.0,
            risk_score=0.5,
        )
        assert high_motivation.total_score > high_relationship.total_score


# =============================================================================
# Combat State Tests
# =============================================================================


class TestCombatState:
    """Tests for combat behavior state determination."""

    def test_aggressive_low_agreeableness(self) -> None:
        """Low agreeableness NPCs are aggressive."""
        profile = create_npc_profile(
            entity_id=uuid4(),
            agreeableness=20,  # Low
        )
        evaluation = CombatEvaluation(hp_percentage=0.8)
        state = get_combat_state(profile, evaluation)
        assert state == CombatState.AGGRESSIVE

    def test_supportive_high_agreeableness_with_allies(self) -> None:
        """High agreeableness NPCs support allies."""
        profile = create_npc_profile(
            entity_id=uuid4(),
            agreeableness=80,  # High
        )
        evaluation = CombatEvaluation(
            hp_percentage=0.8,
            allies_count=2,
        )
        state = get_combat_state(profile, evaluation)
        assert state == CombatState.SUPPORTIVE

    def test_fleeing_low_hp_with_escape(self) -> None:
        """NPCs flee when HP is low and escape is possible."""
        profile = create_npc_profile(entity_id=uuid4())
        evaluation = CombatEvaluation(
            hp_percentage=0.2,  # Below 25%
            escape_routes=1,
            total_enemy_threat=0.7,
        )
        state = get_combat_state(profile, evaluation)
        assert state == CombatState.FLEEING

    def test_surrendering_low_hp_no_escape(self) -> None:
        """NPCs surrender when HP is low and no escape."""
        profile = create_npc_profile(entity_id=uuid4())
        evaluation = CombatEvaluation(
            hp_percentage=0.05,  # Below 10%
            escape_routes=0,
            allies_count=0,
        )
        state = get_combat_state(profile, evaluation)
        assert state == CombatState.SURRENDERING

    def test_high_neuroticism_flees_earlier(self) -> None:
        """High neuroticism NPCs flee at higher HP."""
        # Low neuroticism - won't flee at 35% HP
        # Flee threshold = 0.25 + neuroticism/200
        # Low (20): 0.25 + 0.1 = 0.35, so 0.40 HP won't flee
        calm_profile = create_npc_profile(
            entity_id=uuid4(),
            neuroticism=20,
        )
        evaluation = CombatEvaluation(
            hp_percentage=0.40,  # Above 0.35 threshold
            escape_routes=1,
        )
        calm_state = get_combat_state(calm_profile, evaluation)

        # High neuroticism - will flee at 40% HP
        # High (100): 0.25 + 0.5 = 0.75, so 0.40 HP will flee
        anxious_profile = create_npc_profile(
            entity_id=uuid4(),
            neuroticism=100,
        )
        anxious_state = get_combat_state(anxious_profile, evaluation)

        assert calm_state == CombatState.TACTICAL
        assert anxious_state == CombatState.FLEEING


# =============================================================================
# Dialogue Constraints Tests
# =============================================================================


class TestDialogueConstraints:
    """Tests for dialogue constraint generation."""

    def test_from_context_friendly(self) -> None:
        """Test constraints for a friendly relationship."""
        profile = create_npc_profile(
            entity_id=uuid4(),
            extraversion=80,  # Verbose
            conscientiousness=80,  # Formal
        )
        constraints = DialogueConstraints.from_context(
            profile=profile,
            player_trust=0.7,  # High trust
        )
        assert constraints.verbosity == "verbose"
        assert constraints.formality == "formal"
        assert constraints.attitude_toward_player == "friendly"
        assert constraints.trust_level == "trusting"

    def test_from_context_hostile(self) -> None:
        """Test constraints for a hostile relationship."""
        profile = create_npc_profile(
            entity_id=uuid4(),
            extraversion=20,  # Terse
        )
        constraints = DialogueConstraints.from_context(
            profile=profile,
            player_trust=-0.7,  # Low trust
        )
        assert constraints.verbosity == "terse"
        assert constraints.attitude_toward_player == "hostile"
        assert constraints.trust_level == "suspicious"

    def test_from_context_in_combat(self) -> None:
        """Test constraints during combat."""
        profile = create_npc_profile(entity_id=uuid4())
        constraints = DialogueConstraints.from_context(
            profile=profile,
            in_combat=True,
            emotional_valence=-0.3,
        )
        assert constraints.urgency == "urgent"
        assert constraints.emotional_state == "angry"


# =============================================================================
# NPC Decision Context Tests
# =============================================================================


class TestNPCDecisionContext:
    """Tests for NPCDecisionContext model."""

    def test_create_context(self) -> None:
        """Test creating a decision context."""
        npc_id = uuid4()
        profile = create_npc_profile(entity_id=npc_id)
        context = NPCDecisionContext(
            npc_id=npc_id,
            npc_profile=profile,
            hp_percentage=0.8,
            location_name="Tavern",
            danger_level=2,
        )
        assert context.npc_id == npc_id
        assert context.hp_percentage == 0.8
        assert context.location_name == "Tavern"

    def test_context_with_entities(self) -> None:
        """Test context with entities present."""
        npc_id = uuid4()
        player_id = uuid4()
        profile = create_npc_profile(entity_id=npc_id)
        context = NPCDecisionContext(
            npc_id=npc_id,
            npc_profile=profile,
            entities_present=[
                EntitySummary(
                    id=player_id,
                    name="Hero",
                    entity_type="character",
                    is_player=True,
                )
            ],
        )
        assert len(context.entities_present) == 1
        assert context.entities_present[0].is_player


# =============================================================================
# NPC Service Tests
# =============================================================================


class TestNPCServiceDecision:
    """Tests for NPCService decision making."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.dolt = InMemoryDoltRepository()
        self.neo4j = InMemoryNeo4jRepository()
        self.service = NPCService(dolt=self.dolt, neo4j=self.neo4j)

    def test_decide_action_returns_result(self) -> None:
        """Test that decide_action returns a valid result."""
        npc_id = uuid4()
        profile = create_npc_profile(entity_id=npc_id)
        context = NPCDecisionContext(
            npc_id=npc_id,
            npc_profile=profile,
        )
        result = self.service.decide_action(context)
        assert result.action is not None
        assert result.alternatives_considered > 0

    def test_decide_action_with_filter(self) -> None:
        """Test filtering available actions."""
        npc_id = uuid4()
        profile = create_npc_profile(entity_id=npc_id)
        context = NPCDecisionContext(
            npc_id=npc_id,
            npc_profile=profile,
        )
        result = self.service.decide_action(
            context,
            available_actions=[ActionType.FLEE, ActionType.HIDE],
        )
        assert result.action.action_type in [ActionType.FLEE, ActionType.HIDE]
        assert result.alternatives_considered == 2

    def test_decide_action_motivation_influence(self) -> None:
        """Test that motivations influence action selection."""
        npc_id = uuid4()
        # NPC motivated by survival
        profile = create_npc_profile(
            entity_id=npc_id,
            motivations=[Motivation.SURVIVAL],
            neuroticism=70,  # More likely to flee
        )
        context = NPCDecisionContext(
            npc_id=npc_id,
            npc_profile=profile,
            hp_percentage=0.3,  # Low HP
            danger_level=10,
        )
        result = self.service.decide_action(
            context,
            available_actions=[ActionType.ATTACK, ActionType.FLEE, ActionType.DEFEND],
        )
        # Survival motivation should favor flee/defend over attack
        assert result.action.action_type in [ActionType.FLEE, ActionType.DEFEND]


class TestNPCServiceMemory:
    """Tests for NPCService memory formation."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.dolt = InMemoryDoltRepository()
        self.neo4j = InMemoryNeo4jRepository()
        self.service = NPCService(dolt=self.dolt, neo4j=self.neo4j)

    def test_form_memory_from_event(self) -> None:
        """Test memory formation from an event."""
        npc_id = uuid4()
        actor_id = uuid4()
        universe_id = uuid4()
        event = Event(
            universe_id=universe_id,
            event_type=EventType.ATTACK,
            actor_id=actor_id,
            target_id=npc_id,
            outcome=EventOutcome.SUCCESS,
            narrative_summary="The goblin attacked the merchant.",
        )
        result = self.service.form_memory(npc_id, event)
        assert result.formed
        assert result.memory is not None
        assert result.memory.npc_id == npc_id
        assert result.memory.memory_type == MemoryType.ACTION

    def test_form_memory_importance_calculation(self) -> None:
        """Test that event importance is calculated correctly."""
        npc_id = uuid4()
        actor_id = uuid4()
        universe_id = uuid4()
        # Combat event targeting NPC = high importance
        attack_event = Event(
            universe_id=universe_id,
            event_type=EventType.ATTACK,
            actor_id=actor_id,
            target_id=npc_id,  # Targets NPC (+0.3)
            outcome=EventOutcome.CRITICAL_SUCCESS,  # Critical (+0.2)
            narrative_summary="The enemy attacked!",
        )
        result = self.service.form_memory(npc_id, attack_event)
        assert result.formed
        # Base 0.5 + target_npc 0.3 + combat 0.3 + critical 0.2 = capped at 1.0
        assert result.memory is not None
        assert result.memory.importance == 1.0

    def test_form_memory_emotional_valence(self) -> None:
        """Test emotional valence calculation."""
        npc_id = uuid4()
        actor_id = uuid4()
        universe_id = uuid4()
        # Being healed should be positive
        heal_event = Event(
            universe_id=universe_id,
            event_type=EventType.HEAL,
            actor_id=actor_id,
            target_id=npc_id,
            outcome=EventOutcome.SUCCESS,
            narrative_summary="The cleric healed the merchant.",
        )
        result = self.service.form_memory(npc_id, heal_event)
        assert result.formed
        assert result.memory is not None
        assert result.memory.emotional_valence > 0


# =============================================================================
# Memory Repository Tests
# =============================================================================


class TestMemoryRepository:
    """Tests for in-memory memory repository."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.repo = InMemoryNeo4jRepository()

    def test_create_and_get_memory(self) -> None:
        """Test creating and retrieving a memory."""
        npc_id = uuid4()
        memory = create_memory(
            npc_id=npc_id,
            memory_type=MemoryType.ENCOUNTER,
            description="Met a stranger at the inn.",
            importance=0.7,
        )
        self.repo.create_memory(memory)
        memories = self.repo.get_memories_for_npc(npc_id)
        assert len(memories) == 1
        assert memories[0].description == "Met a stranger at the inn."

    def test_get_memories_ordered_by_timestamp(self) -> None:
        """Test that memories are ordered newest first."""
        npc_id = uuid4()
        for i in range(3):
            memory = create_memory(
                npc_id=npc_id,
                memory_type=MemoryType.OBSERVATION,
                description=f"Observation {i}",
            )
            self.repo.create_memory(memory)

        memories = self.repo.get_memories_for_npc(npc_id)
        assert len(memories) == 3
        # Most recent should be first
        for i in range(len(memories) - 1):
            assert memories[i].timestamp >= memories[i + 1].timestamp

    def test_get_memories_about_entity(self) -> None:
        """Test filtering memories by subject."""
        npc_id = uuid4()
        player_id = uuid4()
        other_id = uuid4()

        # Memory about player
        memory1 = create_memory(
            npc_id=npc_id,
            memory_type=MemoryType.ENCOUNTER,
            description="Met the hero",
            subject_id=player_id,
        )
        # Memory about someone else
        memory2 = create_memory(
            npc_id=npc_id,
            memory_type=MemoryType.ENCOUNTER,
            description="Met the blacksmith",
            subject_id=other_id,
        )
        self.repo.create_memory(memory1)
        self.repo.create_memory(memory2)

        player_memories = self.repo.get_memories_about_entity(npc_id, player_id)
        assert len(player_memories) == 1
        assert player_memories[0].subject_id == player_id

    def test_update_memory_recall(self) -> None:
        """Test updating recall tracking."""
        npc_id = uuid4()
        memory = create_memory(
            npc_id=npc_id,
            memory_type=MemoryType.EMOTION,
            description="Felt happy",
        )
        assert memory.times_recalled == 0
        self.repo.create_memory(memory)

        self.repo.update_memory_recall(memory.id)
        memories = self.repo.get_memories_for_npc(npc_id)
        assert memories[0].times_recalled == 1
        assert memories[0].last_recalled is not None

    def test_delete_memory(self) -> None:
        """Test deleting a memory."""
        npc_id = uuid4()
        memory = create_memory(
            npc_id=npc_id,
            memory_type=MemoryType.RUMOR,
            description="Heard a rumor",
        )
        self.repo.create_memory(memory)
        assert len(self.repo.get_memories_for_npc(npc_id)) == 1

        self.repo.delete_memory(memory.id)
        assert len(self.repo.get_memories_for_npc(npc_id)) == 0


# =============================================================================
# Memory Retrieval Tests
# =============================================================================


class TestMemoryRetrieval:
    """Tests for NPCService memory retrieval with relevance scoring."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.dolt = InMemoryDoltRepository()
        self.neo4j = InMemoryNeo4jRepository()
        self.service = NPCService(dolt=self.dolt, neo4j=self.neo4j)

    def test_retrieve_memories_empty(self) -> None:
        """Test retrieval when NPC has no memories."""
        npc_id = uuid4()
        memories = self.service.retrieve_memories(
            npc_id=npc_id,
            context_description="Walking through the forest",
        )
        assert memories == []

    def test_retrieve_memories_basic(self) -> None:
        """Test basic memory retrieval."""
        npc_id = uuid4()
        memory = create_memory(
            npc_id=npc_id,
            memory_type=MemoryType.ENCOUNTER,
            description="Met a traveler in the forest",
            importance=0.7,
        )
        self.neo4j.create_memory(memory)

        memories = self.service.retrieve_memories(
            npc_id=npc_id,
            context_description="Walking through the forest",
            limit=5,
        )
        assert len(memories) == 1
        assert memories[0].id == memory.id

    def test_retrieve_memories_relevance_scoring(self) -> None:
        """Test that relevant memories score higher."""
        npc_id = uuid4()

        # Relevant memory (about forests)
        forest_memory = create_memory(
            npc_id=npc_id,
            memory_type=MemoryType.ENCOUNTER,
            description="Saw a deer in the dark forest near the mountain",
            importance=0.5,
        )
        # Irrelevant memory (about city)
        city_memory = create_memory(
            npc_id=npc_id,
            memory_type=MemoryType.ENCOUNTER,
            description="Bought bread at the city market",
            importance=0.5,
        )
        self.neo4j.create_memory(forest_memory)
        self.neo4j.create_memory(city_memory)

        memories = self.service.retrieve_memories(
            npc_id=npc_id,
            context_description="Exploring the forest near the mountain",
            limit=2,
        )

        # Forest memory should be ranked first due to keyword overlap
        assert len(memories) == 2
        assert memories[0].id == forest_memory.id

    def test_retrieve_memories_with_subject_filter(self) -> None:
        """Test retrieval filtered by subject entity."""
        npc_id = uuid4()
        player_id = uuid4()
        goblin_id = uuid4()

        player_memory = create_memory(
            npc_id=npc_id,
            memory_type=MemoryType.DIALOGUE,
            description="The hero asked about the treasure",
            subject_id=player_id,
        )
        goblin_memory = create_memory(
            npc_id=npc_id,
            memory_type=MemoryType.ACTION,
            description="The goblin stole my coins",
            subject_id=goblin_id,
        )
        self.neo4j.create_memory(player_memory)
        self.neo4j.create_memory(goblin_memory)

        memories = self.service.retrieve_memories(
            npc_id=npc_id,
            context_description="Talking about treasure",
            subject_id=player_id,
            limit=5,
        )

        assert len(memories) == 1
        assert memories[0].subject_id == player_id

    def test_retrieve_memories_updates_recall_tracking(self) -> None:
        """Test that retrieved memories are marked as recalled."""
        npc_id = uuid4()
        memory = create_memory(
            npc_id=npc_id,
            memory_type=MemoryType.OBSERVATION,
            description="Saw strange lights in the sky",
        )
        self.neo4j.create_memory(memory)

        # Retrieve the memory
        memories = self.service.retrieve_memories(
            npc_id=npc_id,
            context_description="Strange lights appeared",
            limit=5,
        )

        # Check that recall was updated
        assert len(memories) == 1
        assert memories[0].times_recalled == 1
        assert memories[0].last_recalled is not None

    def test_retrieve_memories_respects_limit(self) -> None:
        """Test that limit is respected."""
        npc_id = uuid4()

        for i in range(10):
            memory = create_memory(
                npc_id=npc_id,
                memory_type=MemoryType.OBSERVATION,
                description=f"Event number {i}",
            )
            self.neo4j.create_memory(memory)

        memories = self.service.retrieve_memories(
            npc_id=npc_id,
            context_description="Something happened",
            limit=3,
        )

        assert len(memories) == 3


# =============================================================================
# Keyword Extraction Tests
# =============================================================================


class TestKeywordExtraction:
    """
    Tests for keyword extraction and relevance helpers.

    Note: We test these underscore-prefixed functions directly because they are
    pure utility functions with well-defined inputs/outputs. While underscore
    prefix conventionally indicates internal use, Python doesn't enforce privacy,
    and direct testing of these helpers ensures correctness of the relevance
    scoring algorithm independent of the higher-level memory retrieval API.
    """

    def test_extract_keywords_basic(self) -> None:
        """Test basic keyword extraction."""
        from src.services.npc import _extract_keywords

        keywords = _extract_keywords("The quick brown fox jumps over the lazy dog")
        # Should exclude common stop words like "the"
        assert "quick" in keywords
        assert "brown" in keywords
        assert "fox" in keywords
        assert "jumps" in keywords
        assert "lazy" in keywords
        assert "dog" in keywords
        assert "the" not in keywords

    def test_extract_keywords_filters_short_words(self) -> None:
        """Test that short words are filtered."""
        from src.services.npc import _extract_keywords

        keywords = _extract_keywords("I am a go to be")
        # All are too short or stop words
        assert len(keywords) == 0

    def test_extract_keywords_lowercase(self) -> None:
        """Test that keywords are lowercased."""
        from src.services.npc import _extract_keywords

        keywords = _extract_keywords("FOREST Mountain RIVER")
        assert "forest" in keywords
        assert "mountain" in keywords
        assert "river" in keywords
        assert "FOREST" not in keywords

    def test_calculate_keyword_relevance_full_overlap(self) -> None:
        """Test relevance with full keyword overlap."""
        from src.services.npc import _calculate_keyword_relevance, _extract_keywords

        context_keywords = _extract_keywords("forest mountain river")
        relevance = _calculate_keyword_relevance(
            "Saw a river near the mountain in the forest",
            context_keywords,
        )
        # High overlap should give high relevance
        assert relevance > 0.7

    def test_calculate_keyword_relevance_no_overlap(self) -> None:
        """Test relevance with no keyword overlap."""
        from src.services.npc import _calculate_keyword_relevance, _extract_keywords

        context_keywords = _extract_keywords("forest mountain river")
        relevance = _calculate_keyword_relevance(
            "Bought bread at the city market",
            context_keywords,
        )
        # No overlap should give low relevance
        assert relevance < 0.4

    def test_calculate_keyword_relevance_empty_context(self) -> None:
        """Test relevance with empty context."""
        from src.services.npc import _calculate_keyword_relevance

        relevance = _calculate_keyword_relevance(
            "Some memory description",
            set(),  # Empty context
        )
        # Should return neutral relevance
        assert relevance == 0.5
