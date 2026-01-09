#!/usr/bin/env python3
"""
TTA-Solo Game Launcher.

Run the text adventure from the command line:
    uv run python play.py
    uv run python play.py --name "Gandalf" --tone dark
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="TTA-Solo: An AI-Native Infinite Multiverse Text Adventure",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    uv run python play.py                          # Start with defaults
    uv run python play.py --name "Aria"            # Custom character name
    uv run python play.py --tone dark              # Dark fantasy tone
    uv run python play.py --verbosity verbose      # More detailed output
    uv run python play.py --agents                 # Enable AI agent system
        """,
    )

    parser.add_argument(
        "--name",
        "-n",
        default="Hero",
        help="Your character's name (default: Hero)",
    )
    parser.add_argument(
        "--tone",
        "-t",
        choices=["adventure", "dark", "humorous"],
        default="adventure",
        help="Narrative tone (default: adventure)",
    )
    parser.add_argument(
        "--verbosity",
        "-v",
        choices=["terse", "normal", "verbose"],
        default="normal",
        help="Output verbosity (default: normal)",
    )
    parser.add_argument(
        "--agents",
        "-a",
        action="store_true",
        help="Enable the agent system for enhanced AI interactions",
    )

    args = parser.parse_args()

    # Import here to avoid slow startup for --help
    from src.cli import run_game

    try:
        run_game(
            character_name=args.name,
            tone=args.tone,
            verbosity=args.verbosity,
            use_agents=args.agents,
        )
        return 0
    except KeyboardInterrupt:
        print("\nGoodbye!")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
