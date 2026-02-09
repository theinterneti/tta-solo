"""
Content package for TTA-Solo.

Provides pre-built worlds, scenarios, and content for gameplay.
"""

from src.content.starter_world import StarterWorldResult, create_starter_world
from src.content.universe_templates import (
    UNIVERSE_TEMPLATES,
    get_template_by_index,
    get_template_by_name,
)

__all__ = [
    "StarterWorldResult",
    "create_starter_world",
    "UNIVERSE_TEMPLATES",
    "get_template_by_index",
    "get_template_by_name",
]
