"""
Universal Ability Object (UAO) Models for TTA-Solo.

Provides a unified framework for abilities across magic, tech, and martial sources.
The "Singularity Engine" - a single model that represents any ability in the game.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

# =============================================================================
# Source Classifications
# =============================================================================


class AbilitySource(StrEnum):
    """Primary source of an ability's power."""

    MAGIC = "magic"
    TECH = "tech"
    MARTIAL = "martial"


class MagicSubtype(StrEnum):
    """Subtypes for magic abilities."""

    ARCANE = "arcane"  # Learned/studied magic (wizards)
    DIVINE = "divine"  # Granted by deities (clerics, paladins)
    PRIMAL = "primal"  # Nature-based (druids, rangers)
    PSIONIC = "psionic"  # Mind powers (psychics)


class TechSubtype(StrEnum):
    """Subtypes for tech abilities."""

    BIOTECH = "biotech"  # Organic enhancements
    CYBERTECH = "cybertech"  # Mechanical/electronic implants
    NANOTECH = "nanotech"  # Nanomachine-based abilities


class MartialSubtype(StrEnum):
    """Subtypes for martial abilities."""

    KI = "ki"  # Internal energy manipulation
    STANCE = "stance"  # Combat positioning/forms
    MANEUVER = "maneuver"  # Tactical combat techniques


# =============================================================================
# Resource Mechanisms
# =============================================================================


class MechanismType(StrEnum):
    """How an ability's usage is gated/limited."""

    SLOTS = "slots"  # Traditional spell slots (1st-9th level)
    COOLDOWN = "cooldown"  # Per-encounter uses with recharge chance
    USAGE_DIE = "usage_die"  # Degrading die (d12→d10→...→depleted)
    STRESS = "stress"  # Risk accumulation (high = bad)
    MOMENTUM = "momentum"  # Reward accumulation (high = good)
    FREE = "free"  # No cost (cantrips, at-will)


# =============================================================================
# Targeting
# =============================================================================


class TargetingType(StrEnum):
    """How an ability selects its targets."""

    SELF = "self"
    SINGLE = "single"
    MULTIPLE = "multiple"
    AREA_SPHERE = "area_sphere"
    AREA_CONE = "area_cone"
    AREA_LINE = "area_line"
    AREA_CUBE = "area_cube"


class Targeting(BaseModel):
    """Targeting parameters for an ability."""

    type: TargetingType = TargetingType.SELF
    range_ft: int = Field(default=0, ge=0, description="Range in feet (0 = self/touch)")
    area_size_ft: int | None = Field(
        default=None, ge=0, description="Radius/length depending on type"
    )
    max_targets: int | None = Field(
        default=None, ge=1, description="Maximum targets for MULTIPLE type"
    )

    @model_validator(mode="after")
    def validate_area_targeting(self) -> Targeting:
        """Ensure area types have area_size_ft specified."""
        area_types = {
            TargetingType.AREA_SPHERE,
            TargetingType.AREA_CONE,
            TargetingType.AREA_LINE,
            TargetingType.AREA_CUBE,
        }
        if self.type in area_types and self.area_size_ft is None:
            raise ValueError(f"area_size_ft required for targeting type {self.type.value}")
        return self


# =============================================================================
# Effect Components
# =============================================================================


class DamageEffect(BaseModel):
    """Damage component of an ability."""

    dice: str = Field(description="Dice notation, e.g., '2d6', '3d8+4'")
    damage_type: str = Field(description="fire, cold, slashing, psychic, etc.")
    save_ability: str | None = Field(
        default=None, description="Ability for save (dex, con, wis, etc.)"
    )
    save_dc_stat: str | None = Field(
        default=None, description="Caster's stat used for DC calculation"
    )
    save_for_half: bool = Field(default=False, description="Take half damage on successful save")


class HealingEffect(BaseModel):
    """Healing component of an ability."""

    dice: str | None = Field(default=None, description="Healing dice, e.g., '2d8+3'")
    flat_amount: int = Field(default=0, ge=0, description="Flat healing amount")
    temp_hp: bool = Field(default=False, description="Grant temporary HP instead of healing")

    @model_validator(mode="after")
    def validate_has_healing(self) -> HealingEffect:
        """Ensure at least one healing source is specified."""
        if self.dice is None and self.flat_amount == 0:
            raise ValueError("HealingEffect must have either dice or flat_amount")
        return self


class ConditionEffect(BaseModel):
    """Condition application component of an ability."""

    condition: str = Field(description="Condition name: frightened, prone, stunned, etc.")
    duration_type: str = Field(
        default="rounds", description="Duration type: rounds, minutes, until_save, permanent"
    )
    duration_value: int | None = Field(
        default=None, ge=1, description="Duration amount (for rounds/minutes)"
    )
    save_ability: str | None = Field(default=None, description="Ability for save to end early")
    save_dc_stat: str | None = Field(
        default=None, description="Caster's stat used for DC calculation"
    )

    @model_validator(mode="after")
    def validate_duration(self) -> ConditionEffect:
        """Ensure duration_value is set for timed durations."""
        if self.duration_type in ("rounds", "minutes") and self.duration_value is None:
            raise ValueError(f"duration_value required for duration_type '{self.duration_type}'")
        return self


class StatModifierEffect(BaseModel):
    """Temporary stat modification component of an ability."""

    stat: str = Field(description="Stat to modify: ac, speed, str, attack_rolls, etc.")
    modifier: int = Field(description="Modifier value (+2, -4, etc.)")
    duration_type: str = Field(
        default="rounds", description="Duration type: rounds, minutes, concentration"
    )
    duration_value: int | None = Field(
        default=None, ge=1, description="Duration amount (for rounds/minutes)"
    )


# =============================================================================
# Core Ability Model
# =============================================================================


class Ability(BaseModel):
    """
    Universal Ability Object - the core model for any ability.

    Represents spells, tech abilities, martial techniques, and everything in between.
    """

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="")

    # Source classification
    source: AbilitySource
    subtype: str | None = Field(
        default=None, description="Source-specific subtype (arcane, cybertech, ki, etc.)"
    )

    # Resource mechanism
    mechanism: MechanismType = MechanismType.FREE
    mechanism_details: dict[str, Any] = Field(
        default_factory=dict,
        description="Mechanism-specific parameters (level, max_uses, die_type, etc.)",
    )

    # Effects (at least one should be specified for meaningful abilities)
    damage: DamageEffect | None = None
    healing: HealingEffect | None = None
    conditions: list[ConditionEffect] = Field(default_factory=list)
    stat_modifiers: list[StatModifierEffect] = Field(default_factory=list)

    # Targeting
    targeting: Targeting = Field(default_factory=Targeting)

    # Action economy
    action_cost: str = Field(default="action", description="action, bonus, reaction, free, special")
    requires_concentration: bool = False

    # Metadata
    tags: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(
        default_factory=list, description="Required conditions to use this ability"
    )

    @model_validator(mode="after")
    def validate_mechanism_details(self) -> Ability:
        """Ensure mechanism_details match the mechanism type."""
        if self.mechanism == MechanismType.SLOTS:
            if "level" not in self.mechanism_details:
                raise ValueError("mechanism_details must include 'level' for SLOTS mechanism")
            level = self.mechanism_details["level"]
            if not isinstance(level, int) or level < 0 or level > 9:
                raise ValueError("Spell level must be an integer 0-9")

        elif self.mechanism == MechanismType.COOLDOWN:
            if "max_uses" not in self.mechanism_details:
                raise ValueError("mechanism_details must include 'max_uses' for COOLDOWN mechanism")

        elif self.mechanism == MechanismType.USAGE_DIE:
            if "die_type" not in self.mechanism_details:
                raise ValueError(
                    "mechanism_details must include 'die_type' for USAGE_DIE mechanism"
                )

        elif self.mechanism == MechanismType.STRESS:
            if "stress_cost" not in self.mechanism_details:
                raise ValueError(
                    "mechanism_details must include 'stress_cost' for STRESS mechanism"
                )

        elif self.mechanism == MechanismType.MOMENTUM:
            if "momentum_cost" not in self.mechanism_details:
                raise ValueError(
                    "mechanism_details must include 'momentum_cost' for MOMENTUM mechanism"
                )

        return self

    def has_effects(self) -> bool:
        """Check if this ability has any effects defined."""
        return bool(
            self.damage is not None
            or self.healing is not None
            or self.conditions
            or self.stat_modifiers
        )

    def is_spell(self) -> bool:
        """Check if this is a magic spell."""
        return self.source == AbilitySource.MAGIC

    def is_cantrip(self) -> bool:
        """Check if this is a cantrip (level 0 spell)."""
        return self.source == AbilitySource.MAGIC and self.mechanism == MechanismType.FREE

    def spell_level(self) -> int | None:
        """Get spell level if this is a spell, otherwise None."""
        if self.source != AbilitySource.MAGIC:
            return None
        if self.mechanism == MechanismType.FREE:
            return 0  # Cantrip
        return self.mechanism_details.get("level")

    def is_area_effect(self) -> bool:
        """Check if this ability affects an area."""
        return self.targeting.type in {
            TargetingType.AREA_SPHERE,
            TargetingType.AREA_CONE,
            TargetingType.AREA_LINE,
            TargetingType.AREA_CUBE,
        }


# =============================================================================
# Factory Functions
# =============================================================================


def create_spell(
    name: str,
    level: int,
    description: str = "",
    subtype: MagicSubtype = MagicSubtype.ARCANE,
    damage: DamageEffect | None = None,
    healing: HealingEffect | None = None,
    conditions: list[ConditionEffect] | None = None,
    stat_modifiers: list[StatModifierEffect] | None = None,
    targeting: Targeting | None = None,
    action_cost: str = "action",
    requires_concentration: bool = False,
    tags: list[str] | None = None,
) -> Ability:
    """
    Factory function to create a magic spell.

    Args:
        name: Spell name
        level: Spell level (0 = cantrip, 1-9 for leveled spells)
        description: Spell description
        subtype: Magic subtype (arcane, divine, primal, psionic)
        damage: Damage effect if spell deals damage
        healing: Healing effect if spell heals
        conditions: Conditions applied by the spell
        stat_modifiers: Stat modifications applied by the spell
        targeting: Targeting parameters
        action_cost: Action required to cast
        requires_concentration: Whether spell requires concentration
        tags: Additional tags

    Returns:
        Configured Ability instance
    """
    # Cantrips are free, leveled spells use slots
    mechanism = MechanismType.FREE if level == 0 else MechanismType.SLOTS
    mechanism_details = {} if level == 0 else {"level": level}

    return Ability(
        name=name,
        description=description,
        source=AbilitySource.MAGIC,
        subtype=subtype.value,
        mechanism=mechanism,
        mechanism_details=mechanism_details,
        damage=damage,
        healing=healing,
        conditions=conditions or [],
        stat_modifiers=stat_modifiers or [],
        targeting=targeting or Targeting(),
        action_cost=action_cost,
        requires_concentration=requires_concentration,
        tags=tags or ["spell"],
    )


def create_tech_ability(
    name: str,
    description: str = "",
    subtype: TechSubtype = TechSubtype.CYBERTECH,
    max_uses: int = 1,
    recharge_on_rest: str | None = "short",
    recharge_on: list[int] | None = None,
    damage: DamageEffect | None = None,
    healing: HealingEffect | None = None,
    conditions: list[ConditionEffect] | None = None,
    stat_modifiers: list[StatModifierEffect] | None = None,
    targeting: Targeting | None = None,
    action_cost: str = "action",
    tags: list[str] | None = None,
) -> Ability:
    """
    Factory function to create a tech ability.

    Args:
        name: Ability name
        description: Ability description
        subtype: Tech subtype (biotech, cybertech, nanotech)
        max_uses: Maximum uses before recharge needed
        recharge_on_rest: Rest type that restores uses ("short" or "long")
        recharge_on: Die results that trigger recharge (e.g., [5, 6] for d6)
        damage: Damage effect if ability deals damage
        healing: Healing effect if ability heals
        conditions: Conditions applied by the ability
        stat_modifiers: Stat modifications applied
        targeting: Targeting parameters
        action_cost: Action required to use
        tags: Additional tags

    Returns:
        Configured Ability instance
    """
    mechanism_details: dict[str, Any] = {"max_uses": max_uses}
    if recharge_on_rest:
        mechanism_details["recharge_on_rest"] = recharge_on_rest
    if recharge_on:
        mechanism_details["recharge_on"] = recharge_on

    return Ability(
        name=name,
        description=description,
        source=AbilitySource.TECH,
        subtype=subtype.value,
        mechanism=MechanismType.COOLDOWN,
        mechanism_details=mechanism_details,
        damage=damage,
        healing=healing,
        conditions=conditions or [],
        stat_modifiers=stat_modifiers or [],
        targeting=targeting or Targeting(),
        action_cost=action_cost,
        requires_concentration=False,
        tags=tags or ["tech"],
    )


def create_martial_technique(
    name: str,
    description: str = "",
    subtype: MartialSubtype = MartialSubtype.MANEUVER,
    stress_cost: int = 0,
    momentum_cost: int = 0,
    damage: DamageEffect | None = None,
    healing: HealingEffect | None = None,
    conditions: list[ConditionEffect] | None = None,
    stat_modifiers: list[StatModifierEffect] | None = None,
    targeting: Targeting | None = None,
    action_cost: str = "action",
    tags: list[str] | None = None,
) -> Ability:
    """
    Factory function to create a martial technique.

    Args:
        name: Technique name
        description: Technique description
        subtype: Martial subtype (ki, stance, maneuver)
        stress_cost: Stress added when using this technique
        momentum_cost: Momentum spent to use this technique
        damage: Damage effect if technique deals damage
        healing: Healing effect if technique heals
        conditions: Conditions applied by the technique
        stat_modifiers: Stat modifications applied
        targeting: Targeting parameters
        action_cost: Action required to use
        tags: Additional tags

    Returns:
        Configured Ability instance
    """
    # Determine mechanism based on costs
    if momentum_cost > 0:
        mechanism = MechanismType.MOMENTUM
        mechanism_details: dict[str, Any] = {"momentum_cost": momentum_cost}
        if stress_cost > 0:
            mechanism_details["stress_cost"] = stress_cost
    elif stress_cost > 0:
        mechanism = MechanismType.STRESS
        mechanism_details = {"stress_cost": stress_cost}
    else:
        mechanism = MechanismType.FREE
        mechanism_details = {}

    return Ability(
        name=name,
        description=description,
        source=AbilitySource.MARTIAL,
        subtype=subtype.value,
        mechanism=mechanism,
        mechanism_details=mechanism_details,
        damage=damage,
        healing=healing,
        conditions=conditions or [],
        stat_modifiers=stat_modifiers or [],
        targeting=targeting or Targeting(),
        action_cost=action_cost,
        requires_concentration=False,
        tags=tags or ["martial", "technique"],
    )
