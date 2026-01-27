# TTA-Solo: Navigation System Spec

## Overview

The engine already supports natural language movement ("go to the market", "walk north"). This spec adds convenient CLI commands to make navigation more discoverable and efficient.

## Current State

The engine has full movement support:
- Intent parsing detects MOVE intents
- `_resolve_move` validates against available exits
- `exit_destinations` maps exit names to location IDs
- Location updates on successful movement

## New Commands

### /go <destination>

Quick navigation command that bypasses natural language processing.

```
/go market
/go north
/go "Rusty Dragon Inn"
```

**Behavior:**
1. Look up destination in `exit_destinations` (case-insensitive, partial match)
2. If found: Update location, show travel message
3. If not found: Show error with available exits

### /exits

Show available exits from current location.

```
> /exits

Available exits:
  north - Market Square
  east - Rusty Dragon Inn
  south - Town Gate
```

## Implementation

### _cmd_go

```python
def _cmd_go(self, state: GameState, args: list[str]) -> str | None:
    """Handle go command - quick navigation."""
    if not args:
        return "Where do you want to go? Use /exits to see options."

    destination = " ".join(args).lower()

    # Get current exits (sync - uses direct DB lookups)
    exits = self._get_location_exits(state)

    # Try exact match first, then prefix match
    matched_exit = self._match_exit(destination, exits)

    if matched_exit:
        new_location_id = exits[matched_exit]["id"]
        old_location_id = state.location_id

        # Update state and session
        state.location_id = new_location_id
        session.location_id = new_location_id

        # Update Dolt (truth)
        player.current_location_id = new_location_id
        dolt.save_entity(player)

        # Update Neo4j (context) - maintain LOCATED_IN relationship
        neo4j.delete_relationship(old_located_in_rel)
        neo4j.create_relationship(new_located_in_rel)

        return f"You travel to {exits[matched_exit]['name']}."
    else:
        available = ", ".join(exits.keys())
        return f"Can't go '{destination}'. Available: {available}"
```

### _cmd_exits

```python
def _cmd_exits(self, state: GameState, args: list[str]) -> str | None:
    """Show available exits."""
    exits = self._get_location_exits(state)

    if not exits:
        return "There are no obvious exits."

    lines = ["Available exits:"]
    for direction, info in exits.items():
        lines.append(f"  {direction} - {info['name']}")

    return "\n".join(lines)
```

## Exit Matching

Prefix matching for convenience and disambiguation:
- "market" matches "Market Square" (prefix of location name)
- "n" matches "north" (if only one n-prefixed exit)
- "north" does NOT match "northeast" (avoids ambiguity)

If multiple exits match the prefix, returns None (ambiguous).

## Data Consistency (Dual-State)

Per the project's architecture, location changes must update both databases:

### Dolt (Truth)
- `player.current_location_id` - Player entity's location field
- Persisted via `dolt.save_entity(player)`

### Neo4j (Context)
- `LOCATED_IN` relationship - Tracks where entities are located
- Remove old: `neo4j.delete_relationship(old_rel)`
- Create new: `neo4j.create_relationship(Relationship(type=LOCATED_IN, ...))`

This mirrors the movement handling in `src/engine/game.py` lines 508-529.

## Error Handling

- No args: "Where do you want to go? Use /exits to see options."
- Invalid destination: "Can't go 'foo'. Available: north, east, south"
- Not in session: "No active session."
