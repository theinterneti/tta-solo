"""
Conversation Service for TTA-Solo.

Manages NPC conversations including dialogue choices,
LLM-powered responses, and conversation state.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from src.models.conversation import (
    STANDARD_CHOICES,
    ConversationContext,
    ConversationTopic,
    DialogueChoice,
    DialogueOptions,
)
from src.models.npc import NPCProfile, RelationshipSummary

if TYPE_CHECKING:
    from src.db.interfaces import DoltRepository, Neo4jRepository
    from src.models.entity import Entity
    from src.services.llm import LLMService
    from src.services.npc import NPCService


# Fallback responses when LLM is unavailable
FALLBACK_GREETINGS = {
    "friendly": [
        "Welcome, friend! It's good to see you.",
        "Ah, hello there! What can I do for you?",
        "Well met, traveler! Always nice to see a new face.",
    ],
    "neutral": [
        "Hello. What do you need?",
        "Yes? Can I help you?",
        "What brings you here?",
    ],
    "hostile": [
        "What do you want?",
        "*glares* Yes?",
        "Make it quick.",
    ],
}

FALLBACK_FAREWELLS = {
    "friendly": [
        "Safe travels, friend!",
        "Come back anytime!",
        "Farewell! May fortune favor you.",
    ],
    "neutral": [
        "Farewell.",
        "Until next time.",
        "Take care.",
    ],
    "hostile": [
        "Finally.",
        "Good riddance.",
        "*turns away dismissively*",
    ],
}

FALLBACK_RESPONSES = {
    ConversationTopic.RUMORS: [
        "I've heard a few things, but nothing I'd stake my reputation on.",
        "There's always talk, but who knows what's true?",
        "People say strange things. I try not to listen too closely.",
    ],
    ConversationTopic.ABOUT_SELF: [
        "There's not much to tell, really.",
        "I'm just trying to get by, like everyone else.",
        "Why do you want to know?",
    ],
    ConversationTopic.DIRECTIONS: [
        "I know these parts well enough. What are you looking for?",
        "Depends on where you're trying to go.",
        "I can point you in the right direction.",
    ],
    ConversationTopic.SMALLTALK: [
        "Indeed, indeed.",
        "Mm, yes.",
        "I suppose so.",
    ],
    ConversationTopic.QUEST: [
        "I don't have any tasks for you right now.",
        "Nothing comes to mind at the moment.",
        "Perhaps try asking around elsewhere.",
    ],
    ConversationTopic.SHOP: [
        "Let me show you what I have.",
        "Take a look at my wares.",
        "I've got some good items today.",
    ],
    ConversationTopic.CUSTOM: [
        "Hmm, interesting.",
        "I see.",
        "Is that so?",
    ],
}


@dataclass
class ConversationService:
    """
    Service for managing NPC conversations.

    Handles dialogue choices, LLM-powered responses,
    and conversation state tracking.
    """

    dolt: DoltRepository
    neo4j: Neo4jRepository
    npc_service: NPCService
    llm: LLMService | None = field(default=None)

    async def start_conversation(
        self,
        npc_id: UUID,
        npc_name: str,
        player_id: UUID,
        universe_id: UUID,
        location_id: UUID,
    ) -> tuple[ConversationContext, str, DialogueOptions]:
        """
        Start a conversation with an NPC.

        Args:
            npc_id: The NPC to talk to
            npc_name: Display name of the NPC
            player_id: The player character
            universe_id: Current universe
            location_id: Current location

        Returns:
            - ConversationContext for tracking state
            - Opening greeting (LLM-generated or fallback)
            - Available dialogue choices
        """
        # Create conversation context
        context = ConversationContext(
            npc_id=npc_id,
            npc_name=npc_name,
            player_id=player_id,
            universe_id=universe_id,
            location_id=location_id,
        )

        # Get NPC profile for personality
        profile = self.npc_service.get_profile(npc_id)

        # Get relationships for context
        relationships = self._get_relationships(npc_id, player_id, universe_id)

        # Determine attitude
        attitude = self._determine_attitude(profile, relationships)

        # Generate greeting
        greeting = await self._generate_greeting(
            npc_id=npc_id,
            npc_name=npc_name,
            profile=profile,
            relationships=relationships,
            attitude=attitude,
            location_id=location_id,
        )

        # Build initial dialogue choices
        npc = self.dolt.get_entity(npc_id, universe_id)
        options = self._build_choices(npc, profile, context)

        return context, greeting, options

    async def continue_conversation(
        self,
        context: ConversationContext,
        player_choice: int | str,
    ) -> tuple[str, DialogueOptions | None]:
        """
        Process player's dialogue choice and generate NPC response.

        Args:
            context: Current conversation state
            player_choice: Choice ID (int) or custom text (str)

        Returns:
            - NPC response (LLM-generated or fallback)
            - Next choices (None if conversation ended)
        """
        # Determine topic and player input
        if isinstance(player_choice, int):
            # Find the choice in standard options
            topic, player_input = self._resolve_choice(player_choice, context)
        else:
            # Custom input
            topic = ConversationTopic.CUSTOM
            player_input = player_choice

        # Handle farewell
        if topic == ConversationTopic.FAREWELL:
            farewell = await self._generate_farewell(context)
            context.is_active = False
            context.add_exchange(player_input, topic, farewell)
            return farewell, None

        # Get NPC profile and relationships
        profile = self.npc_service.get_profile(context.npc_id)
        relationships = self._get_relationships(
            context.npc_id, context.player_id, context.universe_id
        )
        attitude = self._determine_attitude(profile, relationships)

        # Generate response
        response = await self._generate_response(
            context=context,
            topic=topic,
            player_input=player_input,
            profile=profile,
            relationships=relationships,
            attitude=attitude,
        )

        # Record exchange
        context.add_exchange(player_input, topic, response)

        # Form memory if exchange is significant
        self._maybe_form_memory(context, topic, player_input, response)

        # Build next choices
        npc = self.dolt.get_entity(context.npc_id, context.universe_id)
        options = self._build_choices(npc, profile, context)

        return response, options

    def end_conversation(self, context: ConversationContext) -> str:
        """
        End the conversation gracefully.

        Args:
            context: Current conversation state

        Returns:
            Farewell message
        """
        context.is_active = False

        # Get attitude for farewell tone
        profile = self.npc_service.get_profile(context.npc_id)
        relationships = self._get_relationships(
            context.npc_id, context.player_id, context.universe_id
        )
        attitude = self._determine_attitude(profile, relationships)

        return secrets.choice(FALLBACK_FAREWELLS.get(attitude, FALLBACK_FAREWELLS["neutral"]))

    def _get_relationships(
        self,
        npc_id: UUID,
        player_id: UUID,
        universe_id: UUID,
    ) -> list[RelationshipSummary]:
        """Get NPC's relationships relevant to this conversation."""
        relationships = []

        # Get relationship with player
        rel = self.neo4j.get_relationship_between(
            from_entity_id=npc_id,
            to_entity_id=player_id,
            universe_id=universe_id,
        )

        if rel:
            # Get player name
            player = self.dolt.get_entity(player_id, universe_id)
            player_name = player.name if player else "stranger"

            relationships.append(
                RelationshipSummary(
                    target_id=player_id,
                    target_name=player_name,
                    relationship_type=rel.relationship_type.value,
                    strength=rel.strength,
                    trust=rel.trust or 0.0,
                )
            )

        return relationships

    def _determine_attitude(
        self,
        profile: NPCProfile | None,
        relationships: list[RelationshipSummary],
    ) -> str:
        """Determine NPC's attitude toward player."""
        # Check for direct relationship
        for rel in relationships:
            if rel.trust > 0.3:
                return "friendly"
            elif rel.trust < -0.3:
                return "hostile"

        # Fall back to personality
        if profile:
            if profile.traits.agreeableness > 60:
                return "friendly"
            elif profile.traits.agreeableness < 40:
                return "hostile"

        return "neutral"

    async def _generate_greeting(
        self,
        npc_id: UUID,
        npc_name: str,
        profile: NPCProfile | None,
        relationships: list[RelationshipSummary],
        attitude: str,
        location_id: UUID,
    ) -> str:
        """Generate an appropriate greeting."""
        # Try LLM first
        if self.llm is not None and self.llm.is_available and profile:
            try:
                # Get location name for context
                location = self.dolt.get_entity(location_id, profile.entity_id)
                situation = f"The player approaches {npc_name} to start a conversation."
                if location:
                    situation = f"At {location.name}. {situation}"

                return await self.npc_service.generate_dialogue(
                    npc_id=npc_id,
                    player_input="*approaches to talk*",
                    profile=profile,
                    relationships=relationships,
                    situation=situation,
                    in_combat=False,
                )
            except Exception:
                pass  # Fall through to fallback

        # Fallback greeting
        greetings = FALLBACK_GREETINGS.get(attitude, FALLBACK_GREETINGS["neutral"])
        return secrets.choice(greetings)

    async def _generate_farewell(self, context: ConversationContext) -> str:
        """Generate a farewell message."""
        profile = self.npc_service.get_profile(context.npc_id)
        relationships = self._get_relationships(
            context.npc_id, context.player_id, context.universe_id
        )
        attitude = self._determine_attitude(profile, relationships)

        # Try LLM
        if self.llm is not None and self.llm.is_available and profile:
            try:
                return await self.npc_service.generate_dialogue(
                    npc_id=context.npc_id,
                    player_input="Goodbye.",
                    profile=profile,
                    relationships=relationships,
                    situation="The player is ending the conversation.",
                    in_combat=False,
                )
            except Exception:
                pass

        # Fallback
        farewells = FALLBACK_FAREWELLS.get(attitude, FALLBACK_FAREWELLS["neutral"])
        return secrets.choice(farewells)

    async def _generate_response(
        self,
        context: ConversationContext,
        topic: ConversationTopic,
        player_input: str,
        profile: NPCProfile | None,
        relationships: list[RelationshipSummary],
        attitude: str,
    ) -> str:
        """Generate NPC response to player input."""
        # Try LLM first
        if self.llm is not None and self.llm.is_available and profile:
            try:
                # Build situation from context
                situation = self._build_situation(context, topic)

                return await self.npc_service.generate_dialogue(
                    npc_id=context.npc_id,
                    player_input=player_input,
                    profile=profile,
                    relationships=relationships,
                    situation=situation,
                    in_combat=False,
                )
            except Exception:
                pass  # Fall through to fallback

        # Fallback response
        responses = FALLBACK_RESPONSES.get(topic, FALLBACK_RESPONSES[ConversationTopic.CUSTOM])
        return secrets.choice(responses)

    def _build_situation(
        self,
        context: ConversationContext,
        topic: ConversationTopic,
    ) -> str:
        """Build situation description for LLM context."""
        parts = [f"Conversation with player, turn {context.turn_count + 1}."]

        if topic == ConversationTopic.RUMORS:
            parts.append("Player is asking about local rumors and news.")
        elif topic == ConversationTopic.QUEST:
            parts.append("Player is asking about available work or quests.")
        elif topic == ConversationTopic.SHOP:
            parts.append("Player is interested in buying or selling items.")
        elif topic == ConversationTopic.ABOUT_SELF:
            parts.append("Player is asking about the NPC's background.")
        elif topic == ConversationTopic.DIRECTIONS:
            parts.append("Player is asking for help navigating the area.")

        # Add recent exchange history
        recent = context.get_recent_exchanges(3)
        if recent:
            parts.append("Recent conversation:")
            for exchange in recent:
                parts.append(f"  Player: {exchange.player_input}")
                parts.append(f"  NPC: {exchange.npc_response}")

        return " ".join(parts)

    def _resolve_choice(
        self,
        choice_id: int,
        context: ConversationContext,
    ) -> tuple[ConversationTopic, str]:
        """Resolve a numeric choice to topic and input text."""
        # Build current choices to find the selected one
        profile = self.npc_service.get_profile(context.npc_id)
        npc = self.dolt.get_entity(context.npc_id, context.universe_id)
        options = self._build_choices(npc, profile, context)

        for choice in options.choices:
            if choice.id == choice_id:
                return choice.topic, choice.preview or choice.label

        # Default to smalltalk if choice not found
        return ConversationTopic.SMALLTALK, "..."

    def _build_choices(
        self,
        npc: Entity | None,
        profile: NPCProfile | None,
        context: ConversationContext,
    ) -> DialogueOptions:
        """Build available dialogue choices based on context."""
        choices: list[DialogueChoice] = []
        choice_id = 1

        # Check if NPC is a merchant
        is_merchant = False
        if npc:
            sells_rels = self.neo4j.get_relationships(
                npc.id,
                context.universe_id,
                relationship_type="SELLS",
            )
            is_merchant = len(sells_rels) > 0

        # Add standard choices based on context
        # Always offer rumors
        if ConversationTopic.RUMORS in STANDARD_CHOICES:
            choice = STANDARD_CHOICES[ConversationTopic.RUMORS].model_copy()
            choice.id = choice_id
            choices.append(choice)
            choice_id += 1

        # Add quest option (always available for now)
        if ConversationTopic.QUEST in STANDARD_CHOICES:
            choice = STANDARD_CHOICES[ConversationTopic.QUEST].model_copy()
            choice.id = choice_id
            choices.append(choice)
            choice_id += 1

        # Add shop if merchant
        if is_merchant and ConversationTopic.SHOP in STANDARD_CHOICES:
            choice = STANDARD_CHOICES[ConversationTopic.SHOP].model_copy()
            choice.id = choice_id
            choices.append(choice)
            choice_id += 1

        # Add about self
        if ConversationTopic.ABOUT_SELF in STANDARD_CHOICES:
            choice = STANDARD_CHOICES[ConversationTopic.ABOUT_SELF].model_copy()
            choice.id = choice_id
            choices.append(choice)
            choice_id += 1

        return DialogueOptions(
            choices=choices,
            allows_custom_input=True,
        )

    def _maybe_form_memory(
        self,
        context: ConversationContext,
        topic: ConversationTopic,
        player_input: str,
        npc_response: str,
    ) -> None:
        """
        Form a memory from a conversation exchange if significant.

        Significant exchanges include:
        - First meeting with player
        - Quest-related discussions
        - Emotional exchanges (high valence)
        - Persuasion/intimidation attempts
        """
        from src.models.npc import MemoryType, create_memory

        # Determine if this exchange is significant enough to remember
        should_remember = False
        memory_type = MemoryType.DIALOGUE
        importance = 0.5
        emotional_valence = 0.0

        # First turn is always memorable (first meeting or re-meeting)
        if context.turn_count == 1:
            should_remember = True
            memory_type = MemoryType.ENCOUNTER
            importance = 0.7

        # Quest-related topics are important
        elif topic == ConversationTopic.QUEST:
            should_remember = True
            importance = 0.8
            emotional_valence = 0.3  # Generally positive (work opportunity)

        # Persuasion/intimidation attempts are memorable
        elif topic in [ConversationTopic.PERSUADE, ConversationTopic.INTIMIDATE]:
            should_remember = True
            importance = 0.7
            # Intimidation creates negative memory
            emotional_valence = -0.5 if topic == ConversationTopic.INTIMIDATE else 0.2

        # About self topics are somewhat memorable (NPC shared about themselves)
        elif topic == ConversationTopic.ABOUT_SELF:
            should_remember = True
            importance = 0.5
            emotional_valence = 0.2

        if not should_remember:
            return

        # Create the memory
        memory = create_memory(
            npc_id=context.npc_id,
            memory_type=memory_type,
            description=f"Player said: '{player_input[:100]}...' about {topic.value}",
            subject_id=context.player_id,
            emotional_valence=emotional_valence,
            importance=importance,
        )

        # Save memory via neo4j
        self.neo4j.create_memory(memory)
