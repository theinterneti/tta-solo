"""Tests for the /setting command and crunch affinity REPL integration."""

from __future__ import annotations

from uuid import uuid4

from src.cli.repl import GameREPL, GameState
from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.engine import GameEngine
from src.engine.models import RollSummary, TurnResult
from src.models.crunch_affinity import SIGNAL_WEIGHTS, CrunchLevel


def _make_state() -> tuple[GameState, GameREPL]:
    """Create a minimal GameState and REPL for testing."""
    dolt = InMemoryDoltRepository()
    neo4j = InMemoryNeo4jRepository()
    engine = GameEngine(dolt=dolt, neo4j=neo4j)

    state = GameState(
        engine=engine,
        universe_id=uuid4(),
    )
    repl = GameREPL()
    return state, repl


# --- /setting command tests ---


def test_setting_shows_current_level():
    state, repl = _make_state()
    result = repl._cmd_setting(state, [])
    assert result is not None
    assert "balanced" in result.lower()
    assert "auto" in result.lower()


def test_setting_crunch_narrative_locks():
    state, repl = _make_state()
    result = repl._cmd_setting(state, ["crunch", "narrative"])
    assert result is not None
    assert "locked" in result.lower()
    assert state.crunch_affinity.level == CrunchLevel.NARRATIVE
    assert state.crunch_affinity.manual_override is True


def test_setting_crunch_detailed_locks():
    state, repl = _make_state()
    result = repl._cmd_setting(state, ["crunch", "detailed"])
    assert result is not None
    assert state.crunch_affinity.level == CrunchLevel.DETAILED


def test_setting_crunch_auto_unlocks():
    state, repl = _make_state()
    # First lock
    repl._cmd_setting(state, ["crunch", "narrative"])
    assert state.crunch_affinity.manual_override is True

    # Then unlock
    result = repl._cmd_setting(state, ["crunch", "auto"])
    assert result is not None
    assert "adaptive" in result.lower() or "unlocked" in result.lower()
    assert state.crunch_affinity.manual_override is False


def test_setting_invalid_level_shows_usage():
    state, repl = _make_state()
    result = repl._cmd_setting(state, ["crunch", "foobar"])
    assert result is not None
    assert "usage" in result.lower()


def test_setting_unknown_setting_shows_usage():
    state, repl = _make_state()
    result = repl._cmd_setting(state, ["foobar"])
    assert result is not None
    assert "unknown" in result.lower()


# --- Signal recording from slash commands ---


def test_slash_attack_records_crunchy_signal():
    state, repl = _make_state()
    weight = repl._command_signal_weight("attack")
    assert weight == SIGNAL_WEIGHTS["slash_combat"]


def test_slash_status_records_info_signal():
    state, repl = _make_state()
    weight = repl._command_signal_weight("status")
    assert weight == SIGNAL_WEIGHTS["slash_info"]


def test_slash_help_is_neutral():
    state, repl = _make_state()
    weight = repl._command_signal_weight("help")
    assert weight == 0.0


def test_slash_look_is_neutral():
    state, repl = _make_state()
    weight = repl._command_signal_weight("look")
    assert weight == 0.0


def test_slash_rest_is_neutral():
    state, repl = _make_state()
    weight = repl._command_signal_weight("rest")
    assert weight == 0.0


# --- Signal recording from natural language ---


def test_natural_language_specific_keyword():
    state, repl = _make_state()
    weight = repl._natural_language_signal_weight("attack the goblin with my longsword")
    assert weight == SIGNAL_WEIGHTS["specific_target"]


def test_natural_language_simple_action():
    state, repl = _make_state()
    weight = repl._natural_language_signal_weight("I swing at the goblin")
    assert weight == SIGNAL_WEIGHTS["natural_simple"]


def test_natural_language_vague():
    state, repl = _make_state()
    weight = repl._natural_language_signal_weight("I try to sneak past the guards")
    assert weight == SIGNAL_WEIGHTS["natural_vague"]


# --- _format_turn_result crunch level tests ---


def _make_turn_result(
    *,
    narrative: str = "You strike the goblin!",
    rolls: list[RollSummary] | None = None,
    state_changes: list[str] | None = None,
) -> TurnResult:
    """Create a TurnResult for formatting tests."""
    return TurnResult(
        narrative=narrative,
        rolls=rolls or [],
        state_changes=state_changes or [],
        turn_id=uuid4(),
    )


def test_format_narrative_hides_rolls():
    repl = GameREPL()
    result = _make_turn_result(
        rolls=[
            RollSummary(description="Attack", roll=15, modifier=5, total=20),
        ],
        state_changes=["HP: Goblin 15 -> 3"],
    )
    output = repl._format_turn_result(result, CrunchLevel.NARRATIVE)
    assert "You strike the goblin!" in output
    # No roll details
    assert "Attack:" not in output
    assert "20" not in output
    # No state changes
    assert "HP:" not in output


def test_format_narrative_shows_crit():
    repl = GameREPL()
    result = _make_turn_result(
        rolls=[
            RollSummary(description="Attack", roll=20, modifier=5, total=25, is_critical=True),
        ],
    )
    output = repl._format_turn_result(result, CrunchLevel.NARRATIVE)
    assert "critical" in output.lower()


def test_format_narrative_shows_fumble():
    repl = GameREPL()
    result = _make_turn_result(
        rolls=[
            RollSummary(description="Attack", roll=1, modifier=5, total=6, is_fumble=True),
        ],
    )
    output = repl._format_turn_result(result, CrunchLevel.NARRATIVE)
    assert "fumble" in output.lower()


def test_format_balanced_shows_totals_without_modifiers():
    repl = GameREPL()
    result = _make_turn_result(
        rolls=[
            RollSummary(description="Attack", roll=15, modifier=5, total=20),
        ],
        state_changes=["HP: Goblin 15 -> 3"],
    )
    output = repl._format_turn_result(result, CrunchLevel.BALANCED)
    assert "[Attack: 20]" in output
    # Should NOT show modifier breakdown in balanced mode
    assert "(15+5)" not in output
    # State changes shown
    assert "HP: Goblin 15 -> 3" in output


def test_format_detailed_shows_full_breakdown():
    repl = GameREPL()
    result = _make_turn_result(
        rolls=[
            RollSummary(description="Attack", roll=15, modifier=5, total=20),
        ],
        state_changes=["HP: Goblin 15 -> 3"],
    )
    output = repl._format_turn_result(result, CrunchLevel.DETAILED)
    assert "[Attack: 20 (15+5)]" in output
    assert "HP: Goblin 15 -> 3" in output


def test_format_detailed_shows_crit():
    repl = GameREPL()
    result = _make_turn_result(
        rolls=[
            RollSummary(description="Attack", roll=20, modifier=5, total=25, is_critical=True),
        ],
    )
    output = repl._format_turn_result(result, CrunchLevel.DETAILED)
    assert "CRITICAL!" in output
    assert "(20+5)" in output
