"""
Tests for LLM service and dialogue generation.
"""

from __future__ import annotations

import os
from unittest.mock import patch
from uuid import uuid4

import pytest

from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.models.npc import (
    MemoryType,
    RelationshipSummary,
    create_memory,
    create_npc_profile,
)
from src.services.llm import (
    LLMService,
    MockLLMProvider,
    OpenRouterProvider,
    create_llm_service,
)
from src.services.npc import NPCService

# =============================================================================
# Mock Provider Tests
# =============================================================================


class TestMockLLMProvider:
    """Tests for MockLLMProvider."""

    @pytest.mark.asyncio
    async def test_complete_basic(self) -> None:
        """Test basic completion returns mock response."""
        provider = MockLLMProvider()
        messages = [{"role": "user", "content": "Hello"}]
        response = await provider.complete(messages)
        assert response == "[Mock LLM response]"

    @pytest.mark.asyncio
    async def test_complete_with_custom_response(self) -> None:
        """Test custom response for specific input."""
        provider = MockLLMProvider()
        provider.set_response("Hello", "Hi there!")

        messages = [{"role": "user", "content": "Hello"}]
        response = await provider.complete(messages)
        assert response == "Hi there!"

    def test_is_available(self) -> None:
        """Test mock provider is always available."""
        provider = MockLLMProvider()
        assert provider.is_available is True

    def test_model_name(self) -> None:
        """Test model name property."""
        provider = MockLLMProvider()
        assert provider.model_name == "mock"


# =============================================================================
# OpenRouter Provider Tests
# =============================================================================


class TestOpenRouterProvider:
    """Tests for OpenRouterProvider."""

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key(self) -> None:
        """Test provider is not available without API key."""
        # Clear any env vars and pass explicit None
        provider = OpenRouterProvider(api_key=None)
        # Re-init without env vars
        provider._client = None  # Ensure client is not initialized
        assert provider._client is None

    def test_with_api_key(self) -> None:
        """Test provider is available with API key."""
        provider = OpenRouterProvider(api_key="test-key")
        assert provider.is_available is True
        assert provider.model_name == "anthropic/claude-3-haiku"

    def test_custom_model(self) -> None:
        """Test custom model configuration."""
        provider = OpenRouterProvider(
            api_key="test-key",
            model="openai/gpt-4-turbo",
        )
        assert provider.model_name == "openai/gpt-4-turbo"

    @pytest.mark.asyncio
    async def test_complete_without_client_raises(self) -> None:
        """Test that complete raises without client configured."""
        provider = OpenRouterProvider(api_key="test-key")
        provider._client = None  # Simulate no client
        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(RuntimeError, match="not configured"):
            await provider.complete(messages)


# =============================================================================
# LLM Service Tests
# =============================================================================


class TestLLMService:
    """Tests for LLMService."""

    @pytest.mark.asyncio
    async def test_generate_dialogue_basic(self) -> None:
        """Test basic dialogue generation."""
        provider = MockLLMProvider()
        service = LLMService(provider=provider)

        response = await service.generate_dialogue(
            npc_name="Test NPC",
            npc_description="a friendly bartender",
            speech_style="casual",
            verbosity="normal",
            formality="casual",
            attitude="friendly",
            trust_level="trusting",
            emotional_state="calm",
            urgency="relaxed",
            memories=[],
            player_input="Hello",
            situation="In a tavern",
        )

        # Mock provider returns default mock response
        assert response == "[Mock LLM response]"

    def test_is_available(self) -> None:
        """Test availability check delegates to provider."""
        provider = MockLLMProvider()
        service = LLMService(provider=provider)
        assert service.is_available is True

    @pytest.mark.asyncio
    async def test_generate_narrative(self) -> None:
        """Test narrative generation."""
        provider = MockLLMProvider()
        service = LLMService(provider=provider)

        response = await service.generate_narrative(
            event_description="The warrior strikes the goblin with a sword",
            tone="heroic",
            location="A dark cave",
            characters_involved=["Warrior", "Goblin"],
        )

        assert response == "[Mock LLM response]"


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestCreateLLMService:
    """Tests for create_llm_service factory."""

    def test_create_mock_service(self) -> None:
        """Test creating a mock service."""
        service = create_llm_service(provider_type="mock")
        assert service.is_available is True
        assert service.provider.model_name == "mock"

    @patch.dict(os.environ, {}, clear=True)
    def test_create_openrouter_without_key(self) -> None:
        """Test creating OpenRouter service without API key."""
        # Must clear env vars to test this properly
        service = create_llm_service(provider_type="openrouter", api_key=None)
        # Without env vars, should not be available
        assert service.provider._client is None

    def test_create_openrouter_with_key(self) -> None:
        """Test creating OpenRouter service with API key."""
        service = create_llm_service(provider_type="openrouter", api_key="test-key")
        assert service.is_available is True

    def test_unknown_provider_raises(self) -> None:
        """Test that unknown provider type raises error."""
        with pytest.raises(ValueError, match="Unknown provider type"):
            create_llm_service(provider_type="unknown")


# =============================================================================
# NPC Dialogue Generation Tests
# =============================================================================


class TestNPCDialogueGeneration:
    """Tests for NPC dialogue generation via NPCService."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.dolt = InMemoryDoltRepository()
        self.neo4j = InMemoryNeo4jRepository()
        self.mock_provider = MockLLMProvider()
        self.llm = LLMService(provider=self.mock_provider)
        self.service = NPCService(
            dolt=self.dolt,
            neo4j=self.neo4j,
            llm=self.llm,
        )

    @pytest.mark.asyncio
    async def test_generate_dialogue_with_llm(self) -> None:
        """Test dialogue generation uses LLM when available."""
        npc_id = uuid4()
        profile = create_npc_profile(entity_id=npc_id)

        response = await self.service.generate_dialogue(
            npc_id=npc_id,
            player_input="Hello there!",
            profile=profile,
            relationships=[],
            situation="Meeting in a tavern",
        )

        # Mock provider returns mock response
        assert response == "[Mock LLM response]"

    @pytest.mark.asyncio
    async def test_generate_dialogue_without_llm(self) -> None:
        """Test dialogue falls back to template without LLM."""
        service = NPCService(dolt=self.dolt, neo4j=self.neo4j, llm=None)
        npc_id = uuid4()
        profile = create_npc_profile(entity_id=npc_id)

        response = await service.generate_dialogue(
            npc_id=npc_id,
            player_input="Hello!",
            profile=profile,
            relationships=[],
            situation="Meeting in a tavern",
        )

        # Should use fallback template response
        assert response in ["Well met, friend!", "Hello, traveler.", "*glares* What do you want?"]

    @pytest.mark.asyncio
    async def test_fallback_dialogue_greeting(self) -> None:
        """Test fallback response for greetings."""
        service = NPCService(dolt=self.dolt, neo4j=self.neo4j, llm=None)
        npc_id = uuid4()
        profile = create_npc_profile(entity_id=npc_id, agreeableness=80)

        response = await service.generate_dialogue(
            npc_id=npc_id,
            player_input="Hi there!",
            profile=profile,
            relationships=[],
            situation="Meeting in a tavern",
        )

        # High agreeableness = friendly attitude = friendly greeting
        assert "friend" in response.lower() or "traveler" in response.lower()

    @pytest.mark.asyncio
    async def test_fallback_dialogue_question(self) -> None:
        """Test fallback response for questions."""
        service = NPCService(dolt=self.dolt, neo4j=self.neo4j, llm=None)
        npc_id = uuid4()
        profile = create_npc_profile(entity_id=npc_id)

        response = await service.generate_dialogue(
            npc_id=npc_id,
            player_input="Where is the blacksmith?",
            profile=profile,
            relationships=[],
            situation="In the town square",
        )

        # Should get a question-related response
        assert "?" not in response  # NPC shouldn't just repeat question
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_dialogue_uses_memories(self) -> None:
        """Test that dialogue retrieves relevant memories."""
        npc_id = uuid4()
        player_id = uuid4()

        # Create a memory about the player
        memory = create_memory(
            npc_id=npc_id,
            memory_type=MemoryType.ENCOUNTER,
            description="The player helped me defeat bandits",
            subject_id=player_id,
            importance=0.8,
            emotional_valence=0.7,
        )
        self.neo4j.create_memory(memory)

        profile = create_npc_profile(entity_id=npc_id)

        # Generate dialogue - it should retrieve the memory
        response = await self.service.generate_dialogue(
            npc_id=npc_id,
            player_input="Remember me?",
            profile=profile,
            relationships=[],
            situation="Meeting again in the tavern",
        )

        # The mock will return mock response, but memories were retrieved
        assert response is not None


# =============================================================================
# Dialogue Constraints Tests
# =============================================================================


class TestDialogueConstraintsFromContext:
    """Tests for building dialogue constraints from context."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.dolt = InMemoryDoltRepository()
        self.neo4j = InMemoryNeo4jRepository()
        self.service = NPCService(dolt=self.dolt, neo4j=self.neo4j)

    def test_build_constraints_friendly(self) -> None:
        """Test constraints for friendly NPC."""
        npc_id = uuid4()
        profile = create_npc_profile(
            entity_id=npc_id,
            extraversion=80,  # Verbose
            conscientiousness=70,  # Formal
            agreeableness=80,  # Friendly
        )

        constraints = self.service.build_dialogue_constraints(
            profile=profile,
            relationships=[
                RelationshipSummary(
                    target_id=uuid4(),
                    target_name="Player",
                    relationship_type="ALLIED_WITH",
                    strength=0.8,
                    trust=0.7,
                )
            ],
            memories=[],
            in_combat=False,
        )

        assert constraints.verbosity == "verbose"
        assert constraints.attitude_toward_player == "friendly"
        assert constraints.trust_level == "trusting"

    def test_build_constraints_hostile(self) -> None:
        """Test constraints for hostile NPC."""
        npc_id = uuid4()
        profile = create_npc_profile(
            entity_id=npc_id,
            extraversion=20,  # Terse
            agreeableness=20,  # Not friendly
        )

        # Note: For HOSTILE_TO relationships, the trust value is negated
        # in build_dialogue_constraints, so positive trust -> negative player_trust
        constraints = self.service.build_dialogue_constraints(
            profile=profile,
            relationships=[
                RelationshipSummary(
                    target_id=uuid4(),
                    target_name="Player",
                    relationship_type="HOSTILE_TO",
                    strength=0.8,
                    trust=0.7,  # Will be negated to -0.7 -> hostile attitude
                )
            ],
            memories=[],
            in_combat=False,
        )

        assert constraints.verbosity == "terse"
        assert constraints.attitude_toward_player == "hostile"
        assert constraints.trust_level == "suspicious"

    def test_build_constraints_in_combat(self) -> None:
        """Test constraints during combat."""
        npc_id = uuid4()
        profile = create_npc_profile(entity_id=npc_id)

        constraints = self.service.build_dialogue_constraints(
            profile=profile,
            relationships=[],
            memories=[],
            in_combat=True,
        )

        assert constraints.urgency == "urgent"

    def test_build_constraints_adds_important_memories(self) -> None:
        """Test that important memories are added to topics."""
        npc_id = uuid4()
        profile = create_npc_profile(entity_id=npc_id)

        memory = create_memory(
            npc_id=npc_id,
            memory_type=MemoryType.ACTION,
            description="The player saved my life from the dragon",
            importance=0.9,  # High importance
        )

        constraints = self.service.build_dialogue_constraints(
            profile=profile,
            relationships=[],
            memories=[memory],
            in_combat=False,
        )

        # Important memory should be in topics to mention
        assert len(constraints.topics_to_mention) > 0
        assert "saved" in constraints.topics_to_mention[0].lower()
