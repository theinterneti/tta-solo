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
from src.models.conversation import ConversationContext, DialogueOptions
from src.models.entity import Entity
from src.services.conversation import ConversationService
from src.services.npc import NPCService
from src.services.quest import QuestService


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
    conversation: ConversationContext | None = None
    """Active conversation if in conversation mode."""
    pending_talk_npc: Entity | None = None
    """NPC that player wants to talk to (for async handler)."""


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
        self.conversation_service: ConversationService | None = None
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
            Command(
                name="abilities",
                aliases=["ab", "spells"],
                description="Show your abilities",
                handler=self._cmd_abilities,
            ),
            Command(
                name="shop",
                aliases=["store"],
                description="Browse items for sale",
                handler=self._cmd_shop,
            ),
            Command(
                name="sell",
                aliases=[],
                description="Sell an item from your inventory",
                handler=self._cmd_sell,
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
        """Handle look command - enhanced version with more details."""
        # Let the engine generate the base narrative through normal processing
        # But we'll return None so it goes through the engine, then we can enhance later
        # For now, the engine's look is already pretty good with NPCs and exits
        return None  # Let the engine handle it - already shows location, NPCs, exits

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
            # Format gold for display
            gold_copper = character.stats.gold_copper
            gold = gold_copper // 100
            silver = (gold_copper % 100) // 10
            cp = gold_copper % 10
            gold_parts = []
            if gold:
                gold_parts.append(f"{gold}gp")
            if silver:
                gold_parts.append(f"{silver}sp")
            if cp or not gold_parts:
                gold_parts.append(f"{cp}cp")
            gold_str = " ".join(gold_parts)

            lines.extend(
                [
                    f"  HP: {character.stats.hp_current}/{character.stats.hp_max}",
                    f"  AC: {character.stats.ac}",
                    f"  Level: {character.stats.level}",
                    f"  Gold: {gold_str}",
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

        quest_service = QuestService(state.engine.dolt, state.engine.neo4j)

        # Handle subcommands
        subcommand = args[0].lower() if args else "active"

        if subcommand == "completed":
            # Get completed quests - for now return empty since we need to filter by character
            return (
                "You haven't completed any quests yet.\n(Quest tracking by character coming soon)"
            )

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
                return (
                    "You have no active quests.\n\nTry '/quests available' to see available quests."
                )

            lines = ["Active Quests:", "-" * 40]
            for quest in quests:
                lines.append(f"  [!] {quest.name}")

                # Show objectives
                if quest.objectives:
                    completed = sum(1 for obj in quest.objectives if obj.is_complete)
                    total = len(quest.objectives)
                    lines.append(f"      Progress: {completed}/{total} objectives")

                    # Show first few objectives
                    for obj in quest.objectives[:3]:
                        status = "[x]" if obj.is_complete else "[ ]"
                        lines.append(f"      {status} {obj.description}")

                # Show rewards
                if quest.rewards:
                    reward_strs = []
                    if quest.rewards.gold:
                        reward_strs.append(f"{quest.rewards.gold} gold")
                    if quest.rewards.item_ids:
                        reward_strs.append("special item")
                    if reward_strs:
                        lines.append(f"      Reward: {', '.join(reward_strs)}")

                lines.append("")  # Blank line between quests

            lines.append("Type '/quests available' to see more quests.")
            return "\n".join(lines)

    def _cmd_talk(self, state: GameState, args: list[str]) -> str | None:
        """Handle talk command - starts a conversation with an NPC."""
        if state.character_id is None or state.universe_id is None or state.location_id is None:
            return "No active session."

        # Check if already in conversation
        if state.conversation is not None:
            return f"You're already talking to {state.conversation.npc_name}. Type [0] to end that conversation first."

        # Check if NPC name was provided
        if not args:
            # List NPCs at current location
            npcs = self._get_npcs_at_location(state)

            if not npcs:
                return "There's nobody here to talk to."

            npc_names = [name for _, name in npcs]
            return (
                "Who do you want to talk to?\n  "
                + "\n  ".join(npc_names)
                + "\n\nUsage: /talk <name>"
            )

        # Get NPC name from args
        npc_name = " ".join(args)

        # Find NPC at current location (partial match)
        npcs = self._get_npcs_at_location(state)

        npc = None
        for npc_id, name in npcs:
            if npc_name.lower() in name.lower():
                npc = state.engine.dolt.get_entity(npc_id, state.universe_id)
                break

        if not npc:
            return f"I don't see '{npc_name}' here."

        # Return None to let async handler take over
        # Store the NPC info for the async handler
        state.pending_talk_npc = npc
        return None

    async def _start_conversation(self, state: GameState, npc) -> str:
        """Start a conversation with an NPC (async version)."""
        if (
            self.conversation_service is None
            or state.character_id is None
            or state.universe_id is None
            or state.location_id is None
        ):
            return "Conversation service not available."

        # Start conversation
        context, greeting, options = await self.conversation_service.start_conversation(
            npc_id=npc.id,
            npc_name=npc.name,
            player_id=state.character_id,
            universe_id=state.universe_id,
            location_id=state.location_id,
        )

        # Store conversation context
        state.conversation = context

        # Format and return
        return self._format_conversation(npc.name, greeting, options)

    def _get_npcs_at_location(self, state: GameState) -> list[tuple[UUID, str]]:
        """Get NPCs at current location.

        Returns:
            List of (entity_id, name) tuples
        """
        if state.location_id is None or state.universe_id is None:
            return []

        # Assign to local vars for type narrowing
        location_id = state.location_id
        universe_id = state.universe_id

        entities_at_location = state.engine.neo4j.get_relationships(
            location_id,
            universe_id,
            relationship_type="LOCATED_IN",
        )

        npcs = []
        for rel in entities_at_location:
            entity = state.engine.dolt.get_entity(rel.from_entity_id, universe_id)
            if entity and entity.type == "character" and entity.id != state.character_id:
                npcs.append((entity.id, entity.name))

        return npcs

    def _format_conversation(
        self,
        npc_name: str,
        response: str,
        options: DialogueOptions | None,
    ) -> str:
        """Format conversation for display."""
        lines = [
            f"{npc_name}:",
            f'  "{response}"',
            "",
        ]

        if options:
            lines.append("What do you say?")
            for choice in options.choices:
                lines.append(f"  [{choice.id}] {choice.label}")
            if options.allows_custom_input:
                lines.append("  [*] Say something else...")
            lines.append("  [0] End conversation")

        return "\n".join(lines)

    async def _process_conversation_input(
        self,
        text: str,
        state: GameState,
    ) -> str:
        """Process input while in conversation mode."""
        if state.conversation is None or self.conversation_service is None:
            return "No active conversation."

        context = state.conversation

        # Handle exit
        if text == "0" or text.lower() in ["bye", "goodbye", "leave", "exit"]:
            farewell = self.conversation_service.end_conversation(context)
            state.conversation = None
            return f'\n{context.npc_name}:\n  "{farewell}"\n\nYou end your conversation with {context.npc_name}.'

        # Handle choice selection or custom input
        if text.isdigit():
            player_choice: int | str = int(text)
        else:
            player_choice = text

        response, options = await self.conversation_service.continue_conversation(
            context, player_choice
        )

        # Check if conversation ended
        if options is None:
            state.conversation = None
            return f'\n{context.npc_name}:\n  "{response}"\n\nYou end your conversation with {context.npc_name}.'

        return self._format_conversation(context.npc_name, response, options)

    def _cmd_abilities(self, state: GameState, args: list[str]) -> str | None:
        """Handle abilities command."""
        if state.character_id is None or state.universe_id is None:
            return "No character loaded."

        # Get character entity
        character = state.engine.dolt.get_entity(state.character_id, state.universe_id)
        if not character:
            return "Character not found."

        # For now, show a placeholder with explanation
        # In the future, this will query actual abilities from the character
        lines = [
            "Abilities:",
            "-" * 40,
            "",
            "(Ability system is implemented but your character doesn't have any abilities yet.)",
            "",
            "The ability system supports:",
            "  • Martial techniques (weapon skills, combat maneuvers)",
            "  • Spells (arcane, divine, primal magic)",
            "  • Tech abilities (gadgets, hacking, systems)",
            "",
            "When abilities are added to your character, they'll appear here with:",
            "  • Usage tracking (charges, spell slots, cooldowns)",
            "  • Detailed descriptions",
            "  • Targeting information",
            "  • Usage via /use <ability name>",
            "",
        ]

        # Show what resources the character has for abilities
        if character.stats:
            stats = character.stats
            lines.append("Your resources:")

            # Show level (determines proficiency bonus)
            if stats.level:
                prof_bonus = (stats.level - 1) // 4 + 2
                lines.append(f"  Level: {stats.level} (Proficiency: +{prof_bonus})")

            # Show ability modifiers that affect abilities
            if stats.abilities:
                lines.append("")
                lines.append("  Ability Modifiers:")
                for attr, val in stats.abilities.model_dump().items():
                    mod = (val - 10) // 2
                    sign = "+" if mod >= 0 else ""
                    attr_name = attr.upper().ljust(3)  # Left-justify to 3 chars
                    lines.append(f"    {attr_name}: {sign}{mod}")

        lines.append("")
        lines.append("Coming soon: Starter abilities will be added based on your character class!")

        return "\n".join(lines)

    def _cmd_shop(self, state: GameState, args: list[str]) -> str | None:
        """Handle shop/buy command - browse and purchase items from merchants."""
        if state.character_id is None or state.universe_id is None or state.location_id is None:
            return "No active session."

        # Get merchants at current location (NPCs with SELLS relationships)
        merchants = self._get_merchants_at_location(state)

        if not merchants:
            return "There are no merchants here."

        # If no arguments, list available merchants and their wares
        if not args:
            lines = ["Merchants:", "-" * 40]
            for _merchant_id, merchant_name, items_for_sale in merchants:
                lines.append(f"\n  {merchant_name}:")
                if items_for_sale:
                    for item_name, price_copper in items_for_sale:
                        price_str = self._format_price(price_copper)
                        lines.append(f"    - {item_name}: {price_str}")
                else:
                    lines.append("    (No items for sale)")
            lines.append("\nTo buy: /shop buy <item name>")
            return "\n".join(lines)

        # Handle buy subcommand
        if args[0].lower() == "buy" and len(args) > 1:
            item_name = " ".join(args[1:])
            return self._buy_item(state, item_name, merchants)

        return "Usage: /shop (list items) or /shop buy <item name>"

    def _get_merchants_at_location(
        self, state: GameState
    ) -> list[tuple[UUID, str, list[tuple[str, int]]]]:
        """Get merchants at current location with their items for sale.

        Returns:
            List of (merchant_id, merchant_name, [(item_name, price_copper), ...])
        """
        if state.location_id is None or state.universe_id is None:
            return []

        universe_id = state.universe_id

        # Get NPCs at location
        npcs = self._get_npcs_at_location(state)

        merchants = []
        for npc_id, npc_name in npcs:
            # Check if NPC has SELLS relationships
            sells_rels = state.engine.neo4j.get_relationships(
                npc_id,
                universe_id,
                relationship_type="SELLS",
            )
            if sells_rels:
                items_for_sale = []
                for rel in sells_rels:
                    item = state.engine.dolt.get_entity(rel.to_entity_id, universe_id)
                    if item and item.item_properties:
                        items_for_sale.append((item.name, item.item_properties.value_copper))
                merchants.append((npc_id, npc_name, items_for_sale))

        return merchants

    def _buy_item(
        self,
        state: GameState,
        item_name: str,
        merchants: list[tuple[UUID, str, list[tuple[str, int]]]],
    ) -> str:
        """Process a purchase transaction."""
        if state.character_id is None or state.universe_id is None:
            return "No active session."

        # Find the item across all merchants
        found_item = None
        found_merchant_name = None
        item_price = 0

        for merchant_id, merchant_name, items_for_sale in merchants:
            for name, price in items_for_sale:
                if name.lower() == item_name.lower():
                    # Get the actual item entity
                    sells_rels = state.engine.neo4j.get_relationships(
                        merchant_id,
                        state.universe_id,
                        relationship_type="SELLS",
                    )
                    for rel in sells_rels:
                        item = state.engine.dolt.get_entity(rel.to_entity_id, state.universe_id)
                        if item and item.name.lower() == item_name.lower():
                            found_item = item
                            found_merchant_name = merchant_name
                            item_price = price
                            break
                    break

        if not found_item:
            return f"No merchant here sells '{item_name}'."

        # Check player's gold
        player = state.engine.dolt.get_entity(state.character_id, state.universe_id)
        if not player or not player.stats:
            return "Could not find your character."

        player_gold = player.stats.gold_copper

        if player_gold < item_price:
            price_str = self._format_price(item_price)
            have_str = self._format_price(player_gold)
            return f"You can't afford {found_item.name}. It costs {price_str}, but you only have {have_str}."

        # Execute the purchase
        new_gold = player_gold - item_price
        player.stats.gold_copper = new_gold
        state.engine.dolt.save_entity(player)

        # Add item to player inventory (CARRIES relationship)
        from src.models.relationships import Relationship, RelationshipType

        state.engine.neo4j.create_relationship(
            Relationship(
                universe_id=state.universe_id,
                from_entity_id=state.character_id,
                to_entity_id=found_item.id,
                relationship_type=RelationshipType.CARRIES,
            )
        )

        price_str = self._format_price(item_price)
        remaining_str = self._format_price(new_gold)
        return (
            f"You bought {found_item.name} from {found_merchant_name} for {price_str}.\n"
            f"Remaining gold: {remaining_str}"
        )

    def _cmd_sell(self, state: GameState, args: list[str]) -> str | None:
        """Handle sell command - sell an item from inventory."""
        if state.character_id is None or state.universe_id is None or state.location_id is None:
            return "No active session."

        if not args:
            return "Usage: /sell <item name>\nSells item at 50% of its value."

        item_name = " ".join(args)

        # Check if there's a merchant here to sell to
        merchants = self._get_merchants_at_location(state)
        if not merchants:
            return "There are no merchants here to sell to."

        # Find item in player inventory
        inventory_rels = state.engine.neo4j.get_relationships(
            state.character_id,
            state.universe_id,
        )

        found_item = None
        found_rel = None
        for rel in inventory_rels:
            if rel.relationship_type.value in ["CARRIES", "WIELDS", "WEARS", "OWNS"]:
                item = state.engine.dolt.get_entity(rel.to_entity_id, state.universe_id)
                if item and item.name.lower() == item_name.lower():
                    found_item = item
                    found_rel = rel
                    break

        if not found_item or not found_rel:
            return f"You don't have '{item_name}' in your inventory."

        if not found_item.item_properties:
            return f"{found_item.name} cannot be sold."

        # Calculate sell price (50% of value)
        base_value = found_item.item_properties.value_copper
        sell_price = base_value // 2

        if sell_price == 0:
            return f"{found_item.name} has no value."

        # Execute the sale
        player = state.engine.dolt.get_entity(state.character_id, state.universe_id)
        if not player or not player.stats:
            return "Could not find your character."

        # Add gold
        player.stats.gold_copper += sell_price
        state.engine.dolt.save_entity(player)

        # Remove item from inventory (delete the relationship)
        state.engine.neo4j.delete_relationship(found_rel.id)

        price_str = self._format_price(sell_price)
        new_gold_str = self._format_price(player.stats.gold_copper)
        return f"You sold {found_item.name} for {price_str}.\nYou now have: {new_gold_str}"

    def _format_price(self, copper: int) -> str:
        """Format copper amount as gold/silver/copper string."""
        gold = copper // 100
        silver = (copper % 100) // 10
        cp = copper % 10

        parts = []
        if gold:
            parts.append(f"{gold}gp")
        if silver:
            parts.append(f"{silver}sp")
        if cp or not parts:
            parts.append(f"{cp}cp")

        return " ".join(parts)

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

        # Check if in conversation mode
        if state.conversation is not None:
            return await self._process_conversation_input(text, state)

        # Handle special commands
        if self._is_command(text):
            cmd_name, args = self._parse_command(text)
            if cmd_name in self.commands:
                result = self.commands[cmd_name].handler(state, args)
                if result is not None:
                    return result
                # Check if talk command wants to start a conversation
                if cmd_name == "talk" and state.pending_talk_npc is not None:
                    npc = state.pending_talk_npc
                    state.pending_talk_npc = None
                    return await self._start_conversation(state, npc)
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

        # Sync GameState with session (location may have changed)
        session = state.engine.get_session(state.session_id)
        if session:
            state.location_id = session.location_id

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

        # Initialize conversation service
        self.conversation_service = ConversationService(
            dolt=dolt,
            neo4j=neo4j,
            npc_service=engine.npc_service,
            llm=None,  # LLM integration can be added via set_llm_service
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
                # Show different prompt when in conversation
                if state.conversation is not None:
                    prompt = f"[talking to {state.conversation.npc_name}] > "
                else:
                    prompt = "> "

                user_input = input(prompt).strip()

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
