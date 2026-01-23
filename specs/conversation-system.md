# TTA-Solo: Conversation System Spec

## 1. Overview

The conversation system enables meaningful dialogue between players and NPCs. It combines pre-defined dialogue choices with LLM-generated responses, ensuring conversations are both predictable enough to be useful and dynamic enough to feel natural.

---

## 2. Core Philosophy

### Hybrid Dialogue Model
- **Choices (Symbolic)**: Player selects from context-aware options
- **Responses (Neural)**: LLM generates NPC responses using personality constraints
- **Topics (Symbolic)**: Conversation topics drive available choices

### Key Principles
1. **Always Escapable**: Player can exit conversation at any time
2. **Personality-Driven**: NPC responses reflect their Big Five traits
3. **Memory-Informed**: NPCs remember past interactions
4. **Context-Aware**: Choices adapt to situation (shop, quest, combat)
5. **Action-Oriented**: Conversations can lead to tangible outcomes

---

## 3. Conversation Flow

```
/talk <NPC>
    │
    ▼
┌─────────────────────────────────────────┐
│  NPC Greeting (LLM-generated)           │
│  "Welcome to the Rusty Dragon, friend!" │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  Dialogue Choices (3-5 options)         │
│  [1] Ask about local rumors             │
│  [2] Inquire about quests               │
│  [3] Browse their wares (if merchant)   │
│  [4] Say something else...              │
│  [0] End conversation                   │
└─────────────────────────────────────────┘
    │
    ▼
Player selects option (or types custom)
    │
    ▼
┌─────────────────────────────────────────┐
│  NPC Response (LLM-generated)           │
│  Constrained by personality + context   │
└─────────────────────────────────────────┘
    │
    ▼
Loop until [0] or context ends
```

---

## 4. Dialogue Topics

### Topic Categories

```python
class ConversationTopic(str, Enum):
    """Available conversation topics."""

    # General
    GREETING = "greeting"       # Initial greeting
    FAREWELL = "farewell"       # Ending conversation
    SMALLTALK = "smalltalk"     # General chat
    CUSTOM = "custom"           # Free-form player input

    # Information
    RUMORS = "rumors"           # Local gossip and news
    DIRECTIONS = "directions"   # How to get somewhere
    LORE = "lore"               # World/location history
    ABOUT_SELF = "about_self"   # NPC's background

    # Transactional
    QUEST = "quest"             # Quest-related dialogue
    SHOP = "shop"               # Buy/sell items
    SERVICE = "service"         # NPC services (inn, heal, etc.)

    # Social
    PERSUADE = "persuade"       # Convince NPC of something
    INTIMIDATE = "intimidate"   # Threaten NPC
    FLATTER = "flatter"         # Compliment NPC
```

### Topic Availability

Topics are filtered based on:
1. **NPC Role**: Merchants have SHOP, quest-givers have QUEST
2. **Relationship**: INTIMIDATE requires hostile or neutral stance
3. **Knowledge**: RUMORS requires NPC to know something
4. **Situation**: No SHOP during combat

```python
def get_available_topics(
    npc: Entity,
    profile: NPCProfile,
    relationships: list[Relationship],
    context: ConversationContext,
) -> list[ConversationTopic]:
    """
    Determine which topics are available for this conversation.

    Always includes: SMALLTALK, CUSTOM, FAREWELL
    Conditional: SHOP (merchant), QUEST (quest-giver), etc.
    """
```

---

## 5. Data Models

### ConversationContext

```python
class ConversationContext(BaseModel):
    """Current state of a conversation."""

    id: UUID = Field(default_factory=uuid4)
    npc_id: UUID
    player_id: UUID
    universe_id: UUID
    location_id: UUID

    # Conversation state
    started_at: datetime = Field(default_factory=datetime.utcnow)
    turn_count: int = 0
    current_topic: ConversationTopic = ConversationTopic.GREETING

    # History (for this conversation)
    exchanges: list[DialogueExchange] = Field(default_factory=list)

    # Transactional state
    pending_quest_id: UUID | None = None
    pending_trade: TradeState | None = None

    # Mood tracking
    npc_mood: float = Field(ge=-1.0, le=1.0, default=0.0)
    """How the NPC feels about this conversation so far."""


class DialogueExchange(BaseModel):
    """A single back-and-forth in conversation."""

    player_input: str
    player_topic: ConversationTopic
    npc_response: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

### DialogueChoice

```python
class DialogueChoice(BaseModel):
    """A selectable dialogue option."""

    id: int  # 1-based index for selection
    topic: ConversationTopic
    label: str  # What player sees
    preview: str | None = None  # Optional preview of what they'll say

    # Metadata
    requires_skill_check: bool = False
    skill_check_dc: int | None = None
    skill_check_ability: str | None = None


class DialogueOptions(BaseModel):
    """Available choices for current conversation turn."""

    choices: list[DialogueChoice]
    allows_custom_input: bool = True
    exit_option_id: int = 0  # Always 0 to exit
```

---

## 6. Conversation Service

```python
@dataclass
class ConversationService:
    """Service for managing NPC conversations."""

    npc_service: NPCService
    llm: LLMService | None = None

    async def start_conversation(
        self,
        npc_id: UUID,
        player_id: UUID,
        universe_id: UUID,
        location_id: UUID,
    ) -> tuple[ConversationContext, str, DialogueOptions]:
        """
        Start a conversation with an NPC.

        Returns:
            - ConversationContext for tracking state
            - Opening greeting (LLM-generated)
            - Available dialogue choices
        """

    async def continue_conversation(
        self,
        context: ConversationContext,
        player_choice: int | str,
    ) -> tuple[str, DialogueOptions | None]:
        """
        Process player's dialogue choice and generate NPC response.

        Args:
            context: Current conversation state
            player_choice: Choice ID (int) or custom text (str)

        Returns:
            - NPC response (LLM-generated)
            - Next choices (None if conversation ended)
        """

    def end_conversation(
        self,
        context: ConversationContext,
    ) -> str:
        """
        End the conversation gracefully.

        Returns farewell message.
        """

    def build_choices(
        self,
        npc: Entity,
        profile: NPCProfile,
        context: ConversationContext,
    ) -> DialogueOptions:
        """
        Build available dialogue choices based on context.
        """
```

---

## 7. LLM Integration

### Dialogue Generation Prompt

```python
CONVERSATION_PROMPT = """
You are {npc_name}, {npc_description}.

PERSONALITY:
- Speech style: {speech_style}
- Attitude toward player: {attitude}
- Current emotional state: {emotional_state}
- Key traits: {trait_summary}

RELEVANT MEMORIES:
{memories}

CURRENT CONVERSATION:
{exchange_history}

PLAYER NOW SAYS: "{player_input}"
TOPIC: {topic}

Respond as {npc_name} would. Guidelines:
- Stay in character based on personality
- Keep response to 2-4 sentences
- If asked about something you don't know, say so in character
- Reference memories if relevant
{additional_constraints}

Your response:
"""
```

### Response Processing

1. Generate response using personality constraints
2. Detect if topic should change (e.g., player asks about quests)
3. Update NPC mood based on interaction
4. Form memory if significant

---

## 8. CLI Integration

### /talk Command (Updated)

```python
def _cmd_talk(self, state: GameState, args: list[str]) -> str | None:
    """Handle talk command - enters conversation mode."""

    # ... existing NPC lookup code ...

    # Start conversation
    context, greeting, options = await self.conversation_service.start_conversation(
        npc_id=npc.id,
        player_id=state.character_id,
        universe_id=state.universe_id,
        location_id=state.location_id,
    )

    # Store conversation context in state
    state.conversation = context

    # Format and return
    return self._format_conversation(npc.name, greeting, options)


def _format_conversation(
    self,
    npc_name: str,
    response: str,
    options: DialogueOptions | None,
) -> str:
    """Format conversation for display."""
    lines = [
        f"{npc_name}:",
        f'  "{response}"',
        "",
    ]

    if options:
        lines.append("What do you say?")
        for choice in options.choices:
            lines.append(f"  [{choice.id}] {choice.label}")
        if options.allows_custom_input:
            lines.append(f"  [*] Say something else...")
        lines.append(f"  [0] End conversation")

    return "\n".join(lines)
```

### Conversation Mode

When in conversation, the REPL routes input differently:

```python
async def _process_input(self, text: str, state: GameState) -> str:
    # Check if in conversation mode
    if state.conversation is not None:
        return await self._process_conversation_input(text, state)

    # ... normal command/game processing ...


async def _process_conversation_input(
    self,
    text: str,
    state: GameState,
) -> str:
    """Process input while in conversation mode."""
    context = state.conversation

    # Handle exit
    if text == "0" or text.lower() in ["bye", "goodbye", "leave", "exit"]:
        farewell = self.conversation_service.end_conversation(context)
        state.conversation = None
        return farewell

    # Handle choice selection
    if text.isdigit():
        choice_id = int(text)
    else:
        # Custom input
        choice_id = text

    response, options = await self.conversation_service.continue_conversation(
        context, choice_id
    )

    # Check if conversation ended
    if options is None:
        state.conversation = None

    return self._format_conversation(
        context.npc_name,
        response,
        options,
    )
```

---

## 9. Memory Integration

### Conversation Memories

After each significant exchange, form a memory:

```python
def _maybe_form_memory(
    self,
    context: ConversationContext,
    exchange: DialogueExchange,
) -> NPCMemory | None:
    """
    Form a memory from a conversation exchange if significant.

    Significant exchanges:
    - First meeting with player
    - Quest-related discussions
    - Emotional exchanges (high valence)
    - Lies or deception
    - Persuasion/intimidation attempts
    """
```

### Memory Retrieval

When starting a conversation, retrieve relevant memories:

```python
def _get_conversation_memories(
    self,
    npc_id: UUID,
    player_id: UUID,
    location_id: UUID,
) -> list[NPCMemory]:
    """
    Get memories relevant to this conversation.

    Prioritizes:
    - Memories about the player
    - Recent memories
    - Emotionally significant memories
    """
```

---

## 10. Special Topics

### Quest Conversations

When topic is QUEST:
1. Check if NPC has available quests
2. Present quest overview
3. Allow player to accept/decline
4. Update quest state on acceptance

```python
async def _handle_quest_topic(
    self,
    context: ConversationContext,
    npc: Entity,
) -> tuple[str, DialogueOptions]:
    """
    Handle quest-related conversation.

    If NPC has quests:
    - Present available quest
    - Generate quest dialogue
    - Offer accept/decline choices

    If no quests:
    - Generate "nothing for you right now" response
    """
```

### Shop Conversations

When topic is SHOP:
1. Switch to shop interface OR
2. Present shopping choices within conversation

```python
async def _handle_shop_topic(
    self,
    context: ConversationContext,
    npc: Entity,
) -> tuple[str, DialogueOptions]:
    """
    Handle shop-related conversation.

    Options:
    - List items for sale
    - Transition to /shop command
    - Negotiate prices (future)
    """
```

---

## 11. Fallback Behavior

When LLM is unavailable, use template responses:

```python
FALLBACK_RESPONSES = {
    ConversationTopic.GREETING: [
        "Hello there.",
        "What do you want?",
        "Yes?",
    ],
    ConversationTopic.RUMORS: [
        "I don't know anything interesting.",
        "Haven't heard much lately.",
        "You should ask someone else.",
    ],
    ConversationTopic.FAREWELL: [
        "Farewell.",
        "Safe travels.",
        "Until next time.",
    ],
    # ... etc
}
```

---

## 12. Implementation Priority

1. **Phase 1**: Basic conversation loop
   - Start/end conversation
   - Fixed dialogue choices
   - Simple greeting/farewell

2. **Phase 2**: LLM integration
   - Wire up `generate_dialogue()` from NPCService
   - Personality-driven responses
   - Topic detection

3. **Phase 3**: Topic handling
   - Quest conversations
   - Shop integration
   - Rumors/lore system

4. **Phase 4**: Memory integration
   - Form memories from conversations
   - Retrieve memories for context
   - Reference past interactions

---

## 13. Example Conversation

```
> /talk Ameiko

Ameiko Kaijitsu:
  "Well, well! A new face in the Rusty Dragon. Welcome, traveler!
   What brings you to Sandpoint?"

What do you say?
  [1] Ask about local rumors
  [2] Inquire about rooms for the night
  [3] Ask about adventuring work
  [*] Say something else...
  [0] End conversation

> 1

Ameiko Kaijitsu:
  "Rumors? Oh, there's always talk in a tavern. Lately folks have been
   whispering about strange lights in the old Kaijitsu manor. My family's
   old place, actually. I wouldn't go poking around there if I were you."

What do you say?
  [1] Ask more about the manor
  [2] Change the subject
  [3] "Why shouldn't I investigate?"
  [*] Say something else...
  [0] End conversation

> 3

Ameiko Kaijitsu:
  "Ha! A bold one, aren't you? Look, I won't stop you. But that place
   has history. Dark history. If you're determined to go, at least
   be careful. And maybe come back to tell me what you find?"

What do you say?
  [1] Accept the informal quest
  [2] Ask what she'd pay for information
  [3] Decline politely
  [*] Say something else...
  [0] End conversation

> 0

Ameiko Kaijitsu:
  "Leaving so soon? Well, safe travels. Come back anytime!"

You end your conversation with Ameiko.
```
