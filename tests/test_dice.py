"""Tests for the dice rolling skill."""

from __future__ import annotations

import pytest

from src.skills.dice import roll_advantage, roll_d20, roll_dice, roll_disadvantage


class TestRollDice:
    """Test the roll_dice function."""

    def test_simple_roll(self):
        """Test basic NdX notation."""
        result = roll_dice("2d6")
        assert result.notation == "2d6"
        assert len(result.rolls) == 2
        assert all(1 <= r <= 6 for r in result.rolls)
        assert result.total == sum(result.rolls)
        assert result.modifier == 0
        assert result.kept is None

    def test_roll_with_modifier(self):
        """Test NdX+M notation."""
        result = roll_dice("1d20+5")
        assert result.notation == "1d20+5"
        assert len(result.rolls) == 1
        assert 1 <= result.rolls[0] <= 20
        assert result.modifier == 5
        assert result.total == result.rolls[0] + 5

    def test_roll_with_negative_modifier(self):
        """Test NdX-M notation."""
        result = roll_dice("1d20-3")
        assert result.modifier == -3
        assert result.total == result.rolls[0] - 3

    def test_keep_highest(self):
        """Test NdXkhN notation."""
        result = roll_dice("4d6kh3")
        assert len(result.rolls) == 4
        assert result.kept is not None
        assert len(result.kept) == 3
        # Kept should be the 3 highest
        assert sorted(result.kept, reverse=True) == result.kept
        assert result.total == sum(result.kept)

    def test_keep_lowest(self):
        """Test NdXklN notation."""
        result = roll_dice("2d20kl1")
        assert len(result.rolls) == 2
        assert result.kept is not None
        assert len(result.kept) == 1
        assert result.kept[0] == min(result.rolls)
        assert result.total == result.kept[0]

    def test_invalid_notation(self):
        """Test that invalid notation raises ValueError."""
        with pytest.raises(ValueError, match="Invalid dice notation"):
            roll_dice("banana")

    def test_keep_more_than_rolled(self):
        """Test that keeping more dice than rolled raises ValueError."""
        with pytest.raises(ValueError, match="Cannot keep"):
            roll_dice("2d6kh5")


class TestConvenienceFunctions:
    """Test convenience roll functions."""

    def test_roll_d20(self):
        """Test d20 convenience function."""
        result = roll_d20()
        assert len(result.rolls) == 1
        assert 1 <= result.rolls[0] <= 20

    def test_roll_d20_with_modifier(self):
        """Test d20 with modifier."""
        result = roll_d20(modifier=5)
        assert result.modifier == 5

    def test_roll_advantage(self):
        """Test advantage roll."""
        result = roll_advantage()
        assert len(result.rolls) == 2
        assert result.kept is not None
        assert len(result.kept) == 1
        assert result.kept[0] == max(result.rolls)

    def test_roll_disadvantage(self):
        """Test disadvantage roll."""
        result = roll_disadvantage()
        assert len(result.rolls) == 2
        assert result.kept is not None
        assert len(result.kept) == 1
        assert result.kept[0] == min(result.rolls)
