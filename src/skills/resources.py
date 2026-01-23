"""
Resource Management Skills for TTA-Solo.

Stateless functions for manipulating resource pools:
- Usage dice rolling and degradation
- Cooldown recharge mechanics
- Stress/Momentum management
"""

from __future__ import annotations

import secrets

from pydantic import BaseModel, Field

from src.models.resources import (
    CooldownRechargeResult,
    CooldownTracker,
    EntityResources,
    StressMomentumPool,
    UsageDie,
    UsageDieResult,
)

# =============================================================================
# Usage Die Functions
# =============================================================================


def roll_usage_die(usage_die: UsageDie) -> UsageDieResult:
    """
    Roll a usage die and check for degradation.

    Uses cryptographic randomness for fair rolling.

    Args:
        usage_die: The usage die to roll

    Returns:
        UsageDieResult with roll, degradation status, and new die type
    """
    if usage_die.depleted:
        return UsageDieResult(
            roll=0,
            die_used="depleted",
            degraded=False,
            new_die=None,
            depleted=True,
        )

    # Roll the current die
    die_size = usage_die.die_size()
    roll = secrets.randbelow(die_size) + 1

    # Check for degradation
    degraded = roll in usage_die.degrade_on
    old_die = usage_die.current_die

    if degraded:
        now_depleted = usage_die.degrade()
        new_die = usage_die.current_die
    else:
        now_depleted = False
        new_die = None

    return UsageDieResult(
        roll=roll,
        die_used=old_die,
        degraded=degraded,
        new_die=new_die if degraded else None,
        depleted=now_depleted,
    )


def restore_usage_die(usage_die: UsageDie, steps: int = 1) -> str:
    """
    Restore a usage die by the specified number of steps.

    Args:
        usage_die: The usage die to restore
        steps: Number of die sizes to upgrade

    Returns:
        The new die type
    """
    usage_die.restore(steps)
    return usage_die.current_die


# =============================================================================
# Cooldown Functions
# =============================================================================


def try_recharge_ability(
    tracker: CooldownTracker,
    ability_name: str = "",
) -> CooldownRechargeResult:
    """
    Attempt to recharge a cooldown ability via die roll.

    Only applicable if the tracker has recharge_on set.
    Uses cryptographic randomness for fair rolling.

    Args:
        tracker: The cooldown tracker
        ability_name: Name of the ability (for result)

    Returns:
        CooldownRechargeResult with roll and recharge status
    """
    if tracker.recharge_on is None:
        return CooldownRechargeResult(
            ability_name=ability_name,
            roll=None,
            recharged=False,
            uses_restored=0,
            current_uses=tracker.current_uses,
            max_uses=tracker.max_uses,
        )

    # Don't recharge if already at max
    if tracker.current_uses >= tracker.max_uses:
        return CooldownRechargeResult(
            ability_name=ability_name,
            roll=None,
            recharged=False,
            uses_restored=0,
            current_uses=tracker.current_uses,
            max_uses=tracker.max_uses,
        )

    # Roll the recharge die
    die_size = tracker.recharge_die_size()
    roll = secrets.randbelow(die_size) + 1

    # Check if roll triggers recharge
    recharged = roll in tracker.recharge_on
    uses_restored = 0

    if recharged:
        uses_restored = tracker.restore_use(1)

    return CooldownRechargeResult(
        ability_name=ability_name,
        roll=roll,
        recharged=recharged,
        uses_restored=uses_restored,
        current_uses=tracker.current_uses,
        max_uses=tracker.max_uses,
    )


class RoundStartRechargeResult(BaseModel):
    """Result of processing all round-start recharges."""

    results: list[CooldownRechargeResult] = Field(default_factory=list)
    total_recharged: int = Field(default=0)


def process_round_start_recharges(
    cooldowns: dict[str, CooldownTracker],
) -> RoundStartRechargeResult:
    """
    Process all recharge rolls at the start of a round.

    Args:
        cooldowns: Dict of ability name to CooldownTracker

    Returns:
        RoundStartRechargeResult with all individual results
    """
    results: list[CooldownRechargeResult] = []
    total_recharged = 0

    for name, tracker in cooldowns.items():
        if tracker.recharge_on is not None:
            result = try_recharge_ability(tracker, name)
            results.append(result)
            total_recharged += result.uses_restored

    return RoundStartRechargeResult(
        results=results,
        total_recharged=total_recharged,
    )


# =============================================================================
# Stress/Momentum Functions
# =============================================================================


class StressThresholdResult(BaseModel):
    """Result of checking stress threshold effects."""

    stress_level: int
    penalty: int = Field(description="Penalty to apply (0, -1, or -2)")
    at_breaking_point: bool
    description: str


def check_stress_effects(pool: StressMomentumPool) -> StressThresholdResult:
    """
    Check current stress effects.

    Args:
        pool: The stress/momentum pool

    Returns:
        StressThresholdResult with effects description
    """
    penalty = pool.stress_penalty()
    at_breaking_point = pool.is_at_breaking_point()

    if at_breaking_point:
        description = "Breaking Point! Must rest or suffer exhaustion."
    elif pool.stress >= 7:
        description = "High stress: -2 to all saving throws."
    elif pool.stress >= 4:
        description = "Moderate stress: Disadvantage on concentration checks."
    else:
        description = "Normal stress levels."

    return StressThresholdResult(
        stress_level=pool.stress,
        penalty=penalty,
        at_breaking_point=at_breaking_point,
        description=description,
    )


class MomentumSpendResult(BaseModel):
    """Result of spending momentum."""

    success: bool
    amount_spent: int
    remaining: int
    insufficient: bool = Field(default=False)


def spend_momentum_for_technique(
    pool: StressMomentumPool,
    cost: int,
) -> MomentumSpendResult:
    """
    Attempt to spend momentum for a technique.

    Args:
        pool: The stress/momentum pool
        cost: Momentum cost of the technique

    Returns:
        MomentumSpendResult with success status
    """
    if pool.momentum < cost:
        return MomentumSpendResult(
            success=False,
            amount_spent=0,
            remaining=pool.momentum,
            insufficient=True,
        )

    pool.spend_momentum(cost)
    return MomentumSpendResult(
        success=True,
        amount_spent=cost,
        remaining=pool.momentum,
        insufficient=False,
    )


class StressGainResult(BaseModel):
    """Result of gaining stress from a technique."""

    stress_added: int
    new_stress: int
    at_breaking_point: bool
    triggered_breaking_point: bool = Field(
        default=False, description="True if this stress gain caused breaking point"
    )


def apply_technique_stress(
    pool: StressMomentumPool,
    stress_cost: int,
) -> StressGainResult:
    """
    Apply stress cost from using a technique.

    Args:
        pool: The stress/momentum pool
        stress_cost: Stress added by the technique

    Returns:
        StressGainResult with new stress status
    """
    was_at_breaking_point = pool.is_at_breaking_point()
    result = pool.add_stress(stress_cost)

    return StressGainResult(
        stress_added=result.change,
        new_stress=result.new_stress,
        at_breaking_point=result.at_breaking_point,
        triggered_breaking_point=result.at_breaking_point and not was_at_breaking_point,
    )


# =============================================================================
# Rest Integration
# =============================================================================


class RestResourceResult(BaseModel):
    """Result of applying rest to all resources."""

    rest_type: str
    resources_restored: dict[str, int] = Field(default_factory=dict)
    stress_reduced: int = Field(default=0)
    spell_slots_restored: dict[int, int] = Field(default_factory=dict)
    usage_dice_restored: list[str] = Field(default_factory=list)


def apply_rest_to_resources(
    resources: EntityResources,
    rest_type: str,
) -> RestResourceResult:
    """
    Apply rest effects to all resource pools.

    Args:
        resources: The entity's resource pools
        rest_type: "short" or "long"

    Returns:
        RestResourceResult with detailed restoration info
    """
    result = RestResourceResult(rest_type=rest_type)

    # Use the composite restore method
    restored = resources.restore_on_rest(rest_type)

    # Parse the restored dict into categories
    for key, value in restored.items():
        if key.startswith("cooldown:"):
            name = key.replace("cooldown:", "")
            result.resources_restored[name] = value
        elif key == "stress_reduced":
            result.stress_reduced = value
        elif key.startswith("spell_slot_level_"):
            level = int(key.replace("spell_slot_level_", ""))
            result.spell_slots_restored[level] = value
        elif key.startswith("usage_die:"):
            name = key.replace("usage_die:", "")
            result.usage_dice_restored.append(name)

    return result


def reduce_stress_on_rest(
    pool: StressMomentumPool,
    rest_type: str,
) -> int:
    """
    Reduce stress based on rest type.

    Short rest: Roll 1d4 stress reduction
    Long rest: Reset stress to 0

    Args:
        pool: The stress/momentum pool
        rest_type: "short" or "long"

    Returns:
        Amount of stress reduced
    """
    if rest_type == "long":
        old_stress = pool.stress
        pool.stress = 0
        return old_stress
    elif rest_type == "short":
        # Roll 1d4 for stress reduction
        reduction = secrets.randbelow(4) + 1
        return pool.reduce_stress(reduction)

    return 0
