# TTA-Solo: CLI User Experience Spec

## 1. Overview

The CLI is the player-facing layer that surfaces the underlying game systems. Currently, many implemented features (quests, inventory, abilities, dialogue) are not accessible through commands. This spec defines improvements to expose existing functionality and create a cohesive gameplay experience.

**Goal**: Upgrade CLI from C+ to B+ gameplay experience by exposing existing systems.

---

## 2. Current State

### Existing Commands
```
/quit, /help, /look, /status, /history, /save, /fork, /clear
```

### Missing Commands (features exist but not exposed)
- `/inventory` - Item management
- `/quests` - Quest tracking
- `/abilities` - Ability/spell usage
- `/talk <npc>` - Conversation system

### Known Issues
1. Navigation doesn't change location visibly
2. NPCs present but not interactive
3. Abilities implemented but no selection UI
4. Quests implemented but not accessible

---

## 3. New Commands

### 3.1 Inventory Command

```
/inventory (aliases: /inv, /i)
```

**Purpose**: Display and manage player inventory.

**Output Format**:
```
Inventory:
----------------------------------------
  Equipped:
    Weapon: Rusty Sword (+2 damage)
    Armor: Leather Armor (AC 11)

  Backpack (5/10 slots):
    - Health Potion (x2)
    - Torch (x3)
    - 25 gold pieces

  Total Weight: 15 lbs
```

**Subcommands**:
- `/inventory` - List all items
- `/inventory use <item>` - Use a consumable
- `/inventory drop <item>` - Drop an item
- `/inventory equip <item>` - Equip weapon/armor
- `/inventory examine <item>` - Get item details

**Data Source**: Query Neo4j for `OWNS` relationships from player character.

---

### 3.2 Quest Command

```
/quests (aliases: /quest, /q)
```

**Purpose**: Display active, available, and completed quests.

**Output Format**:
```
Quests:
----------------------------------------
  Active (2):
    [!] The Missing Shipment (Market District)
        - [x] Talk to the merchant
        - [ ] Find the stolen goods
        - [ ] Return to merchant
        Reward: 50 gold, Merchant's Favor

    [ ] Whispers in the Tavern
        - [ ] Question the locals
        Reward: 30 gold

  Available (1):
    [ ] Safe Passage - Escort needed to Oakwood

  Completed (3): /quests completed
```

**Subcommands**:
- `/quests` - Show active quests
- `/quests available` - Show quests that can be accepted
- `/quests completed` - Show completed quests
- `/quests <quest_name>` - Show details for specific quest
- `/quests accept <quest_name>` - Accept an available quest
- `/quests abandon <quest_name>` - Abandon an active quest

**Data Source**: QuestService via `get_active_quests()`, `get_available_quests()`.

---

### 3.3 Abilities Command

```
/abilities (aliases: /ab, /spells, /skills)
```

**Purpose**: Display and use character abilities.

**Output Format**:
```
Abilities:
----------------------------------------
  Combat:
    [1] Second Wind (1/1 uses) - Heal 1d10+level HP
    [2] Action Surge (0/1 uses) - Extra action this turn

  Spells (Slots: 2/3):
    [3] Magic Missile (1st) - 3 darts, 1d4+1 each
    [4] Shield (1st, Reaction) - +5 AC until next turn
    [5] Burning Hands (1st) - 3d6 fire, 15ft cone

  Cantrips:
    [6] Fire Bolt - 1d10 fire, 120ft range
    [7] Light - Illuminate 20ft radius

Type /use <number> or /use <ability name> to activate.
```

**Subcommands**:
- `/abilities` - List all abilities
- `/use <ability>` - Use an ability (by number or name)
- `/abilities <name>` - Get details for specific ability

**Usage Flow**:
```
> /use 3
Target? (default: nearest enemy)
> the goblin

You cast Magic Missile at the goblin!
Three glowing darts streak through the air...
[Damage: 11 (3+4+4)]
The goblin takes 11 force damage!
```

**Data Source**: Entity stats + Ability models. Use AbilityRouter for resolution.

---

### 3.4 Talk Command

```
/talk <npc> (aliases: /speak, /chat)
```

**Purpose**: Initiate conversation with an NPC.

**Output Format**:
```
You approach Ameiko Kaijitsu, the innkeeper.

Ameiko smiles warmly. "Welcome back, traveler! What brings
you to the Rusty Dragon today?"

  [1] "I'm looking for work."
  [2] "What's the news around town?"
  [3] "Tell me about yourself."
  [4] "I need supplies."
  [5] (Leave conversation)

>
```

**Conversation Flow**:
1. Player initiates with `/talk <npc>`
2. NPC greeting generated using personality traits
3. Player selects numbered option or types custom response
4. NPC responds based on personality, memory, relationship
5. Continues until player exits or conversation ends

**NPC Response Generation**:
- Use `NPCService.generate_dialogue()` for LLM-powered responses
- Fallback to template responses if LLM unavailable
- Incorporate NPC personality (Big Five traits)
- Consider relationship/trust level
- Remember conversation in NPC memory

**Data Source**: NPCService, NPCProfile, Neo4j relationships.

---

### 3.5 Enhanced Look Command

Update existing `/look` to show more context.

**Current**: Basic location description
**Enhanced**:
```
The Rusty Dragon Inn
----------------------------------------
A warm, inviting tavern with the smell of spiced meat
and fresh bread. Lanterns cast dancing shadows on
weathered wooden walls.

  People here:
    - Ameiko Kaijitsu (innkeeper) [friendly]
    - Hooded Stranger [unknown]

  Items of interest:
    - Notice board with job postings
    - Abandoned mug on a corner table

  Exits:
    - North: Market Square
    - East: Kitchen (staff only)
    - South: Main Street
    - West: Private Rooms

  Quests available: "Whispers in the Tavern"
```

---

## 4. Navigation Improvements

### 4.1 Fix Location Transitions

**Problem**: `go north` acknowledges movement but doesn't change location.

**Solution**: Update engine to:
1. Query Neo4j for `CONNECTED_TO` relationships from current location
2. Find matching exit direction
3. Update `state.location_id` to destination
4. Trigger new location description

**Implementation**:
```python
async def handle_movement(direction: str, state: GameState) -> str:
    # Get exits from current location
    exits = neo4j.get_exits(state.location_id)

    # Find matching direction
    destination = exits.get(direction.lower())
    if not destination:
        return f"You can't go {direction} from here."

    # Update location
    old_location = state.location_id
    state.location_id = destination.id

    # Create travel event
    create_travel_event(
        actor_id=state.character_id,
        from_location=old_location,
        to_location=destination.id,
    )

    # Return new location description
    return describe_location(destination)
```

### 4.2 Show Exit Destinations

**Current**: "Exits: north, south, east, west"
**Improved**: "Exits: North (Market Square), South (Main Street)"

Query Neo4j for destination names when listing exits.

---

## 5. Starter World Content

### 5.1 Current Content
- 1 location: The Rusty Dragon Inn
- 2 NPCs: Ameiko, Hooded Stranger
- No quests
- No items beyond starter gear

### 5.2 Expanded Content

**Locations** (minimum 5):
```
The Rusty Dragon Inn (starting)
    |
    +-- North: Market Square
    |       +-- East: Blacksmith
    |
    +-- South: Main Street
    |       +-- South: Town Gate
    |
    +-- East: Kitchen (restricted)
```

**NPCs** (minimum 5):
| Name | Location | Role | Personality |
|------|----------|------|-------------|
| Ameiko Kaijitsu | Inn | Innkeeper | Friendly, curious |
| Hooded Stranger | Inn | Quest giver | Mysterious, guarded |
| Grimnir | Blacksmith | Merchant | Gruff, honest |
| Guard Captain | Town Gate | Authority | Stern, dutiful |
| Merchant | Market | Vendor | Cheerful, greedy |

**Starter Quests** (minimum 3):
1. **Whispers in the Tavern** (Investigate)
   - Given by: Ameiko
   - Objective: Learn about the Hooded Stranger
   - Reward: 20 gold, Ameiko's trust

2. **The Missing Shipment** (Fetch)
   - Given by: Merchant (Market)
   - Objective: Find stolen goods at Town Gate
   - Reward: 50 gold, discount at shop

3. **Arm Yourself** (Tutorial)
   - Given by: System on first visit to Blacksmith
   - Objective: Buy or earn a weapon
   - Reward: Introduction to combat

**Items**:
- Health Potion (Inn, Merchant) - 50g
- Torch (Merchant) - 1g
- Short Sword (Blacksmith) - 10g
- Leather Armor (Blacksmith) - 45g
- Rations (Merchant) - 5g for 5 days

---

## 6. Command Priority

### Phase 1: Core Exposure (High Impact, Low Effort)
1. `/inventory` - Display items player owns
2. `/quests` - Display quest state
3. Fix navigation to actually change locations

### Phase 2: Interactivity (High Impact, Medium Effort)
4. `/talk <npc>` - Basic NPC conversation
5. `/abilities` - Ability listing and usage
6. Enhanced `/look` with NPCs, items, exits

### Phase 3: Content (High Impact, Medium Effort)
7. Add 4 more locations to starter world
8. Add 3 more NPCs
9. Add 3 starter quests
10. Add purchasable items

---

## 7. Technical Requirements

### Database Queries Needed

```python
# Inventory
neo4j.get_relationships(
    from_id=character_id,
    rel_type=RelationshipType.OWNS
)

# Quest availability
quest_service.get_available_quests(
    location_id=location_id,
    character_id=character_id
)

# NPC at location
neo4j.get_entities_at_location(location_id, type=EntityType.CHARACTER)

# Exits from location
neo4j.get_relationships(
    from_id=location_id,
    rel_type=RelationshipType.CONNECTED_TO
)
```

### New REPL Commands Structure

```python
# Add to _register_commands()
Command(
    name="inventory",
    aliases=["inv", "i"],
    description="Show your inventory",
    handler=self._cmd_inventory,
),
Command(
    name="quests",
    aliases=["quest", "q"],
    description="Show your quests",
    handler=self._cmd_quests,
),
Command(
    name="abilities",
    aliases=["ab", "spells"],
    description="Show your abilities",
    handler=self._cmd_abilities,
),
Command(
    name="talk",
    aliases=["speak", "chat"],
    description="Talk to an NPC",
    handler=self._cmd_talk,
),
Command(
    name="use",
    aliases=[],
    description="Use an ability or item",
    handler=self._cmd_use,
),
```

---

## 8. Success Criteria

### Functional Requirements
- [ ] `/inventory` shows all owned items
- [ ] `/quests` shows active, available, completed quests
- [ ] `/abilities` lists character abilities with usage state
- [ ] `/talk <npc>` initiates conversation with response options
- [ ] `/use <ability>` triggers ability resolution
- [ ] `go <direction>` changes location and shows new description
- [ ] `/look` shows NPCs, items, and named exits

### Content Requirements
- [ ] 5+ connected locations in starter world
- [ ] 5+ NPCs with personalities
- [ ] 3+ starter quests
- [ ] 10+ items available (shop or loot)

### Quality Requirements
- [ ] All new commands have tests
- [ ] Navigation works bidirectionally
- [ ] NPC conversation uses personality traits
- [ ] Quest progress persists across sessions

---

## 9. Out of Scope (Future)

- Crafting system
- Party management (multiplayer)
- Procedural dungeon generation
- Real database persistence (covered by separate spec)
- Web/Discord interface
- Voice input

---

## 10. Related Specs

- `engine.md` - Turn processing for new commands
- `npc-ai.md` - Conversation generation
- `quests.md` - Quest data models
- `ontology.md` - Entity/relationship structure
- `moves.md` - GM moves for quest progression
