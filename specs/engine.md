# TTA-Solo: Engine Spec

## 1. Overview

The Engine is the orchestration layer - the "bridge" between the Neural (LLM) and Symbolic (Python skills) layers. It manages the game loop, routes player actions, and coordinates multiple AI agents.

---

## 2. Core Principles

### Neuro-Symbolic Split
- **Neural**: Narrative, dialogue, improvisation, ambiguity resolution
- **Symbolic**: Dice rolls, damage calculation, rule enforcement
- **Bridge**: Engine translates intent → function calls → narrative

### Stateless Execution
- Engine holds no game state between turns
- All state lives in Dolt (truth) and Neo4j (context)
- Each turn is a fresh execution with loaded context

### Fail Forward
- If Symbolic layer fails, Neural takes over
- Never dead-end the player
- Log edge cases for improvement

---

## 3. Agent Architecture

### The Three Agents

```
┌─────────────────────────────────────────────────────┐
│                    Game Master                       │
│  (Orchestrator - routes to specialists)              │
└─────────────────┬───────────────────┬───────────────┘
                  │                   │
         ┌────────▼────────┐ ┌────────▼────────┐
         │  Rules Lawyer   │ │   Lorekeeper    │
         │  (Mechanics)    │ │   (Context)     │
         └─────────────────┘ └─────────────────┘
```

#### Game Master (GM)
- **Role**: Primary narrator and orchestrator
- **Responsibilities**:
  - Interpret player intent
  - Generate narrative descriptions
  - Manage scene pacing (PbtA-style moves)
  - Delegate to specialists when needed
- **Never does**: Dice math, rule lookups, inventing lore

#### Rules Lawyer (RL)
- **Role**: Mechanical enforcer
- **Responsibilities**:
  - Call skills for dice rolls
  - Validate actions against rules
  - Calculate outcomes (damage, DCs, etc.)
  - Enforce SRD 5e constraints
- **Never does**: Generate narrative, make story decisions

#### Lorekeeper (LK)
- **Role**: Context provider
- **Responsibilities**:
  - Query Neo4j for relevant entities/relationships
  - Provide world context to GM
  - Track NPC memories and relationships
  - Surface relevant history
- **Never does**: Make decisions, generate new content

---

## 4. Turn Structure

### The Game Loop

```python
class Turn:
    """A single player turn in the game loop."""

    player_input: str           # Raw player text
    universe_id: UUID           # Current timeline
    actor_id: UUID              # Player's character
    location_id: UUID           # Current location

    # Filled during processing
    intent: Intent | None       # Parsed intent
    context: Context | None     # Retrieved context
    skill_results: list[SkillResult]  # Mechanical outcomes
    events: list[Event]         # Generated events
    narrative: str              # Final response to player
```

### Processing Phases

```
Player Input
     │
     ▼
┌─────────────┐
│ 1. PARSE    │  GM extracts intent from natural language
└─────┬───────┘
      │
      ▼
┌─────────────┐
│ 2. CONTEXT  │  LK retrieves relevant world state
└─────┬───────┘
      │
      ▼
┌─────────────┐
│ 3. RESOLVE  │  RL executes mechanical skills
└─────┬───────┘
      │
      ▼
┌─────────────┐
│ 4. RECORD   │  Engine writes events to Dolt
└─────────────┘
      │
      ▼
┌─────────────┐
│ 5. NARRATE  │  GM generates response
└─────────────┘
      │
      ▼
  Response to Player
```

---

## 5. Intent System

### Intent Types

```python
class IntentType(str, Enum):
    """Categories of player intent."""

    # Combat
    ATTACK = "attack"
    CAST_SPELL = "cast_spell"
    USE_ABILITY = "use_ability"

    # Social
    TALK = "talk"
    PERSUADE = "persuade"
    INTIMIDATE = "intimidate"
    DECEIVE = "deceive"

    # Exploration
    MOVE = "move"
    LOOK = "look"
    SEARCH = "search"
    INTERACT = "interact"

    # Items
    USE_ITEM = "use_item"
    PICK_UP = "pick_up"
    DROP = "drop"
    GIVE = "give"

    # Meta
    REST = "rest"
    WAIT = "wait"
    ASK_QUESTION = "ask_question"  # Player asking about world

    # Special
    FORK = "fork"           # "What if I had..."
    UNCLEAR = "unclear"     # Need clarification
```

### Intent Schema

```python
class Intent(BaseModel):
    """Parsed player intent."""

    type: IntentType
    confidence: float           # 0.0 - 1.0

    # Target extraction
    target_name: str | None     # "the goblin", "the chest"
    target_id: UUID | None      # Resolved entity ID

    # Action details
    method: str | None          # "with my sword", "using fireball"
    dialogue: str | None        # What to say (for TALK intents)

    # Location
    destination: str | None     # For MOVE intents

    # Raw
    original_input: str
    reasoning: str              # Why this intent was chosen
```

---

## 6. Context Retrieval

### Context Schema

```python
class Context(BaseModel):
    """World context for a turn."""

    # Actor state
    actor: Entity
    actor_stats: EntityStats
    actor_inventory: list[Entity]

    # Location
    location: Entity
    entities_present: list[Entity]  # NPCs, items, features
    exits: list[str]                # Available directions

    # Relationships
    known_entities: list[tuple[Entity, Relationship]]
    recent_events: list[Event]      # Last N events

    # Atmosphere (from Neo4j)
    mood: str | None
    danger_level: int
```

### Context Query Flow

```
1. Get actor from Dolt (by actor_id)
2. Get location from Dolt (by location_id)
3. Query Neo4j: entities LOCATED_IN location
4. Query Neo4j: actor's relationships (KNOWS, FEARS, etc.)
5. Query Dolt: recent events in this location
6. Query Neo4j: location atmosphere/mood
```

---

## 7. Skill Execution

### Skill Registry

```python
SKILL_REGISTRY: dict[IntentType, Callable] = {
    IntentType.ATTACK: resolve_attack,
    IntentType.CAST_SPELL: resolve_spell,
    IntentType.PERSUADE: skill_check,  # with "persuasion"
    IntentType.INTIMIDATE: skill_check,  # with "intimidation"
    IntentType.SEARCH: skill_check,  # with "investigation" or "perception"
    IntentType.REST: take_short_rest,  # or take_long_rest
    # ... etc
}
```

### Skill Result Schema

```python
class SkillResult(BaseModel):
    """Result of executing a skill."""

    success: bool
    outcome: EventOutcome

    # Dice
    roll: int | None
    total: int | None
    dc: int | None

    # Effects
    damage: int | None
    healing: int | None
    conditions: list[str]

    # For narrative
    description: str            # "You rolled 18 + 5 = 23 vs AC 15"
    is_critical: bool
    is_fumble: bool
```

---

## 8. PbtA-Style Moves

### Move Outcomes

Following Powered by the Apocalypse design:

- **Strong Hit** (10+): Player gets what they want, plus extra
- **Weak Hit** (7-9): Player gets what they want, but with cost/complication
- **Miss** (6-): Player doesn't get what they want, GM makes a move

### GM Moves (on Miss)

```python
class GMMoveType(str, Enum):
    """Moves the GM can make on player failures."""

    # Soft moves (warnings)
    SHOW_DANGER = "show_danger"
    OFFER_OPPORTUNITY = "offer_opportunity"
    REVEAL_UNWELCOME_TRUTH = "reveal_unwelcome_truth"

    # Hard moves (consequences)
    DEAL_DAMAGE = "deal_damage"
    USE_MONSTER_MOVE = "use_monster_move"
    SEPARATE_THEM = "separate_them"
    TAKE_AWAY = "take_away"
    CAPTURE = "capture"

    # Always available
    ADVANCE_TIME = "advance_time"
    INTRODUCE_NPC = "introduce_npc"
    CHANGE_ENVIRONMENT = "change_environment"
```

---

## 9. Event Recording

### Event Flow

```
Skill Result
     │
     ▼
┌─────────────────┐
│ Create Event(s) │  One or more events from the action
└─────┬───────────┘
      │
      ▼
┌─────────────────┐
│ Append to Dolt  │  Immutable event log
└─────┬───────────┘
      │
      ▼
┌─────────────────┐
│ Update Neo4j    │  Relationship changes (optional)
└─────────────────┘
```

### State Changes

Events may trigger state changes:
- HP changes → Update entity in Dolt
- Movement → Update LOCATED_IN in Neo4j
- Death → Mark entity inactive, create DEATH event
- Relationship change → Update Neo4j edge

---

## 10. Narrative Generation

### Narrative Context

```python
class NarrativeContext(BaseModel):
    """Context for generating the final narrative."""

    intent: Intent
    context: Context
    skill_results: list[SkillResult]
    events: list[Event]

    # Style hints
    tone: str = "adventure"     # adventure, horror, comedy, etc.
    verbosity: str = "normal"   # terse, normal, verbose
    perspective: str = "second" # second person ("You see...")
```

### Narrative Rules

1. **Show, don't tell**: Describe actions and results, not stats
2. **Include sensory details**: Sight, sound, smell when relevant
3. **Reference context**: Use NPC names, location features
4. **Acknowledge player choice**: Reflect their stated intent
5. **Set up next beat**: End with implicit prompt for next action

---

## 11. Error Handling

### Graceful Degradation

```python
class FallbackChain:
    """Try each handler until one succeeds."""

    async def handle(self, turn: Turn) -> str:
        # Try symbolic resolution
        try:
            result = await self.resolve_with_skills(turn)
            return await self.narrate(result)
        except SkillError as e:
            log.warning(f"Skill failed: {e}")

        # Fall back to pure narrative
        try:
            return await self.narrate_without_mechanics(turn)
        except NarrativeError as e:
            log.error(f"Narrative failed: {e}")

        # Ultimate fallback
        return "Something unexpected happened. What do you do?"
```

### Edge Case Logging

```python
class EdgeCase(BaseModel):
    """Log unusual situations for review."""

    turn_id: UUID
    category: str           # "intent_unclear", "skill_failed", etc.
    player_input: str
    context_snapshot: dict
    error: str | None
    fallback_used: str
    timestamp: datetime
```

---

## 12. Implementation Phases

### Phase 1: Basic Loop
- Single-agent GM (no specialists yet)
- Intent parsing with fixed categories
- Skill execution for combat and checks
- Simple narrative generation
- Event recording to in-memory Dolt

### Phase 2: Context Integration
- Neo4j context retrieval
- Relationship-aware responses
- Location descriptions from graph
- Recent event awareness

### Phase 3: Agent Specialization
- Split GM into three agents
- Rules Lawyer for all mechanics
- Lorekeeper for context queries
- Agent communication protocol

### Phase 4: Advanced Features
- PbtA move system
- Fork/branch from conversation
- Multi-character sessions
- Real-time multiplayer (stretch)

---

## 13. API Surface

### Engine Interface

```python
class GameEngine(Protocol):
    """Public interface for the game engine."""

    async def process_turn(
        self,
        player_input: str,
        session_id: UUID,
    ) -> TurnResult:
        """Process a single player turn."""
        ...

    async def start_session(
        self,
        universe_id: UUID,
        character_id: UUID,
    ) -> Session:
        """Start a new game session."""
        ...

    async def end_session(
        self,
        session_id: UUID,
    ) -> None:
        """End a game session."""
        ...

    async def fork_from_here(
        self,
        session_id: UUID,
        reason: str,
    ) -> Universe:
        """Fork the timeline at current point."""
        ...
```

### Turn Result

```python
class TurnResult(BaseModel):
    """Result returned to the player."""

    narrative: str              # The story response

    # Optional details (for UI)
    rolls: list[RollSummary]    # Dice rolled
    state_changes: list[str]    # "HP: 45 → 38"

    # Meta
    turn_id: UUID
    events_created: int
    processing_time_ms: int
```

---

## 14. Dependencies

### Required
- LLM provider (Claude API)
- Dolt repository (truth storage)
- Neo4j repository (context storage)
- All skills from `src/skills/`

### Configuration

```python
class EngineConfig(BaseModel):
    """Engine configuration."""

    # LLM
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 1024
    temperature: float = 0.7

    # Context
    max_recent_events: int = 10
    max_nearby_entities: int = 20

    # Behavior
    verbosity: str = "normal"
    tone: str = "adventure"
    strict_rules: bool = True   # False = more narrative freedom
```
