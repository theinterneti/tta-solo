"""
Condition and Combat State Models for TTA-Solo.

Tracks active conditions, temporary effects, and per-entity combat state.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# =============================================================================
# Standard Conditions
# =============================================================================


class ConditionType(StrEnum):
    """Standard condition types from SRD 5e plus custom conditions."""

    # SRD 5e Conditions
    BLINDED = "blinded"
    CHARMED = "charmed"
    DEAFENED = "deafened"
    EXHAUSTION = "exhaustion"
    FRIGHTENED = "frightened"
    GRAPPLED = "grappled"
    INCAPACITATED = "incapacitated"
    INVISIBLE = "invisible"
    PARALYZED = "paralyzed"
    PETRIFIED = "petrified"
    POISONED = "poisoned"
    PRONE = "prone"
    RESTRAINED = "restrained"
    STUNNED = "stunned"
    UNCONSCIOUS = "unconscious"

    # Custom/Extended Conditions
    BURNING = "burning"  # Taking fire damage over time
    BLEEDING = "bleeding"  # Taking damage over time
    SLOWED = "slowed"  # Speed halved
    HASTED = "hasted"  # Extra action
    CONCENTRATING = "concentrating"  # Meta-condition for tracking


class DurationType(StrEnum):
    """How condition/effect duration is tracked."""

    ROUNDS = "rounds"  # Expires after N rounds
    MINUTES = "minutes"  # Expires after N minutes
    UNTIL_SAVE = "until_save"  # Save to end each turn
    UNTIL_REST = "until_rest"  # Removed on short/long rest
    PERMANENT = "permanent"  # Requires specific removal
    INSTANTANEOUS = "instantaneous"  # One-time application
    CONCENTRATION = "concentration"  # Lasts while concentrating


# =============================================================================
# Condition Instance
# =============================================================================


class ConditionInstance(BaseModel):
    """
    An active condition on an entity.

    Tracks duration, save mechanics, and source information.
    """

    id: UUID = Field(default_factory=uuid4)
    entity_id: UUID = Field(description="Entity affected by this condition")
    universe_id: UUID = Field(description="Universe this condition exists in")

    # Condition type
    condition_type: str = Field(description="Condition name (from ConditionType or custom)")

    # Source tracking
    source_ability_id: UUID | None = Field(
        default=None, description="Ability that caused this condition"
    )
    source_entity_id: UUID | None = Field(
        default=None, description="Entity that applied this condition"
    )

    # Duration
    duration_type: DurationType = DurationType.ROUNDS
    duration_remaining: int | None = Field(
        default=None, ge=0, description="Rounds/minutes remaining (if applicable)"
    )
    applied_at_round: int | None = Field(default=None, description="Combat round when applied")

    # Save to end
    save_ability: str | None = Field(
        default=None, description="Ability for save to end (str, dex, con, int, wis, cha)"
    )
    save_dc: int | None = Field(default=None, ge=1, description="DC to save against")

    # Exhaustion level (only for exhaustion condition)
    exhaustion_level: int = Field(default=1, ge=1, le=6, description="Exhaustion level (1-6)")

    # DoT (damage over time)
    dot_damage: str | None = Field(
        default=None, description="Damage dice dealt each round (e.g., '1d6')"
    )
    dot_damage_type: str | None = Field(
        default=None, description="Damage type for DoT (fire, poison, etc.)"
    )

    def tick(self) -> bool:
        """
        Advance the condition by one round.

        Returns:
            True if the condition has expired, False otherwise.
        """
        if self.duration_type == DurationType.PERMANENT:
            return False

        if self.duration_type == DurationType.INSTANTANEOUS:
            return True

        if self.duration_type == DurationType.UNTIL_SAVE:
            # Never auto-expires, must save
            return False

        if self.duration_type == DurationType.UNTIL_REST:
            # Never auto-expires, must rest
            return False

        if self.duration_remaining is not None:
            self.duration_remaining -= 1
            return self.duration_remaining <= 0

        return False

    def attempt_save(self, roll: int, modifier: int) -> bool:
        """
        Attempt a saving throw to end the condition.

        Args:
            roll: The d20 roll
            modifier: The ability modifier + proficiency

        Returns:
            True if the save succeeds (condition ends), False otherwise.
        """
        if self.save_dc is None:
            return False

        total = roll + modifier
        return total >= self.save_dc

    def is_incapacitating(self) -> bool:
        """Check if this condition prevents taking actions."""
        incapacitating = {
            ConditionType.INCAPACITATED.value,
            ConditionType.PARALYZED.value,
            ConditionType.PETRIFIED.value,
            ConditionType.STUNNED.value,
            ConditionType.UNCONSCIOUS.value,
        }
        return self.condition_type in incapacitating


# =============================================================================
# Active Effect (Temporary Stat Modifiers)
# =============================================================================


class ModifierType(StrEnum):
    """How the modifier is applied."""

    BONUS = "bonus"  # Add to stat
    PENALTY = "penalty"  # Subtract from stat
    SET = "set"  # Set stat to specific value
    MULTIPLY = "multiply"  # Multiply stat


class ActiveEffect(BaseModel):
    """
    A temporary stat modification on an entity.

    Examples: +2 AC from Shield, -10 speed from difficult terrain,
    advantage on saving throws, etc.
    """

    id: UUID = Field(default_factory=uuid4)
    entity_id: UUID = Field(description="Entity affected by this effect")
    universe_id: UUID = Field(description="Universe this effect exists in")

    # Source tracking
    source_ability_id: UUID | None = Field(
        default=None, description="Ability that caused this effect"
    )
    source_entity_id: UUID | None = Field(
        default=None, description="Entity that applied this effect"
    )

    # Effect details
    stat: str = Field(description="Stat being modified (ac, speed, str, attack_rolls, etc.)")
    modifier: int = Field(description="Modification value")
    modifier_type: ModifierType = ModifierType.BONUS

    # Duration
    duration_type: DurationType = DurationType.ROUNDS
    duration_remaining: int | None = Field(
        default=None, ge=0, description="Rounds/minutes remaining"
    )

    # Concentration
    requires_concentration: bool = Field(
        default=False, description="Whether this effect requires concentration"
    )

    def tick(self) -> bool:
        """
        Advance the effect by one round.

        Returns:
            True if the effect has expired, False otherwise.
        """
        if self.duration_type == DurationType.PERMANENT:
            return False

        if self.requires_concentration:
            # Concentration effects don't expire on their own
            return False

        if self.duration_remaining is not None:
            self.duration_remaining -= 1
            return self.duration_remaining <= 0

        return False

    def apply_to_stat(self, base_value: int) -> int:
        """
        Apply this modifier to a stat value.

        Args:
            base_value: The base stat value

        Returns:
            Modified stat value
        """
        if self.modifier_type == ModifierType.BONUS:
            return base_value + self.modifier
        elif self.modifier_type == ModifierType.PENALTY:
            return base_value - self.modifier
        elif self.modifier_type == ModifierType.SET:
            return self.modifier
        elif self.modifier_type == ModifierType.MULTIPLY:
            return base_value * self.modifier
        return base_value


# =============================================================================
# Entity Combat State
# =============================================================================


class EntityCombatState(BaseModel):
    """
    Per-entity combat state tracking.

    Manages conditions, effects, concentration, and action economy.
    """

    entity_id: UUID = Field(description="Entity this state belongs to")
    universe_id: UUID = Field(description="Universe this state exists in")

    # Conditions and effects
    conditions: list[ConditionInstance] = Field(
        default_factory=list, description="Active conditions"
    )
    active_effects: list[ActiveEffect] = Field(
        default_factory=list, description="Active stat modifiers"
    )

    # Concentration
    concentrating_on: UUID | None = Field(
        default=None, description="Ability ID being concentrated on"
    )
    concentration_source: UUID | None = Field(
        default=None, description="Entity who is concentrating (usually self)"
    )

    # Combat tracking
    current_round: int = Field(default=0, ge=0, description="Current combat round")
    initiative: int | None = Field(default=None, description="Initiative roll")

    # Action economy
    has_reaction: bool = Field(default=True)
    has_action: bool = Field(default=True)
    has_bonus_action: bool = Field(default=True)
    movement_remaining: int = Field(default=30, ge=0, description="Movement in feet")

    # Death saves (for 0 HP)
    death_saves_success: int = Field(default=0, ge=0, le=3)
    death_saves_failure: int = Field(default=0, ge=0, le=3)

    def has_condition(self, condition_type: str) -> bool:
        """Check if entity has a specific condition."""
        return any(c.condition_type == condition_type for c in self.conditions)

    def get_condition(self, condition_type: str) -> ConditionInstance | None:
        """Get a condition by type if present."""
        for c in self.conditions:
            if c.condition_type == condition_type:
                return c
        return None

    def add_condition(self, condition: ConditionInstance) -> None:
        """Add a condition to this entity."""
        # Check for duplicate (some conditions stack, some don't)
        existing = self.get_condition(condition.condition_type)
        if existing is None:
            self.conditions.append(condition)
        else:
            # For exhaustion, stack levels
            if condition.condition_type == ConditionType.EXHAUSTION.value:
                existing.exhaustion_level = min(
                    6, existing.exhaustion_level + condition.exhaustion_level
                )
            # For other conditions, refresh duration if new one is longer
            elif (
                condition.duration_remaining is not None
                and existing.duration_remaining is not None
                and condition.duration_remaining > existing.duration_remaining
            ):
                existing.duration_remaining = condition.duration_remaining

    def remove_condition(self, condition_id: UUID) -> bool:
        """Remove a condition by ID."""
        for i, c in enumerate(self.conditions):
            if c.id == condition_id:
                self.conditions.pop(i)
                return True
        return False

    def remove_condition_by_type(self, condition_type: str) -> bool:
        """Remove all conditions of a specific type."""
        initial_count = len(self.conditions)
        self.conditions = [c for c in self.conditions if c.condition_type != condition_type]
        return len(self.conditions) < initial_count

    def add_effect(self, effect: ActiveEffect) -> None:
        """Add an active effect."""
        self.active_effects.append(effect)

    def remove_effect(self, effect_id: UUID) -> bool:
        """Remove an active effect by ID."""
        for i, e in enumerate(self.active_effects):
            if e.id == effect_id:
                self.active_effects.pop(i)
                return True
        return False

    def get_stat_modifier(self, stat: str) -> int:
        """
        Calculate total modifier for a stat from all active effects.

        Args:
            stat: The stat to check (ac, speed, etc.)

        Returns:
            Total modifier (can be negative)
        """
        total = 0
        for effect in self.active_effects:
            if effect.stat == stat:
                if effect.modifier_type == ModifierType.BONUS:
                    total += effect.modifier
                elif effect.modifier_type == ModifierType.PENALTY:
                    total -= effect.modifier
        return total

    def is_incapacitated(self) -> bool:
        """Check if entity is incapacitated by any condition."""
        return any(c.is_incapacitating() for c in self.conditions)

    def is_concentrating(self) -> bool:
        """Check if entity is concentrating on something."""
        return self.concentrating_on is not None

    def break_concentration(self) -> UUID | None:
        """
        Break concentration, returning the ability that was lost.

        Returns:
            The ability ID that was being concentrated on, or None.
        """
        lost_ability = self.concentrating_on
        self.concentrating_on = None
        self.concentration_source = None

        # Also remove any effects that required concentration
        self.active_effects = [e for e in self.active_effects if not e.requires_concentration]

        return lost_ability

    def start_turn(self) -> None:
        """Reset action economy at the start of turn."""
        self.has_action = True
        self.has_bonus_action = True
        # Reaction resets at start of YOUR turn
        self.has_reaction = True
        # Movement would be set based on speed, considering effects
        # For now, default to 30
        self.movement_remaining = 30 + self.get_stat_modifier("speed")

    def end_turn(self) -> list[ConditionInstance]:
        """
        Process end of turn.

        Returns:
            List of conditions that expired.
        """
        expired: list[ConditionInstance] = []

        # Tick all conditions
        for condition in self.conditions[:]:  # Copy list for iteration
            if condition.tick():
                expired.append(condition)
                self.conditions.remove(condition)

        # Tick all effects
        for effect in self.active_effects[:]:
            if effect.tick():
                self.active_effects.remove(effect)

        return expired


# =============================================================================
# Factory Functions
# =============================================================================


def create_condition(
    entity_id: UUID,
    universe_id: UUID,
    condition_type: str,
    duration_type: DurationType = DurationType.ROUNDS,
    duration_rounds: int | None = None,
    save_ability: str | None = None,
    save_dc: int | None = None,
    source_ability_id: UUID | None = None,
    source_entity_id: UUID | None = None,
) -> ConditionInstance:
    """
    Factory function to create a condition instance.

    Args:
        entity_id: Entity to apply condition to
        universe_id: Universe context
        condition_type: Type of condition
        duration_type: How duration is tracked
        duration_rounds: Duration in rounds (if applicable)
        save_ability: Ability for save to end
        save_dc: DC for save
        source_ability_id: Ability that caused this
        source_entity_id: Entity that applied this

    Returns:
        Configured ConditionInstance
    """
    return ConditionInstance(
        entity_id=entity_id,
        universe_id=universe_id,
        condition_type=condition_type,
        duration_type=duration_type,
        duration_remaining=duration_rounds,
        save_ability=save_ability,
        save_dc=save_dc,
        source_ability_id=source_ability_id,
        source_entity_id=source_entity_id,
    )


def create_active_effect(
    entity_id: UUID,
    universe_id: UUID,
    stat: str,
    modifier: int,
    duration_rounds: int | None = None,
    modifier_type: ModifierType = ModifierType.BONUS,
    requires_concentration: bool = False,
    source_ability_id: UUID | None = None,
    source_entity_id: UUID | None = None,
) -> ActiveEffect:
    """
    Factory function to create an active effect.

    Args:
        entity_id: Entity to apply effect to
        universe_id: Universe context
        stat: Stat to modify
        modifier: Modification value
        duration_rounds: Duration in rounds
        modifier_type: How modifier is applied
        requires_concentration: Whether effect needs concentration
        source_ability_id: Ability that caused this
        source_entity_id: Entity that applied this

    Returns:
        Configured ActiveEffect
    """
    duration_type = DurationType.CONCENTRATION if requires_concentration else DurationType.ROUNDS

    return ActiveEffect(
        entity_id=entity_id,
        universe_id=universe_id,
        stat=stat,
        modifier=modifier,
        modifier_type=modifier_type,
        duration_type=duration_type,
        duration_remaining=duration_rounds,
        requires_concentration=requires_concentration,
        source_ability_id=source_ability_id,
        source_entity_id=source_entity_id,
    )


def create_combat_state(
    entity_id: UUID,
    universe_id: UUID,
    initiative: int | None = None,
) -> EntityCombatState:
    """
    Factory function to create a combat state for an entity.

    Args:
        entity_id: Entity this state belongs to
        universe_id: Universe context
        initiative: Initiative roll (if in combat)

    Returns:
        Configured EntityCombatState
    """
    return EntityCombatState(
        entity_id=entity_id,
        universe_id=universe_id,
        initiative=initiative,
    )
