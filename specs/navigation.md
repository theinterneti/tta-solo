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

    # Get current exits
    exits = await self._get_current_exits(state)

    # Try exact match first, then partial
    matched_exit = self._match_exit(destination, exits)

    if matched_exit:
        # Update location
        new_location_id = exits[matched_exit]["id"]
        state.location_id = new_location_id
        session.location_id = new_location_id

        return f"You travel to {exits[matched_exit]['name']}."
    else:
        available = ", ".join(exits.keys())
        return f"Can't go '{destination}'. Available: {available}"
```

### _cmd_exits

```python
def _cmd_exits(self, state: GameState, args: list[str]) -> str | None:
    """Show available exits."""
    exits = await self._get_current_exits(state)

    if not exits:
        return "There are no obvious exits."

    lines = ["Available exits:"]
    for direction, info in exits.items():
        lines.append(f"  {direction} - {info['name']}")

    return "\n".join(lines)
```

## Exit Matching

Partial matching for convenience:
- "market" matches "Market Square"
- "rusty" matches "Rusty Dragon Inn"
- "n" matches "north" (if only one n-exit)

## Error Handling

- No args: "Where do you want to go? Use /exits to see options."
- Invalid destination: "Can't go 'foo'. Available: north, east, south"
- Not in session: "No active session."
