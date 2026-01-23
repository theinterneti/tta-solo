"""
Solo Combat Balance Skills for TTA-Solo.

Implements solo play balance mechanics:
- Fray Die (automatic damage to weaker enemies)
- Damage Thresholds (simplified damage tracking)
- Defy Death (death-defying saves)
- Action Economy Boost
"""

from __future__ import annotations

import secrets
from uuid import UUID

from pydantic import BaseModel, Field

from src.skills.dice import roll_dice

# =============================================================================
# Configuration Models
# =============================================================================


class FrayDieConfig(BaseModel):
    """Configuration for the Fray Die mechanic."""

    die: str = Field(default="d6", description="Base fray die")
    affects_mooks_only: bool = Field(
        default=True, description="Only affects enemies with HD <= character level"
    )
    level_scaling: bool = Field(default=True, description="Die scales with level")
    can_split: bool = Field(default=True, description="Can split damage among multiple targets")


class DefyDeathConfig(BaseModel):
    """Configuration for Defy Death mechanic."""

    base_dc: int = Field(default=10, ge=1, description="Base DC for the save")
    dc_increase_per_use: int = Field(default=5, ge=0, description="DC increase for each use")
    grants_exhaustion: bool = Field(default=True, description="Whether success grants exhaustion")
    max_uses_per_day: int = Field(default=3, ge=1, description="Maximum uses before long rest")


class DamageThresholdConfig(BaseModel):
    """Configuration for damage threshold system."""

    light_threshold: int = Field(default=1, ge=0, description="Minimum damage for light hit")
    medium_threshold: int = Field(default=2, ge=1, description="Damage for medium hit")
    heavy_threshold: int = Field(default=4, ge=2, description="Damage for heavy hit")
    devastating_threshold: int = Field(default=6, ge=3, description="Damage for devastating hit")


class SoloCombatConfig(BaseModel):
    """Master configuration for all solo combat mechanics."""

    # Fray Die
    use_fray_die: bool = Field(default=True, description="Enable Fray Die mechanic")
    fray_config: FrayDieConfig = Field(default_factory=FrayDieConfig)

    # Damage Thresholds
    use_damage_thresholds: bool = Field(
        default=False, description="Use simplified damage thresholds"
    )
    threshold_config: DamageThresholdConfig = Field(default_factory=DamageThresholdConfig)

    # Defy Death
    use_defy_death: bool = Field(default=True, description="Enable Defy Death saves")
    defy_death_config: DefyDeathConfig = Field(default_factory=DefyDeathConfig)

    # Action Economy
    heroic_action_enabled: bool = Field(default=True, description="Allow Heroic Action each round")
    heroic_action_cost: str = Field(
        default="momentum", description="Cost type: momentum, stress, or free"
    )
    heroic_action_amount: int = Field(default=1, description="Amount of resource spent")
    extra_reactions: int = Field(default=1, description="Additional reactions per round")

    # Momentum
    combat_momentum_gain: int = Field(
        default=1, ge=0, description="Momentum gained per round in combat"
    )


# =============================================================================
# Result Models
# =============================================================================


class FrayDieResult(BaseModel):
    """Result of rolling the Fray Die."""

    damage: int = Field(description="Total fray damage rolled")
    die_used: str = Field(description="Die that was rolled")
    targets_hit: list[UUID] = Field(
        default_factory=list, description="Entities that took fray damage"
    )
    damage_per_target: dict[str, int] = Field(
        default_factory=dict, description="UUID str -> damage dealt"
    )
    overflow: int = Field(default=0, description="Damage that couldn't be applied")


class DamageThresholdResult(BaseModel):
    """Result of calculating threshold damage."""

    threshold_level: int = Field(description="Damage threshold achieved (0, 1, 2, 4, 6)")
    description: str = Field(description="Hit description")
    effect_on_mook: str = Field(description="What happens to mook-level enemy")
    effect_on_elite: str = Field(description="What happens to elite enemy")
    is_kill_threshold: bool = Field(default=False, description="Would kill mook-level enemy")


class DefyDeathResult(BaseModel):
    """Result of a Defy Death save."""

    survived: bool = Field(description="Whether character survived")
    roll: int = Field(description="The d20 roll")
    modifier: int = Field(description="CON modifier applied")
    total: int = Field(description="Total result")
    dc: int = Field(description="DC that was required")
    exhaustion_gained: int = Field(default=0, description="Exhaustion levels gained")
    uses_remaining: int = Field(description="Defy Death uses left today")
    is_nat_20: bool = Field(default=False, description="Natural 20 on the roll")
    is_nat_1: bool = Field(default=False, description="Natural 1 on the roll")


class HeroicActionResult(BaseModel):
    """Result of using a Heroic Action."""

    success: bool = Field(description="Whether action was taken")
    cost_type: str = Field(description="What resource was spent")
    cost_amount: int = Field(description="Amount spent")
    reason: str = Field(default="", description="Reason if failed")


class SoloRoundStartResult(BaseModel):
    """Result of processing solo round start."""

    fray_result: FrayDieResult | None = None
    momentum_gained: int = Field(default=0, description="Momentum gained from combat flow")
    stress_reduced: int = Field(default=0, description="Stress reduced if applicable")
    message: str = Field(default="", description="Summary message")


# =============================================================================
# Fray Die Functions
# =============================================================================


def get_fray_die_for_level(level: int, config: FrayDieConfig | None = None) -> str:
    """
    Get the appropriate fray die based on character level.

    Args:
        level: Character level
        config: Fray die configuration

    Returns:
        Die string (e.g., "1d6", "1d8")
    """
    config = config or FrayDieConfig()

    if not config.level_scaling:
        # Ensure proper notation
        die = config.die
        if not die.startswith("1"):
            die = "1" + die
        return die

    if level >= 13:
        return "1d12"
    elif level >= 9:
        return "1d10"
    elif level >= 5:
        return "1d8"
    else:
        return "1d6"


def roll_fray_die(
    actor_level: int,
    enemies: list[tuple[UUID, int]],  # (entity_id, hit_dice)
    config: FrayDieConfig | None = None,
) -> FrayDieResult:
    """
    Roll the Fray Die and apply damage to valid targets.

    Args:
        actor_level: The solo character's level
        enemies: List of (enemy_id, enemy_hit_dice) tuples
        config: Fray die configuration

    Returns:
        FrayDieResult with damage distribution
    """
    config = config or FrayDieConfig()

    # Get appropriate die
    die = get_fray_die_for_level(actor_level, config)

    # Roll the fray die
    result = roll_dice(die)
    total_damage = result.total

    # Filter valid targets (mooks only if configured)
    if config.affects_mooks_only:
        valid_targets = [(eid, hd) for eid, hd in enemies if hd <= actor_level]
    else:
        valid_targets = enemies

    # Distribute damage
    targets_hit: list[UUID] = []
    damage_per_target: dict[str, int] = {}
    remaining_damage = total_damage

    if config.can_split:
        # Distribute among targets, prioritizing lowest HD
        sorted_targets = sorted(valid_targets, key=lambda x: x[1])
        for entity_id, hit_dice in sorted_targets:
            if remaining_damage <= 0:
                break
            # Apply up to target's HD in damage
            damage_to_apply = min(remaining_damage, hit_dice)
            damage_per_target[str(entity_id)] = damage_to_apply
            targets_hit.append(entity_id)
            remaining_damage -= damage_to_apply
    elif valid_targets:
        # Apply all to first valid target
        entity_id, _ = valid_targets[0]
        damage_per_target[str(entity_id)] = total_damage
        targets_hit.append(entity_id)
        remaining_damage = 0

    return FrayDieResult(
        damage=total_damage,
        die_used=die,
        targets_hit=targets_hit,
        damage_per_target=damage_per_target,
        overflow=remaining_damage,
    )


# =============================================================================
# Damage Threshold Functions
# =============================================================================


def calculate_threshold_damage(
    attack_roll: int,
    target_ac: int,
    is_critical: bool = False,
    weapon_weight: str = "medium",
    config: DamageThresholdConfig | None = None,
) -> DamageThresholdResult:
    """
    Calculate simplified threshold damage from an attack.

    Args:
        attack_roll: Total attack roll
        target_ac: Target's AC
        is_critical: Whether this was a critical hit
        weapon_weight: "light", "medium", or "heavy"
        config: Threshold configuration

    Returns:
        DamageThresholdResult with threshold level and effects
    """
    config = config or DamageThresholdConfig()

    # Check if hit
    margin = attack_roll - target_ac

    if margin < 0 and not is_critical:
        return DamageThresholdResult(
            threshold_level=0,
            description="Miss",
            effect_on_mook="No effect",
            effect_on_elite="No effect",
            is_kill_threshold=False,
        )

    # Calculate base threshold
    if margin >= 10:
        base_threshold = config.heavy_threshold
    elif margin >= 5:
        base_threshold = config.medium_threshold
    else:
        base_threshold = config.light_threshold

    # Apply modifiers
    if is_critical:
        base_threshold += 2

    if weapon_weight == "heavy":
        base_threshold += 1
    elif weapon_weight == "light":
        base_threshold = max(1, base_threshold - 1)

    # Determine effects
    if base_threshold >= config.devastating_threshold:
        description = "Devastating hit"
        effect_on_mook = "Instant kill, overflow damage to nearby"
        effect_on_elite = "Critical wound, major debuff"
        is_kill = True
    elif base_threshold >= config.heavy_threshold:
        description = "Heavy hit"
        effect_on_mook = "Instant kill"
        effect_on_elite = "Serious wound"
        is_kill = True
    elif base_threshold >= config.medium_threshold:
        description = "Solid hit"
        effect_on_mook = "Kill (1-2 HD), wound (3+ HD)"
        effect_on_elite = "Wound"
        is_kill = False
    else:
        description = "Light hit"
        effect_on_mook = "1 HP damage"
        effect_on_elite = "Minor wound"
        is_kill = False

    return DamageThresholdResult(
        threshold_level=base_threshold,
        description=description,
        effect_on_mook=effect_on_mook,
        effect_on_elite=effect_on_elite,
        is_kill_threshold=is_kill,
    )


# =============================================================================
# Defy Death Functions
# =============================================================================


def defy_death(
    con_modifier: int,
    damage_taken_this_round: int,
    uses_today: int,
    config: DefyDeathConfig | None = None,
) -> DefyDeathResult:
    """
    Attempt a Defy Death save when reduced to 0 HP.

    Args:
        con_modifier: Character's Constitution modifier
        damage_taken_this_round: Total damage taken this round
        uses_today: How many times Defy Death has been used today
        config: Defy Death configuration

    Returns:
        DefyDeathResult with survival status
    """
    config = config or DefyDeathConfig()

    # Check if uses remaining
    uses_remaining = max(0, config.max_uses_per_day - uses_today)

    if uses_remaining <= 0:
        return DefyDeathResult(
            survived=False,
            roll=0,
            modifier=con_modifier,
            total=0,
            dc=0,
            exhaustion_gained=0,
            uses_remaining=0,
        )

    # Calculate DC
    dc = config.base_dc + damage_taken_this_round + (uses_today * config.dc_increase_per_use)

    # Roll CON save
    roll = secrets.randbelow(20) + 1
    total = roll + con_modifier

    is_nat_20 = roll == 20
    is_nat_1 = roll == 1

    # Natural 20 always succeeds, natural 1 always fails
    if is_nat_20:
        survived = True
    elif is_nat_1:
        survived = False
    else:
        survived = total >= dc

    # Calculate exhaustion
    exhaustion_gained = 1 if survived and config.grants_exhaustion else 0

    return DefyDeathResult(
        survived=survived,
        roll=roll,
        modifier=con_modifier,
        total=total,
        dc=dc,
        exhaustion_gained=exhaustion_gained,
        uses_remaining=uses_remaining - 1 if survived else uses_remaining,
        is_nat_20=is_nat_20,
        is_nat_1=is_nat_1,
    )


# =============================================================================
# Action Economy Functions
# =============================================================================


def use_heroic_action(
    current_momentum: int,
    current_stress: int,
    stress_max: int,
    config: SoloCombatConfig | None = None,
) -> tuple[HeroicActionResult, int, int]:
    """
    Attempt to use a Heroic Action.

    Args:
        current_momentum: Current momentum points
        current_stress: Current stress level
        stress_max: Maximum stress
        config: Solo combat configuration

    Returns:
        Tuple of (result, new_momentum, new_stress)
    """
    config = config or SoloCombatConfig()

    if not config.heroic_action_enabled:
        return (
            HeroicActionResult(
                success=False,
                cost_type="none",
                cost_amount=0,
                reason="Heroic Action is disabled",
            ),
            current_momentum,
            current_stress,
        )

    new_momentum = current_momentum
    new_stress = current_stress

    if config.heroic_action_cost == "momentum":
        if current_momentum < config.heroic_action_amount:
            return (
                HeroicActionResult(
                    success=False,
                    cost_type="momentum",
                    cost_amount=config.heroic_action_amount,
                    reason=f"Insufficient momentum ({current_momentum}/{config.heroic_action_amount})",
                ),
                current_momentum,
                current_stress,
            )
        new_momentum = current_momentum - config.heroic_action_amount

    elif config.heroic_action_cost == "stress":
        # Roll 1d4 for stress cost
        stress_cost = secrets.randbelow(4) + 1
        if current_stress + stress_cost > stress_max:
            return (
                HeroicActionResult(
                    success=False,
                    cost_type="stress",
                    cost_amount=stress_cost,
                    reason=f"Would exceed stress maximum ({current_stress + stress_cost}/{stress_max})",
                ),
                current_momentum,
                current_stress,
            )
        new_stress = current_stress + stress_cost

    # "free" costs nothing

    return (
        HeroicActionResult(
            success=True,
            cost_type=config.heroic_action_cost,
            cost_amount=config.heroic_action_amount
            if config.heroic_action_cost == "momentum"
            else 0,
        ),
        new_momentum,
        new_stress,
    )


# =============================================================================
# Round Start Function
# =============================================================================


def resolve_solo_round_start(
    actor_level: int,
    enemies: list[tuple[UUID, int]],
    current_momentum: int,
    momentum_max: int,
    config: SoloCombatConfig | None = None,
) -> tuple[SoloRoundStartResult, int]:
    """
    Process the start of a round for a solo character.

    Args:
        actor_level: The solo character's level
        enemies: List of (enemy_id, enemy_hit_dice) tuples
        current_momentum: Current momentum
        momentum_max: Maximum momentum
        config: Solo combat configuration

    Returns:
        Tuple of (result, new_momentum)
    """
    config = config or SoloCombatConfig()

    result = SoloRoundStartResult()
    new_momentum = current_momentum

    # Gain combat momentum
    if config.combat_momentum_gain > 0:
        momentum_gained = min(config.combat_momentum_gain, momentum_max - current_momentum)
        result.momentum_gained = momentum_gained
        new_momentum += momentum_gained

    # Roll Fray Die
    if config.use_fray_die and enemies:
        fray_result = roll_fray_die(actor_level, enemies, config.fray_config)
        result.fray_result = fray_result

    # Build message
    parts = []
    if result.momentum_gained > 0:
        parts.append(f"Gained {result.momentum_gained} momentum")
    if result.fray_result and result.fray_result.damage > 0:
        parts.append(f"Fray die: {result.fray_result.damage} damage")

    result.message = ". ".join(parts) + "." if parts else "Round started."

    return result, new_momentum
