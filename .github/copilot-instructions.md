# GitHub Copilot Instructions for TTA-Solo

## Project Overview

TTA-Solo is an **AI-Native Infinite Multiverse Engine** - a neuro-symbolic text adventure where players collaborate with AI to tell stories in a shared, branching multiverse.

### Core Philosophy
This project bridges Neural (LLM) and Symbolic (Python) systems:
- **Neural Layer**: Handles narrative, dialogue, and improvisation
- **Symbolic Layer**: Enforces SRD 5e mechanics strictly (dice, rules, validation)
- **Bridge Layer**: Skills translate player intent into function calls and back

## Stack & Tools

### Core Technologies
- **Language**: Python 3.11+ (required)
- **Database (Truth)**: Dolt - Git-like SQL for branching timelines and event sourcing
- **Database (Context)**: Neo4j - Graph database with native vector search
- **Package Manager**: `uv` (NEVER use pip or poetry)
- **Validation**: Pydantic for all data structures

### Dependencies
- `pydantic>=2.0` - Data validation
- `neo4j>=5.0` - Graph database driver
- `mysql-connector-python>=8.0` - Dolt connection
- `python-dotenv>=1.0` - Environment configuration

### Development Tools
- **Testing**: `pytest>=8.0` with `pytest-asyncio` and `pytest-cov`
- **Linting**: `ruff>=0.4` (100 char line length)
- **Type Checking**: `pyright>=1.1`

## Code Style Rules

### Type Hints (CRITICAL)
- ✅ Use modern union syntax: `str | None`
- ❌ NEVER use: `Optional[str]`, `Union[str, None]`
- ✅ Use: `dict[str, Any]`
- ❌ NEVER use: `Dict[str, Any]`
- Always include `from __future__ import annotations` at the top of files

### Code Standards
- **Line length**: 100 characters max
- **Docstrings**: Google-style format
- **Imports**: Organized and sorted (ruff handles this)
- **Validation**: All data structures must use Pydantic models
- **Target**: Python 3.11+ features are encouraged

### Naming Conventions
- Follow standard Python conventions (PEP 8)
- Use descriptive names for variables and functions
- Constants in UPPER_CASE
- Classes in PascalCase
- Functions and variables in snake_case

## Development Workflow: Spec-Driven

**CRITICAL RULE: NEVER write code before a spec exists**

1. **Spec Phase**: Create markdown file in `/specs/` defining inputs, logic, outputs
2. **Skill Phase**: Implement as stateless Python tool with Pydantic validation
3. **Test Phase**: Write tests that verify the spec (TDD preferred)
4. **Execution Phase**: Wire into the agent loop

### Before Writing ANY Code
- [ ] Spec MUST exist in `/specs/` directory
- [ ] Schema MUST be defined for any new data structures
- [ ] Tests MUST be written (aim for 100% coverage)

### Relevant Specs
- `specs/ontology.md` - Entity and event schemas
- `specs/mechanics.md` - SRD 5e rule implementations
- `specs/multiverse.md` - Timeline branching rules
- `specs/engine.md` - Core game loop architecture

## Critical Rules

### Skills (src/skills/) - MUST Follow These Rules
1. **Stateless**: No global variables, no class instances with state
2. **Pydantic**: All inputs and outputs use Pydantic models
3. **Error Handling**: Graceful failures with structured error returns
4. **No LLM Calls**: Skills NEVER call LLMs directly - that's the engine's job
5. **Pure Functions**: Same input → same output (deterministic)

### Database Access
- Use direct drivers:
  - `mysql-connector-python` for Dolt
  - `neo4j` driver for Neo4j
- ❌ NO ORMs - keep it simple
- All writes go through event sourcing pattern
- Dolt is for immutable truth (facts, events)
- Neo4j is for searchable context (relationships, vectors)

### Data Architecture (Dual-State)
**Dolt Tables** (The Facts):
- `universes` - Timeline branches
- `entities` - Characters, items, locations with JSON stats
- `events` - Immutable event log (the history)

**Neo4j Nodes** (The Context):
- `:Entity`, `:Character`, `:Location`, `:Concept`
- Relationships: `KNOWS`, `LOCATED_IN`, `CAUSED`, `FEARS`
- Vector embeddings on description fields

### Core Axioms
1. **Dolt is for Truth, Neo4j is for Search**
   - Kill a goblin → Event in Dolt (can rollback/fork)
   - Goblin's brother hates you → Relationship in Neo4j (for retrieval)

2. **Stateless Simplicity**
   - Skills fail cleanly, database holds state
   - No Python memory between calls

3. **Fail Forward**
   - If Symbolic fails, Neural takes over to keep story moving
   - Log edge cases for later improvement

## Commands

### Setup
```bash
uv sync                      # Install all dependencies
uv sync --all-extras         # Install with dev dependencies
```

### Development
```bash
uv run pytest -v             # Run tests
uv run pytest -v tests/path  # Run specific test
uv run pytest --cov          # Run with coverage
uv run ruff format .         # Format code
uv run ruff check . --fix    # Lint and auto-fix
uv run pyright src/          # Type check
```

### Database (when configured)
```bash
dolt sql                     # Interactive Dolt shell
dolt branch                  # List timeline branches
dolt checkout -b <name>      # Create new timeline fork
```

## Git Conventions

### Branch Naming
Format: `{initials}/{description}`
- Example: `ti/add-combat-skill`
- Example: `js/fix-dice-bug`

### Commit Messages
Use Conventional Commits format:
- `feat:` - New features
- `fix:` - Bug fixes
- `docs:` - Documentation changes
- `spec:` - Specification updates
- `test:` - Test changes
- `refactor:` - Code refactoring
- `chore:` - Maintenance tasks

### Pull Request Titles
Same format as commit messages.

## Project Structure

```
tta-solo/
├── .github/             # GitHub configuration
├── specs/               # Specifications (MUST exist before code)
│   ├── ontology.md      # Entity/Event schemas
│   ├── mechanics.md     # SRD rule implementations
│   ├── multiverse.md    # Timeline branching rules
│   └── engine.md        # Core game loops
├── src/
│   ├── skills/          # Stateless Python tools
│   ├── engine/          # Core game loops and orchestration
│   ├── models/          # Pydantic models
│   ├── services/        # Business logic
│   └── db/              # Database interfaces
├── tests/               # Test files (aim for 100% coverage)
└── data/                # Local database storage (gitignored)
```

## Testing Philosophy

- Write tests BEFORE or alongside implementation (TDD)
- Aim for 100% code coverage
- Use `pytest` fixtures for common setup
- Mock external dependencies (databases, LLM calls)
- Test both happy paths and error cases
- Keep tests fast and independent

## Security & Best Practices

- Never commit secrets or credentials
- Use `.env` files for local configuration (gitignored)
- Validate all external input with Pydantic
- Handle database errors gracefully
- Log important events and errors
- Keep dependencies up to date

## When to Check Specs

Before implementing ANY task, check if relevant specs apply:
- Creating game mechanics → Check `specs/mechanics.md`
- Working with entities → Check `specs/ontology.md`
- Timeline/branching logic → Check `specs/multiverse.md`
- Engine architecture → Check `specs/engine.md`
- Writing skills → Follow stateless pattern in existing skills

## Package Manager: uv Only

**CRITICAL**: Always use `uv` for package management:
- ✅ `uv sync` - Install dependencies
- ✅ `uv add <package>` - Add new dependency
- ✅ `uv run <command>` - Run commands in virtual environment
- ❌ NEVER use `pip install`
- ❌ NEVER use `poetry`

## Additional Context

This is an experimental project exploring:
- Neuro-symbolic AI architectures
- Event-sourced game state
- Branching narrative timelines
- AI-assisted storytelling
- Stateless skill systems

The goal is to create a D&D-like experience that's:
- Shareable (characters, adventures, worlds)
- Forkable (like git branches)
- AI-native (LLM is a first-class citizen)
- Mechanically sound (real dice, real rules)
