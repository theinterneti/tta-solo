"""Tests for the /rest REPL command."""

from __future__ import annotations

from uuid import uuid4

from src.cli.repl import GameREPL, GameState
from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.engine import GameEngine
from src.models.entity import create_character
from src.models.resources import CooldownTracker, EntityResources


def _make_state(hp_current: int = 20, hp_max: int = 20) -> tuple[GameState, GameREPL]:
    """Create a GameState with a character saved in the in-memory Dolt repo."""
    dolt = InMemoryDoltRepository()
    neo4j = InMemoryNeo4jRepository()
    engine = GameEngine(dolt=dolt, neo4j=neo4j)

    universe_id = uuid4()
    character = create_character(universe_id=universe_id, name="Hero", hp_max=hp_max)
    character.stats.hp_current = hp_current  # type: ignore[union-attr]
    dolt.save_entity(character)

    state = GameState(
        engine=engine,
        universe_id=universe_id,
        character_id=character.id,
    )

    repl = GameREPL()

    return state, repl


# --- Short rest tests ---


def test_short_rest_heals_half_missing_hp():
    state, repl = _make_state(hp_current=10, hp_max=20)
    result = repl._cmd_rest(state, ["short"])

    assert result is not None
    assert "+5" in result
    assert "15/20" in result

    # Verify entity was persisted
    char = state.engine.dolt.get_entity(state.character_id, state.universe_id)
    assert char is not None
    assert char.stats.hp_current == 15  # type: ignore[union-attr]


def test_short_rest_at_full_hp():
    state, repl = _make_state(hp_current=20, hp_max=20)
    result = repl._cmd_rest(state, ["short"])

    assert result is not None
    assert "already full" in result


def test_no_args_defaults_to_short_rest():
    state, repl = _make_state(hp_current=10, hp_max=20)
    result = repl._cmd_rest(state, [])

    assert result is not None
    assert "short rest" in result


# --- Long rest tests ---


def test_long_rest_heals_to_full():
    state, repl = _make_state(hp_current=5, hp_max=20)
    result = repl._cmd_rest(state, ["long"])

    assert result is not None
    assert "+15" in result
    assert "20/20" in result

    char = state.engine.dolt.get_entity(state.character_id, state.universe_id)
    assert char is not None
    assert char.stats.hp_current == 20  # type: ignore[union-attr]


def test_long_rest_resets_defy_death_uses():
    state, repl = _make_state(hp_current=20, hp_max=20)
    state.defy_death_uses = 3
    repl._cmd_rest(state, ["long"])

    assert state.defy_death_uses == 0


def test_long_rest_at_full_hp():
    state, repl = _make_state(hp_current=20, hp_max=20)
    result = repl._cmd_rest(state, ["long"])

    assert result is not None
    assert "already full" in result


def test_long_rest_restores_cooldowns():
    state, repl = _make_state(hp_current=20, hp_max=20)
    state.resources = EntityResources(
        cooldowns={
            "shield_wall": CooldownTracker(
                max_uses=1,
                current_uses=0,
                recharge_on_rest="long",
            ),
        }
    )
    result = repl._cmd_rest(state, ["long"])

    assert result is not None
    assert "shield wall" in result


def test_short_rest_restores_short_rest_cooldowns():
    state, repl = _make_state(hp_current=20, hp_max=20)
    state.resources = EntityResources(
        cooldowns={
            "second_wind": CooldownTracker(
                max_uses=1,
                current_uses=0,
                recharge_on_rest="short",
            ),
        }
    )
    result = repl._cmd_rest(state, ["short"])

    assert result is not None
    assert "second wind" in result


# --- Error handling ---


def test_invalid_rest_type():
    state, repl = _make_state()
    result = repl._cmd_rest(state, ["mega"])

    assert result is not None
    assert "Usage" in result


def test_no_character_loaded():
    state, repl = _make_state()
    state.character_id = None
    result = repl._cmd_rest(state, ["short"])

    assert result == "No character loaded."
