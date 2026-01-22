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

from src.content import create_starter_world
from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.engine import GameEngine
from src.engine.models import EngineConfig, TurnResult
from src.services.npc import NPCService


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
            Command(
                name="inventory",
                aliases=["inv", "i"],
                description="Show your inventory",
                handler=self._cmd_inventory,
            ),
            Command(
                name="quests",
                aliases=["quest", "q"],
                description="Show your quests",
                handler=self._cmd_quests,
            ),
            Command(
                name="talk",
                aliases=["speak", "chat"],
                description="Talk to an NPC",
                handler=self._cmd_talk,
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

    def _cmd_inventory(self, state: GameState, args: list[str]) -> str | None:
        """Handle inventory command."""
        if state.character_id is None or state.universe_id is None:
            return "No character loaded."

        # Get inventory from context (already populated by engine)
        # We can get it by querying relationships directly
        inventory_rels = state.engine.neo4j.get_relationships(
            state.character_id,
            state.universe_id,
            relationship_type=None,  # Get all
        )
        
        # Filter for inventory relationships
        item_ids = []
        for rel in inventory_rels:
            if rel.relationship_type.value in ["CARRIES", "WIELDS", "WEARS", "OWNS"]:
                item_ids.append(rel.to_entity_id)
        
        if not item_ids:
            return "Your inventory is empty."

        lines = ["Inventory:", "-" * 40]

        # Get full entity details for each item
        equipped = []
        backpack = []
        
        for item_id in item_ids:
            item = state.engine.dolt.get_entity(item_id, state.universe_id)
            if item:
                # Check if equipped (would need equipped flag in future)
                # For now, just put everything in backpack
                backpack.append(item)

        if backpack:
            lines.append(f"  Backpack ({len(backpack)} items):")
            for item in backpack:
                # Group same items
                lines.append(f"    - {item.name}")
                if item.description and len(item.description) < 80:
                    lines.append(f"      {item.description}")
        else:
            lines.append("  Backpack: Empty")

        return "\n".join(lines)

    def _cmd_quests(self, state: GameState, args: list[str]) -> str | None:
        """Handle quests command."""
        if state.character_id is None or state.universe_id is None:
            return "No character loaded."

        from src.services.quest import QuestService

        quest_service = QuestService(state.engine.dolt, state.engine.neo4j)

        # Handle subcommands
        subcommand = args[0].lower() if args else "active"

        if subcommand == "completed":
            # Get completed quests - for now return empty since we need to filter by character
            return "You haven't completed any quests yet.\n(Quest tracking by character coming soon)"

        elif subcommand == "available":
            # Get available quests at current location
            quests = quest_service.get_available_quests(state.universe_id)
            if not quests:
                return "No quests available at this location."
            lines = ["Available Quests:", "-" * 40]
            for quest in quests:
                lines.append(f"  [ ] {quest.name}")
                if quest.description:
                    lines.append(f"      {quest.description}")
            return "\n".join(lines)

        else:  # Default: show active quests
            quests = quest_service.get_active_quests(state.universe_id)

            if not quests:
                return "You have no active quests.\n\nTry '/quests available' to see available quests."

            lines = ["Active Quests:", "-" * 40]
            for quest in quests:
                lines.append(f"  [!] {quest.name}")

                # Show objectives
                if quest.objectives:
                    completed = sum(1 for obj in quest.objectives if obj.completed)
                    total = len(quest.objectives)
                    lines.append(f"      Progress: {completed}/{total} objectives")

                    # Show first few objectives
                    for i, obj in enumerate(quest.objectives[:3]):
                        status = "[x]" if obj.completed else "[ ]"
                        lines.append(f"      {status} {obj.description}")

                # Show rewards
                if quest.rewards:
                    reward_strs = []
                    for reward in quest.rewards:
                        if reward.gold:
                            reward_strs.append(f"{reward.gold} gold")
                        if reward.item_id:
                            reward_strs.append("special item")
                    if reward_strs:
                        lines.append(f"      Reward: {', '.join(reward_strs)}")

                lines.append("")  # Blank line between quests

            lines.append("Type '/quests available' to see more quests.")
            return "\n".join(lines)

    def _cmd_talk(self, state: GameState, args: list[str]) -> str | None:
        """Handle talk command."""
        if state.character_id is None or state.universe_id is None or state.location_id is None:
            return "No active session."

        # Check if NPC name was provided
        if not args:
            # List NPCs at current location
            entities_at_location = state.engine.neo4j.get_relationships(
                state.location_id,
                state.universe_id,
                relationship_type="LOCATED_IN",
            )
            
            npcs = []
            for rel in entities_at_location:
                entity = state.engine.dolt.get_entity(rel.from_entity_id, state.universe_id)
                if entity and entity.type == "character" and entity.id != state.character_id:
                    npcs.append(entity.name)
            
            if not npcs:
                return "There's nobody here to talk to."
            
            return f"Who do you want to talk to?\n  " + "\n  ".join(npcs) + "\n\nUsage: /talk <name>"

        # Get NPC name from args
        npc_name = " ".join(args)
        
        # Find NPC at current location
        entities_at_location = state.engine.neo4j.get_relationships(
            state.location_id,
            state.universe_id,
            relationship_type="LOCATED_IN",
        )
        
        npc = None
        for rel in entities_at_location:
            entity = state.engine.dolt.get_entity(rel.from_entity_id, state.universe_id)
            if entity and entity.type == "character" and entity.name.lower() == npc_name.lower():
                npc = entity
                break
        
        if not npc:
            return f"I don't see '{npc_name}' here."

        # Get NPC profile
        from src.services.npc import NPCService
        
        npc_service = state.engine.npc_service  # Use the engine's npc_service
        profile = npc_service.get_profile(npc.id)
        
        if not profile:
            return f"{npc.name} doesn't seem interested in talking right now."

        # Generate greeting based on personality
        greeting = self._generate_greeting(npc, profile)
        
        # For now, return simple greeting (full conversation system would be more complex)
        lines = [
            f"You approach {npc.name}.",
            "",
            greeting,
            "",
            "(Conversation system coming soon - for now, NPCs just greet you!)",
            "",
            "Personality traits:",
        ]
        
        # Show personality
        traits = profile.traits
        lines.append(f"  Openness: {traits.openness}/100")
        lines.append(f"  Conscientiousness: {traits.conscientiousness}/100")
        lines.append(f"  Extraversion: {traits.extraversion}/100")
        lines.append(f"  Agreeableness: {traits.agreeableness}/100")
        lines.append(f"  Neuroticism: {traits.neuroticism}/100")
        
        if profile.speech_style:
            lines.append(f"\nSpeech style: {profile.speech_style}")
        
        return "\n".join(lines)

    def _generate_greeting(self, npc, profile) -> str:
        """Generate a greeting based on NPC personality."""
        traits = profile.traits
        
        # High extraversion = enthusiastic greeting
        if traits.extraversion > 70:
            greetings = [
                f'"{npc.name} beams at you. "Well hello there! What can I do for you today?"',
                f'"{npc.name} waves energetically. "Great to see you! Pull up a chair!"',
                f'"{npc.name} calls out cheerfully. "Welcome, welcome! Always glad to see a new face!"',
            ]
        # Low extraversion = reserved greeting
        elif traits.extraversion < 40:
            greetings = [
                f'{npc.name} nods quietly. "...Hello."',
                f'{npc.name} glances up briefly. "Yes?"',
                f'{npc.name} gives a slight acknowledgment. "What is it?"',
            ]
        # High agreeableness = warm greeting
        elif traits.agreeableness > 70:
            greetings = [
                f'{npc.name} smiles warmly. "Hello, friend. How may I help you?"',
                f'"{npc.name} greets you kindly. "Good to see you. What brings you here?"',
                f'{npc.name} looks up with a gentle expression. "Welcome. Please, come in."',
            ]
        # Default - neutral greeting
        else:
            greetings = [
                f'{npc.name} looks at you. "Yes?"',
                f'"{npc.name} acknowledges your presence. "What do you need?"',
                f'{npc.name} turns to face you. "You wanted something?"',
            ]
        
        import secrets
        return secrets.choice(greetings)

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

    def _create_demo_world(self, state: GameState, npc_service: NPCService) -> None:
        """Create a demo world using the starter world content."""
        result = create_starter_world(
            dolt=state.engine.dolt,
            neo4j=state.engine.neo4j,
            npc_service=npc_service,
            player_name=state.character_name,
        )

        state.universe_id = result.universe.id
        state.location_id = result.starting_location_id
        state.character_id = result.player_character_id

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

        # Create demo world using starter content
        self._create_demo_world(state, engine.npc_service)

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
