# TTA-Solo

**AI-Native Infinite Multiverse Engine**

A Neuro-symbolic text adventure where players collaborate with AI to tell stories in a shared, branching multiverse.

**Current Status**: ✅ **Grade A** - Production Ready | 930 tests passing | 94%+ coverage

## Vision

The ultimate solo "choose your own adventure" D&D experience you can share with friends:
- **Share a character** - Archetype builder across worlds
- **Share an adventure** - Others relive your story's options
- **Share a world** - Create new stories in existing settings
- **Share a world network** - Stories that cross multiple worlds

## Architecture

| Layer | Tech | Purpose |
|-------|------|---------|
| **Truth** | Dolt | Git-like SQL - branching timelines, event sourcing |
| **Brain** | Neo4j | Graph + Vector search - relationships, semantic search |
| **Hands** | Python Skills | Stateless scripts for game mechanics |

### The Neuro-Symbolic Model

- **Neural** (LLM): Narrative, dialogue, improvisation
- **Symbolic** (Python): SRD 5e rules, dice, state validation
- **Bridge** (Skills): Translate intent to mechanics and back

## Quick Start

```bash
# Install dependencies
uv sync --all-extras

# Play the game
uv run python play.py

# Run tests
uv run pytest -v

# Type check
uv run pyright src/
```

## Current Features

- ✅ **Quest System**: Accept, progress, and complete multi-step quests
- ✅ **Conversation**: Talk to NPCs with personality-driven dialogue
- ✅ **Navigation**: Explore 5 locations with /go and /exits commands
- ✅ **Economy**: Buy and sell items, manage gold
- ✅ **Abilities**: Use special powers with /use command (2 starter abilities)
- ✅ **Combat** (tested): Solo combat with momentum, stress, and Defy Death mechanics
- ✅ **Inventory**: Manage items and equipment
- ✅ **Character Stats**: Full D&D 5e compatible attributes

## Status Reports

- 📊 [Latest Playtest (Feb 2026)](PLAYTEST_REPORT_2026_02.md) - Grade A
- 📋 [Spec Implementation Status](SPEC_STATUS.md) - 10/19 complete
- 🗺️ [Next Steps & Roadmap](NEXT_STEPS.md) - Path to A+

## Project Structure

```
tta-solo/
├── specs/              # Specs MUST exist before code
│   ├── ontology.md     # Entity/Event schemas
│   ├── mechanics.md    # SRD rule implementations
│   └── multiverse.md   # Timeline branching rules
├── src/
│   ├── skills/         # Stateless Python tools
│   └── engine/         # Core game loops
├── tests/              # 100% coverage goal
└── data/               # Local database storage
```

## Development Workflow

1. **Spec Phase**: Write spec in `/specs/` before any code
2. **Skill Phase**: Implement as stateless Python with Pydantic
3. **Test Phase**: TDD - write tests that verify the spec
4. **Execute**: Wire into agent loop

## License

MIT
