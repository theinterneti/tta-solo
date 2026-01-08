"""
Core Engine for TTA-Solo.

The engine orchestrates:
- Intent parsing (understanding player actions)
- Skill routing (resolving mechanics)
- Narrative generation (responding to player)
- Event recording (persisting state)
"""

from __future__ import annotations

from src.engine.game import GameEngine, NarrativeGenerator, SimpleNarrativeGenerator
from src.engine.intent import (
    HybridIntentParser,
    LLMProvider,
    MockLLMParser,
    PatternIntentParser,
)
from src.engine.models import (
    Context,
    EngineConfig,
    EntitySummary,
    Intent,
    IntentType,
    RelationshipSummary,
    RollSummary,
    Session,
    SkillResult,
    Turn,
    TurnResult,
)
from src.engine.router import CheckContext, CombatContext, RestContext, SkillRouter

__all__ = [
    # Main engine
    "GameEngine",
    # Models
    "Context",
    "EngineConfig",
    "EntitySummary",
    "Intent",
    "IntentType",
    "RelationshipSummary",
    "RollSummary",
    "Session",
    "SkillResult",
    "Turn",
    "TurnResult",
    # Intent parsing
    "HybridIntentParser",
    "LLMProvider",
    "MockLLMParser",
    "PatternIntentParser",
    # Skill routing
    "CheckContext",
    "CombatContext",
    "RestContext",
    "SkillRouter",
    # Narrative
    "NarrativeGenerator",
    "SimpleNarrativeGenerator",
]
