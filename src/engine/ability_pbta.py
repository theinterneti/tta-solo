"""
Ability-Specific PbtA System for TTA-Solo.

Provides source-specific complications and GM moves for ability use.
Magic, Tech, and Martial abilities each have unique failure modes.
"""

from __future__ import annotations

import random
from enum import StrEnum

from pydantic import BaseModel, Field

from src.models.ability import AbilitySource

# =============================================================================
# Ability Complication Types
# =============================================================================


class ComplicationType(StrEnum):
    """Types of complications that can occur on weak hits."""

    # Magic complications
    SPELL_DRAIN = "spell_drain"  # Extra resource consumed
    WILD_MAGIC = "wild_magic"  # Unpredictable side effect
    CONCENTRATION_STRAIN = "concentration_strain"  # Harder to maintain
    ARCANE_ATTENTION = "arcane_attention"  # Draws unwanted notice

    # Tech complications
    OVERHEAT = "overheat"  # Device needs cooldown
    MALFUNCTION = "malfunction"  # Temporary glitch
    POWER_SURGE = "power_surge"  # Drains other systems
    SYSTEM_ALERT = "system_alert"  # Draws attention

    # Martial complications
    OVEREXTEND = "overextend"  # Left vulnerable
    STRAIN = "strain"  # Physical cost
    TELEGRAPH = "telegraph"  # Enemy learns your pattern
    MOMENTUM_LOSS = "momentum_loss"  # Lose built-up advantage

    # Universal
    COLLATERAL = "collateral"  # Unintended target affected
    DELAYED = "delayed"  # Effect takes longer
    PARTIAL = "partial"  # Reduced effectiveness


class GMAbilityMoveType(StrEnum):
    """GM moves specific to ability failures."""

    # Magic misses
    SPELL_BACKFIRE = "spell_backfire"  # Spell hits caster
    MAGICAL_EXHAUSTION = "magical_exhaustion"  # Temporary magic fatigue
    ATTRACT_ENTITY = "attract_entity"  # Something notices the magic
    COMPONENT_CONSUMED = "component_consumed"  # Extra materials used

    # Tech misses
    CATASTROPHIC_FAILURE = "catastrophic_failure"  # Device damaged
    FEEDBACK_LOOP = "feedback_loop"  # System-wide issues
    SECURITY_BREACH = "security_breach"  # Alerts enemies
    POWER_DRAIN = "power_drain"  # Other abilities affected

    # Martial misses
    OPENING_GIVEN = "opening_given"  # Enemy gets free attack
    INJURY = "injury"  # Self-inflicted wound
    DISARM = "disarm"  # Weapon knocked away
    STUMBLE = "stumble"  # Lose footing/position


# =============================================================================
# Result Models
# =============================================================================


class AbilityComplication(BaseModel):
    """A complication from a weak hit on ability use."""

    type: ComplicationType
    description: str = Field(description="What happened")
    mechanical_effect: str = Field(description="Game mechanical consequence")
    resource_cost: int = Field(default=0, description="Extra resource consumed")
    condition_applied: str | None = Field(default=None, description="Condition to apply")
    stress_gained: int = Field(default=0, description="Stress added")


class AbilityGMMove(BaseModel):
    """A GM move from a miss on ability use."""

    type: GMAbilityMoveType
    description: str = Field(description="What happens")
    damage_to_user: int = Field(default=0, description="Damage dealt to ability user")
    condition_applied: str | None = Field(default=None)
    resource_lost: str | None = Field(default=None, description="Resource depleted")
    enemy_advantage: str | None = Field(default=None, description="Advantage given to enemies")


class AbilityPbtAResult(BaseModel):
    """Result of applying PbtA system to an ability use."""

    outcome: str = Field(description="strong_hit, weak_hit, or miss")
    complication: AbilityComplication | None = None
    gm_move: AbilityGMMove | None = None
    bonus_effect: str | None = Field(default=None, description="Extra benefit on strong hit")


# =============================================================================
# Complication Tables
# =============================================================================


MAGIC_COMPLICATIONS: list[AbilityComplication] = [
    AbilityComplication(
        type=ComplicationType.SPELL_DRAIN,
        description="The spell draws more power than expected.",
        mechanical_effect="Expend an additional spell slot of the same level or lower.",
        resource_cost=1,
    ),
    AbilityComplication(
        type=ComplicationType.WILD_MAGIC,
        description="Arcane energy crackles unpredictably.",
        mechanical_effect="Roll on wild magic table or DM chooses a minor magical effect.",
    ),
    AbilityComplication(
        type=ComplicationType.CONCENTRATION_STRAIN,
        description="Maintaining the spell is harder than usual.",
        mechanical_effect="Disadvantage on concentration checks for this spell.",
        stress_gained=1,
    ),
    AbilityComplication(
        type=ComplicationType.ARCANE_ATTENTION,
        description="Your magic flares visibly in the ethereal plane.",
        mechanical_effect="Magical creatures within 1 mile become aware of your presence.",
    ),
]

TECH_COMPLICATIONS: list[AbilityComplication] = [
    AbilityComplication(
        type=ComplicationType.OVERHEAT,
        description="The device runs hot and needs to cool down.",
        mechanical_effect="This ability cannot be used again for 1d4 rounds.",
    ),
    AbilityComplication(
        type=ComplicationType.MALFUNCTION,
        description="A minor glitch affects performance.",
        mechanical_effect="Next use of this device has disadvantage.",
    ),
    AbilityComplication(
        type=ComplicationType.POWER_SURGE,
        description="The device draws power from other systems.",
        mechanical_effect="One other tech ability loses a charge.",
        resource_cost=1,
    ),
    AbilityComplication(
        type=ComplicationType.SYSTEM_ALERT,
        description="The device emits a detectable signal.",
        mechanical_effect="Enemies with tech detection become aware of your position.",
    ),
]

MARTIAL_COMPLICATIONS: list[AbilityComplication] = [
    AbilityComplication(
        type=ComplicationType.OVEREXTEND,
        description="You commit too fully to the technique.",
        mechanical_effect="The next attack against you has advantage.",
    ),
    AbilityComplication(
        type=ComplicationType.STRAIN,
        description="The technique takes a physical toll.",
        mechanical_effect="Gain 1 stress or take 1d4 damage.",
        stress_gained=1,
    ),
    AbilityComplication(
        type=ComplicationType.TELEGRAPH,
        description="Your opponent reads your movements.",
        mechanical_effect="That enemy has +2 AC against your next attack.",
    ),
    AbilityComplication(
        type=ComplicationType.MOMENTUM_LOSS,
        description="You lose your combat rhythm.",
        mechanical_effect="Lose 1 momentum.",
        resource_cost=1,
    ),
]


# =============================================================================
# GM Move Tables
# =============================================================================


MAGIC_GM_MOVES: list[AbilityGMMove] = [
    AbilityGMMove(
        type=GMAbilityMoveType.SPELL_BACKFIRE,
        description="The spell's energy rebounds upon you!",
        damage_to_user=0,  # Varies by spell
        condition_applied="dazed",
    ),
    AbilityGMMove(
        type=GMAbilityMoveType.MAGICAL_EXHAUSTION,
        description="The failed casting drains your magical reserves.",
        resource_lost="spell_slot",
    ),
    AbilityGMMove(
        type=GMAbilityMoveType.ATTRACT_ENTITY,
        description="Something from beyond notices your magical fumble.",
        enemy_advantage="A magical creature is drawn to investigate.",
    ),
    AbilityGMMove(
        type=GMAbilityMoveType.COMPONENT_CONSUMED,
        description="Material components are wasted in the failed attempt.",
        resource_lost="components",
    ),
]

TECH_GM_MOVES: list[AbilityGMMove] = [
    AbilityGMMove(
        type=GMAbilityMoveType.CATASTROPHIC_FAILURE,
        description="The device sparks and shorts out!",
        damage_to_user=4,  # 1d8 average
        resource_lost="device_charge",
    ),
    AbilityGMMove(
        type=GMAbilityMoveType.FEEDBACK_LOOP,
        description="A cascade failure affects your other systems.",
        condition_applied="system_shock",
    ),
    AbilityGMMove(
        type=GMAbilityMoveType.SECURITY_BREACH,
        description="Your failed attempt triggers security protocols.",
        enemy_advantage="Enemies are alerted and gain a surprise round.",
    ),
    AbilityGMMove(
        type=GMAbilityMoveType.POWER_DRAIN,
        description="The failure drains all connected power sources.",
        resource_lost="all_tech_charges",
    ),
]

MARTIAL_GM_MOVES: list[AbilityGMMove] = [
    AbilityGMMove(
        type=GMAbilityMoveType.OPENING_GIVEN,
        description="Your failed technique leaves you completely exposed!",
        enemy_advantage="One enemy gets an immediate free attack against you.",
    ),
    AbilityGMMove(
        type=GMAbilityMoveType.INJURY,
        description="You hurt yourself with the botched technique.",
        damage_to_user=6,  # 1d10 average
    ),
    AbilityGMMove(
        type=GMAbilityMoveType.DISARM,
        description="Your weapon slips from your grasp!",
        condition_applied="disarmed",
    ),
    AbilityGMMove(
        type=GMAbilityMoveType.STUMBLE,
        description="You lose your footing badly.",
        condition_applied="prone",
    ),
]


# =============================================================================
# Strong Hit Bonuses
# =============================================================================


MAGIC_STRONG_HIT_BONUSES = [
    "The spell is empowered - add one die to damage or extend duration by 50%.",
    "You recover a spell slot of lower level than cast.",
    "The spell leaves a lingering magical effect beneficial to allies.",
    "You gain insight into the magical weave - advantage on next spell attack.",
]

TECH_STRONG_HIT_BONUSES = [
    "The device operates at peak efficiency - effect is maximized.",
    "System optimization grants an extra use before recharge needed.",
    "Tactical data gathered - advantage on next attack against this target.",
    "Energy recycling restores charge to another ability.",
]

MARTIAL_STRONG_HIT_BONUSES = [
    "Perfect execution grants an immediate follow-up attack.",
    "Your technique inspires you - gain 2 momentum.",
    "You find a weakness - this target has -2 AC against your attacks this round.",
    "Combat flow achieved - your next technique costs no resources.",
]


# =============================================================================
# Main Functions
# =============================================================================


def get_weak_hit_complication(source: AbilitySource) -> AbilityComplication:
    """
    Get a random complication for a weak hit based on ability source.

    Args:
        source: The ability's source (magic, tech, martial)

    Returns:
        AbilityComplication appropriate for the source
    """
    if source == AbilitySource.MAGIC:
        return random.choice(MAGIC_COMPLICATIONS)
    elif source == AbilitySource.TECH:
        return random.choice(TECH_COMPLICATIONS)
    else:  # MARTIAL
        return random.choice(MARTIAL_COMPLICATIONS)


def get_miss_gm_move(source: AbilitySource) -> AbilityGMMove:
    """
    Get a random GM move for a miss based on ability source.

    Args:
        source: The ability's source (magic, tech, martial)

    Returns:
        AbilityGMMove appropriate for the source
    """
    if source == AbilitySource.MAGIC:
        return random.choice(MAGIC_GM_MOVES)
    elif source == AbilitySource.TECH:
        return random.choice(TECH_GM_MOVES)
    else:  # MARTIAL
        return random.choice(MARTIAL_GM_MOVES)


def get_strong_hit_bonus(source: AbilitySource) -> str:
    """
    Get a random bonus effect for a strong hit based on ability source.

    Args:
        source: The ability's source (magic, tech, martial)

    Returns:
        Description of the bonus effect
    """
    if source == AbilitySource.MAGIC:
        return random.choice(MAGIC_STRONG_HIT_BONUSES)
    elif source == AbilitySource.TECH:
        return random.choice(TECH_STRONG_HIT_BONUSES)
    else:  # MARTIAL
        return random.choice(MARTIAL_STRONG_HIT_BONUSES)


def apply_ability_pbta(
    outcome: str,
    source: AbilitySource,
) -> AbilityPbtAResult:
    """
    Apply PbtA outcomes to an ability use.

    Args:
        outcome: PbtA outcome ("strong_hit", "weak_hit", "miss")
        source: The ability's source

    Returns:
        AbilityPbtAResult with appropriate effects
    """
    result = AbilityPbtAResult(outcome=outcome)

    if outcome == "strong_hit":
        result.bonus_effect = get_strong_hit_bonus(source)
    elif outcome == "weak_hit":
        result.complication = get_weak_hit_complication(source)
    elif outcome == "miss":
        result.gm_move = get_miss_gm_move(source)

    return result
