"""
Interactive REPL for TTA-Solo.

Provides a text-based interface for playing the game.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypedDict
from uuid import UUID

from src.content import create_starter_world
from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.engine import GameEngine
from src.engine.models import EngineConfig, TurnResult
from src.models.ability import (
    Ability,
    AbilitySource,
    DamageEffect,
    HealingEffect,
    MechanismType,
    Targeting,
    TargetingType,
)
from src.models.conversation import ConversationContext, DialogueOptions
from src.models.entity import Entity
from src.models.relationships import Relationship, RelationshipType
from src.models.resources import CooldownTracker, EntityResources, StressMomentumPool
from src.services.conversation import ConversationService
from src.services.npc import NPCService
from src.services.quest import QuestService
from src.skills.dice import roll_dice


class ExitInfo(TypedDict):
    """Information about a location exit."""

    id: UUID
    name: str


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
    resources: EntityResources | None = None
    """Character's resources and known abilities."""


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
            Command(
                name="go",
                aliases=["travel", "move"],
                description="Travel to a connected location",
                handler=self._cmd_go,
            ),
            Command(
                name="exits",
                aliases=["ex", "doors"],
                description="Show available exits",
                handler=self._cmd_exits,
            ),
            Command(
                name="use",
                aliases=["cast", "activate"],
                description="Use an ability",
                handler=self._cmd_use,
            ),
            Command(
                name="abilities",
                aliases=["spells", "skills", "powers"],
                description="Show your available abilities",
                handler=self._cmd_abilities,
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

        if subcommand == "accept":
            # Accept a quest
            if len(args) < 2:
                return "Usage: /quest accept <quest name>"
            quest_name = " ".join(args[1:])
            return self._accept_quest(state, quest_service, quest_name)

        elif subcommand == "abandon":
            # Abandon an active quest
            if len(args) < 2:
                return "Usage: /quest abandon <quest name>"
            quest_name = " ".join(args[1:])
            return self._abandon_quest(state, quest_service, quest_name)

        elif subcommand == "completed":
            # Get completed quests
            return (
                "You haven't completed any quests yet.\n(Quest tracking by character coming soon)"
            )

        elif subcommand == "available":
            # Get available quests at current location
            quests = quest_service.get_available_quests(state.universe_id)
            if not quests:
                return "No opportunities present themselves at the moment."

            lines = ["Available Opportunities:", "━" * 50, ""]

            for quest in quests:
                # IC: Show quest giver and hint
                if quest.giver_name:
                    lines.append(f"{quest.giver_name} seeks assistance...")
                else:
                    lines.append("An opportunity presents itself...")

                # Short description preview
                if quest.description:
                    preview = (
                        quest.description[:80] + "..."
                        if len(quest.description) > 80
                        else quest.description
                    )
                    lines.append(f'  "{preview}"')

                # OOC: Command hint
                # Simplified quest name for command (lowercase, no special chars)
                simple_name = quest.name.lower().split()[0]
                lines.append(f"  → /quest accept {simple_name}")
                lines.append("")

            return "\n".join(lines)

        else:  # Default: show active quests
            quests = quest_service.get_active_quests(state.universe_id)

            if not quests:
                return (
                    "You have no active quests.\n\nTry '/quests available' to find opportunities."
                )

            lines = ["Your Current Quests:", "━" * 50, ""]

            for quest in quests:
                # Quest title with symbol
                lines.append(f"📜 {quest.name}")

                # IC: Show quest giver
                if quest.giver_name:
                    lines.append(f"   Given by: {quest.giver_name}")

                lines.append("")

                # IC: Show objectives with natural language progress
                for obj in quest.objectives:
                    status = "✓" if obj.is_complete else "▸"

                    lines.append(f"   {status} {obj.description}")

                    # Show progress naturally
                    if obj.quantity_required > 1 and not obj.is_complete:
                        lines.append(
                            f"      Progress: {obj.quantity_current} of {obj.quantity_required}"
                        )

                # IC: Promised reward
                if quest.rewards:
                    reward_strs = []
                    if quest.rewards.gold:
                        reward_strs.append(f"~{quest.rewards.gold} gold")
                    if quest.rewards.experience:
                        reward_strs.append(f"~{quest.rewards.experience} experience")
                    if reward_strs:
                        lines.append("")
                        lines.append(f"   Upon completion: {', '.join(reward_strs)}")

                lines.append("")
                lines.append("━" * 50)
                lines.append("")

            # OOC: Helper text
            lines.append("Type '/quests available' to find more opportunities.")
            lines.append("Type '/quest abandon <name>' to give up on a quest.")

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

    def _cmd_go(self, state: GameState, args: list[str]) -> str | None:
        """Handle go command - travel to a connected location."""
        if state.character_id is None or state.universe_id is None or state.location_id is None:
            return "No active session."

        if not args:
            # Show available exits as help
            exits = self._get_location_exits(state)
            if not exits:
                return "There are no obvious exits from here."
            exit_list = ", ".join(exits.keys())
            return (
                f"Where do you want to go?\n\n"
                f"Available exits: {exit_list}\n\n"
                f"Usage: /go <destination>"
            )

        destination = " ".join(args).lower()

        # Get available exits
        exits = self._get_location_exits(state)

        if not exits:
            return "There are no exits from this location."

        # Try to match destination
        matched_exit = self._match_exit(destination, exits)

        if not matched_exit:
            exit_list = ", ".join(exits.keys())
            return f"Can't go '{destination}'.\n\nAvailable exits: {exit_list}"

        # Get destination info
        dest_id = exits[matched_exit]["id"]
        dest_name = exits[matched_exit]["name"]
        old_location_id = state.location_id

        # Update session location
        session = state.engine.get_session(state.session_id) if state.session_id else None
        if session:
            session.location_id = dest_id

        # Update state
        state.location_id = dest_id

        # Update player entity location in Dolt
        player = state.engine.dolt.get_entity(state.character_id, state.universe_id)
        if player:
            player.current_location_id = dest_id
            state.engine.dolt.save_entity(player)

        # Update LOCATED_IN relationship in Neo4j for data consistency
        # Remove old relationship
        old_rels = state.engine.neo4j.get_relationships(
            state.character_id,
            state.universe_id,
            relationship_type="LOCATED_IN",
        )
        for rel in old_rels:
            if rel.to_entity_id == old_location_id:
                state.engine.neo4j.delete_relationship(rel.id)

        # Create new relationship
        state.engine.neo4j.create_relationship(
            Relationship(
                universe_id=state.universe_id,
                from_entity_id=state.character_id,
                to_entity_id=dest_id,
                relationship_type=RelationshipType.LOCATED_IN,
            )
        )

        return f"You travel to {dest_name}.\n\nType /look to see your surroundings."

    def _cmd_exits(self, state: GameState, args: list[str]) -> str | None:
        """Handle exits command - show available exits."""
        if state.location_id is None or state.universe_id is None:
            return "No active session."

        exits = self._get_location_exits(state)

        if not exits:
            return "There are no obvious exits from here."

        lines = ["Available exits:", "-" * 30]
        for direction, info in exits.items():
            lines.append(f"  {direction} -> {info['name']}")

        lines.append("")
        lines.append("Use /go <exit> to travel.")

        return "\n".join(lines)

    def _get_location_exits(self, state: GameState) -> dict[str, ExitInfo]:
        """Get available exits from current location.

        Returns:
            Dict of exit_name -> ExitInfo with id and name.
        """
        if state.location_id is None or state.universe_id is None:
            return {}

        exits: dict[str, ExitInfo] = {}
        connected_rels = state.engine.neo4j.get_relationships(
            state.location_id,
            state.universe_id,
            relationship_type="CONNECTED_TO",
        )

        for rel in connected_rels:
            # Only use outgoing connections (from current location)
            if rel.from_entity_id != state.location_id:
                continue

            connected_location = state.engine.dolt.get_entity(rel.to_entity_id, state.universe_id)
            if connected_location:
                # Use description as exit name if available, otherwise location name
                exit_name = rel.description if rel.description else connected_location.name
                exits[exit_name.lower()] = {
                    "id": rel.to_entity_id,
                    "name": connected_location.name,
                }

        return exits

    def _match_exit(self, destination: str, exits: dict[str, ExitInfo]) -> str | None:
        """Match destination to an available exit (case-insensitive, prefix match).

        Uses prefix matching to avoid ambiguity (e.g., "north" won't match "northeast").

        Returns:
            Matched exit key or None if no match or ambiguous.
        """
        destination = destination.lower()

        # Try exact match first
        if destination in exits:
            return destination

        # Try prefix match on exit name
        matches = []
        for exit_name in exits:
            if exit_name.startswith(destination):
                matches.append(exit_name)

        # Also check against destination location names using prefix matching
        for exit_name, info in exits.items():
            dest_name = info["name"].lower()
            if dest_name.startswith(destination) and exit_name not in matches:
                matches.append(exit_name)

        # Return if exactly one match
        if len(matches) == 1:
            return matches[0]

        return None

    # =========================================================================
    # Ability Commands
    # =========================================================================

    def _cmd_use(self, state: GameState, args: list[str]) -> str | None:
        """Handle use command - activate an ability."""
        if state.character_id is None or state.universe_id is None:
            return "No active session."

        if state.resources is None:
            return "You have no abilities."

        if not args:
            return self._cmd_abilities(state, [])

        # Parse args: "/use fireball on goblin" or "/use healing word"
        ability_name, target_name = self._parse_use_args(args)

        # Look up ability
        ability = state.resources.get_ability(ability_name)
        if ability is None:
            available = ", ".join(state.resources.list_abilities())
            if available:
                return (
                    f"You don't know an ability called '{ability_name}'.\n\n"
                    f"Your abilities: {available}"
                )
            return f"You don't know an ability called '{ability_name}'."

        # Check and consume resources
        resource_result = self._check_ability_resources(state.resources, ability)
        if resource_result is not None:
            return resource_result

        # Resolve target
        target = self._resolve_ability_target(state, ability, target_name)

        # Execute the ability
        result = self._execute_ability(state, ability, target)
        return result

    def _cmd_abilities(self, state: GameState, args: list[str]) -> str | None:
        """Handle abilities command - show available abilities."""
        if state.resources is None or not state.resources.abilities:
            return "You have no abilities."

        lines = ["Your Abilities:", "-" * 40]

        for ability in state.resources.abilities:
            # Build ability description
            source_tag = f"[{ability.source.value}]"
            effect_parts = []

            if ability.damage:
                effect_parts.append(f"{ability.damage.dice} {ability.damage.damage_type}")
            if ability.healing:
                heal_str = ability.healing.dice or ""
                if ability.healing.flat_amount:
                    heal_str += f"+{ability.healing.flat_amount}"
                effect_parts.append(f"heal {heal_str}")

            effect_str = ", ".join(effect_parts) if effect_parts else "utility"

            # Resource cost
            cost_str = self._format_ability_cost(ability)

            lines.append(f"  {ability.name} {source_tag}")
            lines.append(f"    {ability.description}")
            lines.append(f"    Effect: {effect_str} | Cost: {cost_str}")
            lines.append("")

        # Show resource status
        lines.append("-" * 40)
        lines.append(self._format_resource_status(state.resources))
        lines.append("")
        lines.append("Use /use <ability> to activate.")

        return "\n".join(lines)

    def _parse_use_args(self, args: list[str]) -> tuple[str, str | None]:
        """Parse use command arguments into ability name and optional target."""
        # Look for "on" or "at" to split ability from target
        for i, word in enumerate(args):
            if word.lower() in ("on", "at"):
                ability_name = " ".join(args[:i])
                target_name = " ".join(args[i + 1 :])
                return ability_name, target_name if target_name else None

        # No target specified
        return " ".join(args), None

    def _check_ability_resources(self, resources: EntityResources, ability: Ability) -> str | None:
        """
        Check if character has resources for ability.

        Returns error message if not available, None if OK (and consumes resource).
        """
        mechanism = ability.mechanism
        details = ability.mechanism_details

        if mechanism == MechanismType.SLOTS:
            level = details.get("level", 1)
            if not resources.has_spell_slot(level):
                return f"Not enough spell slots. You need a level {level} slot."
            resources.use_spell_slot(level)

        elif mechanism == MechanismType.COOLDOWN:
            cooldown = resources.get_cooldown(ability.name)
            if cooldown is None:
                # Create cooldown tracker from ability details
                max_uses = details.get("max_uses", 1)
                recharge = details.get("recharge_on_rest", "long")
                from src.models.resources import CooldownTracker

                cooldown = CooldownTracker(
                    max_uses=max_uses, current_uses=max_uses, recharge_on_rest=recharge
                )
                resources.cooldowns[ability.name] = cooldown
            elif not cooldown.has_uses():
                return f"{ability.name} is on cooldown."
            else:
                cooldown.use()

        elif mechanism == MechanismType.MOMENTUM:
            cost = details.get("momentum_cost", 0)
            if resources.stress_momentum is None:
                return "You don't have a momentum pool."
            if not resources.stress_momentum.spend_momentum(cost):
                return (
                    f"Not enough momentum. Need {cost}, have {resources.stress_momentum.momentum}."
                )

        elif mechanism == MechanismType.STRESS:
            cost = details.get("stress_cost", 0)
            if resources.stress_momentum is None:
                return "You don't have a stress pool."
            resources.stress_momentum.add_stress(cost)

        # FREE or USAGE_DIE - allow
        return None

    def _resolve_ability_target(
        self, state: GameState, ability: Ability, target_name: str | None
    ) -> Entity | None:
        """Resolve target for ability."""
        if target_name is None:
            # Self-targeting abilities don't need explicit target
            if (
                ability.targeting.type == TargetingType.SELF
                and state.character_id
                and state.universe_id
            ):
                return state.engine.dolt.get_entity(state.character_id, state.universe_id)
            return None

        target_lower = target_name.lower()

        # Check for self-targeting
        if target_lower in ("myself", "self", "me"):
            if state.character_id and state.universe_id:
                return state.engine.dolt.get_entity(state.character_id, state.universe_id)
            return None

        # Find entity by name at current location
        if state.location_id and state.universe_id:
            located_rels = state.engine.neo4j.get_relationships(
                state.location_id,
                state.universe_id,
                relationship_type="LOCATED_IN",
            )
            for rel in located_rels:
                entity = state.engine.dolt.get_entity(rel.from_entity_id, state.universe_id)
                if entity and target_lower in entity.name.lower():
                    return entity

        return None

    def _execute_ability(self, state: GameState, ability: Ability, target: Entity | None) -> str:
        """Execute an ability and return the result description."""
        lines = []
        lines.append(f"You use {ability.name}!")

        # Roll for effect
        total_damage = 0
        total_healing = 0

        if ability.damage:
            damage_roll = self._roll_dice(ability.damage.dice)
            total_damage = damage_roll
            lines.append(f"  Damage: {damage_roll} {ability.damage.damage_type}")

            if target and target.stats:
                # Apply damage to target
                target.stats.hp_current = max(0, target.stats.hp_current - total_damage)
                state.engine.dolt.save_entity(target)
                if target.stats.hp_current <= 0:
                    lines.append(f"  {target.name} is defeated!")
                else:
                    lines.append(
                        f"  {target.name} takes {total_damage} damage! "
                        f"({target.stats.hp_current}/{target.stats.hp_max} HP)"
                    )

        if ability.healing:
            if ability.healing.dice:
                heal_roll = self._roll_dice(ability.healing.dice)
                if ability.healing.flat_amount:
                    heal_roll += ability.healing.flat_amount
                total_healing = heal_roll
            else:
                total_healing = ability.healing.flat_amount

            # Apply healing to self or target
            heal_target = target
            if not heal_target and state.character_id and state.universe_id:
                heal_target = state.engine.dolt.get_entity(state.character_id, state.universe_id)
            if heal_target and heal_target.stats:
                old_hp = heal_target.stats.hp_current
                heal_target.stats.hp_current = min(
                    heal_target.stats.hp_max, heal_target.stats.hp_current + total_healing
                )
                actual_heal = heal_target.stats.hp_current - old_hp
                state.engine.dolt.save_entity(heal_target)
                lines.append(
                    f"  Healing: {actual_heal} HP restored "
                    f"({heal_target.stats.hp_current}/{heal_target.stats.hp_max} HP)"
                )

        if ability.conditions:
            cond_names = [c.condition for c in ability.conditions]
            lines.append(f"  Conditions applied: {', '.join(cond_names)}")

        return "\n".join(lines)

    def _roll_dice(self, dice_str: str) -> int:
        """Roll dice from a string like '2d6' or '1d10+5'."""
        result = roll_dice(dice_str)
        return result.total

    def _format_ability_cost(self, ability: Ability) -> str:
        """Format ability cost for display."""
        mechanism = ability.mechanism
        details = ability.mechanism_details

        if mechanism == MechanismType.FREE:
            return "Free"
        elif mechanism == MechanismType.SLOTS:
            level = details.get("level", 1)
            return f"Level {level} spell slot"
        elif mechanism == MechanismType.COOLDOWN:
            max_uses = details.get("max_uses", 1)
            recharge = details.get("recharge_on_rest", "long")
            return f"{max_uses}/rest ({recharge})"
        elif mechanism == MechanismType.MOMENTUM:
            cost = details.get("momentum_cost", 0)
            return f"{cost} momentum"
        elif mechanism == MechanismType.STRESS:
            cost = details.get("stress_cost", 0)
            return f"{cost} stress"
        elif mechanism == MechanismType.USAGE_DIE:
            return "Usage die"
        return "Unknown"

    def _format_resource_status(self, resources: EntityResources) -> str:
        """Format current resource status."""
        parts = []

        if resources.spell_slots:
            slot_parts = []
            for level, tracker in sorted(resources.spell_slots.items()):
                slot_parts.append(f"{level}: {tracker.current_slots}/{tracker.max_slots}")
            parts.append(f"Spell Slots: {', '.join(slot_parts)}")

        if resources.stress_momentum:
            pool = resources.stress_momentum
            parts.append(f"Momentum: {pool.momentum}/{pool.momentum_max}")
            parts.append(f"Stress: {pool.stress}/{pool.stress_max}")

        return " | ".join(parts) if parts else "No tracked resources"

    def _create_starter_resources(self) -> EntityResources:
        """Create starter resources with basic abilities for new characters."""
        # Create a basic martial character setup
        second_wind = Ability(
            name="Second Wind",
            description="Draw on your stamina to heal yourself.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.COOLDOWN,
            mechanism_details={"max_uses": 1, "recharge_on_rest": "short"},
            healing=HealingEffect(dice="1d10", flat_amount=1),
            targeting=Targeting(type=TargetingType.SELF),
            action_cost="bonus",
        )

        power_strike = Ability(
            name="Power Strike",
            description="A powerful melee attack that deals extra damage.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.FREE,
            mechanism_details={},
            damage=DamageEffect(dice="1d8", damage_type="bludgeoning"),
            targeting=Targeting(type=TargetingType.SINGLE, range_ft=5),
            action_cost="action",
        )

        # Create resources with abilities and a stress/momentum pool
        resources = EntityResources(
            abilities=[second_wind, power_strike],
            stress_momentum=StressMomentumPool(),
            cooldowns={
                "Second Wind": CooldownTracker(max_uses=1, current_uses=1, recharge_on_rest="short")
            },
        )

        return resources

    def _accept_quest(self, state: GameState, quest_service: QuestService, quest_name: str) -> str:
        """Accept a quest by name."""
        if not state.universe_id:
            return "No active universe."

        # Find matching quest from available quests
        available = quest_service.get_available_quests(state.universe_id)
        quest = None

        quest_name_lower = quest_name.lower()
        for q in available:
            if q.name.lower() == quest_name_lower or quest_name_lower in q.name.lower():
                quest = q
                break

        if not quest:
            available_names = [q.name for q in available]
            if available_names:
                return (
                    f"No opportunity matches '{quest_name}'.\n\n"
                    f"Available: {', '.join(available_names)}"
                )
            return f"No opportunities available matching '{quest_name}'."

        # Accept the quest
        success = quest_service.accept_quest(quest.id)
        if not success:
            return f"Unable to accept: {quest.name}"

        # Show confirmation with IC framing
        lines = []

        # IC: Character accepts the task
        if quest.giver_name:
            lines.append(f"You accept the task from {quest.giver_name}.")
        else:
            lines.append("You set out to accomplish this task.")

        lines.append("")

        # IC: Quest giver's words (the description)
        if quest.description:
            # Wrap in quotes to show it's dialogue
            lines.append(f'"{quest.description}"')
            lines.append("")

        # Mixed IC/OOC: Mission objectives
        lines.append(f"Mission Accepted: {quest.name}")
        lines.append("━" * 50)

        for obj in quest.objectives:
            if obj.quantity_required > 1:
                lines.append(f"  ▸ {obj.description}")
                lines.append(f"    ({obj.quantity_required} required)")
            else:
                lines.append(f"  ▸ {obj.description}")

        # IC: Promised reward
        if quest.rewards:
            reward_strs = []
            if quest.rewards.gold:
                reward_strs.append(f"~{quest.rewards.gold} gold")
            if quest.rewards.experience:
                reward_strs.append(f"~{quest.rewards.experience} experience")
            if reward_strs:
                lines.append("")
                lines.append(f"  Promised reward: {', '.join(reward_strs)}")

        lines.append("")
        # OOC: Helper text in brackets
        lines.append("[Quest added to journal - /quests to review progress]")

        return "\n".join(lines)

    def _abandon_quest(self, state: GameState, quest_service: QuestService, quest_name: str) -> str:
        """Abandon an active quest by name."""
        if not state.universe_id:
            return "No active universe."

        # Find matching quest from active quests
        active = quest_service.get_active_quests(state.universe_id)
        quest = None

        quest_name_lower = quest_name.lower()
        for q in active:
            if q.name.lower() == quest_name_lower or quest_name_lower in q.name.lower():
                quest = q
                break

        if not quest:
            active_names = [q.name for q in active]
            if active_names:
                return (
                    f"Active quest '{quest_name}' not found.\n\n"
                    f"Active quests: {', '.join(active_names)}"
                )
            return f"You don't have an active quest named '{quest_name}'."

        # Abandon the quest
        success = quest_service.abandon_quest(quest.id)
        if not success:
            return f"Unable to abandon: {quest.name}"

        return f"You abandon your quest: {quest.name}\n\n[Removed from quest journal]"

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

        # Initialize character resources with starter abilities
        state.resources = self._create_starter_resources()

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
