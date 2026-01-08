"""Tests for rest and recovery skills."""

from __future__ import annotations

from unittest.mock import patch

from src.skills.dice import DiceResult
from src.skills.rest import (
    CharacterResources,
    HitDice,
    LongRestResult,
    ShortRestResult,
    SpellSlots,
    spend_hit_die,
    take_long_rest,
    take_short_rest,
)

# --- HitDice Tests ---


class TestHitDice:
    """Tests for HitDice model."""

    def test_creation(self):
        hd = HitDice(die_type="d8", total=5, current=5)
        assert hd.die_type == "d8"
        assert hd.total == 5
        assert hd.current == 5

    def test_current_capped_at_total(self):
        """Current should not exceed total."""
        hd = HitDice(die_type="d8", total=5, current=10)
        assert hd.current == 5

    def test_spend_single(self):
        hd = HitDice(die_type="d8", total=5, current=5)
        spent = hd.spend(1)
        assert spent == 1
        assert hd.current == 4

    def test_spend_multiple(self):
        hd = HitDice(die_type="d10", total=5, current=5)
        spent = hd.spend(3)
        assert spent == 3
        assert hd.current == 2

    def test_spend_more_than_available(self):
        hd = HitDice(die_type="d8", total=5, current=2)
        spent = hd.spend(5)
        assert spent == 2  # Only had 2
        assert hd.current == 0

    def test_spend_when_empty(self):
        hd = HitDice(die_type="d8", total=5, current=0)
        spent = hd.spend(1)
        assert spent == 0
        assert hd.current == 0

    def test_recover(self):
        hd = HitDice(die_type="d8", total=5, current=2)
        recovered = hd.recover(2)
        assert recovered == 2
        assert hd.current == 4

    def test_recover_capped_at_total(self):
        hd = HitDice(die_type="d8", total=5, current=4)
        recovered = hd.recover(5)
        assert recovered == 1  # Only room for 1
        assert hd.current == 5


# --- SpellSlots Tests ---


class TestSpellSlots:
    """Tests for SpellSlots model."""

    def test_empty_slots(self):
        ss = SpellSlots()
        assert ss.get_available(1) == 0
        assert ss.get_maximum(1) == 0

    def test_get_available(self):
        ss = SpellSlots(slots={1: (4, 4), 2: (2, 3)})
        assert ss.get_available(1) == 4
        assert ss.get_available(2) == 2
        assert ss.get_available(3) == 0

    def test_get_maximum(self):
        ss = SpellSlots(slots={1: (2, 4), 2: (1, 3)})
        assert ss.get_maximum(1) == 4
        assert ss.get_maximum(2) == 3

    def test_use_slot_success(self):
        ss = SpellSlots(slots={1: (4, 4)})
        result = ss.use_slot(1)
        assert result is True
        assert ss.get_available(1) == 3

    def test_use_slot_empty(self):
        ss = SpellSlots(slots={1: (0, 4)})
        result = ss.use_slot(1)
        assert result is False
        assert ss.get_available(1) == 0

    def test_use_slot_invalid_level(self):
        ss = SpellSlots(slots={1: (4, 4)})
        result = ss.use_slot(5)
        assert result is False

    def test_restore_all(self):
        ss = SpellSlots(slots={1: (1, 4), 2: (0, 3), 3: (2, 2)})
        restored = ss.restore_all()

        assert restored == {1: 3, 2: 3}  # Level 3 was already full
        assert ss.get_available(1) == 4
        assert ss.get_available(2) == 3
        assert ss.get_available(3) == 2

    def test_restore_slot(self):
        ss = SpellSlots(slots={1: (1, 4)})
        actual = ss.restore_slot(1, 2)
        assert actual == 2
        assert ss.get_available(1) == 3


# --- CharacterResources Tests ---


class TestCharacterResources:
    """Tests for CharacterResources model."""

    def test_creation(self):
        char = CharacterResources(
            hp_current=30,
            hp_max=40,
            con_modifier=2,
            hit_dice=HitDice(die_type="d10", total=5, current=5),
        )
        assert char.hp_current == 30
        assert char.hp_max == 40

    def test_hp_capped_at_max(self):
        char = CharacterResources(
            hp_current=50,
            hp_max=40,
            hit_dice=HitDice(die_type="d8", total=5, current=5),
        )
        assert char.hp_current == 40

    def test_heal(self):
        char = CharacterResources(
            hp_current=20,
            hp_max=40,
            hit_dice=HitDice(die_type="d8", total=5, current=5),
        )
        healed = char.heal(15)
        assert healed == 15
        assert char.hp_current == 35

    def test_heal_capped(self):
        char = CharacterResources(
            hp_current=35,
            hp_max=40,
            hit_dice=HitDice(die_type="d8", total=5, current=5),
        )
        healed = char.heal(10)
        assert healed == 5
        assert char.hp_current == 40

    def test_take_damage(self):
        char = CharacterResources(
            hp_current=30,
            hp_max=40,
            hit_dice=HitDice(die_type="d8", total=5, current=5),
        )
        lost = char.take_damage(10)
        assert lost == 10
        assert char.hp_current == 20

    def test_take_damage_with_temp_hp(self):
        char = CharacterResources(
            hp_current=30,
            hp_max=40,
            hp_temp=10,
            hit_dice=HitDice(die_type="d8", total=5, current=5),
        )
        lost = char.take_damage(15)
        assert lost == 5  # 10 absorbed by temp, 5 actual
        assert char.hp_temp == 0
        assert char.hp_current == 25

    def test_temp_hp_absorbs_all(self):
        char = CharacterResources(
            hp_current=30,
            hp_max=40,
            hp_temp=20,
            hit_dice=HitDice(die_type="d8", total=5, current=5),
        )
        lost = char.take_damage(15)
        assert lost == 0
        assert char.hp_temp == 5
        assert char.hp_current == 30


# --- Short Rest Tests ---


class TestTakeShortRest:
    """Tests for take_short_rest function."""

    def test_rest_without_spending_dice(self):
        char = CharacterResources(
            hp_current=20,
            hp_max=40,
            hit_dice=HitDice(die_type="d8", total=5, current=5),
        )
        result = take_short_rest(char, hit_dice_to_spend=0)

        assert isinstance(result, ShortRestResult)
        assert result.hit_dice_spent == 0
        assert result.hp_healed == 0
        assert result.hit_dice_remaining == 5

    def test_spend_one_hit_die(self):
        char = CharacterResources(
            hp_current=20,
            hp_max=40,
            con_modifier=2,
            hit_dice=HitDice(die_type="d8", total=5, current=5),
        )

        mock_roll = DiceResult(notation="1d8", rolls=[5], total=5)
        with patch("src.skills.rest.roll_dice", return_value=mock_roll):
            result = take_short_rest(char, hit_dice_to_spend=1)

        assert result.hit_dice_spent == 1
        assert result.hit_dice_remaining == 4
        # Healed = 5 (roll) + 2 (CON) = 7
        assert result.hp_healed == 7
        assert result.hp_current == 27
        assert result.rolls == [5]

    def test_spend_multiple_hit_dice(self):
        char = CharacterResources(
            hp_current=10,
            hp_max=40,
            con_modifier=1,
            hit_dice=HitDice(die_type="d8", total=5, current=5),
        )

        rolls = iter(
            [
                DiceResult(notation="1d8", rolls=[4], total=4),
                DiceResult(notation="1d8", rolls=[6], total=6),
                DiceResult(notation="1d8", rolls=[3], total=3),
            ]
        )

        with patch("src.skills.rest.roll_dice", side_effect=lambda _: next(rolls)):
            result = take_short_rest(char, hit_dice_to_spend=3)

        assert result.hit_dice_spent == 3
        assert result.hit_dice_remaining == 2
        # (4+1) + (6+1) + (3+1) = 5 + 7 + 4 = 16
        assert result.hp_healed == 16
        assert result.rolls == [4, 6, 3]

    def test_stops_at_max_hp(self):
        char = CharacterResources(
            hp_current=35,
            hp_max=40,
            con_modifier=2,
            hit_dice=HitDice(die_type="d8", total=5, current=5),
        )

        mock_roll = DiceResult(notation="1d8", rolls=[8], total=8)
        with patch("src.skills.rest.roll_dice", return_value=mock_roll):
            result = take_short_rest(char, hit_dice_to_spend=3)

        # First die heals 10 (8+2), but only 5 room, so stops
        assert result.hit_dice_spent == 1
        assert result.hp_healed == 5
        assert result.hp_current == 40

    def test_stops_when_no_dice_left(self):
        char = CharacterResources(
            hp_current=20,
            hp_max=40,
            con_modifier=0,
            hit_dice=HitDice(die_type="d8", total=5, current=2),
        )

        mock_roll = DiceResult(notation="1d8", rolls=[4], total=4)
        with patch("src.skills.rest.roll_dice", return_value=mock_roll):
            result = take_short_rest(char, hit_dice_to_spend=5)

        assert result.hit_dice_spent == 2  # Only had 2
        assert result.hit_dice_remaining == 0

    def test_minimum_1_hp_per_die(self):
        """Even with negative CON, minimum 1 HP per die spent."""
        char = CharacterResources(
            hp_current=10,
            hp_max=40,
            con_modifier=-3,  # Negative CON
            hit_dice=HitDice(die_type="d6", total=5, current=5),
        )

        mock_roll = DiceResult(notation="1d6", rolls=[1], total=1)
        with patch("src.skills.rest.roll_dice", return_value=mock_roll):
            result = take_short_rest(char, hit_dice_to_spend=1)

        # 1 - 3 = -2, but minimum 1
        assert result.hp_healed == 1


# --- Long Rest Tests ---


class TestTakeLongRest:
    """Tests for take_long_rest function."""

    def test_full_hp_recovery(self):
        char = CharacterResources(
            hp_current=10,
            hp_max=40,
            hit_dice=HitDice(die_type="d8", total=5, current=5),
        )
        result = take_long_rest(char)

        assert isinstance(result, LongRestResult)
        assert result.hp_healed == 30
        assert result.hp_current == 40
        assert char.hp_current == 40

    def test_hit_dice_recovery_half(self):
        char = CharacterResources(
            hp_current=40,
            hp_max=40,
            hit_dice=HitDice(die_type="d10", total=6, current=0),
        )
        result = take_long_rest(char)

        # Recover half of 6 = 3
        assert result.hit_dice_recovered == 3
        assert result.hit_dice_current == 3
        assert char.hit_dice.current == 3

    def test_hit_dice_recovery_minimum_1(self):
        char = CharacterResources(
            hp_current=40,
            hp_max=40,
            hit_dice=HitDice(die_type="d8", total=1, current=0),
        )
        result = take_long_rest(char)

        # Minimum 1 die recovered
        assert result.hit_dice_recovered == 1
        assert result.hit_dice_current == 1

    def test_hit_dice_recovery_partial(self):
        """If already have some dice, only recover up to half."""
        char = CharacterResources(
            hp_current=40,
            hp_max=40,
            hit_dice=HitDice(die_type="d8", total=6, current=4),
        )
        result = take_long_rest(char)

        # Max is 6, current is 4, can recover 3, but only room for 2
        assert result.hit_dice_recovered == 2
        assert result.hit_dice_current == 6

    def test_spell_slots_restored(self):
        char = CharacterResources(
            hp_current=40,
            hp_max=40,
            hit_dice=HitDice(die_type="d8", total=5, current=5),
            spell_slots=SpellSlots(slots={1: (1, 4), 2: (0, 3), 3: (2, 2)}),
        )
        result = take_long_rest(char)

        assert result.spell_slots_restored == {1: 3, 2: 3}
        assert char.spell_slots.get_available(1) == 4
        assert char.spell_slots.get_available(2) == 3
        assert char.spell_slots.get_available(3) == 2

    def test_no_spell_slots(self):
        char = CharacterResources(
            hp_current=20,
            hp_max=40,
            hit_dice=HitDice(die_type="d10", total=5, current=2),
            spell_slots=None,
        )
        result = take_long_rest(char)

        assert result.spell_slots_restored == {}


# --- Spend Hit Die Tests ---


class TestSpendHitDie:
    """Tests for spend_hit_die function."""

    def test_spend_single_die(self):
        char = CharacterResources(
            hp_current=20,
            hp_max=40,
            con_modifier=2,
            hit_dice=HitDice(die_type="d8", total=5, current=5),
        )

        mock_roll = DiceResult(notation="1d8", rolls=[6], total=6)
        with patch("src.skills.rest.roll_dice", return_value=mock_roll):
            result = spend_hit_die(char)

        assert result == (6, 8)  # Rolled 6, healed 8 (6+2)
        assert char.hit_dice.current == 4
        assert char.hp_current == 28

    def test_spend_when_empty(self):
        char = CharacterResources(
            hp_current=20,
            hp_max=40,
            hit_dice=HitDice(die_type="d8", total=5, current=0),
        )
        result = spend_hit_die(char)

        assert result is None
        assert char.hp_current == 20

    def test_spend_capped_at_max(self):
        char = CharacterResources(
            hp_current=38,
            hp_max=40,
            con_modifier=3,
            hit_dice=HitDice(die_type="d8", total=5, current=5),
        )

        mock_roll = DiceResult(notation="1d8", rolls=[8], total=8)
        with patch("src.skills.rest.roll_dice", return_value=mock_roll):
            result = spend_hit_die(char)

        # Rolled 8, +3 CON = 11, but only 2 room
        assert result == (8, 2)
        assert char.hp_current == 40
