"""
Resource System Models for TTA-Solo.

Implements resource thermodynamics for ability usage:
- Usage Die (degrading dice)
- Cooldown Tracking
- Stress/Momentum pools
- Spell Slot tracking
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

# =============================================================================
# Usage Die System
# =============================================================================


class UsageDieResult(BaseModel):
    """Result of rolling a usage die."""

    roll: int = Field(description="The die result")
    die_used: str = Field(description="Die that was rolled (e.g., 'd10')")
    degraded: bool = Field(default=False, description="Whether the die degraded")
    new_die: str | None = Field(default=None, description="New die type if degraded")
    depleted: bool = Field(default=False, description="Whether resource is now depleted")


class UsageDie(BaseModel):
    """
    A degrading usage die resource.

    Inspired by The Black Hack - roll the die when using,
    on low results (1-2 by default) it degrades to the next smaller die.
    """

    die_chain: list[str] = Field(
        default=["d4", "d6", "d8", "d10", "d12"],
        description="Die progression from smallest to largest",
    )
    current_index: int = Field(
        default=4, ge=0, description="Current position in die chain (0=smallest)"
    )
    degrade_on: list[int] = Field(
        default=[1, 2], description="Die results that trigger degradation"
    )
    depleted: bool = Field(default=False, description="True if resource is exhausted")

    @model_validator(mode="after")
    def validate_index(self) -> UsageDie:
        """Ensure current_index is within bounds."""
        if self.current_index >= len(self.die_chain):
            raise ValueError(
                f"current_index {self.current_index} out of bounds for die_chain of length {len(self.die_chain)}"
            )
        return self

    @property
    def current_die(self) -> str:
        """Get the current die type."""
        if self.depleted:
            return "depleted"
        return self.die_chain[self.current_index]

    def die_size(self) -> int:
        """Get the numeric size of the current die (e.g., d8 -> 8)."""
        if self.depleted:
            return 0
        die = self.die_chain[self.current_index]
        return int(die[1:])  # Strip 'd' prefix

    def degrade(self) -> bool:
        """
        Degrade the die to the next smaller size.

        Returns:
            True if now depleted, False otherwise.
        """
        if self.depleted:
            return True

        if self.current_index == 0:
            # At smallest die, now depleted
            self.depleted = True
            return True

        self.current_index -= 1
        return False

    def restore(self, steps: int = 1) -> int:
        """
        Restore the die by upgrading it.

        Args:
            steps: Number of steps to upgrade (default 1)

        Returns:
            New current index
        """
        if self.depleted:
            self.depleted = False
            self.current_index = 0  # Start at d4
            # First step just un-depletes, remaining steps upgrade
            steps -= 1

        if steps > 0:
            max_index = len(self.die_chain) - 1
            self.current_index = min(self.current_index + steps, max_index)

        return self.current_index

    def restore_full(self) -> int:
        """
        Fully restore the die to maximum.

        Returns:
            New current index
        """
        self.depleted = False
        self.current_index = len(self.die_chain) - 1
        return self.current_index


# =============================================================================
# Cooldown Tracking
# =============================================================================


class CooldownRechargeResult(BaseModel):
    """Result of attempting to recharge a cooldown ability."""

    ability_name: str = Field(default="", description="Name of the ability")
    roll: int | None = Field(default=None, description="Die roll if applicable")
    recharged: bool = Field(default=False, description="Whether a use was restored")
    uses_restored: int = Field(default=0, description="Number of uses restored")
    current_uses: int = Field(description="Uses remaining after recharge")
    max_uses: int = Field(description="Maximum uses")


class CooldownTracker(BaseModel):
    """
    Tracks cooldown-based ability usage.

    Supports per-rest recovery and roll-based recharge mechanics.
    """

    max_uses: int = Field(ge=1, description="Maximum uses")
    current_uses: int = Field(ge=0, description="Current uses remaining")
    recharge_on: list[int] | None = Field(
        default=None, description="Die results that restore 1 use (e.g., [5, 6])"
    )
    recharge_die: str = Field(default="d6", description="Die to roll for recharge")
    recharge_on_rest: str | None = Field(
        default=None, description="Rest type that restores all uses: 'short' or 'long'"
    )

    @model_validator(mode="after")
    def validate_uses(self) -> CooldownTracker:
        """Ensure current_uses doesn't exceed max_uses."""
        if self.current_uses > self.max_uses:
            raise ValueError(
                f"current_uses ({self.current_uses}) cannot exceed max_uses ({self.max_uses})"
            )
        return self

    def has_uses(self) -> bool:
        """Check if any uses remain."""
        return self.current_uses > 0

    def use(self) -> bool:
        """
        Attempt to use the ability.

        Returns:
            True if use was allowed, False if no uses remaining.
        """
        if self.current_uses <= 0:
            return False
        self.current_uses -= 1
        return True

    def restore_use(self, amount: int = 1) -> int:
        """
        Restore uses.

        Args:
            amount: Number of uses to restore

        Returns:
            Actual number of uses restored
        """
        old_uses = self.current_uses
        self.current_uses = min(self.current_uses + amount, self.max_uses)
        return self.current_uses - old_uses

    def restore_on_rest(self, rest_type: str) -> int:
        """
        Restore uses based on rest type.

        Args:
            rest_type: "short" or "long"

        Returns:
            Number of uses restored
        """
        if self.recharge_on_rest is None:
            return 0

        # Long rest always restores if ability has any rest-based recharge
        if rest_type == "long" or rest_type == self.recharge_on_rest:
            old_uses = self.current_uses
            self.current_uses = self.max_uses
            return self.current_uses - old_uses

        return 0

    def recharge_die_size(self) -> int:
        """Get the numeric size of the recharge die."""
        return int(self.recharge_die[1:])


# =============================================================================
# Stress/Momentum System
# =============================================================================


class StressChangeResult(BaseModel):
    """Result of a stress change."""

    old_stress: int
    new_stress: int
    change: int
    at_breaking_point: bool = Field(default=False, description="True if now at max stress")


class MomentumChangeResult(BaseModel):
    """Result of a momentum change."""

    old_momentum: int
    new_momentum: int
    change: int
    at_max: bool = Field(default=False, description="True if at max momentum")


class StressMomentumPool(BaseModel):
    """
    Dual resource pool for martial characters.

    Stress: Risk accumulation (high = bad)
    Momentum: Reward accumulation (spent for special techniques)
    """

    stress: int = Field(default=0, ge=0, description="Current stress level")
    stress_max: int = Field(default=10, ge=1, description="Maximum stress")
    momentum: int = Field(default=0, ge=0, description="Current momentum")
    momentum_max: int = Field(default=5, ge=1, description="Maximum momentum")

    @model_validator(mode="after")
    def validate_pools(self) -> StressMomentumPool:
        """Ensure values don't exceed maximums."""
        if self.stress > self.stress_max:
            raise ValueError(f"stress ({self.stress}) cannot exceed stress_max ({self.stress_max})")
        if self.momentum > self.momentum_max:
            raise ValueError(
                f"momentum ({self.momentum}) cannot exceed momentum_max ({self.momentum_max})"
            )
        return self

    def is_at_breaking_point(self) -> bool:
        """Check if at maximum stress (breaking point)."""
        return self.stress >= self.stress_max

    def add_stress(self, amount: int) -> StressChangeResult:
        """
        Add stress.

        Args:
            amount: Stress to add

        Returns:
            Result with old/new values and breaking point status
        """
        old_stress = self.stress
        self.stress = min(self.stress + amount, self.stress_max)
        return StressChangeResult(
            old_stress=old_stress,
            new_stress=self.stress,
            change=self.stress - old_stress,
            at_breaking_point=self.is_at_breaking_point(),
        )

    def reduce_stress(self, amount: int) -> int:
        """
        Reduce stress.

        Args:
            amount: Stress to reduce

        Returns:
            Actual amount reduced
        """
        old_stress = self.stress
        self.stress = max(0, self.stress - amount)
        return old_stress - self.stress

    def add_momentum(self, amount: int) -> MomentumChangeResult:
        """
        Add momentum.

        Args:
            amount: Momentum to add

        Returns:
            Result with old/new values
        """
        old_momentum = self.momentum
        self.momentum = min(self.momentum + amount, self.momentum_max)
        return MomentumChangeResult(
            old_momentum=old_momentum,
            new_momentum=self.momentum,
            change=self.momentum - old_momentum,
            at_max=self.momentum >= self.momentum_max,
        )

    def spend_momentum(self, amount: int) -> bool:
        """
        Spend momentum.

        Args:
            amount: Momentum to spend

        Returns:
            True if spent successfully, False if insufficient
        """
        if self.momentum < amount:
            return False
        self.momentum -= amount
        return True

    def take_damage_reset(self) -> int:
        """
        Reset momentum on taking damage.

        Returns:
            Amount of momentum lost
        """
        lost = self.momentum
        self.momentum = 0
        return lost

    def stress_penalty(self) -> int:
        """
        Calculate penalty based on current stress.

        Returns:
            Penalty value (0, -1, or -2)
        """
        if self.stress >= 7:
            return -2
        elif self.stress >= 4:
            return -1
        return 0


# =============================================================================
# Spell Slots
# =============================================================================


class SpellSlotTracker(BaseModel):
    """Tracks spell slots for a specific spell level."""

    level: int = Field(ge=1, le=9, description="Spell level (1-9)")
    max_slots: int = Field(ge=0, description="Maximum slots")
    current_slots: int = Field(ge=0, description="Current slots remaining")

    @model_validator(mode="after")
    def validate_slots(self) -> SpellSlotTracker:
        """Ensure current_slots doesn't exceed max_slots."""
        if self.current_slots > self.max_slots:
            raise ValueError(
                f"current_slots ({self.current_slots}) cannot exceed max_slots ({self.max_slots})"
            )
        return self

    def has_slots(self) -> bool:
        """Check if any slots remain."""
        return self.current_slots > 0

    def use_slot(self) -> bool:
        """
        Use a slot.

        Returns:
            True if slot was used, False if none available.
        """
        if self.current_slots <= 0:
            return False
        self.current_slots -= 1
        return True

    def restore_slots(self, amount: int | None = None) -> int:
        """
        Restore slots.

        Args:
            amount: Slots to restore (None = restore all)

        Returns:
            Actual slots restored
        """
        old_slots = self.current_slots
        if amount is None:
            self.current_slots = self.max_slots
        else:
            self.current_slots = min(self.current_slots + amount, self.max_slots)
        return self.current_slots - old_slots


# =============================================================================
# Entity Resources (Composite)
# =============================================================================


class EntityResources(BaseModel):
    """
    All resource pools for an entity.

    Tracks usage dice, cooldowns, stress/momentum, and spell slots.
    """

    usage_dice: dict[str, UsageDie] = Field(default_factory=dict, description="Named usage dice")
    cooldowns: dict[str, CooldownTracker] = Field(
        default_factory=dict, description="Ability cooldowns keyed by ability name/id"
    )
    stress_momentum: StressMomentumPool | None = Field(
        default=None, description="Stress/Momentum pool (martial characters)"
    )
    spell_slots: dict[int, SpellSlotTracker] | None = Field(
        default=None, description="Spell slots by level (1-9)"
    )

    def has_spell_slot(self, level: int) -> bool:
        """Check if a spell slot of the given level is available."""
        if self.spell_slots is None:
            return False
        tracker = self.spell_slots.get(level)
        return tracker is not None and tracker.has_slots()

    def use_spell_slot(self, level: int) -> bool:
        """
        Use a spell slot of the given level.

        Returns:
            True if slot was used, False if unavailable.
        """
        if self.spell_slots is None:
            return False
        tracker = self.spell_slots.get(level)
        if tracker is None:
            return False
        return tracker.use_slot()

    def get_cooldown(self, ability_name: str) -> CooldownTracker | None:
        """Get cooldown tracker for an ability."""
        return self.cooldowns.get(ability_name)

    def restore_on_rest(self, rest_type: str) -> dict[str, int]:
        """
        Restore resources based on rest type.

        Args:
            rest_type: "short" or "long"

        Returns:
            Dict mapping resource names to amounts restored
        """
        restored: dict[str, int] = {}

        # Restore cooldowns
        for name, tracker in self.cooldowns.items():
            amount = tracker.restore_on_rest(rest_type)
            if amount > 0:
                restored[f"cooldown:{name}"] = amount

        # Restore stress on rest
        if self.stress_momentum is not None:
            if rest_type == "long":
                old = self.stress_momentum.stress
                self.stress_momentum.stress = 0
                if old > 0:
                    restored["stress_reduced"] = old
            # Short rest doesn't auto-reduce stress in this model

        # Restore spell slots on long rest
        if rest_type == "long" and self.spell_slots is not None:
            for level, tracker in self.spell_slots.items():
                amount = tracker.restore_slots()
                if amount > 0:
                    restored[f"spell_slot_level_{level}"] = amount

        # Restore usage dice on long rest
        if rest_type == "long":
            for name, die in self.usage_dice.items():
                if die.depleted or die.current_index < len(die.die_chain) - 1:
                    die.restore_full()
                    restored[f"usage_die:{name}"] = 1

        return restored


# =============================================================================
# Factory Functions
# =============================================================================


def create_usage_die(
    starting_die: str = "d12",
    degrade_on: list[int] | None = None,
) -> UsageDie:
    """
    Create a usage die starting at a specific size.

    Args:
        starting_die: Initial die type (d4, d6, d8, d10, d12)
        degrade_on: Die results that trigger degradation (default [1, 2])

    Returns:
        Configured UsageDie
    """
    die_chain = ["d4", "d6", "d8", "d10", "d12"]
    if starting_die not in die_chain:
        raise ValueError(f"Invalid die type: {starting_die}")

    index = die_chain.index(starting_die)
    return UsageDie(
        die_chain=die_chain,
        current_index=index,
        degrade_on=degrade_on or [1, 2],
    )


def create_cooldown_tracker(
    max_uses: int,
    recharge_on_rest: str | None = "short",
    recharge_on: list[int] | None = None,
    recharge_die: str = "d6",
) -> CooldownTracker:
    """
    Create a cooldown tracker.

    Args:
        max_uses: Maximum uses before recharge
        recharge_on_rest: Rest type that restores uses ("short", "long", or None)
        recharge_on: Die results that restore a use
        recharge_die: Die to roll for recharge

    Returns:
        Configured CooldownTracker
    """
    return CooldownTracker(
        max_uses=max_uses,
        current_uses=max_uses,
        recharge_on_rest=recharge_on_rest,
        recharge_on=recharge_on,
        recharge_die=recharge_die,
    )


def create_spell_slots(slots_by_level: dict[int, int]) -> dict[int, SpellSlotTracker]:
    """
    Create spell slot trackers for multiple levels.

    Args:
        slots_by_level: Dict mapping spell level to number of slots

    Returns:
        Dict of SpellSlotTracker by level
    """
    return {
        level: SpellSlotTracker(level=level, max_slots=count, current_slots=count)
        for level, count in slots_by_level.items()
        if count > 0
    }
