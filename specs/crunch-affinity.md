# Crunch Affinity System

> Adaptively adjusts mechanical detail level based on player behavior.

## Overview

The system tracks how mechanically-engaged a player is and adjusts output detail accordingly. Underlying mechanics are unchanged — only **presentation** adapts. Players can manually lock their preference.

## Three Levels

| Level | Description |
|-------|-------------|
| **NARRATIVE** | Pure story. No roll breakdowns or modifiers. Crits/fumbles still called out dramatically. |
| **BALANCED** | Story + compact mechanics. Roll totals shown, crit/fumble flagged. (Default) |
| **DETAILED** | Full SRD. Roll breakdowns with modifiers, state change log. |

## Adaptive Drift

A sliding window of the last 50 player inputs, each tagged with a signal weight:

| Signal | Weight | Examples |
|--------|--------|----------|
| Slash combat cmd | +0.8 | `/attack`, `/defend`, `/use` |
| Slash info cmd | +0.6 | `/status`, `/abilities`, `/inventory` |
| Natural language (specific) | +0.3 | "attack the goblin with my longsword" |
| Natural language (simple) | -0.6 | "I swing at the goblin" |
| Natural language (vague) | -0.8 | "I try to sneak past" |
| Neutral commands | 0.0 | `/help`, `/clear`, `/look`, `/rest` |

### Score Calculation

Position-weighted average of signals in window (newer inputs = heavier weight), scaled to -100..+100.

```
raw = sum(weight * (position + 1) for position, weight in enumerate(signals))
divisor = sum(range(1, len(signals) + 1))
score = (raw / divisor) * 100
```

### Thresholds

- score <= -20 → NARRATIVE
- score >= +20 → DETAILED
- else → BALANCED

### Manual Override

- `/setting crunch narrative|balanced|detailed` — locks level
- `/setting crunch auto` — re-enables drift

## Output Examples

### NARRATIVE (roll: Attack 18, modifier +5, total 23, critical)

```
Your blade finds its mark with devastating precision! A critical strike!
```

### BALANCED (same roll)

```
Your blade finds its mark with devastating precision!

[Attack: 23 CRITICAL!]
```

### DETAILED (same roll)

```
Your blade finds its mark with devastating precision!

[Attack: 23 (18+5) CRITICAL!]
* HP: Goblin 15 → 3
```

## Data Model

- `CrunchLevel` — StrEnum: narrative, balanced, detailed
- `CrunchAffinity` — Pydantic BaseModel tracking level, raw_score, signal history, manual_override flag
- No persistence — resets each session
- No per-subsystem levels — one level for everything
