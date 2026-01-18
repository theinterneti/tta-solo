# Quest System Specification

## Overview

The quest system provides procedural story hooks and objectives that emerge from gameplay. Quests are generated dynamically based on context (location, NPCs present, player actions) and integrate with the PbtA move system.

## Design Principles

1. **Emergent, not Scripted**: Quests arise from world state, not pre-written scripts
2. **Context-Aware**: Quest generation considers location, NPCs, danger level
3. **Fail Forward**: Failed quest steps create new narrative opportunities
4. **Stateless Generation**: Quest templates + context = unique quests

## Quest Types

### Immediate Quests (Generated on Discovery)
- **Fetch**: Retrieve an item from a location
- **Escort**: Protect an NPC to a destination
- **Hunt**: Defeat a specific enemy or creature
- **Investigate**: Discover information about a mystery
- **Deliver**: Bring an item to an NPC

### Chain Quests (Multi-step)
- Built from 2-4 immediate quest steps
- Each step completion triggers next step generation
- Failure at any step can branch to alternate paths

## Data Models

### Quest
```python
class QuestStatus(str, Enum):
    AVAILABLE = "available"      # Can be discovered
    ACTIVE = "active"            # Player has accepted
    COMPLETED = "completed"      # Successfully finished
    FAILED = "failed"            # Cannot be completed
    ABANDONED = "abandoned"      # Player gave up

class QuestObjective(BaseModel):
    description: str             # "Retrieve the ancient tome"
    objective_type: str          # fetch, defeat, reach, talk, etc.
    target_entity_id: UUID | None  # Entity to interact with
    target_location_id: UUID | None  # Location to reach
    quantity: int = 1            # For "defeat 3 goblins"
    progress: int = 0            # Current progress
    is_complete: bool = False
    is_optional: bool = False

class QuestReward(BaseModel):
    gold: int = 0
    items: list[UUID] = []       # Item entity IDs
    reputation_changes: dict[UUID, int] = {}  # NPC ID -> change
    unlocks_location: UUID | None = None

class Quest(BaseModel):
    id: UUID
    universe_id: UUID
    name: str
    description: str
    quest_type: str              # fetch, escort, hunt, investigate, deliver
    status: QuestStatus = QuestStatus.AVAILABLE

    # Quest giver
    giver_id: UUID | None        # NPC who gave the quest
    giver_name: str | None

    # Objectives
    objectives: list[QuestObjective]
    current_objective_index: int = 0

    # Rewards
    rewards: QuestReward

    # Timing
    created_at: datetime
    expires_at: datetime | None = None  # Optional time limit
    completed_at: datetime | None = None

    # Chain quest support
    parent_quest_id: UUID | None = None
    next_quest_id: UUID | None = None
```

### Quest Templates

Templates define the structure for procedural generation:

```python
class QuestTemplate(BaseModel):
    quest_type: str
    name_patterns: list[str]      # "Retrieve the {item}"
    description_patterns: list[str]
    objective_templates: list[dict]
    reward_ranges: dict[str, tuple[int, int]]
    suitable_locations: list[str]  # Location types
    min_danger_level: int = 0
    max_danger_level: int = 20
```

## Quest Generation

### Trigger Points
1. **NPC Dialogue**: Talking to an NPC may reveal a quest
2. **Location Discovery**: Entering a new location may trigger quests
3. **Item Discovery**: Finding certain items starts quests
4. **GM Move**: OFFER_OPPORTUNITY can generate quest hooks
5. **Event Cascade**: Completing one quest unlocks others

### Generation Algorithm

```python
async def generate_quest(
    context: Context,
    trigger: str,  # "npc_dialogue", "location", "item", "move"
    npc_id: UUID | None = None,
) -> Quest | None:
    """
    Generate a contextually appropriate quest.

    1. Select quest type based on context
    2. Choose template matching location/danger
    3. Fill template with world entities
    4. Create objectives referencing real entities
    5. Calculate rewards based on difficulty
    """
```

### Template Selection Logic

| Context | Preferred Quest Types |
|---------|----------------------|
| Tavern + NPC | Deliver, Investigate, Escort |
| Dungeon | Fetch, Hunt, Investigate |
| Forest | Hunt, Fetch, Escort |
| Market | Deliver, Fetch |
| High Danger | Hunt, Investigate |
| Low Danger | Deliver, Escort, Fetch |

## Quest Tracking

### Progress Updates
- Check quest objectives after each turn
- Update progress when relevant actions occur
- Trigger completion/failure events

### State Persistence
- Quests stored in Dolt as entities
- Active quest IDs stored in Session
- Objective progress updated in real-time

## Integration Points

### With Move Executor
- `OFFER_OPPORTUNITY` can create quest hooks
- `REVEAL_UNWELCOME_TRUTH` can advance investigation quests
- `INTRODUCE_NPC` can add quest givers

### With NPC System
- NPCs have quest affinity based on motivations
- Quest completion affects NPC relationships
- NPC memory includes quest interactions

### With Narrative Generator
- Quest status affects narrative tone
- Objective hints woven into descriptions
- Completion celebrated appropriately

## Example Quests

### Fetch Quest: "The Lost Heirloom"
```
Name: The Lost Heirloom
Type: fetch
Giver: Ameiko (bartender)
Description: Ameiko's grandmother's ring was stolen.
             She believes it's somewhere in the crypt.

Objectives:
1. Travel to The Old Crypt
2. Find the Silver Ring
3. Return to Ameiko

Rewards:
- 50 gold
- Reputation +10 with Ameiko
- Unlocks: Back room of tavern
```

### Hunt Quest: "Pest Control"
```
Name: Pest Control
Type: hunt
Giver: Vorvashali (merchant)
Description: Giant rats are eating the merchant's goods.
             Clear them out from the alley.

Objectives:
1. Defeat 3 Giant Rats in Shadow Alley

Rewards:
- 25 gold
- Healing Potion
```

### Investigate Quest: "The Hooded Stranger"
```
Name: The Hooded Stranger
Type: investigate
Giver: Self (discovered)
Description: The stranger in the tavern seems to know
             something. Find out what they're hiding.

Objectives:
1. Talk to the Hooded Stranger
2. (Branching) Follow them OR Search their room
3. Discover the truth

Rewards:
- Story progression
- New quest chain unlocked
```

## Implementation Phases

### Phase 1: Core Models
- Quest, QuestObjective, QuestReward models
- Quest entity storage in Dolt
- Basic quest state management

### Phase 2: Generation
- Quest templates for each type
- Context-aware generation
- Integration with NPC dialogue

### Phase 3: Tracking
- Objective progress updates
- Completion detection
- Reward distribution

### Phase 4: Integration
- Move Executor hooks
- Narrative enhancement
- Quest chains

## Success Metrics

- Quests feel natural, not forced
- Generation produces variety
- Progress tracking is reliable
- Rewards are balanced
- Failures create interesting outcomes
