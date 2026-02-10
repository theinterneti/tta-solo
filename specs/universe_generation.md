# Universe Generation Spec

> **Status**: Phase A — MVP
> **Depends on**: `specs/ontology.md`, `specs/mechanics.md`, Physics Overlays

## Overview

Replace the hardcoded Eldoria starter world with an LLM-powered generation pipeline where **factions drive worldbuilding**. A `UniverseTemplate` seeds the LLM, which generates interconnected factions, locations shaped by those factions, and NPCs that belong to them.

## Core Concept: Faction-Driven Worldbuilding

Factions are the generative backbone. Every location has a controlling faction. Every NPC belongs to a faction. Economic interdependence between factions creates natural tension.

## Data Models

### UniverseTemplate (the creative seed)

```
UniverseTemplate:
  name: str                      # "Shattered Kingdoms"
  physics_overlay_key: str       # ties to OVERLAY_REGISTRY
  power_source_flavor: str       # "Magic flows from crystallized emotions"
  tone: str                      # grimdark, hopeful, noir, whimsical
  genre_tags: list[str]          # ["political intrigue", "survival"]
  cultural_premise: str          # "Memory is currency, forgetting is a crime"
  economic_premise: str          # "Three factions, three resources, no self-sufficiency"
  geography_hint: str            # "Floating islands connected by chain bridges"
  era_hint: str                  # "Post-collapse renaissance"
  scarcity: str                  # What's scarce — drives conflict
  faction_seeds: list[FactionSeed]  # Optional hints for faction generation
```

### FactionSeed (optional generation hints)

```
FactionSeed:
  name_hint: str | None          # Suggested name
  role_hint: str                 # "rulers", "merchants", "rebels"
  values_hint: str | None        # "honor above all"
```

### Enhanced FactionProperties (backwards-compatible)

New optional fields on existing model:
- `core_values: list[str]` — what they believe
- `ideology_summary: str` — one-line ideology
- `controls_resources: list[str]` — what they control
- `produces: list[str]`, `needs: list[str]` — economic web
- `economic_role: str` — "producers", "traders", "raiders"
- `cultural_traits: list[str]`, `taboos: list[str]`, `aesthetic: str`
- `governance: str`, `leader_title: str`
- `territory_description: str`, `headquarters: str`

### Enhanced LocationProperties (backwards-compatible)

New optional fields:
- `controlling_faction_hint: str` — which faction controls this
- `cultural_flavor: str` — visible cultural markers
- `economic_activity: str` — what happens here economically
- `atmosphere: str` — mood/vibe

### Enhanced Universe

New optional fields:
- `template_id: UUID | None` — which template generated this
- `physics_overlay_key: str` — physics rules
- `world_context: dict[str, Any]` — LLM-generated worldbuilding (freeform JSON)

### New Relationship Types

- `TRADES_WITH` — economic cooperation
- `COMPETES_WITH` — economic/political rivalry
- `DEPENDS_ON` — resource dependency
- `CONTROLS` — territorial/political control
- `INFLUENCES` — soft power / cultural influence

## Generation Pipeline

### Step 1: World Context
- **Input**: UniverseTemplate
- **Output**: `world_context` dict with history, cosmology, naming conventions, tone guide
- **Token budget**: 1024
- **Fallback**: Template fields used directly as world_context

### Step 2: Factions
- **Input**: world_context + faction_seeds
- **Output**: 2-5 factions with full FactionProperties + inter-faction relationships
- **Token budget**: 2048
- **Fallback**: Generate 3 template factions (rulers, merchants, outcasts)

### Step 3: Locations
- **Input**: world_context + factions
- **Output**: 3-7 locations with connections, faction control, economic activity
- **Token budget**: 2048
- **Fallback**: Generate tavern + market + wilderness + dungeon

### Step 4: NPCs
- **Input**: world_context + factions + locations
- **Output**: 1-2 NPCs per location with faction membership, personality, role
- **Token budget**: 2048
- **Fallback**: Generate archetype NPCs (bartender, merchant, guard, stranger)

### Step 5: Wire into DB
- Save all entities to Dolt
- Save all relationships to Neo4j
- Create LOCATED_IN, MEMBER_OF, CONNECTED_TO, CONTROLS, TRADES_WITH relationships

## LLM Contract

Each generation step uses:
- **System prompt**: Defines JSON schema for output + creative constraints
- **User prompt**: Template fields + context from prior steps
- **Temperature**: 0.8 (creative but structured)
- **Response format**: JSON object matching defined schema

The `generate_structured()` method on LLMService forwards prompts to `provider.complete()` with higher token budgets and returns raw text. JSON parsing and validation is handled by the caller (UniverseGenerator).

## Fallback Strategy

If LLM is unavailable or returns invalid JSON:
1. Log the failure
2. Use template-based fallback generation
3. Mark the universe as `used_fallback: true` in world_context
4. Game is always playable — never blocked on LLM

## Pre-Built Templates

Ship 6-8 templates covering major genres:
1. Classic Fantasy, 2. Cyberpunk Sprawl, 3. Cosmic Horror,
4. Political Intrigue, 5. Post-Apocalyptic, 6. Mythic Ages,
7. Weird West, 8. Blank Canvas (maximum LLM improv)

## CLI Integration

At game start:
1. Display numbered template list
2. Player selects template (or "Classic Fantasy" default)
3. Run generation pipeline
4. Create player character in starting location
5. Begin game loop

Keep `create_starter_world()` as the no-LLM fallback (template selection = "Classic (no AI)").

## Integration Points

- `generate_dialogue()` and `generate_narrative()` receive `universe_context` for tone consistency
- `MoveExecutor` NPC generation uses faction + world context
- All downstream LLM calls stay consistent with universe culture/tone

## Testing

- Unit: Template validation, JSON parsing, fallback generation, model backwards compat
- Integration (MockLLMProvider): Full pipeline with canned JSON responses
- Optional: End-to-end with real API
