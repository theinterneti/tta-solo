"""
Crunch Affinity System.

Tracks player mechanical engagement and adapts output detail level.
See specs/crunch-affinity.md for full specification.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CrunchLevel(StrEnum):
    """Output detail levels."""

    NARRATIVE = "narrative"
    BALANCED = "balanced"
    DETAILED = "detailed"


SIGNAL_WEIGHTS: dict[str, float] = {
    # Crunchy (positive) — slash commands with mechanical intent
    "slash_combat": 0.8,
    "slash_info": 0.6,
    # Natural language with specific mechanical keywords
    "specific_target": 0.3,
    # Narrative (negative) — vague or simple natural language
    "natural_simple": -0.6,
    "natural_vague": -0.8,
}

# Thresholds for level transitions
NARRATIVE_THRESHOLD: float = -20.0
DETAILED_THRESHOLD: float = 20.0


class CrunchAffinity(BaseModel):
    """Adaptive crunch level tracker.

    Maintains a sliding window of signal weights from player inputs
    and computes a position-weighted score to determine the current
    detail level.
    """

    level: CrunchLevel = CrunchLevel.BALANCED
    raw_score: float = Field(default=0.0, description="Current score, -100 to +100")
    signals: list[float] = Field(default_factory=list, description="Signal weight history")
    manual_override: bool = Field(default=False, description="Whether level is manually locked")
    history_window: int = Field(default=50, description="Max signals to keep")

    def record_signal(self, weight: float) -> None:
        """Record a new input signal and update the crunch level.

        Args:
            weight: Signal weight (-1.0 to +1.0). Positive = crunchy, negative = narrative.
        """
        if self.manual_override:
            return

        self.signals.append(weight)
        if len(self.signals) > self.history_window:
            self.signals = self.signals[-self.history_window :]

        self._recalculate()

    def set_level(self, level: CrunchLevel) -> None:
        """Manually lock the crunch level.

        Args:
            level: The level to lock to.
        """
        self.level = level
        self.manual_override = True

    def unlock(self) -> None:
        """Re-enable adaptive drift."""
        self.manual_override = False
        self._recalculate()

    def get_status(self) -> str:
        """Return a human-readable status string."""
        mode = "locked" if self.manual_override else "auto"
        return f"Crunch: {self.level.value} ({mode}, score: {self.raw_score:+.0f})"

    def _recalculate(self) -> None:
        """Recalculate raw_score and level from signal history."""
        if not self.signals:
            self.raw_score = 0.0
            self.level = CrunchLevel.BALANCED
            return

        n = len(self.signals)
        weighted_sum = sum(w * (i + 1) for i, w in enumerate(self.signals))
        divisor = n * (n + 1) / 2  # sum(1..n)
        self.raw_score = (weighted_sum / divisor) * 100.0

        # Clamp to range
        self.raw_score = max(-100.0, min(100.0, self.raw_score))

        # Apply thresholds
        if self.raw_score <= NARRATIVE_THRESHOLD:
            self.level = CrunchLevel.NARRATIVE
        elif self.raw_score >= DETAILED_THRESHOLD:
            self.level = CrunchLevel.DETAILED
        else:
            self.level = CrunchLevel.BALANCED
