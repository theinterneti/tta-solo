"""
Saving Throws and Skill Checks.

Implements SRD 5e saving throws and ability/skill checks.
The Symbolic layer - strict DC resolution.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.skills.combat import Abilities, Combatant, get_ability_modifier
from src.skills.dice import roll_dice

# SRD 5e skill to ability mappings
SKILL_ABILITIES: dict[str, Literal["str", "dex", "con", "int", "wis", "cha"]] = {
    # Strength
    "athletics": "str",
    # Dexterity
    "acrobatics": "dex",
    "sleight_of_hand": "dex",
    "stealth": "dex",
    # Intelligence
    "arcana": "int",
    "history": "int",
    "investigation": "int",
    "nature": "int",
    "religion": "int",
    # Wisdom
    "animal_handling": "wis",
    "insight": "wis",
    "medicine": "wis",
    "perception": "wis",
    "survival": "wis",
    # Charisma
    "deception": "cha",
    "intimidation": "cha",
    "performance": "cha",
    "persuasion": "cha",
}


class SaveResult(BaseModel):
    """Result of a saving throw."""

    success: bool
    roll: int = Field(description="The natural d20 result")
    total: int = Field(description="Roll + modifier")
    dc: int = Field(description="Difficulty class to beat")
    margin: int = Field(description="How much over/under DC (positive = success margin)")
    ability: str = Field(description="The ability used")


class CheckResult(BaseModel):
    """Result of an ability or skill check."""

    success: bool
    roll: int = Field(description="The natural d20 result")
    total: int = Field(description="Roll + modifiers")
    dc: int = Field(description="Difficulty class to beat")
    margin: int = Field(description="How much over/under DC")
    skill: str | None = Field(default=None, description="Skill used, if any")
    ability: str = Field(description="The ability used")


class SkillProficiencies(BaseModel):
    """Skill proficiency configuration for a character."""

    proficient: list[str] = Field(default_factory=list)
    expertise: list[str] = Field(default_factory=list)  # Double proficiency


def get_ability_score(abilities: Abilities, ability: str) -> int:
    """Get ability score by name."""
    match ability:
        case "str":
            return abilities.str_
        case "dex":
            return abilities.dex
        case "con":
            return abilities.con
        case "int":
            return abilities.int_
        case "wis":
            return abilities.wis
        case "cha":
            return abilities.cha
        case _:
            raise ValueError(f"Unknown ability: {ability}")


def make_saving_throw(
    entity: Combatant,
    ability: Literal["str", "dex", "con", "int", "wis", "cha"],
    dc: int,
    advantage: bool = False,
    disadvantage: bool = False,
    proficient: bool = False,
) -> SaveResult:
    """
    Make a saving throw against a DC.

    Args:
        entity: The one making the save
        ability: Which ability to use
        dc: Difficulty class to beat
        advantage: Roll 2d20 take highest
        disadvantage: Roll 2d20 take lowest
        proficient: Whether entity is proficient in this save

    Returns:
        SaveResult with success/failure and margin

    SRD Rules:
        - Roll d20 + ability modifier
        - Add proficiency bonus if proficient in that save
        - Meet or exceed DC to succeed
    """
    # Determine roll type
    if advantage and not disadvantage:
        roll_result = roll_dice("2d20kh1")
    elif disadvantage and not advantage:
        roll_result = roll_dice("2d20kl1")
    else:
        roll_result = roll_dice("1d20")

    natural_roll = roll_result.kept[0] if roll_result.kept else roll_result.rolls[0]

    # Get ability modifier
    ability_score = get_ability_score(entity.abilities, ability)
    ability_mod = get_ability_modifier(ability_score)

    # Add proficiency if applicable
    prof_bonus = entity.proficiency_bonus if proficient else 0

    total = natural_roll + ability_mod + prof_bonus
    margin = total - dc
    success = total >= dc

    return SaveResult(
        success=success,
        roll=natural_roll,
        total=total,
        dc=dc,
        margin=margin,
        ability=ability,
    )


def skill_check(
    entity: Combatant,
    skill: str,
    dc: int,
    skill_proficiencies: SkillProficiencies | None = None,
    advantage: bool = False,
    disadvantage: bool = False,
) -> CheckResult:
    """
    Make a skill check against a DC.

    Args:
        entity: The one making the check
        skill: The skill to use (must be in SKILL_ABILITIES)
        dc: Difficulty class to beat
        skill_proficiencies: Proficiency/expertise in skills
        advantage: Roll 2d20 take highest
        disadvantage: Roll 2d20 take lowest

    Returns:
        CheckResult with success/failure and margin

    SRD Rules:
        - Roll d20 + ability modifier (based on skill)
        - Add proficiency bonus if proficient
        - Add double proficiency if expertise
        - Meet or exceed DC to succeed
    """
    skill_lower = skill.lower().replace(" ", "_")

    if skill_lower not in SKILL_ABILITIES:
        raise ValueError(f"Unknown skill: {skill}. Valid skills: {list(SKILL_ABILITIES.keys())}")

    ability = SKILL_ABILITIES[skill_lower]

    # Determine roll type
    if advantage and not disadvantage:
        roll_result = roll_dice("2d20kh1")
    elif disadvantage and not advantage:
        roll_result = roll_dice("2d20kl1")
    else:
        roll_result = roll_dice("1d20")

    natural_roll = roll_result.kept[0] if roll_result.kept else roll_result.rolls[0]

    # Get ability modifier
    ability_score = get_ability_score(entity.abilities, ability)
    ability_mod = get_ability_modifier(ability_score)

    # Proficiency bonus
    prof_bonus = 0
    if skill_proficiencies:
        if skill_lower in skill_proficiencies.expertise:
            prof_bonus = entity.proficiency_bonus * 2  # Expertise
        elif skill_lower in skill_proficiencies.proficient:
            prof_bonus = entity.proficiency_bonus

    total = natural_roll + ability_mod + prof_bonus
    margin = total - dc
    success = total >= dc

    return CheckResult(
        success=success,
        roll=natural_roll,
        total=total,
        dc=dc,
        margin=margin,
        skill=skill_lower,
        ability=ability,
    )


def ability_check(
    entity: Combatant,
    ability: Literal["str", "dex", "con", "int", "wis", "cha"],
    dc: int,
    advantage: bool = False,
    disadvantage: bool = False,
) -> CheckResult:
    """
    Make a raw ability check (no skill) against a DC.

    Args:
        entity: The one making the check
        ability: Which ability to use
        dc: Difficulty class to beat
        advantage: Roll 2d20 take highest
        disadvantage: Roll 2d20 take lowest

    Returns:
        CheckResult with success/failure and margin
    """
    # Determine roll type
    if advantage and not disadvantage:
        roll_result = roll_dice("2d20kh1")
    elif disadvantage and not advantage:
        roll_result = roll_dice("2d20kl1")
    else:
        roll_result = roll_dice("1d20")

    natural_roll = roll_result.kept[0] if roll_result.kept else roll_result.rolls[0]

    # Get ability modifier
    ability_score = get_ability_score(entity.abilities, ability)
    ability_mod = get_ability_modifier(ability_score)

    total = natural_roll + ability_mod
    margin = total - dc
    success = total >= dc

    return CheckResult(
        success=success,
        roll=natural_roll,
        total=total,
        dc=dc,
        margin=margin,
        skill=None,
        ability=ability,
    )
