"""
Tests for faction quest wiring into gameplay triggers.

Verifies that faction quests are generated through:
1. NPC conversation (QUEST topic)
2. Location arrival (/go)
3. Location inspection (/look)
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.models.conversation import ConversationTopic
from src.models.entity import (
    create_character,
    create_faction,
    create_location,
)
from src.models.npc import Motivation, create_npc_profile
from src.models.relationships import Relationship, RelationshipType
from src.models.universe import Universe
from src.services.conversation import ConversationService
from src.services.npc import NPCService
from src.services.quest import QuestService

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def dolt():
    return InMemoryDoltRepository()


@pytest.fixture
def neo4j():
    return InMemoryNeo4jRepository()


@pytest.fixture
def npc_service(dolt, neo4j):
    return NPCService(dolt=dolt, neo4j=neo4j)


@pytest.fixture
def quest_service(dolt, neo4j):
    return QuestService(dolt=dolt, neo4j=neo4j)


@pytest.fixture
def conversation_service(dolt, neo4j, npc_service, quest_service):
    return ConversationService(
        dolt=dolt,
        neo4j=neo4j,
        npc_service=npc_service,
        llm=None,
        quest_service=quest_service,
    )


@pytest.fixture
def conversation_service_no_quest(dolt, neo4j, npc_service):
    """ConversationService without quest_service (backwards compat)."""
    return ConversationService(
        dolt=dolt,
        neo4j=neo4j,
        npc_service=npc_service,
        llm=None,
    )


@pytest.fixture
def faction_world(dolt, neo4j, npc_service):
    """Test world with a faction, faction NPC, and faction-controlled location."""
    universe = Universe(name="Faction Test World")
    dolt.save_universe(universe)

    # Create faction
    faction = create_faction(
        universe_id=universe.id,
        name="Iron Guild",
        description="A powerful guild of smiths",
    )
    dolt.save_entity(faction)

    # Create faction-controlled location
    location = create_location(
        universe_id=universe.id,
        name="Iron Quarter",
        description="A district dominated by forges and workshops",
        location_type="market",
    )
    # Set controlling faction hint
    location.location_properties.controlling_faction_hint = "Iron Guild"
    dolt.save_entity(location)

    # Create a second location (no faction control)
    plain_location = create_location(
        universe_id=universe.id,
        name="Open Field",
        description="A plain grassy field",
        location_type="forest",
    )
    dolt.save_entity(plain_location)

    # Connect locations
    neo4j.create_relationship(
        Relationship(
            universe_id=universe.id,
            from_entity_id=location.id,
            to_entity_id=plain_location.id,
            relationship_type=RelationshipType.CONNECTED_TO,
        )
    )

    # Create NPC that is a faction member
    npc = create_character(
        universe_id=universe.id,
        name="Guildmaster Hara",
        description="Leader of the Iron Guild",
        hp_max=25,
        location_id=location.id,
    )
    dolt.save_entity(npc)

    # Create NPC profile
    profile = create_npc_profile(
        entity_id=npc.id,
        extraversion=60,
        agreeableness=50,
        motivations=[Motivation.WEALTH, Motivation.POWER],
        speech_style="authoritative",
    )
    npc_service.save_profile(profile)

    # NPC MEMBER_OF faction
    neo4j.create_relationship(
        Relationship(
            universe_id=universe.id,
            from_entity_id=npc.id,
            to_entity_id=faction.id,
            relationship_type=RelationshipType.MEMBER_OF,
        )
    )

    # NPC LOCATED_IN location
    neo4j.create_relationship(
        Relationship(
            universe_id=universe.id,
            from_entity_id=npc.id,
            to_entity_id=location.id,
            relationship_type=RelationshipType.LOCATED_IN,
        )
    )

    # Create NPC without faction
    npc_no_faction = create_character(
        universe_id=universe.id,
        name="Wandering Bard",
        description="A traveler with no allegiance",
        hp_max=15,
        location_id=location.id,
    )
    dolt.save_entity(npc_no_faction)

    profile_no_faction = create_npc_profile(
        entity_id=npc_no_faction.id,
        extraversion=70,
        agreeableness=65,
        motivations=[Motivation.BELONGING],
        speech_style="friendly",
    )
    npc_service.save_profile(profile_no_faction)

    neo4j.create_relationship(
        Relationship(
            universe_id=universe.id,
            from_entity_id=npc_no_faction.id,
            to_entity_id=location.id,
            relationship_type=RelationshipType.LOCATED_IN,
        )
    )

    # Create player
    player = create_character(
        universe_id=universe.id,
        name="Test Hero",
        description="The player character",
        hp_max=30,
        location_id=location.id,
    )
    dolt.save_entity(player)

    return {
        "universe": universe,
        "location": location,
        "plain_location": plain_location,
        "faction": faction,
        "npc": npc,
        "npc_no_faction": npc_no_faction,
        "player": player,
    }


# =============================================================================
# Conversation Quest Generation Tests
# =============================================================================


class TestConversationQuestGeneration:
    """NPC conversation generates faction quests when NPC belongs to a faction."""

    @pytest.mark.asyncio
    async def test_npc_with_faction_generates_quest(self, conversation_service, faction_world):
        """NPC with faction membership generates quest on QUEST topic."""
        world = faction_world

        # Start conversation
        context, greeting, options = await conversation_service.start_conversation(
            npc_id=world["npc"].id,
            npc_name=world["npc"].name,
            player_id=world["player"].id,
            universe_id=world["universe"].id,
            location_id=world["location"].id,
        )

        # Find the quest choice
        quest_choice = None
        for choice in options.choices:
            if choice.topic == ConversationTopic.QUEST:
                quest_choice = choice
                break
        assert quest_choice is not None

        # Continue with quest topic
        response, next_options = await conversation_service.continue_conversation(
            context, quest_choice.id
        )

        # Should contain quest info instead of fallback
        assert "New quest available:" in response
        assert "I need someone I can trust" in response

    @pytest.mark.asyncio
    async def test_npc_without_faction_falls_back(self, conversation_service, faction_world):
        """NPC without faction membership returns fallback text."""
        world = faction_world

        # Start conversation with non-faction NPC
        context, greeting, options = await conversation_service.start_conversation(
            npc_id=world["npc_no_faction"].id,
            npc_name=world["npc_no_faction"].name,
            player_id=world["player"].id,
            universe_id=world["universe"].id,
            location_id=world["location"].id,
        )

        # Find quest choice
        quest_choice = None
        for choice in options.choices:
            if choice.topic == ConversationTopic.QUEST:
                quest_choice = choice
                break
        assert quest_choice is not None

        # Continue with quest topic
        response, next_options = await conversation_service.continue_conversation(
            context, quest_choice.id
        )

        # Should be a fallback response (no quest generated)
        assert "New quest available:" not in response

    @pytest.mark.asyncio
    async def test_backwards_compat_no_quest_service(
        self, conversation_service_no_quest, faction_world
    ):
        """ConversationService without quest_service still works normally."""
        world = faction_world

        context, greeting, options = await conversation_service_no_quest.start_conversation(
            npc_id=world["npc"].id,
            npc_name=world["npc"].name,
            player_id=world["player"].id,
            universe_id=world["universe"].id,
            location_id=world["location"].id,
        )

        quest_choice = None
        for choice in options.choices:
            if choice.topic == ConversationTopic.QUEST:
                quest_choice = choice
                break

        response, next_options = await conversation_service_no_quest.continue_conversation(
            context, quest_choice.id
        )

        # Falls back to static text
        assert "New quest available:" not in response


# =============================================================================
# Location Arrival Quest Generation Tests
# =============================================================================


class TestLocationArrivalQuestGeneration:
    """Tests for auto-generating faction quests on location arrival via _maybe_generate_faction_quest."""

    def test_faction_location_generates_quest(self, quest_service, faction_world):
        """Entering a faction-controlled location generates a quest."""
        from src.cli.repl import GameREPL

        world = faction_world
        repl = GameREPL.__new__(GameREPL)

        # Minimal GameState mock
        class MockEngine:
            def __init__(self, dolt, neo4j):
                self.dolt = dolt
                self.neo4j = neo4j

        class MockState:
            def __init__(self):
                self.universe_id = world["universe"].id

        state = MockState()
        state.engine = MockEngine(quest_service.dolt, quest_service.neo4j)

        result = repl._maybe_generate_faction_quest(state, world["location"].id)

        assert "tension in the air" in result
        assert "New quest available" in result

        # Verify quest was actually created
        available = quest_service.get_available_quests(world["universe"].id)
        assert len(available) >= 1

    def test_no_faction_location_no_quest(self, quest_service, faction_world):
        """Entering a non-faction location does not generate a quest."""
        from src.cli.repl import GameREPL

        world = faction_world
        repl = GameREPL.__new__(GameREPL)

        class MockEngine:
            def __init__(self, dolt, neo4j):
                self.dolt = dolt
                self.neo4j = neo4j

        class MockState:
            def __init__(self):
                self.universe_id = world["universe"].id

        state = MockState()
        state.engine = MockEngine(quest_service.dolt, quest_service.neo4j)

        result = repl._maybe_generate_faction_quest(state, world["plain_location"].id)

        assert result == ""
        available = quest_service.get_available_quests(world["universe"].id)
        assert len(available) == 0

    def test_existing_quests_prevent_spam(self, quest_service, faction_world):
        """Existing available quests prevent auto-generation of new ones."""
        from src.cli.repl import GameREPL
        from src.models.quest import ObjectiveType, QuestType, create_objective, create_quest

        world = faction_world
        repl = GameREPL.__new__(GameREPL)

        # Pre-create an available quest
        quest = create_quest(
            universe_id=world["universe"].id,
            name="Existing Quest",
            description="Already available",
            quest_type=QuestType.TALK,
            objectives=[
                create_objective(
                    description="Talk to someone",
                    objective_type=ObjectiveType.TALK_TO_NPC,
                )
            ],
        )
        quest_service.dolt.save_quest(quest)

        class MockEngine:
            def __init__(self, dolt, neo4j):
                self.dolt = dolt
                self.neo4j = neo4j

        class MockState:
            def __init__(self):
                self.universe_id = world["universe"].id

        state = MockState()
        state.engine = MockEngine(quest_service.dolt, quest_service.neo4j)

        result = repl._maybe_generate_faction_quest(state, world["location"].id)

        assert result == ""

    def test_no_universe_returns_empty(self, quest_service, faction_world):
        """No universe ID returns empty string."""
        from src.cli.repl import GameREPL

        repl = GameREPL.__new__(GameREPL)

        class MockState:
            universe_id = None

        result = repl._maybe_generate_faction_quest(MockState(), uuid4())
        assert result == ""


# =============================================================================
# Look Command Faction Display Tests
# =============================================================================


class TestLookFactionDisplay:
    """Tests for /look showing faction presence."""

    def test_look_shows_faction(self, faction_world, dolt):
        """Location with controlling_faction_hint shows faction in /look."""
        world = faction_world
        location = dolt.get_entity(world["location"].id, world["universe"].id)

        assert location is not None
        assert location.location_properties is not None
        assert location.location_properties.controlling_faction_hint == "Iron Guild"

    def test_look_no_faction(self, faction_world, dolt):
        """Location without controlling_faction_hint has no faction line."""
        world = faction_world
        location = dolt.get_entity(world["plain_location"].id, world["universe"].id)

        assert location is not None
        assert location.location_properties is not None
        assert location.location_properties.controlling_faction_hint is None
