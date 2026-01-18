# TTA-Solo: Move Executor Spec

## 1. Overview

The Move Executor transforms PbtA GM moves from narrative-only text into **generative actions** that create entities, modify world state, and persist changes to the database. This enables procedural world-building driven by gameplay outcomes.

---

## 2. Core Philosophy

### Neuro-Symbolic Move Execution
- **Symbolic**: Move selection logic (existing `select_gm_move()`)
- **Neural**: Content generation for entities (LLM with template fallback)
- **Bridge**: MoveExecutor translates move type → entity creation → narrative

### Key Principles
1. **Moves Create Reality**: A triggered move should produce tangible game state changes
2. **Graceful Degradation**: LLM failures fall back to templates - never break the game
3. **Context-Aware**: Generated content fits the situation (location, danger, relationships)
4. **Persistent**: Created entities are real game objects stored in Dolt/Neo4j

---

## 3. Move Categories

### Generative Moves (create entities)
| Move Type | Creates |
|-----------|---------|
| `INTRODUCE_NPC` | Character entity + NPC profile + LOCATED_IN relationship |
| `CHANGE_ENVIRONMENT` | Location feature, connected location, or atmosphere change |
| `REVEAL_UNWELCOME_TRUTH` | Lore entity or secret with relationships |

### Effect Moves (modify existing state)
| Move Type | Effect |
|-----------|--------|
| `DEAL_DAMAGE` | Already handled in router - damage added to result |
| `TAKE_AWAY` | Mark item as destroyed/lost, remove from inventory |
| `CAPTURE` | Relocate actor, create TRAPPED_IN relationship |
| `SEPARATE_THEM` | Move entities to different locations |

### Narrative-Only Moves (no state change)
| Move Type | Behavior |
|-----------|----------|
| `SHOW_DANGER` | Return narrative description only |
| `OFFER_OPPORTUNITY` | Return narrative with suggested action |
| `USE_MONSTER_MOVE` | Return narrative (creature action described) |
| `ADVANCE_TIME` | Return narrative (may become generative later) |

---

## 4. Input

### MoveExecutionRequest

```python
class MoveExecutionRequest(BaseModel):
    """Request to execute a GM move."""

    move: GMMove  # From pbta.py
    context: Context  # Current game context
    session: Session  # Active session
    trigger_reason: str = "miss"  # "miss", "weak_hit", "proactive"
```

### GMMove (existing in pbta.py)

```python
class GMMove(BaseModel):
    """A GM move selected in response to a player miss."""

    type: GMMoveType
    is_hard: bool
    description: str
    damage: int | None = None
    condition: str | None = None
```

---

## 5. Output

### MoveExecutionResult

```python
class MoveExecutionResult(BaseModel):
    """Result of executing a GM move."""

    success: bool
    narrative: str  # Generated or template narrative

    # Entities created/modified
    entities_created: list[UUID] = Field(default_factory=list)
    entities_modified: list[UUID] = Field(default_factory=list)
    relationships_created: list[UUID] = Field(default_factory=list)

    # State changes for display
    state_changes: list[str] = Field(default_factory=list)

    # Error tracking
    error: str | None = None
    used_fallback: bool = False  # True if LLM failed and template used
```

---

## 6. Process

### 6.1 Main Execution Flow

```
1. RECEIVE move execution request
2. LOOKUP generator for move type
   - If no generator → return narrative-only result
3. ATTEMPT LLM generation (if available)
   - Build context-aware prompt
   - Parse JSON response
4. ON FAILURE → use template fallback
5. CREATE entities via factory functions
6. PERSIST to Dolt (entity) and Neo4j (relationships)
7. GENERATE narrative describing what happened
8. RETURN MoveExecutionResult
```

### 6.2 INTRODUCE_NPC Process

```
Input: GMMove(type=INTRODUCE_NPC), Context, Session
Output: MoveExecutionResult with new NPC

1. ANALYZE context
   - Location type (tavern, dungeon, market, etc.)
   - Danger level
   - Existing entities (avoid duplicates)
   - Recent events

2. GENERATE NPC parameters
   If LLM available:
     - Build prompt with context
     - Request: name, description, role, traits, motivations, speech_style
     - Parse JSON response
   Else:
     - Select from templates by location type
     - Randomize within constraints

3. CREATE character entity
   entity = create_character(
       universe_id=session.universe_id,
       name=npc_params.name,
       description=npc_params.description,
       hp_max=10 + danger_level,
       ac=10 + (danger_level // 5),
       location_id=session.location_id,
   )
   dolt.save_entity(entity)

4. CREATE NPC profile
   profile = create_npc_profile(
       entity_id=entity.id,
       openness=npc_params.traits.openness,
       ...
   )
   npc_service.save_profile(profile)

5. CREATE relationships
   located_in = Relationship(
       universe_id=session.universe_id,
       from_entity_id=entity.id,
       to_entity_id=session.location_id,
       relationship_type=RelationshipType.LOCATED_IN,
   )
   neo4j.create_relationship(located_in)

6. GENERATE narrative
   narrative = f"{entity.name} appears. {entity.description}"
   (Or LLM-generated introduction)

7. RETURN MoveExecutionResult(
       success=True,
       narrative=narrative,
       entities_created=[entity.id],
       relationships_created=[located_in.id],
   )
```

### 6.3 CHANGE_ENVIRONMENT Process

```
Input: GMMove(type=CHANGE_ENVIRONMENT), Context, Session
Output: MoveExecutionResult with location modification

1. DETERMINE change type based on context
   - danger_level < 5 → atmosphere change (mood)
   - danger_level 5-10 → new feature (discoverable)
   - danger_level > 10 → hazard or escape route

2. For NEW_FEATURE:
   feature_entity = create_entity(
       universe_id=session.universe_id,
       name="Hidden Alcove",  # Generated or template
       type=EntityType.OBJECT,
       description="A shadowy recess in the wall...",
   )
   dolt.save_entity(feature_entity)

   # Link to location
   contains_rel = Relationship(
       from_entity_id=session.location_id,
       to_entity_id=feature_entity.id,
       relationship_type=RelationshipType.CONTAINS,
   )
   neo4j.create_relationship(contains_rel)

3. For ATMOSPHERE_CHANGE:
   # Update or create HAS_ATMOSPHERE relationship
   neo4j.update_or_create_relationship(
       from_entity_id=session.location_id,
       relationship_type="HAS_ATMOSPHERE",
       description="An eerie silence falls...",
   )

4. RETURN MoveExecutionResult with changes
```

### 6.4 TAKE_AWAY Process

```
Input: GMMove(type=TAKE_AWAY), Context, Session
Output: MoveExecutionResult with item removed

1. SELECT item to take
   - Prefer equipped items (WIELDS, WEARS)
   - Then carried items (CARRIES)
   - Skip quest items (if flagged)

2. MARK item as lost
   item_entity.is_active = False
   item_entity.description += " [Lost]"
   dolt.update_entity(item_entity)

3. REMOVE relationships
   neo4j.delete_relationship(actor_id, item_id, "CARRIES"|"WIELDS"|"WEARS")

4. RECORD event
   Event(type=ITEM_LOST, target_id=item_id, ...)

5. RETURN result with narrative
   "Your {item.name} slips from your grasp and is lost!"
```

### 6.5 CAPTURE Process

```
Input: GMMove(type=CAPTURE), Context, Session
Output: MoveExecutionResult with actor relocated

1. CREATE or SELECT trap location
   If escape_routes == 0:
     # Already trapped, intensify
     narrative = "The walls close in further..."
   Else:
     trap_location = create_location(
         universe_id=session.universe_id,
         name="Holding Cell",
         description="A cramped, dark cell...",
         danger_level=context.danger_level,
     )
     dolt.save_entity(trap_location)

2. UPDATE actor location
   neo4j.update_relationship(
       from_entity_id=actor_id,
       to_entity_id=trap_location.id,
       relationship_type=LOCATED_IN,
   )

3. CREATE TRAPPED_IN relationship
   neo4j.create_relationship(
       from_entity_id=actor_id,
       to_entity_id=trap_location.id,
       relationship_type="TRAPPED_IN",
   )

4. UPDATE session location
   session.location_id = trap_location.id

5. RETURN result
```

---

## 7. NPC Generation Parameters

### NPCGenerationParams

```python
class NPCGenerationParams(BaseModel):
    """Parameters for generating a new NPC."""

    name: str
    description: str
    role: str  # merchant, guard, traveler, etc.

    traits: PersonalityTraits
    motivations: list[Motivation] = Field(max_length=3)
    speech_style: str = "neutral"
    quirks: list[str] = Field(default_factory=list, max_length=2)

    # Combat stats (derived from role + danger)
    hp_max: int = 10
    ac: int = 10

    # Initial disposition
    initial_attitude: str = "neutral"  # friendly, neutral, hostile
```

### LLM Generation Prompt

```
You are an NPC generator for a tabletop RPG. Generate a contextually appropriate NPC.

Current Location: {location.name} ({location.type})
Location Description: {location.description}
Danger Level: {danger_level}/20
Existing Characters: {[e.name for e in entities_present]}
Recent Events: {recent_events}
Trigger: {trigger_reason}

Generate a NEW character who fits this scene. Output JSON:
{
    "name": "string (fantasy-appropriate)",
    "description": "1-2 sentence physical/behavioral description",
    "role": "merchant|guard|traveler|criminal|noble|peasant|adventurer|scholar|priest",
    "traits": {
        "openness": 0-100,
        "conscientiousness": 0-100,
        "extraversion": 0-100,
        "agreeableness": 0-100,
        "neuroticism": 0-100
    },
    "motivations": ["survival"|"wealth"|"power"|"knowledge"|"duty"|...],
    "speech_style": "formal|crude|poetic|terse|warm|cold|nervous",
    "quirks": ["optional behavioral quirk"],
    "initial_attitude": "friendly|neutral|hostile"
}
```

---

## 8. Template Fallbacks

### NPC Templates by Location Type

```python
NPC_TEMPLATES: dict[str, list[NPCTemplate]] = {
    "tavern": [
        NPCTemplate(
            names=["Greta", "Old Tom", "Bron", "Mira the Red"],
            roles=["barkeeper", "patron", "bard", "gambler"],
            descriptions=[
                "a weathered face that's seen too many bar fights",
                "nursing a drink and watching the door",
            ],
            trait_ranges={
                "extraversion": (50, 80),
                "agreeableness": (40, 70),
            },
            speech_styles=["warm", "gruff", "chatty"],
        ),
    ],
    "dungeon": [
        NPCTemplate(
            names=["The Prisoner", "Whisper", "Lost One"],
            roles=["prisoner", "survivor", "lost_soul"],
            descriptions=[
                "shackled to the wall, eyes hollow",
                "huddled in a corner, barely alive",
            ],
            trait_ranges={
                "neuroticism": (60, 95),
                "extraversion": (10, 40),
            },
            speech_styles=["fearful", "desperate", "resigned"],
        ),
    ],
    "market": [
        NPCTemplate(
            names=["Merchant Finn", "Silverhand", "Madame Vera"],
            roles=["merchant", "pickpocket", "fortune_teller"],
            trait_ranges={
                "extraversion": (60, 90),
                "conscientiousness": (30, 70),
            },
            speech_styles=["persuasive", "shifty", "mysterious"],
        ),
    ],
    "default": [
        NPCTemplate(
            names=["Stranger", "Traveler", "Local"],
            roles=["traveler", "commoner", "wanderer"],
            trait_ranges={},  # Use defaults
            speech_styles=["neutral"],
        ),
    ],
}
```

### Environment Feature Templates

```python
ENVIRONMENT_FEATURES: dict[str, list[str]] = {
    "dungeon": [
        ("Hidden Passage", "A section of wall that slides aside..."),
        ("Collapsed Tunnel", "Rubble blocks what was once a passage..."),
        ("Underground Stream", "Water trickles through a crack in the floor..."),
    ],
    "tavern": [
        ("Back Room", "A door you hadn't noticed leads to a private area..."),
        ("Loose Floorboard", "A board creaks, revealing a hollow beneath..."),
    ],
    "forest": [
        ("Animal Trail", "A narrow path through the undergrowth..."),
        ("Hollow Tree", "An ancient oak with a dark cavity..."),
    ],
    "default": [
        ("Shadowy Corner", "An area the light doesn't quite reach..."),
        ("Strange Mark", "An unfamiliar symbol scratched into the surface..."),
    ],
}
```

---

## 9. Edge Cases

### LLM Failures
- **Timeout**: Use template after 5s timeout
- **Invalid JSON**: Parse what we can, fill gaps with defaults
- **Empty response**: Fall back to template
- **Rate limit**: Use template, log for monitoring

### Entity Creation Failures
- **Dolt write fails**: Return error result, don't create partial state
- **Neo4j write fails**: Rollback Dolt entity, return error
- **Duplicate name**: Append number suffix ("Guard 2")

### Context Edge Cases
- **Empty location**: Still generate NPC (they arrived with player)
- **Max entities reached**: Skip INTRODUCE_NPC, use narrative-only
- **No items to take**: TAKE_AWAY becomes "Nothing to lose... this time"
- **Already captured**: CAPTURE intensifies ("walls closing in")

### Invalid Move Types
- Unknown move type: Return narrative-only with warning log
- Null move: Return empty success result

---

## 10. Service Interface

```python
@dataclass
class MoveExecutor:
    """
    Executes GM moves, creating entities and modifying world state.

    The bridge between move selection (pbta.py) and world generation.
    """

    dolt: DoltRepository
    neo4j: Neo4jRepository
    npc_service: NPCService
    llm: LLMService | None = None

    async def execute(
        self,
        move: GMMove,
        context: Context,
        session: Session,
        trigger_reason: str = "miss",
    ) -> MoveExecutionResult:
        """Execute a GM move, potentially creating entities."""
        ...

    async def execute_introduce_npc(
        self,
        context: Context,
        session: Session,
        trigger_reason: str,
    ) -> MoveExecutionResult:
        """Generate and create a new NPC."""
        ...

    async def execute_change_environment(
        self,
        context: Context,
        session: Session,
        trigger_reason: str,
    ) -> MoveExecutionResult:
        """Modify or extend the current location."""
        ...

    async def execute_take_away(
        self,
        context: Context,
        session: Session,
    ) -> MoveExecutionResult:
        """Remove an item from the actor."""
        ...

    async def execute_capture(
        self,
        context: Context,
        session: Session,
    ) -> MoveExecutionResult:
        """Trap the actor in a location."""
        ...
```

---

## 11. Integration Points

### Router Integration

```python
# In SkillRouter._apply_pbta(), after selecting GM move on MISS:

elif pbta_outcome == PbtAOutcome.MISS:
    gm_move = select_gm_move(...)

    if self._move_executor is not None:
        exec_result = await self._move_executor.execute(
            move=gm_move,
            context=context,
            session=session,
            trigger_reason="miss",
        )
        updates["entities_created"] = exec_result.entities_created
        updates["relationships_created"] = exec_result.relationships_created
        updates["gm_move_type"] = gm_move.type.value
        updates["description"] = f"{result.description} {exec_result.narrative}"
    else:
        # Fallback to narrative-only (existing behavior)
        updates["description"] = f"{result.description} {gm_move.description}"
```

### SkillResult Updates

```python
class SkillResult(BaseModel):
    # ... existing fields ...

    # NEW: Move execution tracking
    entities_created: list[UUID] = Field(default_factory=list)
    relationships_created: list[UUID] = Field(default_factory=list)
    move_used_fallback: bool = False
```

---

## 12. Testing Strategy

### Unit Tests
- Each move executor method in isolation
- Template fallback when LLM=None
- Template fallback on LLM exception
- Entity creation and persistence
- Relationship creation

### Integration Tests
- Full flow: miss → move selection → execution → entity in DB
- Router integration with MoveExecutor
- Multiple moves in sequence

### Property Tests
- Generated NPCs always have valid traits (0-100)
- Generated NPCs always have 1-3 motivations
- No duplicate entity IDs created
