"""
Core Engine for TTA-Solo.

The engine orchestrates:
- Intent parsing (understanding player actions)
- Skill routing (resolving mechanics)
- Narrative generation (responding to player)
- Event recording (persisting state)

Phase 3 introduces specialized agents:
- GM (Game Master): Orchestration and narrative
- Rules Lawyer: Mechanical enforcement
- Lorekeeper: Context retrieval

Phase 4 introduces:
- PbtA move system (strong hit/weak hit/miss)
- GM moves on failures
"""

from __future__ import annotations

from src.engine.agents import (
    Agent,
    AgentMessage,
    AgentOrchestrator,
    AgentRole,
    GMAgent,
    LorekeeperAgent,
    MessageType,
    RulesLawyerAgent,
)
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
    EngineForkResult,
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
from src.engine.pbta import (
    GMMove,
    GMMoveType,
    PbtAOutcome,
    PbtAResult,
    calculate_pbta_outcome,
    get_strong_hit_bonus,
    get_weak_hit_complication,
    select_gm_move,
)
from src.engine.router import CheckContext, CombatContext, RestContext, SkillRouter

__all__ = [
    # Main engine
    "GameEngine",
    # Agents (Phase 3)
    "Agent",
    "AgentMessage",
    "AgentOrchestrator",
    "AgentRole",
    "GMAgent",
    "LorekeeperAgent",
    "MessageType",
    "RulesLawyerAgent",
    # PbtA (Phase 4)
    "GMMove",
    "GMMoveType",
    "PbtAOutcome",
    "PbtAResult",
    "calculate_pbta_outcome",
    "get_strong_hit_bonus",
    "get_weak_hit_complication",
    "select_gm_move",
    # Models
    "Context",
    "EngineConfig",
    "EntitySummary",
    "EngineForkResult",
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
