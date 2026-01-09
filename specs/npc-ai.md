# TTA-Solo: NPC AI Spec

## 1. Overview

NPCs (Non-Player Characters) are autonomous agents within the game world. They have personalities, goals, memories, and relationships that drive their behavior. This spec defines how NPCs make decisions and respond to player actions.

---

## 2. Core Philosophy

### Neuro-Symbolic NPC Behavior
- **Symbolic**: Personality traits, relationship scores, goal priorities (deterministic)
- **Neural**: Dialogue generation, creative responses, improvisation (LLM)
- **Bridge**: Symbolic layer constrains and guides neural output

### Key Principles
1. **Consistent Personality**: NPCs behave according to their defined traits
2. **Relationship-Aware**: Past interactions influence current behavior
3. **Goal-Directed**: NPCs pursue their own objectives
4. **Contextually Appropriate**: Responses fit the situation
5. **Memorable**: NPCs remember significant events

---

## 3. Personality Model

### The Big Five Traits

Each NPC has scores (0-100) for five core personality dimensions:

```python
class PersonalityTraits(BaseModel):
    """Big Five personality model for NPCs."""

    openness: int = Field(ge=0, le=100, default=50)
    # High: Creative, curious, open to new ideas
    # Low: Practical, conventional, prefers routine

    conscientiousness: int = Field(ge=0, le=100, default=50)
    # High: Organized, disciplined, reliable
    # Low: Spontaneous, flexible, careless

    extraversion: int = Field(ge=0, le=100, default=50)
    # High: Outgoing, energetic, talkative
    # Low: Reserved, solitary, quiet

    agreeableness: int = Field(ge=0, le=100, default=50)
    # High: Friendly, compassionate, cooperative
    # Low: Competitive, suspicious, antagonistic

    neuroticism: int = Field(ge=0, le=100, default=50)
    # High: Anxious, moody, easily stressed
    # Low: Calm, stable, resilient
```

### Motivations

NPCs have ranked motivations that drive their goals:

```python
class Motivation(str, Enum):
    """What drives this NPC."""

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
```

### NPC Profile

```python
class NPCProfile(BaseModel):
    """Complete NPC personality and motivation profile."""

    entity_id: UUID

    # Personality
    traits: PersonalityTraits

    # Motivations (ordered by priority)
    motivations: list[Motivation] = Field(max_length=3)

    # Behavioral quirks (free-form for LLM)
    quirks: list[str] = Field(default_factory=list)
    # Examples: "speaks in third person", "obsessed with cleanliness"

    # Speech patterns
    speech_style: str = "neutral"
    # Examples: "formal", "crude", "poetic", "terse"

    # Alignment tendency (soft guidance, not strict)
    lawful_chaotic: int = Field(ge=-100, le=100, default=0)  # -100 chaotic, +100 lawful
    good_evil: int = Field(ge=-100, le=100, default=0)  # -100 evil, +100 good
```

---

## 4. Memory System

### Memory Types

```python
class MemoryType(str, Enum):
    """Types of memories NPCs can form."""

    ENCOUNTER = "encounter"      # Met this entity
    DIALOGUE = "dialogue"        # What was said
    ACTION = "action"            # What someone did
    OBSERVATION = "observation"  # What they witnessed
    RUMOR = "rumor"              # Heard from others
    EMOTION = "emotion"          # How they felt
```

### Memory Schema

```python
class NPCMemory(BaseModel):
    """A single memory held by an NPC."""

    id: UUID = Field(default_factory=uuid4)
    npc_id: UUID
    memory_type: MemoryType

    # What happened
    subject_id: UUID | None = None  # Entity this memory is about
    description: str  # Brief description

    # Emotional impact
    emotional_valence: float = Field(ge=-1.0, le=1.0, default=0.0)
    # -1.0 = very negative, +1.0 = very positive

    importance: float = Field(ge=0.0, le=1.0, default=0.5)
    # 0.0 = trivial, 1.0 = life-changing

    # Temporal
    event_id: UUID | None = None  # Linked event if applicable
    timestamp: datetime

    # Decay
    times_recalled: int = 0
    last_recalled: datetime | None = None
```

### Memory Retrieval

Memories are retrieved based on:
1. **Relevance**: Semantic similarity to current context
2. **Recency**: More recent memories are more accessible
3. **Importance**: Significant memories persist longer
4. **Emotional intensity**: Strong emotions enhance recall

```python
def retrieve_memories(
    npc_id: UUID,
    context: Context,
    limit: int = 5,
) -> list[NPCMemory]:
    """
    Retrieve relevant memories for current situation.

    Uses Neo4j vector search on memory descriptions
    combined with recency and importance weighting.
    """
```

---

## 5. Decision Making

### Action Selection Framework

NPCs select actions through a weighted decision process:

```python
class ActionOption(BaseModel):
    """A potential action an NPC can take."""

    action_type: str  # "attack", "flee", "negotiate", "help", etc.
    target_id: UUID | None = None
    description: str

    # Weights (calculated by symbolic layer)
    motivation_score: float  # How well does this serve my goals?
    relationship_score: float  # How does this affect my relationships?
    personality_score: float  # How consistent with my personality?
    risk_score: float  # How dangerous is this?

    @property
    def total_score(self) -> float:
        """Combined score for action selection."""
        return (
            self.motivation_score * 0.35 +
            self.relationship_score * 0.25 +
            self.personality_score * 0.25 +
            (1.0 - self.risk_score) * 0.15  # Invert: lower risk = better
        )
```

### Decision Context

```python
class NPCDecisionContext(BaseModel):
    """Everything an NPC knows when making a decision."""

    # Self
    npc_profile: NPCProfile
    current_state: EntityStats

    # Environment
    location: EntitySummary
    entities_present: list[EntitySummary]
    danger_level: int

    # Social
    relationships: list[RelationshipSummary]
    relevant_memories: list[NPCMemory]

    # Situation
    current_events: list[str]  # What's happening right now
    player_intent: Intent | None  # What is the player trying to do
```

### Decision Process

```
1. GATHER CONTEXT
   - Load NPC profile
   - Retrieve relevant memories
   - Get current relationships
   - Assess situation

2. GENERATE OPTIONS
   - What actions are possible?
   - Filter by physical capability
   - Filter by knowledge (NPC must know about option)

3. SCORE OPTIONS (Symbolic)
   - Motivation alignment
   - Relationship impact
   - Personality consistency
   - Risk assessment

4. SELECT ACTION
   - Usually highest scoring
   - Small random factor for unpredictability
   - Personality affects selection (high neuroticism = more erratic)

5. GENERATE RESPONSE (Neural)
   - LLM generates dialogue/description
   - Constrained by personality and speech style
   - Informed by memories and relationships
```

---

## 6. Relationship Influence

### Relationship Effects on Behavior

```python
RELATIONSHIP_BEHAVIOR_MODIFIERS = {
    # Relationship type: (action_types_favored, action_types_avoided)
    RelationshipType.ALLIED_WITH: (
        ["help", "defend", "share", "warn"],
        ["attack", "betray", "deceive"]
    ),
    RelationshipType.HOSTILE_TO: (
        ["attack", "hinder", "deceive", "flee"],
        ["help", "share", "trust"]
    ),
    RelationshipType.FEARS: (
        ["flee", "hide", "appease", "submit"],
        ["confront", "attack", "challenge"]
    ),
    RelationshipType.RESPECTS: (
        ["listen", "defer", "assist", "learn"],
        ["dismiss", "mock", "disobey"]
    ),
    RelationshipType.DISTRUSTS: (
        ["verify", "watch", "withhold", "test"],
        ["share_secrets", "rely_on", "trust"]
    ),
}
```

### Trust Mechanics

Trust affects information sharing:

```python
def calculate_disclosure_level(
    npc_id: UUID,
    target_id: UUID,
    information_sensitivity: float,  # 0-1
) -> bool:
    """
    Determine if NPC will share information.

    High trust + low sensitivity = share
    Low trust + high sensitivity = withhold
    """
    relationship = get_relationship(npc_id, target_id)
    trust = relationship.trust if relationship else 0.5

    threshold = information_sensitivity * (1.5 - trust)
    return random.random() > threshold
```

---

## 7. Dialogue Generation

### Dialogue Constraints

The Neural layer generates dialogue, but the Symbolic layer provides constraints:

```python
class DialogueConstraints(BaseModel):
    """Constraints for LLM dialogue generation."""

    # From personality
    speech_style: str
    extraversion_level: str  # "terse", "normal", "verbose"
    formality: str  # "casual", "neutral", "formal"

    # From relationship
    attitude_toward_player: str  # "friendly", "neutral", "hostile"
    trust_level: str  # "trusting", "guarded", "suspicious"

    # From situation
    emotional_state: str  # "calm", "angry", "afraid", "happy"
    urgency: str  # "relaxed", "normal", "urgent"

    # Content constraints
    topics_to_mention: list[str] = Field(default_factory=list)
    topics_to_avoid: list[str] = Field(default_factory=list)
    secrets_known: list[str] = Field(default_factory=list)  # Can reveal if trust high
    lies_to_tell: list[str] = Field(default_factory=list)  # If deceptive
```

### Dialogue Prompt Template

```python
NPC_DIALOGUE_PROMPT = """
You are {npc_name}, a {npc_description}.

PERSONALITY:
- Speech style: {speech_style}
- Attitude: {attitude}
- Emotional state: {emotional_state}

RELATIONSHIP WITH PLAYER:
{relationship_summary}

RELEVANT MEMORIES:
{memories}

CURRENT SITUATION:
{situation}

PLAYER SAID: "{player_input}"

Respond as {npc_name} would. Keep response to 1-3 sentences.
{additional_constraints}
"""
```

---

## 8. Combat Behavior

### Combat AI States

```python
class CombatState(str, Enum):
    """NPC combat behavior states."""

    AGGRESSIVE = "aggressive"  # Attack strongest threat
    DEFENSIVE = "defensive"    # Protect self, counterattack only
    TACTICAL = "tactical"      # Use positioning and abilities strategically
    SUPPORTIVE = "supportive"  # Help allies, heal, buff
    FLEEING = "fleeing"        # Trying to escape
    SURRENDERING = "surrendering"  # Giving up
```

### Combat Decision Factors

```python
class CombatEvaluation(BaseModel):
    """NPC's assessment of combat situation."""

    # Self assessment
    hp_percentage: float
    resources_remaining: float  # Spells, abilities
    escape_routes: int

    # Threat assessment
    enemies_count: int
    strongest_enemy_threat: float  # 0-1
    total_enemy_threat: float

    # Ally assessment
    allies_count: int
    ally_health_average: float

    # Derived
    @property
    def should_flee(self) -> bool:
        """Determine if NPC should attempt to flee."""
        return (
            self.hp_percentage < 0.25 and
            self.total_enemy_threat > 0.5 and
            self.escape_routes > 0
        )

    @property
    def should_surrender(self) -> bool:
        """Determine if NPC should surrender."""
        return (
            self.hp_percentage < 0.1 and
            self.escape_routes == 0 and
            self.allies_count == 0
        )
```

### Combat Personality Influence

```python
def get_combat_state(
    npc_profile: NPCProfile,
    evaluation: CombatEvaluation,
) -> CombatState:
    """
    Determine combat behavior based on personality and situation.
    """
    # Cowardly NPCs flee earlier
    flee_threshold = 0.25 + (npc_profile.traits.neuroticism / 200)

    # Aggressive NPCs attack more
    if npc_profile.traits.agreeableness < 30:
        return CombatState.AGGRESSIVE

    # Protective NPCs support allies
    if evaluation.allies_count > 0 and npc_profile.traits.agreeableness > 70:
        return CombatState.SUPPORTIVE

    # Check flee conditions
    if evaluation.hp_percentage < flee_threshold:
        if evaluation.escape_routes > 0:
            return CombatState.FLEEING
        return CombatState.SURRENDERING

    # Default to tactical
    return CombatState.TACTICAL
```

---

## 9. NPC Service Interface

### Core Service

```python
@dataclass
class NPCService:
    """Service for NPC AI operations."""

    dolt: DoltRepository
    neo4j: Neo4jRepository
    llm: LLMProvider | None = None

    async def decide_action(
        self,
        npc_id: UUID,
        context: Context,
        player_action: Intent | None = None,
    ) -> ActionOption:
        """
        Determine what action an NPC should take.

        Returns the selected action with reasoning.
        """

    async def generate_dialogue(
        self,
        npc_id: UUID,
        context: Context,
        player_input: str,
    ) -> str:
        """
        Generate NPC dialogue response.

        Uses personality constraints to guide LLM output.
        """

    async def form_memory(
        self,
        npc_id: UUID,
        event: Event,
    ) -> NPCMemory | None:
        """
        Create a memory from an event if significant enough.

        Returns None if event is too trivial to remember.
        """

    async def update_relationship(
        self,
        npc_id: UUID,
        target_id: UUID,
        event: Event,
    ) -> RelationshipDelta:
        """
        Update NPC's relationship based on an event.

        Returns the change in relationship metrics.
        """

    def get_combat_action(
        self,
        npc_id: UUID,
        combat_context: CombatContext,
    ) -> CombatAction:
        """
        Determine NPC's action in combat.

        Pure symbolic - no LLM needed.
        """
```

---

## 10. Storage

### Neo4j Nodes

```cypher
// NPC Profile stored as node properties
(:Character {
    id: $uuid,
    name: "Grizzled Bartender",

    // Personality (Big Five)
    openness: 40,
    conscientiousness: 70,
    extraversion: 60,
    agreeableness: 55,
    neuroticism: 30,

    // Motivations (JSON array)
    motivations: ["wealth", "safety", "respect"],

    // Speech
    speech_style: "gruff",
    quirks: ["wipes glass constantly", "knows everyone's name"]
})

// Memories as separate nodes
(:Memory {
    id: $uuid,
    npc_id: $npc_uuid,
    type: "encounter",
    description: "Player helped drive off thugs",
    emotional_valence: 0.8,
    importance: 0.7,
    timestamp: datetime()
})

// Link memories to NPCs
(npc:Character)-[:REMEMBERS]->(memory:Memory)

// Link memories to subjects
(memory:Memory)-[:ABOUT]->(subject:Entity)
```

### Dolt Tables

```sql
-- NPC profiles (extends entities)
CREATE TABLE npc_profiles (
    entity_id UUID PRIMARY KEY,
    traits JSON NOT NULL,  -- PersonalityTraits
    motivations JSON NOT NULL,  -- list[Motivation]
    speech_style VARCHAR(50),
    quirks JSON,
    lawful_chaotic INT DEFAULT 0,
    good_evil INT DEFAULT 0,
    created_at DATETIME DEFAULT NOW(),
    updated_at DATETIME DEFAULT NOW()
);

-- NPC memories (for persistence, Neo4j for search)
CREATE TABLE npc_memories (
    id UUID PRIMARY KEY,
    npc_id UUID NOT NULL,
    memory_type VARCHAR(50) NOT NULL,
    subject_id UUID,
    description TEXT NOT NULL,
    emotional_valence FLOAT DEFAULT 0,
    importance FLOAT DEFAULT 0.5,
    event_id UUID,
    timestamp DATETIME NOT NULL,
    times_recalled INT DEFAULT 0,
    last_recalled DATETIME,
    FOREIGN KEY (npc_id) REFERENCES entities(id)
);
```

---

## 11. Implementation Priority

1. **Phase 1**: Personality model and NPC profiles
2. **Phase 2**: Basic decision making (action selection)
3. **Phase 3**: Memory system (formation and retrieval)
4. **Phase 4**: Dialogue generation with constraints
5. **Phase 5**: Combat AI
6. **Phase 6**: Relationship influence on behavior
