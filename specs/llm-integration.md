# TTA-Solo: LLM Integration Spec

## 1. Overview

This spec defines the LLM integration layer for TTA-Solo. The design prioritizes:
- **BYOK (Bring Your Own Key)**: Users provide their own API keys
- **Provider Flexibility**: OpenRouter as default (supports 100+ models)
- **Graceful Degradation**: Game works without LLM, just less flavorful

---

## 2. Architecture

### Provider Abstraction

```
┌─────────────────────────────────────────────┐
│              LLMService                      │
│  (High-level interface for game features)   │
├─────────────────────────────────────────────┤
│         LLMProvider (Protocol)              │
│  - complete(messages) -> str                │
│  - complete_structured(messages, schema)    │
├─────────────────────────────────────────────┤
│ OpenRouterProvider │ MockProvider │ Future  │
└─────────────────────────────────────────────┘
```

### Why OpenRouter?

1. **Single API, many models**: Claude, GPT-4, Llama, Mistral, Gemini, etc.
2. **OpenAI-compatible**: Uses standard `openai` Python library
3. **Pay-per-use**: No subscriptions required
4. **Free tier**: Some models available at no cost

---

## 3. Configuration

### Environment Variables

```bash
# Required for LLM features
OPENROUTER_API_KEY=sk-or-...

# Optional: Override default model
OPENROUTER_MODEL=anthropic/claude-3-haiku

# Optional: Custom base URL (for other OpenAI-compatible APIs)
LLM_BASE_URL=https://openrouter.ai/api/v1

# Optional: Site info for OpenRouter rankings
OPENROUTER_SITE_URL=https://github.com/your-repo
OPENROUTER_SITE_NAME=TTA-Solo
```

### Default Model Selection

Priority order:
1. User-specified via `OPENROUTER_MODEL`
2. `anthropic/claude-3-haiku` (fast, cheap, good quality)
3. Fallback to mock provider if no API key

### Recommended Models by Use Case

| Use Case | Recommended Model | Fallback |
|----------|------------------|----------|
| Dialogue Generation | claude-3-haiku | Mock |
| Intent Parsing | claude-3-haiku | Rule-based |
| Complex Narrative | claude-3-sonnet | claude-3-haiku |

---

## 4. Provider Interface

### Core Protocol

```python
from typing import Protocol

class LLMProvider(Protocol):
    """Interface for LLM providers."""

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
```

### OpenRouter Implementation

```python
@dataclass
class OpenRouterProvider:
    """OpenRouter LLM provider using OpenAI-compatible API."""

    api_key: str
    model: str = "anthropic/claude-3-haiku"
    base_url: str = "https://openrouter.ai/api/v1"
    site_url: str | None = None
    site_name: str | None = None

    _client: AsyncOpenAI = field(init=False)

    def __post_init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            default_headers={
                "HTTP-Referer": self.site_url or "",
                "X-Title": self.site_name or "TTA-Solo",
            }
        )

    async def complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 256,
        temperature: float = 0.7,
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""
```

### Mock Provider (for testing/offline)

```python
class MockLLMProvider:
    """Mock provider for testing and offline play."""

    model_name: str = "mock"
    is_available: bool = True

    async def complete(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 256,
        temperature: float = 0.7,
    ) -> str:
        # Return template-based response
        return "[Mock LLM response]"
```

---

## 5. LLM Service

### High-Level Interface

```python
@dataclass
class LLMService:
    """
    High-level LLM service for game features.

    Provides specialized methods for common operations,
    handling prompt construction and response parsing.
    """

    provider: LLMProvider

    async def generate_dialogue(
        self,
        npc_name: str,
        npc_description: str,
        constraints: DialogueConstraints,
        player_input: str,
        context: str,
    ) -> str:
        """Generate NPC dialogue response."""

    async def parse_intent(
        self,
        player_input: str,
        context: str,
    ) -> Intent:
        """Parse player intent using LLM."""

    async def generate_narrative(
        self,
        event_description: str,
        tone: str,
        context: str,
    ) -> str:
        """Generate narrative description of an event."""
```

---

## 6. Dialogue Generation

### Prompt Template

```python
NPC_DIALOGUE_SYSTEM = """You are roleplaying as {npc_name}, {npc_description}.

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
{memories}

CONSTRAINTS:
{constraints}

Respond in character as {npc_name}. Keep response to 1-3 sentences unless more detail is needed.
Do not break character or mention being an AI."""

NPC_DIALOGUE_USER = """The player says: "{player_input}"

Current situation: {situation}

Respond as {npc_name}:"""
```

### Integration with NPCService

```python
class NPCService:
    llm: LLMService | None = None

    async def generate_dialogue(
        self,
        npc_id: UUID,
        player_input: str,
        context: Context,
    ) -> str:
        """Generate NPC dialogue using personality constraints."""

        if self.llm is None:
            return self._fallback_dialogue(npc_id, player_input)

        # Get NPC profile
        profile = self._get_profile(npc_id)

        # Build constraints from profile and context
        constraints = DialogueConstraints.from_context(
            profile=profile,
            player_trust=self._get_player_trust(npc_id, context),
            in_combat=context.danger_level > 5,
        )

        # Retrieve relevant memories
        memories = self.retrieve_memories(npc_id, player_input)

        # Generate dialogue
        return await self.llm.generate_dialogue(
            npc_name=profile.entity_id,  # Will need name lookup
            npc_description="...",
            constraints=constraints,
            player_input=player_input,
            context=self._format_context(context, memories),
        )
```

---

## 7. Error Handling

### Graceful Degradation

```python
async def generate_dialogue_safe(
    self,
    npc_id: UUID,
    player_input: str,
    context: Context,
) -> str:
    """Generate dialogue with fallback on error."""
    try:
        if self.llm and self.llm.provider.is_available:
            return await self.generate_dialogue(npc_id, player_input, context)
    except Exception as e:
        logger.warning(f"LLM generation failed: {e}")

    # Fallback to template-based response
    return self._fallback_dialogue(npc_id, player_input)
```

### Fallback Responses

Template-based responses when LLM unavailable:
- Greetings: "Hello, traveler."
- Questions: "I don't know much about that."
- Hostility: "*glares silently*"
- Trading: "Let me see what you have."

---

## 8. Rate Limiting & Costs

### Cost Awareness

```python
@dataclass
class LLMUsageTracker:
    """Track LLM usage for cost awareness."""

    total_tokens: int = 0
    total_requests: int = 0

    def log_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.total_tokens += prompt_tokens + completion_tokens
        self.total_requests += 1

    def estimate_cost(self, cost_per_1k_tokens: float = 0.00025) -> float:
        """Estimate cost in USD (default: claude-3-haiku pricing)."""
        return (self.total_tokens / 1000) * cost_per_1k_tokens
```

### Caching (Future)

Consider caching common responses:
- Generic greetings
- Shop interactions
- Combat taunts

---

## 9. Testing Strategy

### Unit Tests

```python
class TestOpenRouterProvider:
    """Tests for OpenRouter provider."""

    @pytest.mark.asyncio
    async def test_complete_basic(self, mock_openai):
        """Test basic completion."""

    def test_missing_api_key(self):
        """Test graceful handling of missing API key."""

    def test_is_available(self):
        """Test availability check."""

class TestLLMService:
    """Tests for LLM service."""

    @pytest.mark.asyncio
    async def test_generate_dialogue(self, mock_provider):
        """Test dialogue generation."""

    @pytest.mark.asyncio
    async def test_fallback_on_error(self, failing_provider):
        """Test fallback when provider fails."""
```

### Integration Tests (Manual)

```python
@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("OPENROUTER_API_KEY"), reason="No API key")
async def test_real_openrouter():
    """Test with real OpenRouter API (manual run only)."""
```

---

## 10. Implementation Priority

1. **Phase 1**: Core provider interface + OpenRouter implementation
2. **Phase 2**: LLMService with dialogue generation
3. **Phase 3**: Integration with NPCService
4. **Phase 4**: Fallback templates
5. **Phase 5**: Usage tracking and caching (optional)
