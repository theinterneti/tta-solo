"""Tests for the CrunchAffinity model."""

from __future__ import annotations

from src.models.crunch_affinity import CrunchAffinity, CrunchLevel


def test_default_initialization():
    ca = CrunchAffinity()
    assert ca.level == CrunchLevel.BALANCED
    assert ca.raw_score == 0.0
    assert ca.signals == []
    assert ca.manual_override is False
    assert ca.history_window == 50


def test_crunchy_signals_drift_to_detailed():
    ca = CrunchAffinity()
    for _ in range(10):
        ca.record_signal(0.8)
    assert ca.level == CrunchLevel.DETAILED
    assert ca.raw_score > 20.0


def test_narrative_signals_drift_to_narrative():
    ca = CrunchAffinity()
    for _ in range(10):
        ca.record_signal(-0.8)
    assert ca.level == CrunchLevel.NARRATIVE
    assert ca.raw_score < -20.0


def test_mixed_signals_stay_balanced():
    ca = CrunchAffinity()
    # Alternate between crunchy and narrative
    for i in range(20):
        ca.record_signal(0.8 if i % 2 == 0 else -0.8)
    assert ca.level == CrunchLevel.BALANCED
    assert -20.0 < ca.raw_score < 20.0


def test_manual_override_locks_level():
    ca = CrunchAffinity()
    ca.set_level(CrunchLevel.NARRATIVE)
    assert ca.level == CrunchLevel.NARRATIVE
    assert ca.manual_override is True

    # Signals should be ignored
    for _ in range(20):
        ca.record_signal(0.8)
    assert ca.level == CrunchLevel.NARRATIVE
    assert len(ca.signals) == 0  # Signals not even recorded


def test_unlock_resumes_drift():
    ca = CrunchAffinity()
    # Lock to narrative
    ca.set_level(CrunchLevel.NARRATIVE)
    assert ca.manual_override is True

    # Unlock
    ca.unlock()
    assert ca.manual_override is False

    # Now signals should work
    for _ in range(10):
        ca.record_signal(0.8)
    assert ca.level == CrunchLevel.DETAILED


def test_history_window_trimming():
    ca = CrunchAffinity(history_window=5)
    for _ in range(10):
        ca.record_signal(0.5)
    assert len(ca.signals) == 5


def test_position_weighting_recent_signals_dominate():
    ca = CrunchAffinity()
    # Start with many narrative signals
    for _ in range(20):
        ca.record_signal(-0.8)
    assert ca.level == CrunchLevel.NARRATIVE

    # Add crunchy signals — recent ones should dominate
    for _ in range(30):
        ca.record_signal(0.8)

    assert ca.level == CrunchLevel.DETAILED
    assert ca.raw_score > 0


def test_get_status_auto():
    ca = CrunchAffinity()
    status = ca.get_status()
    assert "auto" in status
    assert "balanced" in status


def test_get_status_locked():
    ca = CrunchAffinity()
    ca.set_level(CrunchLevel.DETAILED)
    status = ca.get_status()
    assert "locked" in status
    assert "detailed" in status


def test_score_clamped_to_range():
    ca = CrunchAffinity()
    # All max-weight signals
    for _ in range(50):
        ca.record_signal(1.0)
    assert ca.raw_score <= 100.0

    ca2 = CrunchAffinity()
    for _ in range(50):
        ca2.record_signal(-1.0)
    assert ca2.raw_score >= -100.0


def test_unlock_recalculates_from_existing_signals():
    ca = CrunchAffinity()
    # Record crunchy signals
    for _ in range(10):
        ca.record_signal(0.8)
    assert ca.level == CrunchLevel.DETAILED

    # Lock to narrative
    ca.set_level(CrunchLevel.NARRATIVE)
    assert ca.level == CrunchLevel.NARRATIVE

    # Unlock — should recalculate from existing signals
    ca.unlock()
    assert ca.level == CrunchLevel.DETAILED
