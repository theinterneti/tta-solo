"""
Combat Resolution Skills.

Implements SRD 5e attack resolution with strict rule enforcement.
The Symbolic layer - no hallucination, just dice and math.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from src.skills.dice import roll_dice


class CoverType(str, Enum):
    """Cover types per SRD 5e."""

    NONE = "none"
    HALF = "half"  # +2 AC
    THREE_QUARTERS = "three_quarters"  # +5 AC
    TOTAL = "total"  # Can't be targeted directly


class WeaponProperty(str, Enum):
    """Weapon properties per SRD 5e."""

    FINESSE = "finesse"  # Can use DEX instead of STR
    RANGED = "ranged"  # Uses DEX
    THROWN = "thrown"  # Can be thrown
    TWO_HANDED = "two_handed"
    VERSATILE = "versatile"
    LIGHT = "light"
    HEAVY = "heavy"


class Weapon(BaseModel):
    """A weapon used for attacks."""

    name: str
    damage_dice: str = Field(description="Damage notation, e.g., '1d8', '2d6'")
    damage_type: str = Field(description="e.g., 'slashing', 'piercing', 'bludgeoning'")
    properties: list[WeaponProperty] = Field(default_factory=list)


class Abilities(BaseModel):
    """Ability scores for an entity."""

    str_: int = Field(default=10, alias="str")
    dex: int = 10
    con: int = 10
    int_: int = Field(default=10, alias="int")
    wis: int = 10
    cha: int = 10

    model_config = {"populate_by_name": True}


class Combatant(BaseModel):
    """Minimal combatant info needed for attack resolution."""

    name: str
    ac: int = 10
    abilities: Abilities = Field(default_factory=Abilities)
    proficiency_bonus: int = 2
    proficient_weapons: list[str] = Field(default_factory=list)


class AttackResult(BaseModel):
    """Result of an attack roll."""

    hit: bool
    critical: bool = False
    fumble: bool = False
    attack_roll: int = Field(description="The natural d20 result")
    total_attack: int = Field(description="Roll + modifiers")
    target_ac: int
    damage: int | None = Field(default=None, description="Only if hit")
    damage_type: str | None = None


def get_ability_modifier(score: int) -> int:
    """Calculate ability modifier from score (SRD formula)."""
    return (score - 10) // 2


def get_attack_ability(weapon: Weapon, attacker: Combatant) -> Literal["str", "dex"]:
    """Determine which ability to use for attack roll."""
    if WeaponProperty.RANGED in weapon.properties:
        return "dex"
    if WeaponProperty.FINESSE in weapon.properties:
        # Finesse: use higher of STR or DEX
        str_mod = get_ability_modifier(attacker.abilities.str_)
        dex_mod = get_ability_modifier(attacker.abilities.dex)
        return "dex" if dex_mod > str_mod else "str"
    return "str"


def get_cover_bonus(cover: CoverType) -> int:
    """Get AC bonus from cover."""
    match cover:
        case CoverType.NONE:
            return 0
        case CoverType.HALF:
            return 2
        case CoverType.THREE_QUARTERS:
            return 5
        case CoverType.TOTAL:
            return 99  # Effectively unhittable


def resolve_attack(
    attacker: Combatant,
    target: Combatant,
    weapon: Weapon,
    cover: CoverType = CoverType.NONE,
    advantage: bool = False,
    disadvantage: bool = False,
) -> AttackResult:
    """
    Resolve a single attack per SRD 5e rules.

    Args:
        attacker: The attacking combatant
        target: The target combatant
        weapon: The weapon being used
        cover: Target's cover (affects AC)
        advantage: Roll 2d20 take highest
        disadvantage: Roll 2d20 take lowest

    Returns:
        AttackResult with hit/miss, damage if hit

    SRD Rules Enforced:
        - Natural 20: Always hits, critical (double damage dice)
        - Natural 1: Always misses (fumble)
        - Finesse weapons can use DEX
        - Ranged weapons use DEX
        - Cover adds to AC
    """
    # Determine attack roll type
    if advantage and not disadvantage:
        roll_result = roll_dice("2d20kh1")
    elif disadvantage and not advantage:
        roll_result = roll_dice("2d20kl1")
    else:
        # Normal roll, or advantage and disadvantage cancel
        roll_result = roll_dice("1d20")

    natural_roll = roll_result.kept[0] if roll_result.kept else roll_result.rolls[0]

    # Get ability modifier
    attack_ability = get_attack_ability(weapon, attacker)
    if attack_ability == "str":
        ability_mod = get_ability_modifier(attacker.abilities.str_)
    else:
        ability_mod = get_ability_modifier(attacker.abilities.dex)

    # Proficiency bonus
    prof_bonus = 0
    if weapon.name.lower() in [w.lower() for w in attacker.proficient_weapons]:
        prof_bonus = attacker.proficiency_bonus

    total_attack = natural_roll + ability_mod + prof_bonus

    # Calculate effective AC with cover
    effective_ac = target.ac + get_cover_bonus(cover)

    # Determine hit/miss per SRD
    critical = natural_roll == 20
    fumble = natural_roll == 1

    if fumble:
        hit = False
    elif critical:
        hit = True
    else:
        hit = total_attack >= effective_ac

    # Calculate damage if hit
    damage: int | None = None
    if hit:
        damage_roll = roll_dice(weapon.damage_dice)
        base_damage = damage_roll.total

        # Add ability modifier to damage
        base_damage += ability_mod

        # Critical: double the dice (roll again and add)
        if critical:
            crit_roll = roll_dice(weapon.damage_dice)
            base_damage += crit_roll.total

        # Minimum 1 damage on hit (can't heal by attacking)
        damage = max(1, base_damage)

    return AttackResult(
        hit=hit,
        critical=critical,
        fumble=fumble,
        attack_roll=natural_roll,
        total_attack=total_attack,
        target_ac=effective_ac,
        damage=damage,
        damage_type=weapon.damage_type if hit else None,
    )
