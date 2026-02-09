"""
Interactive REPL for TTA-Solo.

Provides a text-based interface for playing the game.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypedDict
from uuid import UUID, uuid4

from src.content import UNIVERSE_TEMPLATES, create_starter_world, get_template_by_index
from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.engine import GameEngine
from src.engine.models import EngineConfig, TurnResult
from src.models.ability import (
    Ability,
    AbilitySource,
    ConditionEffect,
    DamageEffect,
    HealingEffect,
    MechanismType,
    StatModifierEffect,
    Targeting,
    TargetingType,
)
from src.models.condition import ActiveEffect, DurationType, ModifierType
from src.models.conversation import ConversationContext, DialogueOptions
from src.models.entity import Entity, EntityType
from src.models.relationships import Relationship, RelationshipType
from src.models.resources import CooldownTracker, EntityResources, StressMomentumPool
from src.services.conversation import ConversationService
from src.services.npc import NPCService
from src.services.quest import QuestService
from src.services.universe_generator import UniverseGenerator
from src.skills.combat import Abilities as CombatAbilities
from src.skills.combat import Combatant, Weapon, WeaponProperty, resolve_attack
from src.skills.dice import roll_dice
from src.skills.solo_combat import defy_death, resolve_solo_round_start


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
    defy_death_uses: int = 0
    """Number of Defy Death saves used today."""
    active_effects: list[ActiveEffect] = field(default_factory=list)
    """Active stat modifier effects (e.g., +2 AC from Brace for Impact)."""
    world_context: dict = field(default_factory=dict)
    """LLM-generated world context for downstream prompts."""


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
            Command(
                name="attack",
                aliases=["fight", "hit"],
                description="Attack an enemy",
                handler=self._cmd_attack,
            ),
            Command(
                name="defend",
                aliases=["dodge", "block"],
                description="Take a defensive stance (enemies attack at disadvantage)",
                handler=self._cmd_defend,
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
        if state.location_id is None or state.universe_id is None:
            return "You're nowhere. Something is wrong."

        location = state.engine.dolt.get_entity(state.location_id, state.universe_id)
        if not location:
            return "You can't see anything."

        lines = [location.name, "=" * len(location.name), ""]

        if location.description:
            lines.append(location.description)
            lines.append("")

        # Show NPCs (non-hostile)
        npcs = self._get_npcs_at_location(state)
        if npcs:
            lines.append("People here:")
            for _, npc_name in npcs:
                lines.append(f"  - {npc_name}")
            lines.append("")

        # Show enemies
        enemies = self._get_enemies_at_location(state)
        if enemies:
            lines.append("Enemies:")
            for enemy in enemies:
                hp_status = (
                    f"({enemy.stats.hp_current}/{enemy.stats.hp_max} HP)" if enemy.stats else ""
                )
                lines.append(f"  - {enemy.name} {hp_status}")
            lines.append("")

        # Show exits
        exits = self._get_location_exits(state)
        if exits:
            lines.append("Exits:")
            for direction, info in exits.items():
                lines.append(f"  {direction} -> {info['name']}")

        return "\n".join(lines)

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

            ac_mod = self._get_ac_modifier(state)
            ac_display = character.stats.ac + ac_mod
            ac_str = str(ac_display)
            if ac_mod != 0:
                sign = "+" if ac_mod > 0 else ""
                ac_str = f"{ac_display} ({character.stats.ac}{sign}{ac_mod})"

            lines.extend(
                [
                    f"  HP: {character.stats.hp_current}/{character.stats.hp_max}",
                    f"  AC: {ac_str}",
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
                # Create a simple slug from quest name (avoid articles)
                words = quest.name.lower().split()
                # Skip common articles
                simple_name = next((w for w in words if w not in ("a", "an", "the")), words[0])
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
            # Handle both relationship directions (in-memory vs real Neo4j may differ)
            if rel.from_entity_id == location_id:
                other_entity_id = rel.to_entity_id
            elif rel.to_entity_id == location_id:
                other_entity_id = rel.from_entity_id
            else:
                continue  # Relationship doesn't involve this location

            entity = state.engine.dolt.get_entity(other_entity_id, universe_id)
            if entity and entity.type == "character" and entity.id != state.character_id:
                # Skip hostile entities - they show under "Enemies" instead
                if entity.tags and any(t in entity.tags for t in ["enemy", "hostile"]):
                    continue
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
            npc_id = context.npc_id  # Save before clearing context
            state.conversation = None
            quest_notification = self._check_quest_progress(state, "dialogue", npc_id)
            return f'\n{context.npc_name}:\n  "{farewell}"\n\nYou end your conversation with {context.npc_name}.{quest_notification}'

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
            npc_id = context.npc_id  # Save before clearing context
            state.conversation = None
            quest_notification = self._check_quest_progress(state, "dialogue", npc_id)
            return f'\n{context.npc_name}:\n  "{response}"\n\nYou end your conversation with {context.npc_name}.{quest_notification}'

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

        # Check location-based quest objectives
        quest_notification = self._check_quest_progress(state, "location", dest_id)

        return f"You travel to {dest_name}.\n\nType /look to see your surroundings.{quest_notification}"

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
            if ability.stat_modifiers:
                for mod in ability.stat_modifiers:
                    sign = "+" if mod.modifier > 0 else ""
                    effect_parts.append(f"{sign}{mod.modifier} {mod.stat.upper()}")
            if ability.conditions:
                for cond in ability.conditions:
                    effect_parts.append(cond.condition)
            if "stress" in ability.tags:
                effect_parts.append("-1 stress")
            if "movement" in ability.tags:
                effect_parts.append("safe movement")

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

        # Handle stat modifiers (e.g., Brace for Impact's +2 AC)
        if ability.stat_modifiers and state.character_id and state.universe_id:
            for mod in ability.stat_modifiers:
                sign = "+" if mod.modifier > 0 else ""
                duration = ""
                dur_type = DurationType.ROUNDS
                dur_remaining = mod.duration_value
                if mod.duration_type == "rounds" and mod.duration_value:
                    duration = (
                        f" for {mod.duration_value} round{'s' if mod.duration_value > 1 else ''}"
                    )
                elif mod.duration_type == "concentration":
                    duration = " (concentration)"
                    dur_type = DurationType.CONCENTRATION
                    dur_remaining = None

                # Persist the effect so it applies in combat calculations
                effect = ActiveEffect(
                    id=uuid4(),
                    entity_id=state.character_id,
                    universe_id=state.universe_id,
                    stat=mod.stat,
                    modifier=mod.modifier,
                    modifier_type=ModifierType.BONUS if mod.modifier > 0 else ModifierType.PENALTY,
                    duration_type=dur_type,
                    duration_remaining=dur_remaining,
                    requires_concentration=(mod.duration_type == "concentration"),
                )
                state.active_effects.append(effect)

                lines.append(f"  {mod.stat.upper()} {sign}{mod.modifier}{duration}")

        # Handle stress recovery (Rally ability)
        if "stress" in ability.tags and state.resources and state.resources.stress_momentum:
            pool = state.resources.stress_momentum
            if pool.stress > 0:
                reduced = pool.reduce_stress(1)
                lines.append(
                    f"  Stress reduced by {reduced}! (Stress: {pool.stress}/{pool.stress_max})"
                )
            else:
                lines.append("  You're already calm and focused.")

        # Handle damage abilities
        if ability.damage:
            damage_roll = self._roll_dice(ability.damage.dice)
            lines.append(f"  Damage: {damage_roll} {ability.damage.damage_type}")

            # For multi-target abilities (like Cleave), get multiple targets
            if ability.targeting.type == TargetingType.MULTIPLE:
                targets = self._get_multiple_targets(state, ability.targeting.max_targets or 2)
                if targets:
                    for t in targets:
                        if t.stats:
                            t.stats.hp_current = max(0, t.stats.hp_current - damage_roll)
                            state.engine.dolt.save_entity(t)
                            if t.stats.hp_current <= 0:
                                lines.append(f"  {t.name} is defeated!")
                                self._remove_entity_from_location(state, t)
                                loot_note = self._grant_combat_rewards(state, t)
                                if loot_note:
                                    lines.append(f"  {loot_note}")
                                quest_note = self._check_quest_progress(state, "defeat", t.id)
                                if quest_note:
                                    lines.append(f"  {quest_note}")
                            else:
                                lines.append(
                                    f"  {t.name} takes {damage_roll} damage! "
                                    f"({t.stats.hp_current}/{t.stats.hp_max} HP)"
                                )
                else:
                    lines.append("  No enemies in range!")
            elif target and target.stats:
                # Single target damage
                target.stats.hp_current = max(0, target.stats.hp_current - damage_roll)
                state.engine.dolt.save_entity(target)
                if target.stats.hp_current <= 0:
                    lines.append(f"  {target.name} is defeated!")
                    self._remove_entity_from_location(state, target)
                    loot_note = self._grant_combat_rewards(state, target)
                    if loot_note:
                        lines.append(f"  {loot_note}")
                    quest_note = self._check_quest_progress(state, "defeat", target.id)
                    if quest_note:
                        lines.append(f"  {quest_note}")
                else:
                    lines.append(
                        f"  {target.name} takes {damage_roll} damage! "
                        f"({target.stats.hp_current}/{target.stats.hp_max} HP)"
                    )

        # Handle healing abilities
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

        # Handle conditions (Cheap Shot's stun, etc.)
        if ability.conditions and target:
            for cond in ability.conditions:
                duration_str = ""
                if cond.duration_type == "rounds" and cond.duration_value:
                    duration_str = (
                        f" for {cond.duration_value} round{'s' if cond.duration_value > 1 else ''}"
                    )
                elif cond.duration_type == "until_save":
                    duration_str = " (save ends)"
                lines.append(f"  {target.name} is {cond.condition}{duration_str}!")
        elif ability.conditions:
            # No target specified for condition ability
            cond_names = [c.condition for c in ability.conditions]
            lines.append(f"  Effect: {', '.join(cond_names)}")

        # Handle movement/utility abilities (Disengage, etc.)
        if "movement" in ability.tags:
            lines.append("  You can move freely without provoking opportunity attacks this turn.")

        return "\n".join(lines)

    def _get_multiple_targets(self, state: GameState, max_targets: int) -> list[Entity]:
        """Get multiple enemy targets for AoE abilities like Cleave."""
        enemies = self._get_enemies_at_location(state)
        return enemies[:max_targets]

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

    # =========================================================================
    # Combat Commands
    # =========================================================================

    def _cmd_attack(self, state: GameState, args: list[str]) -> str | None:
        """Handle attack command - full combat round against an enemy."""
        if state.character_id is None or state.universe_id is None or state.location_id is None:
            return "No active session."

        if not args:
            return "Attack whom? Usage: /attack <target>"

        target_name = " ".join(args).lower()

        # Find hostile entities at current location
        enemies = self._get_enemies_at_location(state)
        if not enemies:
            return "There are no enemies here to attack."

        # Match target by name
        target = None
        for enemy in enemies:
            if target_name in enemy.name.lower():
                target = enemy
                break

        if not target:
            enemy_names = [e.name for e in enemies]
            return f"No enemy matching '{target_name}'. Enemies here: {', '.join(enemy_names)}"

        lines: list[str] = []

        # 1. Round start: momentum + fray die
        round_start_lines = self._process_round_start(state, enemies)
        lines.extend(round_start_lines)

        # Re-check target is still alive (fray die may have killed it)
        target_entity = state.engine.dolt.get_entity(target.id, state.universe_id)
        if not target_entity or not target_entity.stats or target_entity.stats.hp_current <= 0:
            # Target was killed by fray die
            if lines:
                lines.append("")
            # Still process enemy turns if any survive
            surviving = self._get_enemies_at_location(state)
            if surviving:
                enemy_lines = self._process_enemy_turns(state, surviving)
                lines.extend(enemy_lines)
            lines.append(self._format_combat_status(state))
            return "\n".join(lines)

        # 2. Player attack
        if lines:
            lines.append("")

        weapon = self._get_player_weapon(state)
        player = state.engine.dolt.get_entity(state.character_id, state.universe_id)
        if not player:
            return "Could not find your character."

        ac_mod = self._get_ac_modifier(state)
        attacker = self._entity_to_combatant(player, ac_modifier=ac_mod)
        defender = self._entity_to_combatant(target_entity)

        result = resolve_attack(attacker, defender, weapon)

        if result.critical:
            lines.append(
                f"Critical hit! You strike {target_entity.name} for {result.damage} "
                f"{result.damage_type} damage!"
            )
        elif result.hit:
            lines.append(
                f"You hit {target_entity.name} for {result.damage} {result.damage_type} damage!"
            )
        elif result.fumble:
            lines.append(f"You swing wildly and miss {target_entity.name} completely!")
        else:
            lines.append(
                f"Your attack misses {target_entity.name}. "
                f"(Rolled {result.total_attack} vs AC {result.target_ac})"
            )

        # Apply damage if hit
        if result.hit and result.damage and target_entity.stats:
            target_entity.stats.hp_current -= result.damage
            state.engine.dolt.save_entity(target_entity)

            if target_entity.stats.hp_current <= 0:
                lines.append(f"{target_entity.name} falls defeated!")
                self._remove_entity_from_location(state, target_entity)
                loot_note = self._grant_combat_rewards(state, target_entity)
                if loot_note:
                    lines.append(loot_note)
                quest_notification = self._check_quest_progress(state, "defeat", target_entity.id)
                if quest_notification:
                    lines.append(quest_notification)
            else:
                lines.append(
                    f"{target_entity.name} has {target_entity.stats.hp_current}/"
                    f"{target_entity.stats.hp_max} HP remaining."
                )

        # 3. Enemy counterattacks
        surviving = self._get_enemies_at_location(state)
        if surviving:
            lines.append("")
            enemy_lines = self._process_enemy_turns(state, surviving)
            lines.extend(enemy_lines)

        # 4. Combat status line
        lines.append(self._format_combat_status(state))

        return "\n".join(lines)

    def _cmd_defend(self, state: GameState, args: list[str]) -> str | None:
        """Handle defend command - take a defensive stance, enemies attack at disadvantage."""
        if state.character_id is None or state.universe_id is None or state.location_id is None:
            return "No active session."

        enemies = self._get_enemies_at_location(state)
        if not enemies:
            return "There are no enemies here. You lower your guard."

        lines: list[str] = ["You take a defensive stance, ready to dodge and parry.", ""]

        # Process enemy turns with disadvantage
        enemy_lines = self._process_enemy_turns(state, enemies, disadvantage=True)
        lines.extend(enemy_lines)

        # Combat status line
        lines.append(self._format_combat_status(state))

        return "\n".join(lines)

    def _get_enemies_at_location(self, state: GameState) -> list[Entity]:
        """Get hostile entities at player's current location."""
        if not state.location_id or not state.universe_id:
            return []

        # Get all entities at location via LOCATED_IN relationships
        relationships = state.engine.neo4j.get_relationships(
            state.location_id,
            state.universe_id,
            relationship_type="LOCATED_IN",
        )

        enemies = []
        for rel in relationships:
            # Handle both relationship directions (in-memory vs real Neo4j may differ)
            if rel.from_entity_id == state.location_id:
                other_entity_id = rel.to_entity_id
            elif rel.to_entity_id == state.location_id:
                other_entity_id = rel.from_entity_id
            else:
                continue  # Relationship doesn't involve this location

            entity = state.engine.dolt.get_entity(other_entity_id, state.universe_id)
            # Check: is character, not player, hostile, and alive
            if (
                entity
                and entity.type == EntityType.CHARACTER
                and entity.id != state.character_id
                and entity.tags
                and any(t in entity.tags for t in ["enemy", "hostile"])
                and entity.stats
                and entity.stats.hp_current > 0
            ):
                enemies.append(entity)

        return enemies

    def _get_ac_modifier(self, state: GameState) -> int:
        """Get total AC modifier from active effects."""
        total = 0
        for effect in state.active_effects:
            if effect.stat == "ac":
                if effect.modifier_type == ModifierType.BONUS:
                    total += effect.modifier
                elif effect.modifier_type == ModifierType.PENALTY:
                    total -= effect.modifier
        return total

    def _tick_active_effects(self, state: GameState) -> list[str]:
        """Tick all active effects and return messages for expired ones."""
        expired_msgs = []
        remaining = []
        for effect in state.active_effects:
            if effect.tick():
                expired_msgs.append(f"  {effect.stat.upper()} modifier expired.")
            else:
                remaining.append(effect)
        state.active_effects = remaining
        return expired_msgs

    def _entity_to_combatant(self, entity: Entity, *, ac_modifier: int = 0) -> Combatant:
        """Convert Entity to Combatant for combat resolution."""
        stats = entity.stats
        if not stats:
            return Combatant(name=entity.name)

        return Combatant(
            name=entity.name,
            ac=stats.ac + ac_modifier,
            abilities=CombatAbilities(
                str=stats.abilities.str_,
                dex=stats.abilities.dex,
                con=stats.abilities.con,
                int=stats.abilities.int_,
                wis=stats.abilities.wis,
                cha=stats.abilities.cha,
            ),
            proficiency_bonus=stats.proficiency_bonus,
            proficient_weapons=["shortsword", "longsword"],  # Default
        )

    def _get_player_weapon(self, state: GameState) -> Weapon:
        """Get player's equipped weapon or default."""
        # Default: Rusty Shortsword from starter inventory
        return Weapon(
            name="Rusty Shortsword",
            damage_dice="1d6",
            damage_type="slashing",
            properties=[WeaponProperty.FINESSE, WeaponProperty.LIGHT],
        )

    def _get_enemy_weapon(self, entity: Entity) -> Weapon:
        """Get weapon for an enemy entity."""
        # SRD Goblin: Scimitar
        if entity.tags and "goblin" in entity.tags:
            return Weapon(
                name="Scimitar",
                damage_dice="1d6",
                damage_type="slashing",
                properties=[WeaponProperty.FINESSE, WeaponProperty.LIGHT],
            )
        # Default: basic melee
        return Weapon(
            name="Claws",
            damage_dice="1d4",
            damage_type="slashing",
            properties=[],
        )

    def _process_round_start(self, state: GameState, enemies: list[Entity]) -> list[str]:
        """Process solo round start: momentum gain + fray die."""
        if not state.resources or not state.resources.stress_momentum:
            return []
        if not state.character_id or not state.universe_id:
            return []

        character_id = state.character_id
        universe_id = state.universe_id
        pool = state.resources.stress_momentum

        # Build enemy list for fray die: (entity_id, hit_dice)
        enemy_tuples: list[tuple[UUID, int]] = []
        for e in enemies:
            hd = e.stats.level if e.stats else 1
            enemy_tuples.append((e.id, hd))

        # Get player level
        player = state.engine.dolt.get_entity(character_id, universe_id)
        actor_level = player.stats.level if player and player.stats else 1

        result, new_momentum = resolve_solo_round_start(
            actor_level, enemy_tuples, pool.momentum, pool.momentum_max
        )
        pool.momentum = new_momentum

        lines: list[str] = []
        if result.momentum_gained > 0:
            lines.append(f"[Combat flow: +{result.momentum_gained} momentum]")

        # Apply fray die damage to actual entities
        if result.fray_result and result.fray_result.damage > 0:
            for target_id_str, dmg in result.fray_result.damage_per_target.items():
                fray_target = state.engine.dolt.get_entity(UUID(target_id_str), universe_id)
                if fray_target and fray_target.stats:
                    fray_target.stats.hp_current -= dmg
                    state.engine.dolt.save_entity(fray_target)
                    if fray_target.stats.hp_current <= 0:
                        lines.append(
                            f"Your fighting spirit fells {fray_target.name}! (Fray: {dmg} damage)"
                        )
                        self._remove_entity_from_location(state, fray_target)
                        loot_note = self._grant_combat_rewards(state, fray_target)
                        if loot_note:
                            lines.append(loot_note)
                        quest_note = self._check_quest_progress(state, "defeat", fray_target.id)
                        if quest_note:
                            lines.append(quest_note)
                    else:
                        lines.append(
                            f"Your presence wounds {fray_target.name}! (Fray: {dmg} damage)"
                        )

        return lines

    def _process_enemy_turns(
        self, state: GameState, enemies: list[Entity], disadvantage: bool = False
    ) -> list[str]:
        """Process enemy counterattacks against the player."""
        if not state.character_id or not state.universe_id:
            return []
        player = state.engine.dolt.get_entity(state.character_id, state.universe_id)
        if not player or not player.stats:
            return []

        ac_mod = self._get_ac_modifier(state)
        defender = self._entity_to_combatant(player, ac_modifier=ac_mod)
        lines: list[str] = []

        for enemy in enemies:
            attacker = self._entity_to_combatant(enemy)
            weapon = self._get_enemy_weapon(enemy)
            result = resolve_attack(attacker, defender, weapon, disadvantage=disadvantage)

            if result.critical:
                lines.append(
                    f"{enemy.name} scores a critical hit for {result.damage} "
                    f"{result.damage_type} damage!"
                )
            elif result.hit:
                lines.append(
                    f"{enemy.name} hits you for {result.damage} {result.damage_type} damage!"
                )
            else:
                lines.append(f"{enemy.name} attacks but misses.")

            # Apply damage
            if result.hit and result.damage:
                player.stats.hp_current -= result.damage

                # Add stress when taking damage
                if state.resources and state.resources.stress_momentum:
                    state.resources.stress_momentum.add_stress(1)

                # Check for Defy Death
                if player.stats.hp_current <= 0:
                    defy_lines = self._process_defy_death(state, player, result.damage)
                    lines.extend(defy_lines)

                # Always persist HP changes (including death) before possibly breaking
                state.engine.dolt.save_entity(player)

                if player.stats.hp_current <= 0:
                    break  # Player is dead, stop enemy turns

        # Tick active effects at end of round
        expired_msgs = self._tick_active_effects(state)
        lines.extend(expired_msgs)

        return lines

    def _process_defy_death(
        self, state: GameState, player: Entity, damage_this_round: int
    ) -> list[str]:
        """Process Defy Death when player reaches 0 HP."""
        if not player.stats:
            return []

        con_mod = (player.stats.abilities.con - 10) // 2

        result = defy_death(con_mod, damage_this_round, state.defy_death_uses)

        lines: list[str] = []
        if result.survived:
            player.stats.hp_current = 1
            state.defy_death_uses += 1
            if result.is_nat_20:
                lines.append("NATURAL 20! You defy death spectacularly! (1 HP)")
            else:
                lines.append(f"You defy death! (Rolled {result.total} vs DC {result.dc}) (1 HP)")
            if result.exhaustion_gained:
                lines.append("You gain 1 level of exhaustion.")
            lines.append(f"[Defy Death uses remaining: {result.uses_remaining}]")
        else:
            if result.is_nat_1:
                lines.append("Natural 1... You cannot escape death this time.")
            else:
                lines.append(f"You fall in battle. (Rolled {result.total} vs DC {result.dc})")
            lines.append("Your vision fades to black...")

        return lines

    def _format_combat_status(self, state: GameState) -> str:
        """Format combat status line."""
        parts: list[str] = []

        if not state.character_id or not state.universe_id:
            return "\n[No character data]"
        player = state.engine.dolt.get_entity(state.character_id, state.universe_id)
        if player and player.stats:
            parts.append(f"HP: {player.stats.hp_current}/{player.stats.hp_max}")

        if state.resources and state.resources.stress_momentum:
            pool = state.resources.stress_momentum
            parts.append(f"Momentum: {pool.momentum}/{pool.momentum_max}")
            if pool.stress > 0:
                parts.append(f"Stress: {pool.stress}/{pool.stress_max}")

        enemies = self._get_enemies_at_location(state)
        if enemies:
            parts.append(f"Enemies: {len(enemies)} remaining")

        return f"\n[{' | '.join(parts)}]"

    def _grant_combat_rewards(self, state: GameState, defeated: Entity) -> str | None:
        """Grant gold loot when an enemy is defeated. Returns notification or None."""
        if not state.character_id or not state.universe_id:
            return None

        # Determine gold drop based on enemy type
        if defeated.tags and "goblin" in defeated.tags:
            # Goblin loot: 1d4+2 gp (3-6gp each, ~13.5gp for 3 goblins)
            gold_roll = roll_dice("1d4+2")
            gold_copper = gold_roll.total * 100
        else:
            # Default loot: 1d6 sp
            gold_roll = roll_dice("1d6")
            gold_copper = gold_roll.total * 10

        if gold_copper <= 0:
            return None

        player = state.engine.dolt.get_entity(state.character_id, state.universe_id)
        if not player or not player.stats:
            return None

        player.stats.gold_copper += gold_copper
        state.engine.dolt.save_entity(player)

        return f"[Loot: {self._format_price(gold_copper)}]"

    def _remove_entity_from_location(self, state: GameState, entity: Entity) -> None:
        """Remove defeated entity from location."""
        if not state.location_id or not state.universe_id:
            return

        # Find and delete the LOCATED_IN relationship
        relationships = state.engine.neo4j.get_relationships(
            entity.id,
            state.universe_id,
            relationship_type="LOCATED_IN",
        )

        for rel in relationships:
            if rel.to_entity_id == state.location_id:
                state.engine.neo4j.delete_relationship(rel.id)
                break

        # Mark entity as inactive (soft delete)
        entity.is_active = False
        state.engine.dolt.save_entity(entity)

    def _create_starter_resources(self) -> EntityResources:
        """Create starter resources with narrative-first abilities.

        These abilities use universe-agnostic names and descriptions.
        The LLM will narrate HOW they manifest based on the universe's
        physics overlay and current context.
        """
        # =================================================================
        # Recovery Abilities
        # =================================================================

        catch_your_breath = Ability(
            name="Catch Your Breath",
            description="Draw on your inner reserves to recover from injury. A moment of focus restores your vitality.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.COOLDOWN,
            mechanism_details={"max_uses": 1, "recharge_on_rest": "short"},
            healing=HealingEffect(dice="1d10", flat_amount=1),
            targeting=Targeting(type=TargetingType.SELF),
            action_cost="bonus",
            tags=["recovery", "healing", "self"],
        )

        steel_your_nerves = Ability(
            name="Steel Your Nerves",
            description="Center yourself and shake off the weight of fear and doubt. You regain your composure.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.COOLDOWN,
            mechanism_details={"max_uses": 1, "recharge_on_rest": "short"},
            targeting=Targeting(type=TargetingType.SELF),
            action_cost="action",
            tags=["recovery", "stress", "mental"],
        )

        # =================================================================
        # Offensive Abilities
        # =================================================================

        mighty_blow = Ability(
            name="Mighty Blow",
            description="Channel everything into a single devastating strike. Raw power overwhelming defense.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.FREE,
            mechanism_details={},
            damage=DamageEffect(dice="1d8", damage_type="bludgeoning"),
            targeting=Targeting(type=TargetingType.SINGLE, range_ft=5),
            action_cost="action",
            tags=["attack", "power", "melee"],
        )

        sweeping_strike = Ability(
            name="Sweeping Strike",
            description="A wide, arcing attack that catches multiple foes. Momentum carries through each target.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.MOMENTUM,
            mechanism_details={"momentum_cost": 2},
            damage=DamageEffect(dice="1d8", damage_type="slashing"),
            targeting=Targeting(type=TargetingType.MULTIPLE, range_ft=5, max_targets=2),
            action_cost="action",
            tags=["attack", "area", "momentum"],
        )

        exploit_weakness = Ability(
            name="Exploit Weakness",
            description="Find the gap in their guard, the flaw in their system, the crack in their confidence. Strike true.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.FREE,
            mechanism_details={},
            damage=DamageEffect(dice="2d6", damage_type="piercing"),
            targeting=Targeting(type=TargetingType.SINGLE, range_ft=5),
            action_cost="free",
            tags=["attack", "precision", "tactical"],
            prerequisites=["Target must be distracted or vulnerable"],
        )

        # =================================================================
        # Defensive Abilities
        # =================================================================

        brace_for_impact = Ability(
            name="Brace for Impact",
            description="Prepare yourself to absorb incoming punishment. Set your stance, raise your guard, steel your resolve.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.FREE,
            mechanism_details={},
            stat_modifiers=[
                StatModifierEffect(
                    stat="ac",
                    modifier=2,
                    duration_type="rounds",
                    duration_value=1,
                )
            ],
            targeting=Targeting(type=TargetingType.SELF),
            action_cost="bonus",
            tags=["defensive", "protection", "stance"],
        )

        slip_away = Ability(
            name="Slip Away",
            description="Extract yourself from danger with practiced ease. They reach for you, but you're already gone.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.FREE,
            mechanism_details={},
            targeting=Targeting(type=TargetingType.SELF),
            action_cost="bonus",
            tags=["defensive", "movement", "evasion"],
        )

        # =================================================================
        # Control Abilities
        # =================================================================

        dirty_trick = Ability(
            name="Dirty Trick",
            description="Fight without honor when survival demands it. Sand in the eyes, a low blow, a sudden distraction.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.MOMENTUM,
            mechanism_details={"momentum_cost": 3},
            conditions=[
                ConditionEffect(
                    condition="stunned",
                    duration_type="rounds",
                    duration_value=1,
                    save_ability="con",
                )
            ],
            targeting=Targeting(type=TargetingType.SINGLE, range_ft=5),
            action_cost="action",
            tags=["control", "debuff", "tactical"],
        )

        # Create resources with narrative-first abilities
        resources = EntityResources(
            abilities=[
                # Recovery
                catch_your_breath,
                steel_your_nerves,
                # Offensive
                mighty_blow,
                sweeping_strike,
                exploit_weakness,
                # Defensive
                brace_for_impact,
                slip_away,
                # Control
                dirty_trick,
            ],
            stress_momentum=StressMomentumPool(),
            cooldowns={
                "Catch Your Breath": CooldownTracker(
                    max_uses=1, current_uses=1, recharge_on_rest="short"
                ),
                "Steel Your Nerves": CooldownTracker(
                    max_uses=1, current_uses=1, recharge_on_rest="short"
                ),
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

        # Score-based matching: exact > starts-with > contains
        # Prefer shorter names on tie (more specific match)
        quest_name_lower = quest_name.lower()
        best_score = 0
        for q in available:
            name_lower = q.name.lower()
            if name_lower == quest_name_lower:
                score = 3
            elif name_lower.startswith(quest_name_lower):
                score = 2
            elif quest_name_lower in name_lower:
                score = 1
            else:
                continue
            # Higher score wins; on tie, shorter name wins
            if score > best_score or (
                score == best_score and (quest is None or len(q.name) < len(quest.name))
            ):
                best_score = score
                quest = q

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

    def _check_quest_progress(
        self,
        state: GameState,
        check_type: str,
        target_id: UUID,
    ) -> str:
        """Check quest progress after player action and return notification text."""
        if state.universe_id is None:
            return ""

        quest_service = QuestService(state.engine.dolt, state.engine.neo4j)

        results = []
        if check_type == "location":
            results = quest_service.check_location_objectives(state.universe_id, target_id)
        elif check_type == "dialogue":
            results = quest_service.check_dialogue_objectives(state.universe_id, target_id)
        elif check_type == "defeat":
            results = quest_service.check_defeat_objectives(state.universe_id, target_id)

        # Build IC-style notifications
        notifications = []
        for result in results:
            if result.objective_updated and result.narrative:
                if result.objective_completed:
                    notifications.append(f"\n[{result.narrative}]")
                else:
                    # Show progress update for multi-kill objectives
                    notifications.append(f"\n[{result.narrative}]")
            if result.quest_completed and result.rewards_granted:
                rewards = result.rewards_granted
                reward_parts = []
                if rewards.gold > 0:
                    reward_parts.append(f"{rewards.gold} gold")
                if rewards.experience > 0:
                    reward_parts.append(f"{rewards.experience} XP")
                if reward_parts:
                    notifications.append(
                        f"\n[Quest completed! Received: {', '.join(reward_parts)}]"
                    )
                else:
                    notifications.append("\n[Quest completed!]")

        return "".join(notifications)

    def _abandon_quest(self, state: GameState, quest_service: QuestService, quest_name: str) -> str:
        """Abandon an active quest by name."""
        if not state.universe_id:
            return "No active universe."

        # Find matching quest from active quests
        active = quest_service.get_active_quests(state.universe_id)
        quest = None

        # Score-based matching: exact > starts-with > contains
        # Prefer shorter names on tie (more specific match)
        quest_name_lower = quest_name.lower()
        best_score = 0
        for q in active:
            name_lower = q.name.lower()
            if name_lower == quest_name_lower:
                score = 3
            elif name_lower.startswith(quest_name_lower):
                score = 2
            elif quest_name_lower in name_lower:
                score = 1
            else:
                continue
            # Higher score wins; on tie, shorter name wins
            if score > best_score or (
                score == best_score and (quest is None or len(q.name) < len(quest.name))
            ):
                best_score = score
                quest = q

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

    def _select_universe_template(self) -> int | None:
        """Display template selection menu. Returns index or None for classic fallback."""
        print("\nChoose your universe:")
        print("-" * 50)
        for i, template in enumerate(UNIVERSE_TEMPLATES):
            tags = ", ".join(template.genre_tags[:3])
            print(f"  {i + 1}. {template.name} ({tags})")
        print(f"  {len(UNIVERSE_TEMPLATES) + 1}. Classic Eldoria (no AI generation)")
        print()

        while True:
            try:
                choice = input(f"Select (1-{len(UNIVERSE_TEMPLATES) + 1}): ").strip()
                if not choice:
                    return 0  # Default to first template
                num = int(choice)
                if num == len(UNIVERSE_TEMPLATES) + 1:
                    return None  # Classic fallback
                if 1 <= num <= len(UNIVERSE_TEMPLATES):
                    return num - 1
                print(f"Please enter 1-{len(UNIVERSE_TEMPLATES) + 1}")
            except ValueError:
                print("Please enter a number.")

    def _create_demo_world(self, state: GameState, npc_service: NPCService) -> None:
        """Create a demo world using the starter world content (classic fallback)."""
        result = create_starter_world(
            dolt=state.engine.dolt,
            neo4j=state.engine.neo4j,
            npc_service=npc_service,
            player_name=state.character_name,
        )

        state.universe_id = result.universe.id
        state.location_id = result.starting_location_id
        state.character_id = result.player_character_id

    async def _create_generated_world(
        self, state: GameState, npc_service: NPCService, template_index: int
    ) -> None:
        """Create a world using the LLM generation pipeline."""
        template = get_template_by_index(template_index)
        if not template:
            self._create_demo_world(state, npc_service)
            return

        print(f"\nGenerating '{template.name}'...")
        generator = UniverseGenerator(
            dolt=state.engine.dolt,
            neo4j=state.engine.neo4j,
            npc_service=npc_service,
            llm=None,  # LLM integration can be added via set_llm_service
        )

        result = await generator.generate_from_template(
            template=template,
            player_name=state.character_name,
        )

        state.universe_id = result.universe.id
        state.location_id = result.starting_location_id
        state.character_id = result.player_character_id
        state.world_context = result.universe.world_context

        if result.used_fallback:
            print("(Generated with template fallback — no LLM configured)")
        else:
            print("World generated successfully!")
        print(f"Factions: {', '.join(result.factions.keys())}")
        print(f"Locations: {', '.join(result.locations.keys())}")
        print(f"NPCs: {', '.join(result.npcs.keys())}")

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

        # Universe selection
        template_index = self._select_universe_template()
        if template_index is None:
            # Classic Eldoria fallback
            self._create_demo_world(state, engine.npc_service)
        else:
            # LLM-powered generation
            await self._create_generated_world(state, engine.npc_service, template_index)

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
