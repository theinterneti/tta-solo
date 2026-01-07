"""
Dice Rolling Skill.

Implements fair, cryptographically random dice rolling following SRD notation.
"""

from __future__ import annotations

import re
import secrets

from pydantic import BaseModel, Field


class DiceResult(BaseModel):
    """Result of a dice roll."""

    notation: str = Field(description="Original dice notation")
    rolls: list[int] = Field(description="Individual die results")
    kept: list[int] | None = Field(default=None, description="Kept dice for kh/kl")
    modifier: int = Field(default=0, description="Any +/- modifier")
    total: int = Field(description="Final result")


def roll_dice(notation: str) -> DiceResult:
    """
    Roll dice using standard notation.

    Supports:
    - NdX: Roll N dice with X sides (e.g., "2d6", "1d20")
    - NdX+M: Add modifier (e.g., "1d20+5", "2d6-2")
    - NdXkhN: Keep highest N dice (e.g., "4d6kh3")
    - NdXklN: Keep lowest N dice (e.g., "2d20kl1")

    Args:
        notation: Dice notation string

    Returns:
        DiceResult with individual rolls and total

    Examples:
        >>> result = roll_dice("2d6+3")
        >>> result.total  # Sum of 2d6 plus 3
        >>> result.rolls  # [4, 2] (example)

        >>> result = roll_dice("4d6kh3")
        >>> result.kept   # [6, 5, 4] (highest 3)
        >>> result.rolls  # [6, 5, 4, 1] (all 4 rolls)
    """
    notation = notation.lower().strip()

    # Parse the notation
    # Pattern: NdX (optional: kh/klN) (optional: +/-M)
    pattern = r"^(\d+)d(\d+)(?:(kh|kl)(\d+))?([+-]\d+)?$"
    match = re.match(pattern, notation)

    if not match:
        raise ValueError(f"Invalid dice notation: {notation}")

    num_dice = int(match.group(1))
    die_size = int(match.group(2))
    keep_type = match.group(3)  # "kh" or "kl" or None
    keep_count = int(match.group(4)) if match.group(4) else None
    modifier = int(match.group(5)) if match.group(5) else 0

    if num_dice < 1 or die_size < 1:
        raise ValueError("Number of dice and die size must be positive")

    if keep_count is not None and keep_count > num_dice:
        raise ValueError(f"Cannot keep {keep_count} dice when only rolling {num_dice}")

    # Roll the dice using cryptographic randomness
    rolls = [secrets.randbelow(die_size) + 1 for _ in range(num_dice)]

    # Handle keep highest/lowest
    kept: list[int] | None = None
    if keep_type == "kh" and keep_count:
        sorted_rolls = sorted(rolls, reverse=True)
        kept = sorted_rolls[:keep_count]
        dice_sum = sum(kept)
    elif keep_type == "kl" and keep_count:
        sorted_rolls = sorted(rolls)
        kept = sorted_rolls[:keep_count]
        dice_sum = sum(kept)
    else:
        dice_sum = sum(rolls)

    total = dice_sum + modifier

    return DiceResult(
        notation=notation,
        rolls=rolls,
        kept=kept,
        modifier=modifier,
        total=total,
    )


def roll_d20(modifier: int = 0) -> DiceResult:
    """Convenience function for d20 rolls."""
    notation = f"1d20{'+' if modifier >= 0 else ''}{modifier}" if modifier else "1d20"
    return roll_dice(notation)


def roll_advantage(modifier: int = 0) -> DiceResult:
    """Roll with advantage (2d20, keep highest)."""
    notation = f"2d20kh1{'+' if modifier >= 0 else ''}{modifier}" if modifier else "2d20kh1"
    return roll_dice(notation)


def roll_disadvantage(modifier: int = 0) -> DiceResult:
    """Roll with disadvantage (2d20, keep lowest)."""
    notation = f"2d20kl1{'+' if modifier >= 0 else ''}{modifier}" if modifier else "2d20kl1"
    return roll_dice(notation)
