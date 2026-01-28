# TTA-Solo: Use Ability Command Spec

## Overview

The `/use <ability>` command allows players to use abilities directly from the CLI, bypassing natural language processing. This integrates with the existing ability system (UAO - Universal Ability Object).

## Current State

The engine has a robust ability system:
- `Ability` model with effects (damage, healing, conditions)
- `EntityResources` tracking (spell slots, cooldowns, stress/momentum)
- `_resolve_ability()` in router handles mechanics
- PbtA overlay for narrative outcomes

**Missing:** No way to invoke abilities via CLI command.

## New Command

### /use <ability_name> [on <target>]

Quick ability activation that:
1. Looks up ability by name from character's known abilities
2. Validates resource availability
3. Resolves the ability via existing router logic
4. Returns narrative result

```
/use fireball
/use healing word on myself
/use shield
/use second wind
```

## Implementation

### 1. Add Abilities to EntityResources

```python
class EntityResources(BaseModel):
    # ... existing fields ...
    abilities: list[Ability] = Field(
        default_factory=list,
        description="Abilities known by this entity"
    )

    def get_ability(self, name: str) -> Ability | None:
        """Look up ability by name (case-insensitive, prefix match)."""
        name_lower = name.lower()
        for ability in self.abilities:
            if ability.name.lower() == name_lower:
                return ability
        # Try prefix match
        for ability in self.abilities:
            if ability.name.lower().startswith(name_lower):
                return ability
        return None
```

### 2. CLI Command Handler

```python
def _cmd_use(self, state: GameState, args: list[str]) -> str | None:
    """Handle use command - activate an ability."""
    if not state.session_id:
        return "No active session."

    if not args:
        return self._show_available_abilities(state)

    # Parse: "/use fireball on goblin" or "/use healing word"
    ability_name, target_name = self._parse_use_args(args)

    # Get character's resources
    resources = self._get_character_resources(state)
    if not resources:
        return "No abilities available."

    # Look up ability
    ability = resources.get_ability(ability_name)
    if not ability:
        return f"Unknown ability: '{ability_name}'"

    # Resolve target (if any)
    target = self._resolve_target(state, target_name) if target_name else None

    # Execute via engine
    result = self._execute_ability(state, ability, target)
    return self._format_ability_result(ability, result)
```

### 3. Ability Execution Flow

```
/use fireball on goblin
       │
       ▼
┌──────────────────────────────┐
│ 1. Parse args                │
│    ability_name = "fireball" │
│    target_name = "goblin"    │
└──────────────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ 2. Look up ability           │
│    resources.get_ability()   │
└──────────────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ 3. Check resources           │
│    - Spell slot available?   │
│    - Cooldown ready?         │
│    - Enough momentum?        │
└──────────────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ 4. Resolve target            │
│    Find entity by name       │
└──────────────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ 5. Execute ability           │
│    router._resolve_ability() │
└──────────────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│ 6. Format result             │
│    Damage, effects, PbtA     │
└──────────────────────────────┘
```

## /abilities Command

Show character's available abilities:

```
> /abilities

Your Abilities:
---------------
  Fireball (3rd level spell) - 8d6 fire damage in 20ft radius
  Shield (1st level spell) - +5 AC until next turn
  Second Wind (martial) - Heal 1d10+level HP

Spell Slots: 1st: 2/4, 2nd: 2/3, 3rd: 0/2
```

## Resource Validation

Before executing, validate resources:

| Mechanism | Check | Consume |
|-----------|-------|---------|
| SLOTS | `has_spell_slot(level)` | `use_spell_slot(level)` |
| COOLDOWN | `cooldown.has_uses()` | `cooldown.use()` |
| MOMENTUM | `pool.momentum >= cost` | `pool.spend_momentum(cost)` |
| STRESS | Always available | `pool.add_stress(cost)` |
| FREE | Always available | Nothing |

## Target Resolution

Parse target from args:
- "on <name>" or "at <name>" → find entity by name
- "myself" / "self" / "me" → target self
- No target specified → use ability's default targeting

## Error Messages

- No args: "What ability? Use /abilities to see your options."
- Unknown ability: "You don't know an ability called 'fireball'."
- No resources: "Not enough spell slots. You need a level 3 slot."
- Invalid target: "Can't find 'goblin' here."
- Wrong target type: "Fireball can't target yourself!"

## Starter Abilities

Add default abilities to starter characters:

```python
STARTER_ABILITIES = [
    create_martial_technique(
        name="Second Wind",
        description="You have a limited well of stamina. Heal 1d10 + your level.",
        healing=HealingEffect(dice="1d10", flat_amount=1),
        targeting=Targeting(type=TargetingType.SELF),
        stress_cost=0,
        momentum_cost=0,
    ),
]
```
