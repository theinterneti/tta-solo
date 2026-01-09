"""
Interactive REPL for TTA-Solo.

Provides a text-based interface for playing the game.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.engine import GameEngine
from src.engine.models import EngineConfig, TurnResult
from src.models import (
    AbilityScores,
    Universe,
    create_character,
    create_location,
)


@dataclass
class GameState:
    """Current state of the game session."""

    engine: GameEngine
    session_id: UUID | None = None
    universe_id: UUID | None = None
    character_id: UUID | None = None
    location_id: UUID | None = None
    character_name: str = "Hero"
    running: bool = True


@dataclass
class Command:
    """A special REPL command."""

    name: str
    aliases: list[str]
    description: str
    handler: Callable[[GameState, list[str]], str | None]


class GameREPL:
    """
    Interactive REPL for playing TTA-Solo.

    Handles user input, special commands, and game output.
    """

    def __init__(
        self,
        *,
        tone: str = "adventure",
        verbosity: str = "normal",
        use_agents: bool = False,
    ) -> None:
        self.tone = tone
        self.verbosity = verbosity
        self.use_agents = use_agents
        self.commands: dict[str, Command] = {}
        self._register_commands()

    def _register_commands(self) -> None:
        """Register all special commands."""
        commands = [
            Command(
                name="quit",
                aliases=["exit", "q"],
                description="Exit the game",
                handler=self._cmd_quit,
            ),
            Command(
                name="help",
                aliases=["?", "h"],
                description="Show available commands",
                handler=self._cmd_help,
            ),
            Command(
                name="look",
                aliases=["l"],
                description="Look around the current location",
                handler=self._cmd_look,
            ),
            Command(
                name="status",
                aliases=["stats", "me"],
                description="Show character status",
                handler=self._cmd_status,
            ),
            Command(
                name="history",
                aliases=["hist"],
                description="Show recent events",
                handler=self._cmd_history,
            ),
            Command(
                name="save",
                aliases=["s"],
                description="Save the current game state",
                handler=self._cmd_save,
            ),
            Command(
                name="fork",
                aliases=["branch", "whatif"],
                description="Fork the timeline (what if scenario)",
                handler=self._cmd_fork,
            ),
            Command(
                name="clear",
                aliases=["cls"],
                description="Clear the screen",
                handler=self._cmd_clear,
            ),
        ]

        for cmd in commands:
            self.commands[cmd.name] = cmd
            for alias in cmd.aliases:
                self.commands[alias] = cmd

    def _cmd_quit(self, state: GameState, args: list[str]) -> str | None:
        """Handle quit command."""
        state.running = False
        return "Farewell, adventurer! Your story shall be remembered..."

    def _cmd_help(self, state: GameState, args: list[str]) -> str | None:
        """Handle help command."""
        lines = [
            "Available Commands:",
            "-" * 40,
        ]

        # Get unique commands (no aliases)
        seen = set()
        for cmd in self.commands.values():
            if cmd.name not in seen:
                aliases = f" ({', '.join(cmd.aliases)})" if cmd.aliases else ""
                lines.append(f"  /{cmd.name}{aliases} - {cmd.description}")
                seen.add(cmd.name)

        lines.extend(
            [
                "",
                "Tips:",
                "  - Type any action in plain English",
                "  - Examples: 'look around', 'go north', 'talk to the merchant'",
                "  - Use /fork to explore what-if scenarios",
            ]
        )

        return "\n".join(lines)

    def _cmd_look(self, state: GameState, args: list[str]) -> str | None:
        """Handle look command - returns None to process as regular input."""
        return None  # Let the engine handle it

    def _cmd_status(self, state: GameState, args: list[str]) -> str | None:
        """Handle status command."""
        if state.character_id is None:
            return "No character loaded."

        if state.universe_id is None:
            return "No universe loaded."

        character = state.engine.dolt.get_entity(state.character_id, state.universe_id)

        if character is None:
            return "Character not found."

        lines = [
            f"Character: {character.name}",
            "-" * 40,
        ]

        if character.stats:
            lines.extend(
                [
                    f"  HP: {character.stats.hp_current}/{character.stats.hp_max}",
                    f"  AC: {character.stats.ac}",
                    f"  Level: {character.stats.level}",
                ]
            )

            if character.stats.abilities:
                lines.append("  Abilities:")
                for attr, val in character.stats.abilities.model_dump().items():
                    mod = (val - 10) // 2
                    sign = "+" if mod >= 0 else ""
                    lines.append(f"    {attr.upper()[:3]}: {val} ({sign}{mod})")

        if character.description:
            lines.extend(["", f"  {character.description}"])

        return "\n".join(lines)

    def _cmd_history(self, state: GameState, args: list[str]) -> str | None:
        """Handle history command."""
        if state.universe_id is None or state.location_id is None:
            return "No active session."

        events = state.engine.dolt.get_events_at_location(
            state.universe_id, state.location_id, limit=10
        )

        if not events:
            return "No recent events at this location."

        lines = ["Recent Events:", "-" * 40]
        for event in events:
            summary = event.narrative_summary or f"{event.event_type.value}"
            lines.append(f"  - {summary}")

        return "\n".join(lines)

    def _cmd_save(self, state: GameState, args: list[str]) -> str | None:
        """Handle save command."""
        # In-memory implementation doesn't persist
        return "Game state saved. (Note: In-memory mode - data not persisted to disk)"

    def _cmd_fork(self, state: GameState, args: list[str]) -> str | None:
        """Handle fork command - returns None to let special fork logic handle it."""
        # If no args provided, give usage hint
        if not args:
            return (
                "To fork the timeline, provide a reason:\n"
                "  /fork I attacked the stranger instead\n"
                "  /fork what if I had joined the goblins\n\n"
                "Or use natural language: 'what if I had...'"
            )
        # Let the fork logic in _process_input handle it
        return None

    def _cmd_clear(self, state: GameState, args: list[str]) -> str | None:
        """Handle clear command."""
        os.system("cls" if os.name == "nt" else "clear")
        return None

    def _is_command(self, text: str) -> bool:
        """Check if input is a special command."""
        return text.startswith("/")

    def _parse_command(self, text: str) -> tuple[str, list[str]]:
        """Parse a command into name and arguments."""
        parts = text[1:].split()  # Remove leading /
        if not parts:
            return "", []
        return parts[0].lower(), parts[1:]

    async def _process_input(self, text: str, state: GameState) -> str:
        """Process user input and return response."""
        text = text.strip()

        if not text:
            return ""

        # Handle special commands
        if self._is_command(text):
            cmd_name, args = self._parse_command(text)
            if cmd_name in self.commands:
                result = self.commands[cmd_name].handler(state, args)
                if result is not None:
                    return result
                # Fall through to engine processing
                # Preserve arguments for commands like /fork that need them
                text = f"{cmd_name} {' '.join(args)}" if args else cmd_name

        # Handle fork command specially
        if text.lower().startswith("fork") or text.lower().startswith("what if"):
            if state.session_id is None:
                return "No active session to fork."

            reason = text[5:].strip() if text.lower().startswith("fork") else text[8:].strip()
            if not reason:
                reason = "exploring an alternative path"

            result = await state.engine.fork_from_here(
                state.session_id,
                reason=reason,
            )

            if result.success:
                # Switch to the new session
                state.session_id = result.new_session_id
                state.universe_id = result.new_universe_id
                return result.narrative or "You step into an alternate timeline..."
            else:
                return f"Cannot fork timeline: {result.error}"

        # Process through game engine
        if state.session_id is None:
            return "No active session. Something went wrong."

        turn_result = await state.engine.process_turn(text, state.session_id)
        return self._format_turn_result(turn_result)

    def _format_turn_result(self, result: TurnResult) -> str:
        """Format a turn result for display."""
        parts = []

        # Main narrative
        parts.append(result.narrative)

        # Show rolls if any
        if result.rolls:
            parts.append("")
            for roll in result.rolls:
                roll_str = f"[{roll.description}: {roll.total}"
                if roll.modifier != 0:
                    sign = "+" if roll.modifier > 0 else ""
                    roll_str += f" ({roll.roll}{sign}{roll.modifier})"
                if roll.is_critical:
                    roll_str += " CRITICAL!"
                elif roll.is_fumble:
                    roll_str += " FUMBLE!"
                roll_str += "]"
                parts.append(roll_str)

        # Show state changes
        if result.state_changes:
            parts.append("")
            for change in result.state_changes:
                parts.append(f"* {change}")

        # Show any errors
        if result.error:
            parts.append(f"\n[Error: {result.error}]")

        return "\n".join(parts)

    def _print_banner(self) -> None:
        """Print the game banner."""
        banner = r"""
  _____ _____  _         ____        _
 |_   _|_   _|/ \       / ___|  ___ | | ___
   | |   | | / _ \ _____\___ \ / _ \| |/ _ \
   | |   | |/ ___ \_____|__) | (_) | | (_) |
   |_|   |_/_/   \_\    |____/ \___/|_|\___/

    The Text Adventure - Solo Edition
    An AI-Native Infinite Multiverse Engine
"""
        print(banner)
        print("Type /help for commands, or just describe your action.\n")

    def _create_demo_world(self, state: GameState) -> None:
        """Create a demo world for testing."""
        # Create Prime universe
        universe = Universe(
            name="Prime",
            description="The original timeline",
            dolt_branch="main",
        )
        state.engine.dolt.save_universe(universe)
        state.universe_id = universe.id

        # Create starting location
        tavern = create_location(
            name="The Rusty Dragon Inn",
            description="A cozy tavern with a roaring fireplace. The smell of ale and roasted meat fills the air.",
            universe_id=universe.id,
            danger_level=0,
            terrain="urban",
            tags=["inn", "tavern", "safe"],
        )
        state.engine.dolt.save_entity(tavern)
        state.location_id = tavern.id

        # Create player character
        character = create_character(
            name=state.character_name,
            description="A brave adventurer seeking fortune and glory.",
            universe_id=universe.id,
            hp_max=10,
            ac=14,
            abilities=AbilityScores.model_validate(
                {
                    "str": 14,
                    "dex": 12,
                    "con": 13,
                    "int": 10,
                    "wis": 11,
                    "cha": 10,
                }
            ),
        )
        character.current_location_id = tavern.id
        state.engine.dolt.save_entity(character)
        state.character_id = character.id

        # Create some NPCs
        bartender = create_character(
            name="Ameiko Kaijitsu",
            description="The friendly bartender and owner of the Rusty Dragon Inn.",
            universe_id=universe.id,
            hp_max=18,
            ac=12,
        )
        bartender.current_location_id = tavern.id
        state.engine.dolt.save_entity(bartender)

        mysterious_stranger = create_character(
            name="Hooded Stranger",
            description="A cloaked figure sitting in the corner, nursing a drink.",
            universe_id=universe.id,
            hp_max=30,
            ac=16,
        )
        mysterious_stranger.current_location_id = tavern.id
        state.engine.dolt.save_entity(mysterious_stranger)

    async def run(self, character_name: str = "Hero") -> None:
        """Run the interactive REPL."""
        # Initialize databases (in-memory for now)
        dolt = InMemoryDoltRepository()
        neo4j = InMemoryNeo4jRepository()

        # Create engine
        config = EngineConfig(
            tone=self.tone,
            verbosity=self.verbosity,
        )
        engine = GameEngine(
            dolt=dolt,
            neo4j=neo4j,
            config=config,
            use_agents=self.use_agents,
        )

        # Create game state
        state = GameState(
            engine=engine,
            character_name=character_name,
        )

        # Create demo world
        self._create_demo_world(state)

        # Start session
        if state.universe_id and state.character_id and state.location_id:
            session = await engine.start_session(
                universe_id=state.universe_id,
                character_id=state.character_id,
                location_id=state.location_id,
            )
            state.session_id = session.id

        # Print banner
        self._print_banner()

        # Initial look
        print(f"Welcome, {state.character_name}!")
        print()
        initial = await self._process_input("look around", state)
        print(initial)
        print()

        # Main loop
        while state.running:
            try:
                user_input = input("> ").strip()

                if not user_input:
                    continue

                response = await self._process_input(user_input, state)

                if response:
                    print()
                    print(response)
                    print()

            except KeyboardInterrupt:
                print("\n")
                state.running = False
            except EOFError:
                print("\n")
                state.running = False

        print("Thanks for playing!")


def run_game(
    character_name: str = "Hero",
    tone: str = "adventure",
    verbosity: str = "normal",
    use_agents: bool = False,
) -> None:
    """
    Run the TTA-Solo game.

    Args:
        character_name: Name for the player character
        tone: Narrative tone (adventure, dark, humorous)
        verbosity: Output verbosity (terse, normal, verbose)
        use_agents: Enable the agent system (Phase 3)
    """
    repl = GameREPL(
        tone=tone,
        verbosity=verbosity,
        use_agents=use_agents,
    )
    asyncio.run(repl.run(character_name))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="TTA-Solo Text Adventure")
    parser.add_argument("--name", default="Hero", help="Character name")
    parser.add_argument(
        "--tone",
        choices=["adventure", "dark", "humorous"],
        default="adventure",
        help="Narrative tone",
    )
    parser.add_argument(
        "--verbosity",
        choices=["terse", "normal", "verbose"],
        default="normal",
        help="Output verbosity",
    )
    parser.add_argument(
        "--agents",
        action="store_true",
        help="Enable agent system",
    )

    args = parser.parse_args()
    run_game(
        character_name=args.name,
        tone=args.tone,
        verbosity=args.verbosity,
        use_agents=args.agents,
    )
