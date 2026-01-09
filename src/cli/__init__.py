"""
TTA-Solo Command Line Interface.

Provides an interactive REPL for playing the game.
"""

from __future__ import annotations

from src.cli.repl import GameREPL, run_game

__all__ = [
    "GameREPL",
    "run_game",
]
