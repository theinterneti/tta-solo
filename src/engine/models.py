"""
Engine Data Models for TTA-Solo.

Defines the core data structures for the game loop:
- Intent: Parsed player action
- Context: World state for a turn
- TurnResult: Response to the player
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """Categories of player intent."""

    # Combat
    ATTACK = "attack"
    CAST_SPELL = "cast_spell"
    USE_ABILITY = "use_ability"

    # Social
    TALK = "talk"
    PERSUADE = "persuade"
    INTIMIDATE = "intimidate"
    DECEIVE = "deceive"

    # Exploration
    MOVE = "move"
    LOOK = "look"
    SEARCH = "search"
    INTERACT = "interact"

    # Items
    USE_ITEM = "use_item"
    PICK_UP = "pick_up"
    DROP = "drop"
    GIVE = "give"

    # Meta
    REST = "rest"
    WAIT = "wait"
    ASK_QUESTION = "ask_question"

    # Special
    FORK = "fork"
    UNCLEAR = "unclear"


class Intent(BaseModel):
    """Parsed player intent."""

    type: IntentType
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the parse")

    # Target extraction
    target_name: str | None = Field(default=None, description="Target name from input")
    target_id: UUID | None = Field(default=None, description="Resolved entity ID")

    # Action details
    method: str | None = Field(default=None, description="How to perform action")
    dialogue: str | None = Field(default=None, description="What to say (TALK)")
    destination: str | None = Field(default=None, description="Where to go (MOVE)")

    # Raw input
    original_input: str = Field(description="The player's original input")
    reasoning: str = Field(default="", description="Why this intent was chosen")


class RollSummary(BaseModel):
    """Summary of a dice roll for display."""

    description: str = Field(description="What was rolled for")
    roll: int = Field(description="The natural roll")
    modifier: int = Field(default=0, description="Total modifier")
    total: int = Field(description="Final result")
    success: bool | None = Field(default=None, description="Pass/fail if applicable")
    is_critical: bool = Field(default=False)
    is_fumble: bool = Field(default=False)


class SkillResult(BaseModel):
    """Result of executing a skill."""

    success: bool
    outcome: str = Field(description="success, failure, critical_success, etc.")

    # Dice
    roll: int | None = None
    total: int | None = None
    dc: int | None = None

    # Effects
    damage: int | None = None
    healing: int | None = None
    conditions: list[str] = Field(default_factory=list)

    # For narrative
    description: str = Field(default="", description="Human-readable result")
    is_critical: bool = False
    is_fumble: bool = False

    # PbtA (Phase 4)
    pbta_outcome: str | None = Field(
        default=None, description="PbtA outcome: strong_hit, weak_hit, miss"
    )
    gm_move_type: str | None = Field(
        default=None, description="GM move type on miss"
    )
    gm_move_description: str | None = Field(
        default=None, description="Description of GM move"
    )
    weak_hit_complication: str | None = Field(
        default=None, description="Complication on weak hit"
    )
    strong_hit_bonus: str | None = Field(
        default=None, description="Bonus effect on strong hit"
    )

    def to_roll_summary(self, label: str = "Roll") -> RollSummary:
        """Convert to a RollSummary for display."""
        return RollSummary(
            description=label,
            roll=self.roll or 0,
            modifier=(self.total or 0) - (self.roll or 0),
            total=self.total or self.roll or 0,
            success=self.success,
            is_critical=self.is_critical,
            is_fumble=self.is_fumble,
        )


class EntitySummary(BaseModel):
    """Lightweight entity info for context."""

    id: UUID
    name: str
    type: str
    description: str = ""
    hp_current: int | None = None
    hp_max: int | None = None
    ac: int | None = None


class RelationshipSummary(BaseModel):
    """Lightweight relationship info for context."""

    entity: EntitySummary
    relationship_type: str
    strength: float = 1.0
    trust: float | None = None
    description: str = ""


class Context(BaseModel):
    """World context for a turn."""

    # Actor state
    actor: EntitySummary
    actor_inventory: list[EntitySummary] = Field(default_factory=list)

    # Location
    location: EntitySummary
    entities_present: list[EntitySummary] = Field(default_factory=list)
    exits: list[str] = Field(default_factory=list)

    # Relationships - entities the actor knows/has relationships with
    known_entities: list[RelationshipSummary] = Field(
        default_factory=list, description="Actor's relationships with other entities"
    )

    # Recent history
    recent_events: list[str] = Field(
        default_factory=list, description="Recent event summaries"
    )

    # Atmosphere
    mood: str | None = None
    danger_level: int = Field(default=0, ge=0, le=20)


class Turn(BaseModel):
    """A single player turn in the game loop."""

    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Input
    player_input: str
    universe_id: UUID
    actor_id: UUID
    location_id: UUID

    # Processing results (filled during turn)
    intent: Intent | None = None
    context: Context | None = None
    skill_results: list[SkillResult] = Field(default_factory=list)
    events_created: list[UUID] = Field(default_factory=list)
    narrative: str = ""

    # Metadata
    processing_time_ms: int = 0
    error: str | None = None


class TurnResult(BaseModel):
    """Result returned to the player."""

    narrative: str = Field(description="The story response")

    # Optional details for UI
    rolls: list[RollSummary] = Field(default_factory=list)
    state_changes: list[str] = Field(default_factory=list)

    # Meta
    turn_id: UUID
    events_created: int = 0
    processing_time_ms: int = 0

    # Error info (if any)
    error: str | None = None


class Session(BaseModel):
    """
    An active game session.

    Supports multi-character sessions (Phase 4) where multiple
    characters can participate, with one active at a time.
    """

    model_config = {"extra": "allow"}  # Allow extra fields for backwards compat

    id: UUID = Field(default_factory=uuid4)
    universe_id: UUID
    location_id: UUID

    # Character management (Phase 4: multi-character support)
    character_ids: list[UUID] = Field(
        default_factory=list,
        description="All characters in this session",
    )
    active_character_id: UUID | None = Field(
        default=None,
        description="Currently active character (takes turns)",
    )

    # Session state
    started_at: datetime = Field(default_factory=datetime.utcnow)
    last_turn_at: datetime | None = None
    turn_count: int = 0

    # Configuration
    tone: str = "adventure"
    verbosity: str = "normal"

    def __init__(self, **data):
        """Handle backwards compatibility with old character_id field."""
        # Handle old-style character_id parameter
        if "character_id" in data and "character_ids" not in data:
            char_id = data.pop("character_id")
            data["character_ids"] = [char_id]
            data["active_character_id"] = char_id
        super().__init__(**data)

    # Backwards compatibility property
    @property
    def character_id(self) -> UUID:
        """Get the active character ID (backwards compatible)."""
        if self.active_character_id is not None:
            return self.active_character_id
        if self.character_ids:
            return self.character_ids[0]
        raise ValueError("No characters in session")

    def add_character(self, character_id: UUID, make_active: bool = False) -> None:
        """
        Add a character to the session.

        Args:
            character_id: UUID of the character to add
            make_active: Whether to make this character active
        """
        if character_id not in self.character_ids:
            self.character_ids.append(character_id)

        if make_active or self.active_character_id is None:
            self.active_character_id = character_id

    def remove_character(self, character_id: UUID) -> bool:
        """
        Remove a character from the session.

        Args:
            character_id: UUID of the character to remove

        Returns:
            True if removed, False if not found
        """
        if character_id not in self.character_ids:
            return False

        self.character_ids.remove(character_id)

        # If we removed the active character, switch to another
        if self.active_character_id == character_id:
            self.active_character_id = self.character_ids[0] if self.character_ids else None

        return True

    def switch_character(self, character_id: UUID) -> bool:
        """
        Switch to a different active character.

        Args:
            character_id: UUID of the character to switch to

        Returns:
            True if switched, False if character not in session
        """
        if character_id not in self.character_ids:
            return False

        self.active_character_id = character_id
        return True

    def get_inactive_characters(self) -> list[UUID]:
        """Get all characters that are not currently active."""
        return [c for c in self.character_ids if c != self.active_character_id]


class EngineConfig(BaseModel):
    """Engine configuration."""

    # LLM settings
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 1024
    temperature: float = 0.7

    # Context settings
    max_recent_events: int = 10
    max_nearby_entities: int = 20

    # Behavior
    verbosity: str = "normal"
    tone: str = "adventure"
    strict_rules: bool = True


class ForkResult(BaseModel):
    """Result of a fork/branch operation from the game engine."""

    success: bool
    new_universe_id: UUID | None = Field(
        default=None, description="ID of the newly created universe"
    )
    new_session_id: UUID | None = Field(
        default=None, description="ID of the new session in forked universe"
    )
    fork_reason: str = Field(default="", description="Why this fork was created")
    narrative: str = Field(
        default="", description="Narrative description of the fork"
    )
    error: str | None = Field(default=None, description="Error message if failed")
