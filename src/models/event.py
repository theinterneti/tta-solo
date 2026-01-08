"""
Event Models for TTA-Solo.

Events are the atomic units of story - immutable records of what happened.
Stored in Dolt's `events` table as an append-only log.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of events that can occur in the game world."""

    # Combat events
    COMBAT_START = "combat_start"
    COMBAT_ROUND = "combat_round"
    COMBAT_END = "combat_end"
    ATTACK = "attack"
    DAMAGE = "damage"
    HEAL = "heal"
    DEATH = "death"

    # Social events
    DIALOGUE = "dialogue"
    PERSUASION = "persuasion"
    INTIMIDATION = "intimidation"
    DECEPTION = "deception"

    # Movement events
    TRAVEL = "travel"
    ENTER_LOCATION = "enter_location"
    EXIT_LOCATION = "exit_location"

    # Item events
    ITEM_PICKUP = "item_pickup"
    ITEM_DROP = "item_drop"
    ITEM_TRANSFER = "item_transfer"
    ITEM_USE = "item_use"
    ITEM_EQUIP = "item_equip"
    ITEM_UNEQUIP = "item_unequip"

    # Economy events
    TRANSACTION_BUY = "transaction_buy"
    TRANSACTION_SELL = "transaction_sell"
    LOOT = "loot"

    # Rest events
    SHORT_REST = "short_rest"
    LONG_REST = "long_rest"

    # Skill/ability events
    SKILL_CHECK = "skill_check"
    SAVING_THROW = "saving_throw"
    ABILITY_CHECK = "ability_check"

    # World events
    FORK = "fork"
    WORLD_CHANGE = "world_change"
    TIME_PASSAGE = "time_passage"

    # Meta events
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    PLAYER_JOIN = "player_join"
    PLAYER_LEAVE = "player_leave"


class EventOutcome(str, Enum):
    """Possible outcomes of an event."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    CRITICAL_SUCCESS = "critical_success"
    CRITICAL_FAILURE = "critical_failure"
    NEUTRAL = "neutral"


class CombatPayload(BaseModel):
    """Payload for combat-related events."""

    target_id: UUID | None = None
    weapon: str | None = None
    attack_roll: int | None = None
    damage_roll: int | None = None
    damage_type: str | None = None
    is_critical: bool = False
    is_fumble: bool = False
    conditions_applied: list[str] = Field(default_factory=list)


class DialoguePayload(BaseModel):
    """Payload for dialogue events."""

    listener_id: UUID | None = None
    text: str
    emotion: str | None = None
    language: str = "common"


class TravelPayload(BaseModel):
    """Payload for travel events."""

    from_location_id: UUID | None = None
    to_location_id: UUID
    travel_method: str = "walking"
    distance: int | None = None  # in feet
    duration_minutes: int | None = None


class ItemPayload(BaseModel):
    """Payload for item-related events."""

    item_id: UUID
    item_name: str
    quantity: int = 1
    from_entity_id: UUID | None = None
    to_entity_id: UUID | None = None


class TransactionPayload(BaseModel):
    """Payload for economic transactions."""

    counterparty_id: UUID | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    currency_amount: int = 0  # in copper pieces
    transaction_type: str = "purchase"


class CheckPayload(BaseModel):
    """Payload for skill checks and saving throws."""

    check_type: str  # skill name or ability
    dc: int
    roll: int
    modifier: int
    total: int
    advantage: bool = False
    disadvantage: bool = False


class RestPayload(BaseModel):
    """Payload for rest events."""

    rest_type: str  # "short" or "long"
    hp_healed: int = 0
    hit_dice_spent: int = 0
    hit_dice_recovered: int = 0
    spell_slots_recovered: dict[int, int] = Field(default_factory=dict)


class ForkPayload(BaseModel):
    """Payload for timeline fork events."""

    parent_universe_id: UUID
    child_universe_id: UUID
    fork_reason: str
    fork_point_event_id: UUID | None = None


class Event(BaseModel):
    """
    Core event model - the atomic unit of story.

    Events are immutable records stored in Dolt's event log.
    They capture what happened, who did it, and the outcome.
    """

    id: UUID = Field(default_factory=uuid4)
    universe_id: UUID = Field(description="Which timeline this event occurred in")
    event_type: EventType
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When this event occurred (in-game time)"
    )
    real_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When this event was recorded (real time)"
    )

    # Who and what
    actor_id: UUID = Field(description="Who initiated this event")
    target_id: UUID | None = Field(default=None, description="Who/what was affected")
    location_id: UUID | None = Field(default=None, description="Where this happened")

    # Outcome
    outcome: EventOutcome = EventOutcome.NEUTRAL
    roll: int | None = Field(default=None, description="The d20 roll if applicable")

    # Payload (type-specific data)
    payload: dict[str, Any] = Field(default_factory=dict, description="Event-specific data")

    # Narrative
    narrative_summary: str = Field(default="", description="LLM-generated narrative description")

    # Causality chain
    caused_by_event_id: UUID | None = Field(
        default=None, description="Parent event that triggered this"
    )

    def is_combat_event(self) -> bool:
        """Check if this is a combat-related event."""
        return self.event_type in {
            EventType.COMBAT_START,
            EventType.COMBAT_ROUND,
            EventType.COMBAT_END,
            EventType.ATTACK,
            EventType.DAMAGE,
            EventType.HEAL,
            EventType.DEATH,
        }

    def is_social_event(self) -> bool:
        """Check if this is a social event."""
        return self.event_type in {
            EventType.DIALOGUE,
            EventType.PERSUASION,
            EventType.INTIMIDATION,
            EventType.DECEPTION,
        }

    def is_movement_event(self) -> bool:
        """Check if this is a movement event."""
        return self.event_type in {
            EventType.TRAVEL,
            EventType.ENTER_LOCATION,
            EventType.EXIT_LOCATION,
        }


def create_combat_event(
    universe_id: UUID,
    actor_id: UUID,
    event_type: EventType,
    target_id: UUID | None = None,
    location_id: UUID | None = None,
    attack_roll: int | None = None,
    damage: int | None = None,
    damage_type: str | None = None,
    is_critical: bool = False,
    outcome: EventOutcome = EventOutcome.NEUTRAL,
    narrative: str = "",
) -> Event:
    """Factory function to create a combat event."""
    payload = CombatPayload(
        target_id=target_id,
        attack_roll=attack_roll,
        damage_roll=damage,
        damage_type=damage_type,
        is_critical=is_critical,
    )
    return Event(
        universe_id=universe_id,
        event_type=event_type,
        actor_id=actor_id,
        target_id=target_id,
        location_id=location_id,
        outcome=outcome,
        roll=attack_roll,
        payload=payload.model_dump(),
        narrative_summary=narrative,
    )


def create_dialogue_event(
    universe_id: UUID,
    speaker_id: UUID,
    text: str,
    listener_id: UUID | None = None,
    location_id: UUID | None = None,
    emotion: str | None = None,
    narrative: str = "",
) -> Event:
    """Factory function to create a dialogue event."""
    payload = DialoguePayload(
        listener_id=listener_id,
        text=text,
        emotion=emotion,
    )
    return Event(
        universe_id=universe_id,
        event_type=EventType.DIALOGUE,
        actor_id=speaker_id,
        target_id=listener_id,
        location_id=location_id,
        outcome=EventOutcome.NEUTRAL,
        payload=payload.model_dump(),
        narrative_summary=narrative or text,
    )


def create_travel_event(
    universe_id: UUID,
    traveler_id: UUID,
    to_location_id: UUID,
    from_location_id: UUID | None = None,
    travel_method: str = "walking",
    narrative: str = "",
) -> Event:
    """Factory function to create a travel event."""
    payload = TravelPayload(
        from_location_id=from_location_id,
        to_location_id=to_location_id,
        travel_method=travel_method,
    )
    return Event(
        universe_id=universe_id,
        event_type=EventType.TRAVEL,
        actor_id=traveler_id,
        location_id=to_location_id,
        outcome=EventOutcome.SUCCESS,
        payload=payload.model_dump(),
        narrative_summary=narrative,
    )


def create_check_event(
    universe_id: UUID,
    actor_id: UUID,
    event_type: EventType,
    check_type: str,
    dc: int,
    roll: int,
    modifier: int,
    outcome: EventOutcome,
    location_id: UUID | None = None,
    narrative: str = "",
) -> Event:
    """Factory function to create a skill check or saving throw event."""
    payload = CheckPayload(
        check_type=check_type,
        dc=dc,
        roll=roll,
        modifier=modifier,
        total=roll + modifier,
    )
    return Event(
        universe_id=universe_id,
        event_type=event_type,
        actor_id=actor_id,
        location_id=location_id,
        outcome=outcome,
        roll=roll,
        payload=payload.model_dump(),
        narrative_summary=narrative,
    )


def create_fork_event(
    parent_universe_id: UUID,
    child_universe_id: UUID,
    actor_id: UUID,
    fork_reason: str,
    fork_point_event_id: UUID | None = None,
) -> Event:
    """Factory function to create a timeline fork event."""
    payload = ForkPayload(
        parent_universe_id=parent_universe_id,
        child_universe_id=child_universe_id,
        fork_reason=fork_reason,
        fork_point_event_id=fork_point_event_id,
    )
    return Event(
        universe_id=child_universe_id,
        event_type=EventType.FORK,
        actor_id=actor_id,
        outcome=EventOutcome.SUCCESS,
        payload=payload.model_dump(),
        narrative_summary=f"Timeline forked: {fork_reason}",
    )
