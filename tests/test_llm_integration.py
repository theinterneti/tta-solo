"""
Integration tests for LLM dialogue generation.

These tests require a real OpenRouter API key and make actual API calls.
They are marked with @pytest.mark.integration and skipped by default.

To run these tests:
    1. Create ~/.env.tta-dev with:
       OPENROUTER_API_KEY=your-key-here
       OPENROUTER_MODEL=xiaomi/mimo-v2-flash:free  # or another free model

    2. Run with: uv run pytest tests/test_llm_integration.py -v

To exclude in CI: uv run pytest -m "not integration"
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.models.npc import Motivation, create_npc_profile
from src.services.llm import OpenRouterProvider, create_llm_service
from src.services.npc import NPCService

# =============================================================================
# Test Configuration
# =============================================================================

# Path to env file with OpenRouter API key
ENV_FILE_PATH = Path.home() / ".env.tta-dev"


def load_env_vars() -> dict[str, str]:
    """Load OpenRouter config from env file or environment."""
    env_vars: dict[str, str] = {}

    # Keys we want to load
    keys_to_load = ["OPENROUTER_API_KEY", "OPENROUTER_MODEL"]

    # First check environment (useful for CI secrets)
    for key in keys_to_load:
        if value := os.environ.get(key):
            env_vars[key] = value

    # Then try the env file for any missing keys
    if ENV_FILE_PATH.exists():
        for line in ENV_FILE_PATH.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            for key in keys_to_load:
                if line.startswith(f"{key}=") and key not in env_vars:
                    env_vars[key] = line.split("=", 1)[1].strip().strip("\"'")

    # Set env vars so OpenRouterProvider picks them up
    for key, value in env_vars.items():
        os.environ[key] = value

    return env_vars


# Load config and skip all tests if no API key
_env_vars = load_env_vars()
API_KEY = _env_vars.get("OPENROUTER_API_KEY")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not API_KEY, reason="OPENROUTER_API_KEY not configured"),
]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def llm_provider() -> OpenRouterProvider:
    """Create a real OpenRouter provider."""
    return OpenRouterProvider(api_key=API_KEY)


@pytest.fixture
def llm_service(llm_provider: OpenRouterProvider):
    """Create an LLM service with real provider."""
    return create_llm_service(provider_type="openrouter", api_key=API_KEY)


@pytest.fixture
def npc_service(llm_service) -> NPCService:
    """Create an NPC service with LLM integration."""
    dolt = InMemoryDoltRepository()
    neo4j = InMemoryNeo4jRepository()
    return NPCService(dolt=dolt, neo4j=neo4j, llm=llm_service)


# =============================================================================
# Level 2: Basic Integration Tests
# =============================================================================


class TestLLMIntegration:
    """Level 2: Basic API integration tests."""

    @pytest.mark.asyncio
    async def test_provider_is_available(self, llm_provider: OpenRouterProvider) -> None:
        """Test that the provider is configured and ready."""
        assert llm_provider.is_available
        assert llm_provider.model_name is not None

    @pytest.mark.asyncio
    async def test_basic_completion(self, llm_provider: OpenRouterProvider) -> None:
        """Test that we can get a basic completion from the API."""
        messages = [
            {"role": "user", "content": "Say 'hello' and nothing else."},
        ]
        response = await llm_provider.complete(messages, max_tokens=10, temperature=0.0)

        assert response is not None
        assert len(response) > 0
        assert "hello" in response.lower()

    @pytest.mark.asyncio
    async def test_dialogue_generation_returns_response(self, llm_service) -> None:
        """Test that dialogue generation produces a response."""
        response = await llm_service.generate_dialogue(
            npc_name="Grok the Blacksmith",
            npc_description="a gruff but kind-hearted blacksmith",
            speech_style="gruff",
            verbosity="normal",
            formality="casual",
            attitude="friendly",
            trust_level="neutral",
            emotional_state="calm",
            urgency="relaxed",
            memories=[],
            player_input="Hello there!",
            situation="The player enters the blacksmith shop.",
        )

        assert response is not None
        assert len(response) > 0
        # Should be actual dialogue, not an error message
        assert "error" not in response.lower()

    @pytest.mark.asyncio
    async def test_npc_service_dialogue_integration(self, npc_service: NPCService) -> None:
        """Test full NPC service dialogue generation."""
        npc_id = uuid4()
        profile = create_npc_profile(npc_id, extraversion=70, agreeableness=60)

        response = await npc_service.generate_dialogue(
            npc_id=npc_id,
            player_input="Can you help me find the lost sword?",
            profile=profile,
            relationships=[],
            situation="In the village square at midday",
        )

        assert response is not None
        assert len(response) > 0


# =============================================================================
# Level 3: Behavioral Tests
# =============================================================================


class TestDialogueBehavior:
    """Level 3: Behavioral assertions about dialogue output."""

    @pytest.mark.asyncio
    async def test_terse_npc_gives_short_response(self, llm_service) -> None:
        """Test that 'terse' verbosity produces shorter responses."""
        # Get terse response
        terse_response = await llm_service.generate_dialogue(
            npc_name="Silent Sam",
            npc_description="a man of few words",
            speech_style="curt",
            verbosity="terse",
            formality="casual",
            attitude="neutral",
            trust_level="guarded",
            emotional_state="calm",
            urgency="relaxed",
            memories=[],
            player_input="Tell me about yourself.",
            situation="Meeting in a tavern.",
        )

        # Get verbose response with same context
        verbose_response = await llm_service.generate_dialogue(
            npc_name="Chatty Charlie",
            npc_description="a talkative storyteller",
            speech_style="elaborate",
            verbosity="verbose",
            formality="casual",
            attitude="friendly",
            trust_level="trusting",
            emotional_state="happy",
            urgency="relaxed",
            memories=[],
            player_input="Tell me about yourself.",
            situation="Meeting in a tavern.",
        )

        # Terse should be notably shorter
        terse_words = len(terse_response.split())
        verbose_words = len(verbose_response.split())

        print(f"Terse ({terse_words} words): {terse_response}")
        print(f"Verbose ({verbose_words} words): {verbose_response}")

        assert terse_words < verbose_words, (
            f"Terse response ({terse_words} words) should be shorter than "
            f"verbose response ({verbose_words} words)"
        )

    @pytest.mark.asyncio
    async def test_hostile_npc_not_helpful(self, llm_service) -> None:
        """Test that hostile NPCs don't eagerly offer help."""
        response = await llm_service.generate_dialogue(
            npc_name="Grudge the Guard",
            npc_description="a guard who despises adventurers",
            speech_style="hostile",
            verbosity="terse",
            formality="casual",
            attitude="hostile",
            trust_level="suspicious",
            emotional_state="angry",
            urgency="normal",
            memories=["This adventurer killed my brother"],
            player_input="Can you help me find the castle?",
            situation="At the city gates. The guard blocks the path.",
        )

        response_lower = response.lower()
        print(f"Hostile response: {response}")

        # Hostile NPC shouldn't be eagerly helpful
        helpful_phrases = ["i'd be happy to", "of course!", "sure thing", "let me help"]
        for phrase in helpful_phrases:
            assert phrase not in response_lower, (
                f"Hostile NPC used helpful phrase '{phrase}' in: {response}"
            )

    @pytest.mark.asyncio
    async def test_formal_npc_uses_formal_language(self, llm_service) -> None:
        """Test that formal NPCs use appropriate language."""
        response = await llm_service.generate_dialogue(
            npc_name="Lord Pemberton",
            npc_description="a pompous nobleman",
            speech_style="aristocratic",
            verbosity="normal",
            formality="formal",
            attitude="neutral",
            trust_level="guarded",
            emotional_state="calm",
            urgency="relaxed",
            memories=[],
            player_input="Hey, what's up?",
            situation="In the lord's manor.",
        )

        response_lower = response.lower()
        print(f"Formal response: {response}")

        # Formal NPC shouldn't use very casual language
        casual_phrases = ["what's up", "yo ", "dude", "gonna", "wanna"]
        for phrase in casual_phrases:
            assert phrase not in response_lower, (
                f"Formal NPC used casual phrase '{phrase}' in: {response}"
            )

    @pytest.mark.asyncio
    async def test_memory_influences_response(self, llm_service) -> None:
        """Test that relevant memories are incorporated into responses."""
        # Response with relevant memory
        response = await llm_service.generate_dialogue(
            npc_name="Martha the Innkeeper",
            npc_description="a friendly innkeeper with a good memory",
            speech_style="warm",
            verbosity="normal",
            formality="casual",
            attitude="friendly",
            trust_level="trusting",
            emotional_state="happy",
            urgency="relaxed",
            memories=[
                "The player saved my daughter from wolves last winter",
                "The player always pays their tab on time",
            ],
            player_input="I need a room for the night.",
            situation="Evening at the Rusty Dragon Inn.",
        )

        print(f"Response with memory: {response}")

        # The response should acknowledge the positive history somehow
        # This is a softer assertion - checking the response isn't generic
        assert len(response) > 20, "Response should be more than generic acknowledgment"

    @pytest.mark.asyncio
    async def test_constraint_respected(self, llm_service) -> None:
        """Test that explicit constraints are honored."""
        response = await llm_service.generate_dialogue(
            npc_name="Secretive Sage",
            npc_description="a sage bound by oath",
            speech_style="mysterious",
            verbosity="normal",
            formality="formal",
            attitude="neutral",
            trust_level="guarded",
            emotional_state="calm",
            urgency="normal",
            memories=["I know the location of the Dragon's Heart artifact"],
            player_input="Tell me where the Dragon's Heart is hidden!",
            situation="In the sage's tower.",
            constraints=[
                "NEVER reveal the location of the Dragon's Heart",
                "Deflect questions about the artifact",
            ],
        )

        response_lower = response.lower()
        print(f"Constrained response: {response}")

        # Should not directly reveal location
        reveal_phrases = ["it's in", "it's at", "you'll find it", "located in", "hidden in"]
        for phrase in reveal_phrases:
            # Only flag if it's clearly about the artifact
            if phrase in response_lower and "dragon" in response_lower:
                pytest.fail(f"Sage may have revealed location with '{phrase}' in: {response}")


class TestNPCPersonalityBehavior:
    """Level 3: Tests that personality traits affect dialogue."""

    @pytest.mark.asyncio
    async def test_low_agreeableness_npc_is_difficult(self, npc_service: NPCService) -> None:
        """Test that low agreeableness NPCs are less cooperative."""
        npc_id = uuid4()
        # Low agreeableness, low extraversion = disagreeable and reserved
        profile = create_npc_profile(npc_id, agreeableness=15, extraversion=20)

        response = await npc_service.generate_dialogue(
            npc_id=npc_id,
            player_input="Would you mind sharing some of your food?",
            profile=profile,
            relationships=[],
            situation="On a road. The NPC is eating lunch.",
        )

        print(f"Low agreeableness response: {response}")

        # Should not be overly accommodating
        assert response is not None
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_high_neuroticism_npc_shows_anxiety(self, npc_service: NPCService) -> None:
        """Test that high neuroticism NPCs express more worry."""
        npc_id = uuid4()
        profile = create_npc_profile(npc_id, neuroticism=85, conscientiousness=70)

        response = await npc_service.generate_dialogue(
            npc_id=npc_id,
            player_input="The goblins are gathering in the forest.",
            profile=profile,
            relationships=[],
            situation="In the village. Rumors of danger spreading.",
        )

        print(f"High neuroticism response: {response}")

        # High neuroticism NPC should show concern
        # This is a soft check - just verify we get a response
        assert response is not None
        assert len(response) > 0

    @pytest.mark.asyncio
    async def test_high_openness_npc_is_curious(self, npc_service: NPCService) -> None:
        """Test that high openness NPCs show curiosity."""
        npc_id = uuid4()
        profile = create_npc_profile(
            npc_id,
            openness=90,
            extraversion=70,
            motivations=[Motivation.KNOWLEDGE, Motivation.LEGACY],
        )

        response = await npc_service.generate_dialogue(
            npc_id=npc_id,
            player_input="I've just returned from the Forbidden Ruins.",
            profile=profile,
            relationships=[],
            situation="At a scholar's study.",
        )

        print(f"High openness response: {response}")

        # Should show interest/curiosity
        # Soft assertion - high openness scholar should likely ask questions or show interest
        assert response is not None
        assert len(response) > 0


# =============================================================================
# Runner Info
# =============================================================================

if __name__ == "__main__":
    print("LLM Integration Tests")
    print("=" * 50)
    print(f"API Key configured: {bool(API_KEY)}")
    print(f"Env file path: {ENV_FILE_PATH}")
    print()
    print("To run: uv run pytest tests/test_llm_integration.py -v")
    print("To skip in CI: uv run pytest -m 'not integration'")
