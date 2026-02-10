# Faction Quest Generation Specification

## Overview

Faction tensions (rivalries, trade dependencies, territorial disputes) become a primary source of procedurally generated quests. The existing location-based template system gets a new "faction" layer that produces richer, world-aware quests driven by inter-faction relationships created in Phase A (universe generation).

## Design Principles

1. **World-Driven**: Quests emerge from faction relationships, not random templates
2. **Backwards-Compatible**: No factions at location = existing behavior unchanged
3. **Reputation-Aware**: Quest rewards include faction reputation via `QuestReward.reputation_changes`
4. **LLM-Enhanced**: Faction context passed to LLM enhancer for richer narratives

## Data Models

### FactionTension

Lightweight model representing a tension between two factions relevant to quest generation:

```python
class FactionTension(BaseModel):
    faction_a_name: str
    faction_b_name: str
    faction_a_id: UUID
    faction_b_id: UUID
    relationship_type: str  # TRADES_WITH, COMPETES_WITH, etc.
    description: str
```

### QuestContext Additions (all optional, backwards-compatible)

```python
controlling_faction: Entity | None       # Faction controlling this location
factions_at_location: list[Entity]       # All factions with presence here
faction_tensions: list[FactionTension]   # Tensions between factions
world_context_summary: str               # Universe worldbuilding summary
```

## Faction Quest Templates

Templates keyed by faction relationship type:

| Relationship | Templates | Quest Types |
|---|---|---|
| TRADES_WITH | Trade Route Escort, Supply Delivery | ESCORT, DELIVER |
| COMPETES_WITH | Spy Mission, Sabotage Operation, Intercept Shipment | INVESTIGATE, HUNT, FETCH |
| DEPENDS_ON | Secure Supply Line, Broker Alliance | ESCORT, TALK |
| CONTROLS | Investigate Corruption, Deliver Tribute | INVESTIGATE, DELIVER |
| INFLUENCES | Gather Intel, Counter Propaganda | INVESTIGATE, TALK |

Templates use substitution variables: `{faction_a}`, `{faction_b}`, `{resource}`, `{territory}`.

## Quest Generation Flow

### Template Selection (60/40 faction preference)

1. If `context.faction_tensions` is non-empty → 60% chance to use faction templates
2. Pick a random tension → key into faction templates by `relationship_type`
3. If no faction templates match or roll fails → fall back to location-based selection

### Template Filling

When a faction template is selected:
- `{faction_a}` / `{faction_b}` from the selected tension
- `{resource}` from faction's `controls_resources` / `produces` / `needs`
- `{territory}` from faction's `territory_description`
- Quest giver preference: NPCs who are MEMBER_OF faction_a
- `reputation_changes` on reward: faction_a gets +rep, faction_b gets -rep (for competitive quests)

### LLM Enhancement

Append to LLM prompt:
```
Faction Context:
- {faction_a} ({values}) {rel_type} {faction_b} ({values})
- World: {world_context_summary}
```

## Context Building

In `build_quest_context()`, after existing NPC/location queries:

1. Read `controlling_faction_hint` from `location.location_properties`
2. Find matching faction entity by name via `dolt.get_entity_by_name()`
3. Query all faction entities via `dolt.get_entities_by_type("faction", universe_id)`
4. For each faction pair, query Neo4j for faction-to-faction relationships
5. Build `FactionTension` list from discovered relationships
6. Get universe's `world_context` dict → extract summary string

## Reputation Rewards

Uses existing `QuestReward.reputation_changes: dict[UUID, int]` field:

- **TRADES_WITH quests**: +rep for quest giver's faction (faction_a)
- **COMPETES_WITH quests**: +rep for quest giver's faction, -rep for rival
- **DEPENDS_ON quests**: +rep for dependent faction
- **CONTROLS quests**: +rep for controlling faction
- **INFLUENCES quests**: +rep for influencing faction

## What We're NOT Building

- Faction reputation UI/tracking (just the reward data)
- Quest chains across factions
- Faction war/diplomacy mechanics
- Changes to existing location-based quest templates

## Success Metrics

- Faction quests feel driven by world tensions, not generic
- Existing quest generation unchanged when no factions exist
- Reputation changes populate on faction quest rewards
- LLM enhancement produces faction-aware narrative
