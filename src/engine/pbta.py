"""
PbtA (Powered by the Apocalypse) Move System for TTA-Solo.

Implements the three-tier outcome system:
- Strong Hit (10+): Full success plus extra benefit
- Weak Hit (7-9): Success with cost or complication
- Miss (6-): Failure, GM makes a move

Also provides GM move selection for miss outcomes.
"""

from __future__ import annotations

import random
from enum import Enum

from pydantic import BaseModel, Field


class PbtAOutcome(str, Enum):
    """PbtA-style outcome tiers."""

    STRONG_HIT = "strong_hit"  # 10+: Full success + extra
    WEAK_HIT = "weak_hit"  # 7-9: Success with cost
    MISS = "miss"  # 6-: Failure, GM makes a move


class GMMoveType(str, Enum):
    """
    Moves the GM can make on player failures.

    Categorized as:
    - Soft moves: Warnings that telegraph danger
    - Hard moves: Direct consequences
    - Always available: Can be used anytime
    """

    # Soft moves (warnings)
    SHOW_DANGER = "show_danger"
    OFFER_OPPORTUNITY = "offer_opportunity"
    REVEAL_UNWELCOME_TRUTH = "reveal_unwelcome_truth"

    # Hard moves (consequences)
    DEAL_DAMAGE = "deal_damage"
    USE_MONSTER_MOVE = "use_monster_move"
    SEPARATE_THEM = "separate_them"
    TAKE_AWAY = "take_away"
    CAPTURE = "capture"

    # Always available
    ADVANCE_TIME = "advance_time"
    INTRODUCE_NPC = "introduce_npc"
    CHANGE_ENVIRONMENT = "change_environment"


# GM moves categorized by severity
SOFT_MOVES = {
    GMMoveType.SHOW_DANGER,
    GMMoveType.OFFER_OPPORTUNITY,
    GMMoveType.REVEAL_UNWELCOME_TRUTH,
}

HARD_MOVES = {
    GMMoveType.DEAL_DAMAGE,
    GMMoveType.USE_MONSTER_MOVE,
    GMMoveType.SEPARATE_THEM,
    GMMoveType.TAKE_AWAY,
    GMMoveType.CAPTURE,
}

NEUTRAL_MOVES = {
    GMMoveType.ADVANCE_TIME,
    GMMoveType.INTRODUCE_NPC,
    GMMoveType.CHANGE_ENVIRONMENT,
}


class GMMove(BaseModel):
    """A GM move selected in response to a player miss."""

    type: GMMoveType
    is_hard: bool = Field(description="Whether this is a hard (consequential) move")
    description: str = Field(default="", description="What the GM move does")
    damage: int | None = Field(default=None, description="Damage dealt if applicable")
    condition: str | None = Field(default=None, description="Condition applied if any")


class PbtAResult(BaseModel):
    """Result of PbtA outcome calculation."""

    outcome: PbtAOutcome
    margin: int = Field(description="How far above/below thresholds")
    gm_move: GMMove | None = Field(default=None, description="GM move if miss")
    bonus_effect: str | None = Field(default=None, description="Extra effect on strong hit")


# Threshold mapping: d20 result ranges to PbtA outcomes
# We map the d20 system (1-20 + modifiers) to PbtA's 2d6 style outcomes
# Using percentile mapping: bottom ~17% miss, middle ~25% weak hit, top ~58% strong hit
# For d20 total: <10 = miss, 10-14 = weak hit, 15+ = strong hit
PBTA_THRESHOLDS = {
    "miss": 10,  # Below this is a miss
    "weak_hit": 15,  # Below this (but >= miss) is weak hit
    # >= weak_hit threshold is strong hit
}


def calculate_pbta_outcome(
    total: int,
    dc: int | None = None,
    is_critical: bool = False,
    is_fumble: bool = False,
) -> PbtAOutcome:
    """
    Calculate PbtA outcome from a d20 roll.

    Maps d20 results to PbtA's three-tier system:
    - Critical hit always = Strong Hit
    - Fumble always = Miss
    - Otherwise based on total vs DC or absolute thresholds

    Args:
        total: Total roll result (die + modifiers)
        dc: Difficulty class if applicable
        is_critical: Whether the roll was a natural 20
        is_fumble: Whether the roll was a natural 1

    Returns:
        PbtAOutcome enum value
    """
    # Criticals and fumbles override normal calculation
    if is_critical:
        return PbtAOutcome.STRONG_HIT
    if is_fumble:
        return PbtAOutcome.MISS

    # If we have a DC, calculate based on margin of success/failure
    if dc is not None:
        margin = total - dc
        if margin >= 5:  # Beat by 5+ = strong hit
            return PbtAOutcome.STRONG_HIT
        elif margin >= 0:  # Beat or tied = weak hit
            return PbtAOutcome.WEAK_HIT
        else:  # Failed = miss
            return PbtAOutcome.MISS

    # Without DC, use absolute thresholds
    if total >= PBTA_THRESHOLDS["weak_hit"]:
        return PbtAOutcome.STRONG_HIT
    elif total >= PBTA_THRESHOLDS["miss"]:
        return PbtAOutcome.WEAK_HIT
    else:
        return PbtAOutcome.MISS


def select_gm_move(
    danger_level: int = 0,
    is_combat: bool = False,
    recent_soft_moves: int = 0,
) -> GMMove:
    """
    Select an appropriate GM move for a miss.

    The selection logic follows PbtA principles:
    - Soft moves are preferred when danger is low
    - Hard moves after repeated soft moves or in high danger
    - Combat situations favor damage/monster moves

    Args:
        danger_level: Current location danger (0-20)
        is_combat: Whether this is during combat
        recent_soft_moves: How many soft moves have been made recently

    Returns:
        GMMove with selected type and description
    """
    # Determine if we should make a hard move
    make_hard_move = (
        danger_level >= 10  # High danger
        or recent_soft_moves >= 2  # Already warned twice
        or (is_combat and random.random() < 0.5)  # 50% in combat
    )

    if make_hard_move:
        if is_combat:
            # Combat favors damage or monster moves
            move_type = random.choice([
                GMMoveType.DEAL_DAMAGE,
                GMMoveType.USE_MONSTER_MOVE,
                GMMoveType.TAKE_AWAY,
            ])
        else:
            move_type = random.choice(list(HARD_MOVES))
    else:
        # Default to soft moves
        move_type = random.choice(list(SOFT_MOVES))

    # Build the move with description
    return GMMove(
        type=move_type,
        is_hard=move_type in HARD_MOVES,
        description=_get_move_description(move_type),
        damage=_get_move_damage(move_type, danger_level) if move_type == GMMoveType.DEAL_DAMAGE else None,
    )


def _get_move_description(move_type: GMMoveType) -> str:
    """Get a template description for a GM move type."""
    descriptions = {
        # Soft moves
        GMMoveType.SHOW_DANGER: "Something dangerous reveals itself...",
        GMMoveType.OFFER_OPPORTUNITY: "An opportunity presents itself, but at a cost...",
        GMMoveType.REVEAL_UNWELCOME_TRUTH: "You realize something troubling...",
        # Hard moves
        GMMoveType.DEAL_DAMAGE: "The enemy strikes back!",
        GMMoveType.USE_MONSTER_MOVE: "The creature uses its special ability!",
        GMMoveType.SEPARATE_THEM: "You're driven apart from your allies!",
        GMMoveType.TAKE_AWAY: "Something important is lost or broken!",
        GMMoveType.CAPTURE: "You find yourself trapped!",
        # Neutral moves
        GMMoveType.ADVANCE_TIME: "Time passes, and the situation changes...",
        GMMoveType.INTRODUCE_NPC: "Someone new arrives on the scene...",
        GMMoveType.CHANGE_ENVIRONMENT: "The environment shifts around you...",
    }
    return descriptions.get(move_type, "Something happens...")


def _get_move_damage(move_type: GMMoveType, danger_level: int) -> int:
    """Calculate damage for a damage-dealing move."""
    if move_type != GMMoveType.DEAL_DAMAGE:
        return 0

    # Base damage scales with danger level
    # Danger 0-5: 1d4 (avg 2.5), 6-10: 1d6 (avg 3.5), 11-15: 1d8 (avg 4.5), 16+: 1d10 (avg 5.5)
    if danger_level <= 5:
        return random.randint(1, 4)
    elif danger_level <= 10:
        return random.randint(1, 6)
    elif danger_level <= 15:
        return random.randint(1, 8)
    else:
        return random.randint(1, 10)


def get_strong_hit_bonus(intent_type: str) -> str:
    """
    Get the bonus effect for a strong hit based on intent type.

    Strong hits in PbtA give something extra beyond success.

    Args:
        intent_type: The type of action being resolved

    Returns:
        Description of the bonus effect
    """
    bonuses = {
        "attack": "You find an opening for a follow-up attack.",
        "persuade": "They're genuinely convinced and may help further.",
        "intimidate": "They're completely cowed and won't oppose you.",
        "deceive": "They believe you completely and share useful information.",
        "search": "You find exactly what you're looking for, and something else useful.",
        "move": "You move swiftly and gain a tactical advantage.",
        "rest": "You feel especially refreshed and ready for action.",
    }
    return bonuses.get(intent_type, "You succeed with style.")


def get_weak_hit_complication(intent_type: str) -> str:
    """
    Get the complication for a weak hit based on intent type.

    Weak hits succeed but with a cost or complication.

    Args:
        intent_type: The type of action being resolved

    Returns:
        Description of the complication
    """
    complications = {
        "attack": "You hit, but leave yourself exposed.",
        "persuade": "They agree, but want something in return.",
        "intimidate": "They comply, but will resent you for it.",
        "deceive": "They believe you, but remain suspicious.",
        "search": "You find something, but it takes longer than expected.",
        "move": "You get there, but the journey was harder than expected.",
        "rest": "You rest, but something interrupts your peace.",
    }
    return complications.get(intent_type, "You succeed, but barely.")
