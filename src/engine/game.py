"""
Game Engine for TTA-Solo.

The main orchestration layer that processes player turns.
Coordinates intent parsing, skill execution, and narrative generation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID, uuid4

from src.db.interfaces import DoltRepository, Neo4jRepository
from src.engine.intent import HybridIntentParser, LLMProvider
from src.engine.models import (
    Context,
    EngineConfig,
    EntitySummary,
    Intent,
    IntentType,
    Session,
    SkillResult,
    Turn,
    TurnResult,
)
from src.engine.router import SkillRouter
from src.models import Entity, Event, EventOutcome, EventType


class NarrativeGenerator(Protocol):
    """Interface for narrative generation."""

    async def generate(
        self,
        intent: Intent,
        context: Context,
        skill_results: list[SkillResult],
    ) -> str:
        """Generate narrative response."""
        ...


class SimpleNarrativeGenerator:
    """Simple template-based narrative generator for Phase 1."""

    def __init__(self, tone: str = "adventure", verbosity: str = "normal") -> None:
        self.tone = tone
        self.verbosity = verbosity

    async def generate(
        self,
        intent: Intent,
        context: Context,
        skill_results: list[SkillResult],
    ) -> str:
        """Generate a simple narrative from skill results."""
        parts = []

        # Add skill result descriptions
        for result in skill_results:
            if result.description:
                parts.append(result.description)

        # Add some flavor based on intent type
        if not parts:
            parts.append(self._default_narrative(intent, context))

        narrative = " ".join(parts)

        # Add a prompt for next action if verbose
        if self.verbosity == "verbose":
            narrative += "\n\nWhat do you do?"

        return narrative

    def _default_narrative(self, intent: Intent, context: Context) -> str:
        """Generate default narrative for intents without skill results."""
        defaults = {
            IntentType.LOOK: f"You take in your surroundings in {context.location.name}.",
            IntentType.WAIT: "Time passes...",
            IntentType.UNCLEAR: "I'm not sure what you want to do. Could you be more specific?",
            IntentType.ASK_QUESTION: "That's an interesting question about the world.",
            IntentType.FORK: "You consider what might have been...",
        }
        return defaults.get(intent.type, "You do that.")


@dataclass
class GameEngine:
    """
    Main game engine orchestrating the game loop.

    Coordinates:
    - Intent parsing (understanding player actions)
    - Context retrieval (getting world state)
    - Skill execution (resolving mechanics)
    - Event recording (persisting changes)
    - Narrative generation (responding to player)
    """

    dolt: DoltRepository
    neo4j: Neo4jRepository
    config: EngineConfig = field(default_factory=EngineConfig)

    # Components (initialized in __post_init__)
    intent_parser: HybridIntentParser = field(init=False)
    router: SkillRouter = field(init=False)
    narrator: NarrativeGenerator = field(init=False)

    # Session tracking
    _sessions: dict[UUID, Session] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize engine components."""
        self.intent_parser = HybridIntentParser()
        self.router = SkillRouter()
        self.narrator = SimpleNarrativeGenerator(
            tone=self.config.tone,
            verbosity=self.config.verbosity,
        )

    def set_llm_provider(self, provider: LLMProvider) -> None:
        """Set the LLM provider for intent parsing."""
        self.intent_parser = HybridIntentParser(llm_provider=provider)

    def set_narrative_generator(self, generator: NarrativeGenerator) -> None:
        """Set a custom narrative generator."""
        self.narrator = generator

    async def start_session(
        self,
        universe_id: UUID,
        character_id: UUID,
        location_id: UUID | None = None,
    ) -> Session:
        """
        Start a new game session.

        Args:
            universe_id: The timeline to play in
            character_id: The player's character
            location_id: Starting location (or get from character)

        Returns:
            New Session object
        """
        # Get character to find location if not provided
        if location_id is None:
            character = self.dolt.get_entity(character_id, universe_id)
            if character and character.current_location_id:
                location_id = character.current_location_id
            else:
                # Use a default location
                location_id = uuid4()

        session = Session(
            universe_id=universe_id,
            character_id=character_id,
            location_id=location_id,
            tone=self.config.tone,
            verbosity=self.config.verbosity,
        )

        self._sessions[session.id] = session
        return session

    async def end_session(self, session_id: UUID) -> None:
        """End a game session."""
        self._sessions.pop(session_id, None)

    def get_session(self, session_id: UUID) -> Session | None:
        """Get an active session."""
        return self._sessions.get(session_id)

    async def process_turn(
        self,
        player_input: str,
        session_id: UUID,
    ) -> TurnResult:
        """
        Process a single player turn.

        This is the main game loop entry point.

        Args:
            player_input: Raw text from the player
            session_id: The active session ID

        Returns:
            TurnResult with narrative and metadata
        """
        start_time = time.time()

        # Get session
        session = self._sessions.get(session_id)
        if session is None:
            return TurnResult(
                narrative="No active session found.",
                turn_id=uuid4(),
                error="Session not found",
            )

        # Create turn record
        turn = Turn(
            player_input=player_input,
            universe_id=session.universe_id,
            actor_id=session.character_id,
            location_id=session.location_id,
        )

        try:
            # Phase 1: Parse intent
            turn.intent = await self.intent_parser.parse(player_input)

            # Phase 2: Get context
            turn.context = await self._get_context(session)

            # Phase 3: Resolve mechanics
            if turn.intent.type != IntentType.UNCLEAR:
                skill_result = self.router.resolve(turn.intent, turn.context)
                turn.skill_results.append(skill_result)

                # Update location if movement succeeded
                if turn.intent.type == IntentType.MOVE and skill_result.success:
                    # In a real implementation, we'd resolve the destination
                    # to an actual location ID
                    pass

            # Phase 4: Record events
            await self._record_events(turn, session)

            # Phase 5: Generate narrative
            turn.narrative = await self.narrator.generate(
                turn.intent,
                turn.context,
                turn.skill_results,
            )

        except Exception as e:
            turn.error = str(e)
            turn.narrative = "Something unexpected happened. What do you do?"

        # Calculate processing time
        turn.processing_time_ms = int((time.time() - start_time) * 1000)

        # Update session
        session.turn_count += 1
        session.last_turn_at = turn.timestamp

        # Build result
        rolls = [r.to_roll_summary() for r in turn.skill_results if r.roll is not None]

        return TurnResult(
            narrative=turn.narrative,
            rolls=rolls,
            state_changes=self._extract_state_changes(turn.skill_results),
            turn_id=turn.id,
            events_created=len(turn.events_created),
            processing_time_ms=turn.processing_time_ms,
            error=turn.error,
        )

    async def _get_context(self, session: Session) -> Context:
        """Build context for the current turn."""
        # Get actor
        actor_entity = self.dolt.get_entity(session.character_id, session.universe_id)
        if actor_entity:
            actor = self._entity_to_summary(actor_entity)
        else:
            actor = EntitySummary(
                id=session.character_id,
                name="Unknown",
                type="character",
            )

        # Get location
        location_entity = self.dolt.get_entity(session.location_id, session.universe_id)
        if location_entity:
            location = self._entity_to_summary(location_entity)
        else:
            location = EntitySummary(
                id=session.location_id,
                name="Unknown Location",
                type="location",
            )

        # Get entities in location
        entities_present = []
        relationships = self.neo4j.get_relationships(
            session.location_id,
            session.universe_id,
            relationship_type="LOCATED_IN",
        )
        for rel in relationships[:self.config.max_nearby_entities]:
            entity = self.dolt.get_entity(rel.from_entity_id, session.universe_id)
            if entity and entity.id != session.character_id:
                entities_present.append(self._entity_to_summary(entity))

        # Get recent events
        recent_events = self.dolt.get_events(
            session.universe_id,
            limit=self.config.max_recent_events,
        )
        event_summaries = [e.narrative_summary for e in recent_events if e.narrative_summary]

        return Context(
            actor=actor,
            location=location,
            entities_present=entities_present,
            recent_events=event_summaries,
            danger_level=location_entity.location_properties.danger_level
            if location_entity and location_entity.location_properties
            else 0,
        )

    def _entity_to_summary(self, entity: Entity) -> EntitySummary:
        """Convert Entity to lightweight EntitySummary."""
        return EntitySummary(
            id=entity.id,
            name=entity.name,
            type=entity.type.value,
            description=entity.description,
            hp_current=entity.stats.hp_current if entity.stats else None,
            hp_max=entity.stats.hp_max if entity.stats else None,
            ac=entity.stats.ac if entity.stats else None,
        )

    async def _record_events(self, turn: Turn, session: Session) -> None:
        """Record events from the turn."""
        if not turn.skill_results:
            return

        for result in turn.skill_results:
            if turn.intent is None:
                continue

            # Map intent to event type
            event_type = self._intent_to_event_type(turn.intent.type)

            # Create event
            event = Event(
                universe_id=session.universe_id,
                event_type=event_type,
                actor_id=session.character_id,
                target_id=turn.intent.target_id,
                location_id=session.location_id,
                outcome=self._result_to_outcome(result),
                roll=result.roll,
                payload={
                    "intent_type": turn.intent.type.value,
                    "description": result.description,
                },
                narrative_summary=result.description,
            )

            self.dolt.append_event(event)
            turn.events_created.append(event.id)

    def _intent_to_event_type(self, intent_type: IntentType) -> EventType:
        """Map intent type to event type."""
        mapping = {
            IntentType.ATTACK: EventType.ATTACK,
            IntentType.CAST_SPELL: EventType.ATTACK,
            IntentType.TALK: EventType.DIALOGUE,
            IntentType.PERSUADE: EventType.PERSUASION,
            IntentType.INTIMIDATE: EventType.INTIMIDATION,
            IntentType.DECEIVE: EventType.DECEPTION,
            IntentType.MOVE: EventType.TRAVEL,
            IntentType.REST: EventType.SHORT_REST,
            IntentType.SEARCH: EventType.SKILL_CHECK,
        }
        return mapping.get(intent_type, EventType.SKILL_CHECK)

    def _result_to_outcome(self, result: SkillResult) -> EventOutcome:
        """Map skill result to event outcome."""
        if result.is_critical:
            return EventOutcome.CRITICAL_SUCCESS
        elif result.is_fumble:
            return EventOutcome.CRITICAL_FAILURE
        elif result.success:
            return EventOutcome.SUCCESS
        else:
            return EventOutcome.FAILURE

    def _extract_state_changes(self, results: list[SkillResult]) -> list[str]:
        """Extract state change descriptions from skill results."""
        changes = []
        for result in results:
            if result.damage:
                changes.append(f"Dealt {result.damage} damage")
            if result.healing:
                changes.append(f"Healed {result.healing} HP")
            if result.conditions:
                changes.append(f"Applied: {', '.join(result.conditions)}")
        return changes
