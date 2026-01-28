# IC vs OOC Information Presentation

## Design Philosophy

TTA-Solo blends **In-Character (IC)** immersive narrative with **Out-of-Character (OOC)** game mechanics information. The goal is to maintain immersion while providing players the data they need.

## Core Principles

### 1. IC-First, OOC-Subtle
- Start with narrative/character perspective
- Layer in mechanics where needed
- Use visual distinction for pure OOC info

### 2. Natural Language Over Numbers
- ✅ "2 of 3 goblins defeated"
- ❌ "Goblins: 2/3"

### 3. Symbols for Immersion
- 📜 Quest/scroll
- ▸ Active objective
- ✓ Complete
- ✗ Failed
- ━ Separators (instead of dashes)
- 💰 Gold
- ⭐ Experience

### 4. Bracket Pure Meta-Information
```
You accept the task from Vorvashali.

[Quest added to journal - /quests to review]
```

The bracketed text is clearly OOC helper information.

### 5. Rewards as IC Promises
**Before completion:**
- ✅ "Upon completion: ~50 gold"
- ❌ "Reward: 50 gold"

**During completion:**
- ✅ "He hands you a pouch of gold coins."
- ❌ "Received 50 gold"

## Implementation Examples

### Quest Accept

**IC-First Presentation:**
```
You accept the task from Vorvashali Voon.

"There's been goblin trouble in Tickwood Forest," he says grimly. 
"Deal with the raiders and I'll make it worth your while."

Mission Accepted: Goblin Trouble
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ▸ Hunt down the goblin raiders in Tickwood Forest
    (3 required)
  
  Promised reward: ~50 gold, ~30 experience

[Quest added to journal - /quests to review progress]
```

**What makes this good:**
- Opens with character action ("You accept...")
- Shows dialogue in quotes
- Clear visual separation
- Objectives use symbols
- Rewards framed as promises
- OOC help text bracketed

### Active Quests

**IC-Focused Display:**
```
Your Current Quests:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📜 Goblin Trouble
   Given by: Vorvashali Voon

   ▸ Hunt down the goblin raiders in Tickwood Forest
      Progress: 2 of 3

   Upon completion: ~50 gold, ~30 experience

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**What makes this good:**
- Quest icon (📜)
- Attribution (who gave it)
- Natural progress language
- Future-tense for rewards ("upon completion")

### Available Opportunities

**IC-Framed Discovery:**
```
Available Opportunities:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ameiko Kaijitsu seeks assistance...
  "I need someone to make a delivery..."
  → /quest accept welcome

Vorvashali Voon warns of goblin trouble...
  "Raiders have been spotted in the forest..."
  → /quest accept goblin
```

**What makes this good:**
- Called "opportunities" not "quests"
- Shows WHO needs help
- Preview of quest giver dialogue
- Command shown as hint (→)

## UI Hierarchy

**Layer 1: Pure IC Narrative**
```
You strike down the goblin raider!
```

**Layer 2: IC with OOC Hints**
```
📜 Goblin Trouble
   Progress: 2 of 3 goblins
```

**Layer 3: Pure OOC Meta**
```
[Quest progress updated - /quests to review]
```

## What to Avoid

### ❌ Too Gamey
```
✓ Quest Accepted: Goblin Trouble
XP Reward: 30
Gold Reward: 50
Status: ACTIVE
```

### ❌ Checkbox Hell
```
[ ] Talk to NPC (0/1)
[ ] Kill enemies (2/5)
[X] Go to location (1/1)
```

### ❌ Raw Data Dumps
```
Quest ID: quest_123
Type: HUNT
Target: goblin
Quantity: 3
Progress: 2
```

## Context-Specific Guidelines

### Combat
During combat, be brief but stay IC:
```
You strike down the goblin raider!

[Quest: Goblin Trouble - 3 of 3 goblins defeated (quest complete)]
```

### Conversation
Weave quest updates into dialogue:
```
"You've done well," Vorvashali says, handing you a coin purse.
"The forest is safe again, thanks to you."

Received: 50 gold, 30 experience

[Quest completed: Goblin Trouble]
```

### Exploration
Discovery should feel natural:
```
As you enter the forest, you recall Vorvashali's words
about goblin raiders in these parts.

[Quest objective: Hunt goblin raiders - 0 of 3]
```

## Benefits of This Approach

1. **Immersion**: Players stay in character
2. **Clarity**: Important info still visible
3. **Polish**: Feels professional, not amateur
4. **Flexibility**: Can adjust IC/OOC ratio per context
5. **Accessibility**: Symbols + text works for all players

## Future Considerations

- **Colorization**: Could add subtle colors for IC (white) vs OOC (gray)
- **Verbosity Setting**: Let players choose IC-heavy vs data-heavy
- **Journal Voice**: Could frame quest log as character's journal entries
- **Dynamic Framing**: NPCs could have different dialogue styles

## Remember

> "Show, don't tell. Frame, don't dump. Immerse, don't break."

The best UI is invisible - players should feel like they're experiencing a story, not navigating menus.
