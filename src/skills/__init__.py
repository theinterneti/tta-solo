"""
Stateless Skills for TTA-Solo.

Skills are pure functions that:
- Take structured input (Pydantic models)
- Execute game logic (dice, rules, database queries)
- Return structured output
- NEVER maintain state between calls
- NEVER call LLMs directly
"""

from src.skills.checks import (
    SKILL_ABILITIES,
    CheckResult,
    SaveResult,
    SkillProficiencies,
    ability_check,
    make_saving_throw,
    skill_check,
)
from src.skills.combat import (
    Abilities,
    AttackResult,
    Combatant,
    CoverType,
    Weapon,
    WeaponProperty,
    get_ability_modifier,
    resolve_attack,
)
from src.skills.dice import DiceResult, roll_dice

__all__ = [
    # Dice
    "roll_dice",
    "DiceResult",
    # Combat
    "resolve_attack",
    "AttackResult",
    "Combatant",
    "Weapon",
    "WeaponProperty",
    "Abilities",
    "CoverType",
    "get_ability_modifier",
    # Checks & Saves
    "make_saving_throw",
    "SaveResult",
    "skill_check",
    "ability_check",
    "CheckResult",
    "SkillProficiencies",
    "SKILL_ABILITIES",
]
