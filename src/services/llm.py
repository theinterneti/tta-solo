"""
LLM Service for TTA-Solo.

Provides BYOK (Bring Your Own Key) LLM integration via OpenRouter.
OpenRouter supports 100+ models through an OpenAI-compatible API.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol

from openai import AsyncOpenAI


class LLMProvider(Protocol):
    """
    Interface for LLM providers.

    Supports any OpenAI-compatible API (OpenRouter, OpenAI, Ollama, etc.)
    """

    async def complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 256,
        temperature: float = 0.7,
    ) -> str:
        """
        Generate a completion from messages.

        Args:
            messages: List of {"role": "user"|"assistant"|"system", "content": str}
            max_tokens: Maximum tokens in response
            temperature: Randomness (0.0 = deterministic, 1.0 = creative)

        Returns:
            Generated text response
        """
        ...

    @property
    def model_name(self) -> str:
        """The model being used."""
        ...

    @property
    def is_available(self) -> bool:
        """Whether the provider is configured and ready."""
        ...


@dataclass
class OpenRouterProvider:
    """
    OpenRouter LLM provider using OpenAI-compatible API.

    OpenRouter provides access to 100+ models (Claude, GPT-4, Llama, etc.)
    through a single API. Users bring their own API key.

    Configuration via environment variables:
        OPENROUTER_API_KEY: Your OpenRouter API key (required)
        OPENROUTER_MODEL: Model to use (default: anthropic/claude-3-haiku)
        LLM_BASE_URL: Custom base URL (default: OpenRouter)
        OPENROUTER_SITE_URL: Your site URL for rankings (optional)
        OPENROUTER_SITE_NAME: Your site name (optional)
    """

    api_key: str | None = None
    model: str = "anthropic/claude-3-haiku"
    base_url: str = "https://openrouter.ai/api/v1"
    site_url: str | None = None
    site_name: str = "TTA-Solo"

    _client: AsyncOpenAI | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        """Initialize from environment if not provided."""
        # Load from environment if not explicitly provided
        if self.api_key is None:
            self.api_key = os.getenv("OPENROUTER_API_KEY")

        if os.getenv("OPENROUTER_MODEL"):
            self.model = os.getenv("OPENROUTER_MODEL", self.model)

        if os.getenv("LLM_BASE_URL"):
            self.base_url = os.getenv("LLM_BASE_URL", self.base_url)

        if os.getenv("OPENROUTER_SITE_URL"):
            self.site_url = os.getenv("OPENROUTER_SITE_URL")

        if os.getenv("OPENROUTER_SITE_NAME"):
            self.site_name = os.getenv("OPENROUTER_SITE_NAME", self.site_name)

        # Initialize client if API key is available
        if self.api_key:
            headers = {"X-Title": self.site_name}
            if self.site_url:
                headers["HTTP-Referer"] = self.site_url

            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                default_headers=headers,
            )

    @property
    def model_name(self) -> str:
        """The model being used."""
        return self.model

    @property
    def is_available(self) -> bool:
        """Whether the provider is configured and ready."""
        return self._client is not None

    async def complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 256,
        temperature: float = 0.7,
    ) -> str:
        """
        Generate a completion from messages.

        Args:
            messages: List of {"role": "user"|"assistant"|"system", "content": str}
            max_tokens: Maximum tokens in response
            temperature: Randomness (0.0 = deterministic, 1.0 = creative)

        Returns:
            Generated text response

        Raises:
            RuntimeError: If provider is not configured (no API key)
        """
        if self._client is None:
            raise RuntimeError(
                "OpenRouter provider not configured. "
                "Set OPENROUTER_API_KEY environment variable."
            )

        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=max_tokens,
            temperature=temperature,
        )

        return response.choices[0].message.content or ""


@dataclass
class MockLLMProvider:
    """
    Mock LLM provider for testing and offline play.

    Returns template-based responses without making API calls.
    """

    model: str = "mock"
    responses: dict[str, str] = field(default_factory=dict)

    @property
    def model_name(self) -> str:
        """The model being used."""
        return self.model

    @property
    def is_available(self) -> bool:
        """Mock provider is always available."""
        return True

    async def complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 256,
        temperature: float = 0.7,
    ) -> str:
        """Return a mock response."""
        # Check for custom response based on last user message
        if messages:
            last_user_msg = next(
                (m["content"] for m in reversed(messages) if m["role"] == "user"),
                "",
            )
            if last_user_msg in self.responses:
                return self.responses[last_user_msg]

        return "[Mock LLM response]"

    def set_response(self, trigger: str, response: str) -> None:
        """Set a custom response for a specific input."""
        self.responses[trigger] = response


@dataclass
class LLMService:
    """
    High-level LLM service for game features.

    Provides specialized methods for common operations,
    handling prompt construction and response parsing.
    """

    provider: LLMProvider

    @property
    def is_available(self) -> bool:
        """Whether LLM features are available."""
        return self.provider.is_available

    async def generate_dialogue(
        self,
        npc_name: str,
        npc_description: str,
        speech_style: str,
        verbosity: str,
        formality: str,
        attitude: str,
        trust_level: str,
        emotional_state: str,
        urgency: str,
        memories: list[str],
        player_input: str,
        situation: str,
        constraints: list[str] | None = None,
    ) -> str:
        """
        Generate NPC dialogue response.

        Args:
            npc_name: Name of the NPC
            npc_description: Brief description of the NPC
            speech_style: How the NPC speaks (e.g., "formal", "crude", "poetic")
            verbosity: How much the NPC talks ("terse", "normal", "verbose")
            formality: Level of formality ("casual", "neutral", "formal")
            attitude: Attitude toward player ("friendly", "neutral", "hostile")
            trust_level: How much NPC trusts player ("trusting", "guarded", "suspicious")
            emotional_state: Current emotion ("calm", "angry", "afraid", "happy")
            urgency: Situation urgency ("relaxed", "normal", "urgent")
            memories: Relevant memories as strings
            player_input: What the player said
            situation: Description of current situation
            constraints: Additional constraints (topics to mention/avoid)

        Returns:
            Generated dialogue response
        """
        # Build system prompt
        system_prompt = f"""You are roleplaying as {npc_name}, {npc_description}.

PERSONALITY:
- Speech style: {speech_style}
- Verbosity: {verbosity}
- Formality: {formality}

CURRENT STATE:
- Attitude toward player: {attitude}
- Trust level: {trust_level}
- Emotional state: {emotional_state}
- Urgency: {urgency}

RELEVANT MEMORIES:
{chr(10).join(f'- {m}' for m in memories) if memories else '- None relevant'}

{f"CONSTRAINTS:{chr(10)}{chr(10).join(f'- {c}' for c in constraints)}" if constraints else ""}

Respond in character as {npc_name}. Keep response to 1-3 sentences unless more detail is warranted.
Do not break character or mention being an AI. Do not use quotation marks around your response."""

        # Build user prompt
        user_prompt = f"""The player says: "{player_input}"

Current situation: {situation}

Respond as {npc_name}:"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        return await self.provider.complete(
            messages=messages,
            max_tokens=256,
            temperature=0.7,
        )

    async def generate_narrative(
        self,
        event_description: str,
        tone: str,
        location: str,
        characters_involved: list[str],
    ) -> str:
        """
        Generate narrative description of an event.

        Args:
            event_description: What happened (mechanical description)
            tone: Narrative tone ("gritty", "heroic", "comedic", etc.)
            location: Where it happened
            characters_involved: Names of characters involved

        Returns:
            Narrative description
        """
        system_prompt = f"""You are a narrator for a tabletop RPG game.
Your tone is {tone}.
Write vivid, engaging descriptions of events.
Keep responses to 2-4 sentences."""

        user_prompt = f"""Describe this event narratively:

Event: {event_description}
Location: {location}
Characters: {', '.join(characters_involved)}

Narrate:"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        return await self.provider.complete(
            messages=messages,
            max_tokens=256,
            temperature=0.8,
        )


def create_llm_service(
    provider_type: str = "openrouter",
    **kwargs,
) -> LLMService:
    """
    Factory function to create an LLM service.

    Args:
        provider_type: Type of provider ("openrouter", "mock")
        **kwargs: Provider-specific configuration

    Returns:
        Configured LLMService

    Example:
        # Auto-configure from environment
        service = create_llm_service()

        # Explicit configuration
        service = create_llm_service(
            provider_type="openrouter",
            api_key="sk-or-...",
            model="anthropic/claude-3-sonnet",
        )

        # Mock for testing
        service = create_llm_service(provider_type="mock")
    """
    if provider_type == "mock":
        provider = MockLLMProvider(**kwargs)
    elif provider_type == "openrouter":
        provider = OpenRouterProvider(**kwargs)
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")

    return LLMService(provider=provider)
