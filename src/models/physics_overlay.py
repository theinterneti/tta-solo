"""
Physics Overlays for universe-specific rule modifications.

Physics Overlays allow abilities to behave differently based on the universe's rules.
A fireball spell might work normally in a high fantasy world but be impossible in a
hard sci-fi setting, while tech abilities might be enhanced in a cyberpunk world.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from src.models.ability import AbilitySource


class SourceModifier(str, Enum):
    """How a physics overlay modifies an ability source."""

    ENHANCED = "enhanced"  # +1 die to damage/healing, advantage on ability checks
    NORMAL = "normal"  # No modification
    RESTRICTED = "restricted"  # -2 to save DCs, disadvantage on ability checks
    FORBIDDEN = "forbidden"  # Ability cannot be used at all


class ConditionModifier(BaseModel):
    """Modifies how a specific condition behaves in this universe."""

    duration_multiplier: float = 1.0  # Multiply duration by this
    save_dc_modifier: int = 0  # Add/subtract from save DCs
    effect_intensity: float = 1.0  # Modify condition severity


class PhysicsOverlay(BaseModel):
    """Universe-specific rules that modify ability mechanics."""

    name: str
    description: str

    # Source modifiers - how each ability source is affected
    source_modifiers: dict[AbilitySource, SourceModifier] = Field(default_factory=dict)

    # Global multipliers
    healing_multiplier: float = 1.0  # Affects all healing (0.5x to 2x)
    stress_multiplier: float = 1.0  # Affects stress gain (0.5x to 2x)

    # Condition-specific modifiers
    condition_modifiers: dict[str, ConditionModifier] = Field(default_factory=dict)

    # Special flags
    magic_side_effects: bool = False  # Magic has chance of wild magic effects
    tech_crit_bonus: bool = False  # Tech abilities have expanded crit range
    resource_scarcity: bool = False  # Resources are harder to find/use
    allow_legendary_actions: bool = False  # Characters can take legendary actions

    def get_source_modifier(self, source: AbilitySource) -> SourceModifier:
        """Get the modifier for a given ability source."""
        return self.source_modifiers.get(source, SourceModifier.NORMAL)

    def get_condition_modifier(self, condition_type: str) -> ConditionModifier:
        """Get the modifier for a given condition type."""
        return self.condition_modifiers.get(condition_type, ConditionModifier())

    def is_source_forbidden(self, source: AbilitySource) -> bool:
        """Check if an ability source is forbidden in this universe."""
        return self.get_source_modifier(source) == SourceModifier.FORBIDDEN

    def is_source_enhanced(self, source: AbilitySource) -> bool:
        """Check if an ability source is enhanced in this universe."""
        return self.get_source_modifier(source) == SourceModifier.ENHANCED

    def is_source_restricted(self, source: AbilitySource) -> bool:
        """Check if an ability source is restricted in this universe."""
        return self.get_source_modifier(source) == SourceModifier.RESTRICTED


# =============================================================================
# Pre-built Overlays
# =============================================================================

HIGH_FANTASY_OVERLAY = PhysicsOverlay(
    name="High Fantasy",
    description="A world where magic flows freely",
    source_modifiers={
        AbilitySource.MAGIC: SourceModifier.ENHANCED,
        AbilitySource.TECH: SourceModifier.NORMAL,
        AbilitySource.MARTIAL: SourceModifier.NORMAL,
    },
    healing_multiplier=1.25,
    stress_multiplier=0.75,
    condition_modifiers={
        "frightened": ConditionModifier(duration_multiplier=0.75),
    },
)

LOW_MAGIC_OVERLAY = PhysicsOverlay(
    name="Low Magic",
    description="Magic is rare and carries risk",
    source_modifiers={
        AbilitySource.MAGIC: SourceModifier.RESTRICTED,
        AbilitySource.TECH: SourceModifier.NORMAL,
        AbilitySource.MARTIAL: SourceModifier.ENHANCED,
    },
    healing_multiplier=0.75,
    stress_multiplier=1.25,
    magic_side_effects=True,
)

CYBERPUNK_OVERLAY = PhysicsOverlay(
    name="Cyberpunk",
    description="Chrome and neon, tech is king",
    source_modifiers={
        AbilitySource.MAGIC: SourceModifier.FORBIDDEN,
        AbilitySource.TECH: SourceModifier.ENHANCED,
        AbilitySource.MARTIAL: SourceModifier.NORMAL,
    },
    stress_multiplier=1.0,
    tech_crit_bonus=True,
    condition_modifiers={
        "system_shock": ConditionModifier(duration_multiplier=1.5),
    },
)

HORROR_OVERLAY = PhysicsOverlay(
    name="Horror",
    description="Darkness and dread permeate everything",
    source_modifiers={
        AbilitySource.MAGIC: SourceModifier.NORMAL,
        AbilitySource.TECH: SourceModifier.RESTRICTED,
        AbilitySource.MARTIAL: SourceModifier.NORMAL,
    },
    healing_multiplier=0.5,
    stress_multiplier=1.5,
    condition_modifiers={
        "frightened": ConditionModifier(duration_multiplier=2.0, save_dc_modifier=2),
        "charmed": ConditionModifier(duration_multiplier=1.5),
    },
)

MYTHIC_OVERLAY = PhysicsOverlay(
    name="Mythic",
    description="Where legends walk and gods intervene",
    source_modifiers={
        AbilitySource.MAGIC: SourceModifier.ENHANCED,
        AbilitySource.TECH: SourceModifier.RESTRICTED,
        AbilitySource.MARTIAL: SourceModifier.ENHANCED,
    },
    healing_multiplier=1.5,
    stress_multiplier=0.5,
    allow_legendary_actions=True,
)

POST_APOCALYPTIC_OVERLAY = PhysicsOverlay(
    name="Post-Apocalyptic",
    description="Survival in the wasteland",
    source_modifiers={
        AbilitySource.MAGIC: SourceModifier.RESTRICTED,
        AbilitySource.TECH: SourceModifier.RESTRICTED,
        AbilitySource.MARTIAL: SourceModifier.ENHANCED,
    },
    healing_multiplier=0.75,
    stress_multiplier=1.25,
    resource_scarcity=True,
)

# Neutral overlay with no modifications
NEUTRAL_OVERLAY = PhysicsOverlay(
    name="Neutral",
    description="Standard physics with no special rules",
    source_modifiers={
        AbilitySource.MAGIC: SourceModifier.NORMAL,
        AbilitySource.TECH: SourceModifier.NORMAL,
        AbilitySource.MARTIAL: SourceModifier.NORMAL,
    },
)


# =============================================================================
# Overlay Registry
# =============================================================================

OVERLAY_REGISTRY: dict[str, PhysicsOverlay] = {
    "high_fantasy": HIGH_FANTASY_OVERLAY,
    "low_magic": LOW_MAGIC_OVERLAY,
    "cyberpunk": CYBERPUNK_OVERLAY,
    "horror": HORROR_OVERLAY,
    "mythic": MYTHIC_OVERLAY,
    "post_apocalyptic": POST_APOCALYPTIC_OVERLAY,
    "neutral": NEUTRAL_OVERLAY,
}


def get_overlay(name: str) -> PhysicsOverlay | None:
    """Get a physics overlay by name."""
    return OVERLAY_REGISTRY.get(name.lower().replace(" ", "_"))


def list_overlays() -> list[str]:
    """List all available overlay names."""
    return list(OVERLAY_REGISTRY.keys())


# =============================================================================
# Application Functions
# =============================================================================


def apply_healing_overlay(amount: int, overlay: PhysicsOverlay | None) -> int:
    """Apply overlay modification to healing amount."""
    if overlay is None:
        return amount
    return int(amount * overlay.healing_multiplier)


def apply_stress_overlay(amount: int, overlay: PhysicsOverlay | None) -> int:
    """Apply overlay modification to stress gain."""
    if overlay is None:
        return amount
    return int(amount * overlay.stress_multiplier)


def apply_condition_duration_overlay(
    condition_type: str,
    base_duration: int,
    overlay: PhysicsOverlay | None,
) -> int:
    """Apply overlay modification to condition duration."""
    if overlay is None:
        return base_duration

    modifier = overlay.get_condition_modifier(condition_type)
    return int(base_duration * modifier.duration_multiplier)


def apply_condition_dc_overlay(
    condition_type: str,
    base_dc: int,
    overlay: PhysicsOverlay | None,
) -> int:
    """Apply overlay modification to condition save DC."""
    if overlay is None:
        return base_dc

    modifier = overlay.get_condition_modifier(condition_type)
    return base_dc + modifier.save_dc_modifier


def get_source_effect(
    source: AbilitySource,
    overlay: PhysicsOverlay | None,
) -> dict[str, bool | int]:
    """
    Get the effects of an overlay on an ability source.

    Returns:
        Dict with keys:
        - forbidden: bool - True if ability cannot be used
        - advantage: bool - True if ability gets advantage
        - disadvantage: bool - True if ability gets disadvantage
        - damage_dice_bonus: int - Extra damage dice to add
        - dc_modifier: int - Modifier to save DCs
    """
    if overlay is None:
        return {
            "forbidden": False,
            "advantage": False,
            "disadvantage": False,
            "damage_dice_bonus": 0,
            "dc_modifier": 0,
        }

    modifier = overlay.get_source_modifier(source)

    if modifier == SourceModifier.FORBIDDEN:
        return {
            "forbidden": True,
            "advantage": False,
            "disadvantage": False,
            "damage_dice_bonus": 0,
            "dc_modifier": 0,
        }
    elif modifier == SourceModifier.ENHANCED:
        return {
            "forbidden": False,
            "advantage": True,
            "disadvantage": False,
            "damage_dice_bonus": 1,
            "dc_modifier": 0,
        }
    elif modifier == SourceModifier.RESTRICTED:
        return {
            "forbidden": False,
            "advantage": False,
            "disadvantage": True,
            "damage_dice_bonus": 0,
            "dc_modifier": -2,
        }
    else:  # NORMAL
        return {
            "forbidden": False,
            "advantage": False,
            "disadvantage": False,
            "damage_dice_bonus": 0,
            "dc_modifier": 0,
        }
