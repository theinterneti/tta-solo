"""
Conversation Models for TTA-Solo.

Defines the data structures for NPC conversations including
topics, dialogue choices, and conversation state.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ConversationTopic(str, Enum):
    """Available conversation topics."""

    # General
    GREETING = "greeting"
    FAREWELL = "farewell"
    SMALLTALK = "smalltalk"
    CUSTOM = "custom"

    # Information
    RUMORS = "rumors"
    DIRECTIONS = "directions"
    LORE = "lore"
    ABOUT_SELF = "about_self"

    # Transactional
    QUEST = "quest"
    SHOP = "shop"
    SERVICE = "service"

    # Social
    PERSUADE = "persuade"
    INTIMIDATE = "intimidate"
    FLATTER = "flatter"


class DialogueChoice(BaseModel):
    """A selectable dialogue option."""

    id: int
    """1-based index for selection (0 is always exit)."""

    topic: ConversationTopic
    """The topic this choice relates to."""

    label: str
    """What player sees as the option text."""

    preview: str | None = None
    """Optional preview of what they'll actually say."""

    requires_skill_check: bool = False
    """Whether selecting this requires a skill check."""

    skill_check_dc: int | None = None
    """DC for the skill check if required."""

    skill_check_ability: str | None = None
    """Ability to use for skill check (cha, int, etc.)."""


class DialogueOptions(BaseModel):
    """Available choices for current conversation turn."""

    choices: list[DialogueChoice] = Field(default_factory=list)
    """The available dialogue choices."""

    allows_custom_input: bool = True
    """Whether player can type custom input."""

    exit_option_id: int = 0
    """ID for exit option (always 0)."""


class DialogueExchange(BaseModel):
    """A single back-and-forth in conversation."""

    player_input: str
    """What the player said."""

    player_topic: ConversationTopic
    """The topic of the player's input."""

    npc_response: str
    """The NPC's response."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    """When this exchange occurred."""


class ConversationContext(BaseModel):
    """Current state of a conversation."""

    id: UUID = Field(default_factory=uuid4)
    """Unique identifier for this conversation."""

    npc_id: UUID
    """The NPC being talked to."""

    npc_name: str
    """Name of the NPC (cached for display)."""

    player_id: UUID
    """The player character."""

    universe_id: UUID
    """Which universe this is in."""

    location_id: UUID
    """Where the conversation is happening."""

    # Conversation state
    started_at: datetime = Field(default_factory=datetime.utcnow)
    """When the conversation started."""

    turn_count: int = 0
    """Number of exchanges so far."""

    current_topic: ConversationTopic = ConversationTopic.GREETING
    """Current conversation topic."""

    is_active: bool = True
    """Whether conversation is still ongoing."""

    # History
    exchanges: list[DialogueExchange] = Field(default_factory=list)
    """History of this conversation."""

    # NPC state
    npc_mood: float = Field(ge=-1.0, le=1.0, default=0.0)
    """How the NPC feels about this conversation (-1 negative, +1 positive)."""

    # Transactional state
    pending_quest_id: UUID | None = None
    """Quest being discussed if any."""

    def add_exchange(
        self,
        player_input: str,
        topic: ConversationTopic,
        npc_response: str,
    ) -> None:
        """Add an exchange to the conversation history."""
        self.exchanges.append(
            DialogueExchange(
                player_input=player_input,
                player_topic=topic,
                npc_response=npc_response,
            )
        )
        self.turn_count += 1
        self.current_topic = topic

    def get_recent_exchanges(self, limit: int = 5) -> list[DialogueExchange]:
        """Get the most recent exchanges."""
        return self.exchanges[-limit:]


# Standard dialogue choice templates
STANDARD_CHOICES = {
    ConversationTopic.RUMORS: DialogueChoice(
        id=1,
        topic=ConversationTopic.RUMORS,
        label="Ask about local rumors",
        preview="Have you heard any interesting news lately?",
    ),
    ConversationTopic.QUEST: DialogueChoice(
        id=2,
        topic=ConversationTopic.QUEST,
        label="Inquire about work or quests",
        preview="Is there anything you need help with?",
    ),
    ConversationTopic.SHOP: DialogueChoice(
        id=3,
        topic=ConversationTopic.SHOP,
        label="Browse their wares",
        preview="What do you have for sale?",
    ),
    ConversationTopic.ABOUT_SELF: DialogueChoice(
        id=4,
        topic=ConversationTopic.ABOUT_SELF,
        label="Ask about them",
        preview="Tell me about yourself.",
    ),
    ConversationTopic.DIRECTIONS: DialogueChoice(
        id=5,
        topic=ConversationTopic.DIRECTIONS,
        label="Ask for directions",
        preview="Can you help me find my way around?",
    ),
    ConversationTopic.SMALLTALK: DialogueChoice(
        id=6,
        topic=ConversationTopic.SMALLTALK,
        label="Make small talk",
        preview="Nice weather we're having...",
    ),
}
