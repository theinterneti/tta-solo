"""
Stateless Skills for TTA-Solo.

Skills are pure functions that:
- Take structured input (Pydantic models)
- Execute game logic (dice, rules, database queries)
- Return structured output
- NEVER maintain state between calls
- NEVER call LLMs directly
"""

from src.skills.dice import DiceResult, roll_dice

__all__ = ["roll_dice", "DiceResult"]
