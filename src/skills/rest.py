"""
Rest and Recovery Skills.

Implements SRD 5e short rest and long rest mechanics.
Handles HP recovery, hit dice, and spell slot restoration.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from src.skills.dice import roll_dice


class HitDice(BaseModel):
    """
    Hit dice pool for a character.

    Hit dice are used during short rests to recover HP.
    """

    die_type: str = Field(description="Die size, e.g., 'd8', 'd10'")
    total: int = Field(ge=1, description="Maximum hit dice (usually = level)")
    current: int = Field(ge=0, description="Available hit dice to spend")

    @model_validator(mode="after")
    def current_not_exceeds_total(self) -> HitDice:
        if self.current > self.total:
            self.current = self.total
        return self

    def spend(self, count: int = 1) -> int:
        """
        Spend hit dice and return how many were actually spent.

        Returns the actual number spent (may be less if not enough available).
        """
        actual = min(count, self.current)
        self.current -= actual
        return actual

    def recover(self, count: int) -> int:
        """
        Recover hit dice (typically during long rest).

        Returns the actual number recovered.
        """
        space = self.total - self.current
        actual = min(count, space)
        self.current += actual
        return actual


class SpellSlots(BaseModel):
    """
    Spell slot tracking for a spellcaster.

    Keys are slot levels (1-9), values are [current, maximum].
    """

    slots: dict[int, tuple[int, int]] = Field(
        default_factory=dict,
        description="Slot level -> (current, max)",
    )

    def get_available(self, level: int) -> int:
        """Get available slots at a given level."""
        if level not in self.slots:
            return 0
        return self.slots[level][0]

    def get_maximum(self, level: int) -> int:
        """Get maximum slots at a given level."""
        if level not in self.slots:
            return 0
        return self.slots[level][1]

    def use_slot(self, level: int) -> bool:
        """
        Use a spell slot of the given level.

        Returns True if successful, False if no slots available.
        """
        if level not in self.slots:
            return False
        current, maximum = self.slots[level]
        if current <= 0:
            return False
        self.slots[level] = (current - 1, maximum)
        return True

    def restore_all(self) -> dict[int, int]:
        """
        Restore all spell slots to maximum (long rest).

        Returns dict of level -> slots restored.
        """
        restored = {}
        for level, (current, maximum) in self.slots.items():
            if current < maximum:
                restored[level] = maximum - current
                self.slots[level] = (maximum, maximum)
        return restored

    def restore_slot(self, level: int, count: int = 1) -> int:
        """
        Restore specific slots (for abilities like Arcane Recovery).

        Returns actual number restored.
        """
        if level not in self.slots:
            return 0
        current, maximum = self.slots[level]
        space = maximum - current
        actual = min(count, space)
        self.slots[level] = (current + actual, maximum)
        return actual


class CharacterResources(BaseModel):
    """
    Trackable resources for a character.

    This is a lightweight model for rest mechanics - not the full Entity.
    """

    hp_current: int = Field(ge=0, description="Current hit points")
    hp_max: int = Field(ge=1, description="Maximum hit points")
    hp_temp: int = Field(default=0, ge=0, description="Temporary hit points")
    con_modifier: int = Field(default=0, description="Constitution modifier for hit dice")
    hit_dice: HitDice
    spell_slots: SpellSlots | None = Field(default=None)

    @model_validator(mode="after")
    def hp_not_exceeds_max(self) -> CharacterResources:
        if self.hp_current > self.hp_max:
            self.hp_current = self.hp_max
        return self

    def heal(self, amount: int) -> int:
        """
        Heal HP up to maximum.

        Returns actual HP healed.
        """
        space = self.hp_max - self.hp_current
        actual = min(amount, space)
        self.hp_current += actual
        return actual

    def take_damage(self, amount: int) -> int:
        """
        Take damage, consuming temp HP first.

        Returns actual HP lost (after temp HP absorbed).
        """
        # Temp HP absorbs first
        if self.hp_temp > 0:
            if amount <= self.hp_temp:
                self.hp_temp -= amount
                return 0
            else:
                amount -= self.hp_temp
                self.hp_temp = 0

        # Remaining damage to HP
        actual = min(amount, self.hp_current)
        self.hp_current -= actual
        return actual


class ShortRestResult(BaseModel):
    """Result of taking a short rest."""

    hit_dice_spent: int
    hit_dice_remaining: int
    hp_healed: int
    hp_current: int
    hp_max: int
    rolls: list[int] = Field(default_factory=list, description="Individual hit die rolls")


class LongRestResult(BaseModel):
    """Result of taking a long rest."""

    hp_healed: int
    hp_current: int
    hp_max: int
    hit_dice_recovered: int
    hit_dice_current: int
    hit_dice_max: int
    spell_slots_restored: dict[int, int] = Field(
        default_factory=dict, description="Slots restored per level"
    )


def take_short_rest(
    character: CharacterResources,
    hit_dice_to_spend: int = 0,
) -> ShortRestResult:
    """
    Take a short rest (1 hour).

    During a short rest, a character can spend hit dice to recover HP.
    Each hit die rolled + CON modifier = HP healed.

    Args:
        character: The character's resources
        hit_dice_to_spend: Number of hit dice to spend (0 = rest without healing)

    Returns:
        ShortRestResult with healing details

    SRD Rules:
        - Can spend any number of available hit dice
        - Each die: roll + CON modifier (minimum 0 HP per die)
        - Temp HP remains unchanged
    """
    dice_spent = 0
    total_healed = 0
    rolls = []

    for _ in range(hit_dice_to_spend):
        if character.hit_dice.current <= 0:
            break

        character.hit_dice.spend(1)
        dice_spent += 1

        # Roll the hit die
        roll_result = roll_dice(f"1{character.hit_dice.die_type}")
        roll_value = roll_result.total

        # Add CON modifier, minimum 1 HP per die spent
        hp_from_die = max(1, roll_value + character.con_modifier)
        rolls.append(roll_value)

        # Heal
        actual_healed = character.heal(hp_from_die)
        total_healed += actual_healed

        # Stop if at max HP
        if character.hp_current >= character.hp_max:
            break

    return ShortRestResult(
        hit_dice_spent=dice_spent,
        hit_dice_remaining=character.hit_dice.current,
        hp_healed=total_healed,
        hp_current=character.hp_current,
        hp_max=character.hp_max,
        rolls=rolls,
    )


def take_long_rest(character: CharacterResources) -> LongRestResult:
    """
    Take a long rest (8 hours).

    A long rest fully restores HP, recovers half of max hit dice,
    and restores all spell slots.

    Args:
        character: The character's resources

    Returns:
        LongRestResult with recovery details

    SRD Rules:
        - Regain all lost HP
        - Regain half of total hit dice (minimum 1)
        - Regain all expended spell slots
        - Temp HP remains unchanged
    """
    # Heal to full
    hp_healed = character.hp_max - character.hp_current
    character.hp_current = character.hp_max

    # Recover half of max hit dice (minimum 1)
    dice_to_recover = max(1, character.hit_dice.total // 2)
    dice_recovered = character.hit_dice.recover(dice_to_recover)

    # Restore spell slots
    slots_restored: dict[int, int] = {}
    if character.spell_slots:
        slots_restored = character.spell_slots.restore_all()

    return LongRestResult(
        hp_healed=hp_healed,
        hp_current=character.hp_current,
        hp_max=character.hp_max,
        hit_dice_recovered=dice_recovered,
        hit_dice_current=character.hit_dice.current,
        hit_dice_max=character.hit_dice.total,
        spell_slots_restored=slots_restored,
    )


def spend_hit_die(
    character: CharacterResources,
) -> tuple[int, int] | None:
    """
    Spend a single hit die and return (roll, hp_healed).

    Convenience function for spending one hit die at a time.

    Returns:
        Tuple of (die_roll, actual_hp_healed) or None if no dice available
    """
    if character.hit_dice.current <= 0:
        return None

    character.hit_dice.spend(1)
    roll_result = roll_dice(f"1{character.hit_dice.die_type}")
    roll_value = roll_result.total

    hp_from_die = max(1, roll_value + character.con_modifier)
    actual_healed = character.heal(hp_from_die)

    return (roll_value, actual_healed)
