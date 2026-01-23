"""
Tests for the conversation system.
"""

from __future__ import annotations

import pytest

from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.models.conversation import (
    STANDARD_CHOICES,
    ConversationContext,
    ConversationTopic,
    DialogueChoice,
    DialogueExchange,
    DialogueOptions,
)
from src.models.entity import create_character, create_location
from src.models.npc import Motivation, create_npc_profile
from src.models.universe import Universe
from src.services.conversation import ConversationService
from src.services.npc import NPCService


@pytest.fixture
def dolt():
    """Create an in-memory Dolt repository."""
    return InMemoryDoltRepository()


@pytest.fixture
def neo4j():
    """Create an in-memory Neo4j repository."""
    return InMemoryNeo4jRepository()


@pytest.fixture
def npc_service(dolt, neo4j):
    """Create an NPC service."""
    return NPCService(dolt=dolt, neo4j=neo4j)


@pytest.fixture
def conversation_service(dolt, neo4j, npc_service):
    """Create a conversation service."""
    return ConversationService(
        dolt=dolt,
        neo4j=neo4j,
        npc_service=npc_service,
        llm=None,  # Use fallback responses
    )


@pytest.fixture
def test_world(dolt, neo4j, npc_service):
    """Create a test world with an NPC and player."""
    # Create universe
    universe = Universe(name="Test World")
    dolt.save_universe(universe)

    # Create location
    location = create_location(
        universe_id=universe.id,
        name="Test Tavern",
        description="A cozy tavern",
        location_type="tavern",
    )
    dolt.save_entity(location)

    # Create NPC
    npc = create_character(
        universe_id=universe.id,
        name="Test Bartender",
        description="A friendly bartender",
        hp_max=20,
        location_id=location.id,
    )
    dolt.save_entity(npc)

    # Create NPC profile
    profile = create_npc_profile(
        entity_id=npc.id,
        extraversion=70,  # Friendly
        agreeableness=60,
        motivations=[Motivation.WEALTH, Motivation.BELONGING],
        speech_style="friendly",
    )
    npc_service.save_profile(profile)

    # Create player
    player = create_character(
        universe_id=universe.id,
        name="Test Player",
        description="The player character",
        hp_max=30,
        location_id=location.id,
    )
    dolt.save_entity(player)

    return {
        "universe": universe,
        "location": location,
        "npc": npc,
        "player": player,
        "profile": profile,
    }


class TestConversationModels:
    """Tests for conversation data models."""

    def test_dialogue_choice_creation(self):
        """DialogueChoice should be creatable with all fields."""
        choice = DialogueChoice(
            id=1,
            topic=ConversationTopic.RUMORS,
            label="Ask about rumors",
            preview="Have you heard anything interesting?",
        )

        assert choice.id == 1
        assert choice.topic == ConversationTopic.RUMORS
        assert choice.label == "Ask about rumors"
        assert choice.preview == "Have you heard anything interesting?"

    def test_dialogue_options_creation(self):
        """DialogueOptions should contain multiple choices."""
        choices = [
            DialogueChoice(id=1, topic=ConversationTopic.RUMORS, label="Ask about rumors"),
            DialogueChoice(id=2, topic=ConversationTopic.QUEST, label="Ask about work"),
        ]
        options = DialogueOptions(choices=choices)

        assert len(options.choices) == 2
        assert options.allows_custom_input is True
        assert options.exit_option_id == 0

    def test_conversation_context_creation(self, test_world):
        """ConversationContext should track conversation state."""
        context = ConversationContext(
            npc_id=test_world["npc"].id,
            npc_name=test_world["npc"].name,
            player_id=test_world["player"].id,
            universe_id=test_world["universe"].id,
            location_id=test_world["location"].id,
        )

        assert context.npc_id == test_world["npc"].id
        assert context.turn_count == 0
        assert context.current_topic == ConversationTopic.GREETING
        assert context.is_active is True

    def test_conversation_context_add_exchange(self, test_world):
        """ConversationContext should track exchanges."""
        context = ConversationContext(
            npc_id=test_world["npc"].id,
            npc_name=test_world["npc"].name,
            player_id=test_world["player"].id,
            universe_id=test_world["universe"].id,
            location_id=test_world["location"].id,
        )

        context.add_exchange(
            player_input="Tell me about rumors",
            topic=ConversationTopic.RUMORS,
            npc_response="I've heard some interesting things...",
        )

        assert context.turn_count == 1
        assert context.current_topic == ConversationTopic.RUMORS
        assert len(context.exchanges) == 1
        assert context.exchanges[0].player_input == "Tell me about rumors"

    def test_standard_choices_exist(self):
        """Standard dialogue choices should be defined."""
        assert ConversationTopic.RUMORS in STANDARD_CHOICES
        assert ConversationTopic.QUEST in STANDARD_CHOICES
        assert ConversationTopic.ABOUT_SELF in STANDARD_CHOICES


class TestConversationService:
    """Tests for the ConversationService."""

    @pytest.mark.asyncio
    async def test_start_conversation(self, conversation_service, test_world):
        """Starting a conversation should return greeting and choices."""
        context, greeting, options = await conversation_service.start_conversation(
            npc_id=test_world["npc"].id,
            npc_name=test_world["npc"].name,
            player_id=test_world["player"].id,
            universe_id=test_world["universe"].id,
            location_id=test_world["location"].id,
        )

        assert context is not None
        assert context.npc_id == test_world["npc"].id
        assert context.is_active is True
        assert greeting  # Should have some greeting text
        assert len(options.choices) > 0

    @pytest.mark.asyncio
    async def test_continue_conversation_with_choice(self, conversation_service, test_world):
        """Selecting a dialogue choice should get a response."""
        context, _, _ = await conversation_service.start_conversation(
            npc_id=test_world["npc"].id,
            npc_name=test_world["npc"].name,
            player_id=test_world["player"].id,
            universe_id=test_world["universe"].id,
            location_id=test_world["location"].id,
        )

        # Select first choice (usually rumors)
        response, options = await conversation_service.continue_conversation(context, 1)

        assert response  # Should have response text
        assert context.turn_count == 1
        assert options is not None  # Conversation should continue

    @pytest.mark.asyncio
    async def test_continue_conversation_with_custom_text(self, conversation_service, test_world):
        """Custom text input should get a response."""
        context, _, _ = await conversation_service.start_conversation(
            npc_id=test_world["npc"].id,
            npc_name=test_world["npc"].name,
            player_id=test_world["player"].id,
            universe_id=test_world["universe"].id,
            location_id=test_world["location"].id,
        )

        # Use custom input
        response, options = await conversation_service.continue_conversation(
            context, "Hello, how are you today?"
        )

        assert response
        assert context.turn_count == 1
        assert context.current_topic == ConversationTopic.CUSTOM

    @pytest.mark.asyncio
    async def test_end_conversation(self, conversation_service, test_world):
        """Ending conversation should return farewell and mark as inactive."""
        context, _, _ = await conversation_service.start_conversation(
            npc_id=test_world["npc"].id,
            npc_name=test_world["npc"].name,
            player_id=test_world["player"].id,
            universe_id=test_world["universe"].id,
            location_id=test_world["location"].id,
        )

        farewell = conversation_service.end_conversation(context)

        assert farewell  # Should have farewell text
        assert context.is_active is False

    @pytest.mark.asyncio
    async def test_multiple_exchanges(self, conversation_service, test_world):
        """Multiple exchanges should accumulate in history."""
        context, _, _ = await conversation_service.start_conversation(
            npc_id=test_world["npc"].id,
            npc_name=test_world["npc"].name,
            player_id=test_world["player"].id,
            universe_id=test_world["universe"].id,
            location_id=test_world["location"].id,
        )

        # Have a few exchanges
        await conversation_service.continue_conversation(context, 1)
        await conversation_service.continue_conversation(context, "That's interesting")
        await conversation_service.continue_conversation(context, 2)

        assert context.turn_count == 3
        assert len(context.exchanges) == 3

    @pytest.mark.asyncio
    async def test_choices_include_shop_for_merchant(self, conversation_service, test_world, neo4j):
        """Merchants should have shop dialogue option."""
        from src.models.entity import create_item
        from src.models.relationships import Relationship, RelationshipType

        # Create an item for sale
        item = create_item(
            universe_id=test_world["universe"].id,
            name="Test Sword",
            value_copper=1000,
        )
        conversation_service.dolt.save_entity(item)

        # Make NPC a merchant by adding SELLS relationship
        neo4j.create_relationship(
            Relationship(
                universe_id=test_world["universe"].id,
                from_entity_id=test_world["npc"].id,
                to_entity_id=item.id,
                relationship_type=RelationshipType.SELLS,
            )
        )

        context, _, options = await conversation_service.start_conversation(
            npc_id=test_world["npc"].id,
            npc_name=test_world["npc"].name,
            player_id=test_world["player"].id,
            universe_id=test_world["universe"].id,
            location_id=test_world["location"].id,
        )

        # Check that shop option is available
        topics = [c.topic for c in options.choices]
        assert ConversationTopic.SHOP in topics


class TestDialogueExchange:
    """Tests for DialogueExchange model."""

    def test_exchange_creation(self):
        """DialogueExchange should store conversation data."""
        exchange = DialogueExchange(
            player_input="Hello",
            player_topic=ConversationTopic.GREETING,
            npc_response="Well met!",
        )

        assert exchange.player_input == "Hello"
        assert exchange.player_topic == ConversationTopic.GREETING
        assert exchange.npc_response == "Well met!"
        assert exchange.timestamp is not None


class TestConversationTopics:
    """Tests for ConversationTopic enum."""

    def test_all_topics_exist(self):
        """All expected topics should be defined."""
        topics = list(ConversationTopic)

        assert ConversationTopic.GREETING in topics
        assert ConversationTopic.FAREWELL in topics
        assert ConversationTopic.RUMORS in topics
        assert ConversationTopic.QUEST in topics
        assert ConversationTopic.SHOP in topics
        assert ConversationTopic.CUSTOM in topics
        assert ConversationTopic.ABOUT_SELF in topics


class TestConversationMemory:
    """Tests for conversation memory formation."""

    @pytest.mark.asyncio
    async def test_first_exchange_forms_memory(self, conversation_service, test_world, neo4j):
        """First exchange should form a memory."""
        context, _, _ = await conversation_service.start_conversation(
            npc_id=test_world["npc"].id,
            npc_name=test_world["npc"].name,
            player_id=test_world["player"].id,
            universe_id=test_world["universe"].id,
            location_id=test_world["location"].id,
        )

        # First exchange
        await conversation_service.continue_conversation(context, 1)

        # Check memory was formed
        memories = neo4j.get_memories_for_npc(test_world["npc"].id)
        assert len(memories) >= 1

    @pytest.mark.asyncio
    async def test_quest_topic_forms_memory(self, conversation_service, test_world, neo4j):
        """Quest-related exchanges should form memories."""
        context, _, _ = await conversation_service.start_conversation(
            npc_id=test_world["npc"].id,
            npc_name=test_world["npc"].name,
            player_id=test_world["player"].id,
            universe_id=test_world["universe"].id,
            location_id=test_world["location"].id,
        )

        # Skip first exchange to get past the ENCOUNTER memory
        await conversation_service.continue_conversation(context, 1)

        # Quest exchange (choice 2 is quest)
        await conversation_service.continue_conversation(context, 2)

        # Check memories were formed
        memories = neo4j.get_memories_for_npc(test_world["npc"].id)
        assert len(memories) >= 2  # Encounter + Quest
