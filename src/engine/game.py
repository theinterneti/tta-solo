"""
Game Engine for TTA-Solo.

The main orchestration layer that processes player turns.
Coordinates intent parsing, skill execution, and narrative generation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol
from uuid import UUID, uuid4

from src.db.interfaces import DoltRepository, Neo4jRepository
from src.engine.intent import HybridIntentParser, LLMProvider
from src.engine.models import (
    Context,
    EngineConfig,
    EntitySummary,
    ForkResult,
    Intent,
    IntentType,
    RelationshipSummary,
    Session,
    SkillResult,
    Turn,
    TurnResult,
)
from src.engine.router import SkillRouter
from src.models import Entity, Event, EventOutcome, EventType, RelationshipType
from src.services.multiverse import MultiverseService

if TYPE_CHECKING:
    from src.engine.agents import (
        AgentOrchestrator as AgentOrchestratorType,
    )
    from src.engine.agents import (
        GMAgent as GMAgentType,
    )
    from src.engine.agents import (
        LorekeeperAgent as LorekeeperAgentType,
    )
    from src.engine.agents import (
        RulesLawyerAgent as RulesLawyerAgentType,
    )

# Module-level agent classes (lazy loaded)
_AgentOrchestrator: type[AgentOrchestratorType] | None = None
_GMAgent: type[GMAgentType] | None = None
_RulesLawyerAgent: type[RulesLawyerAgentType] | None = None
_LorekeeperAgent: type[LorekeeperAgentType] | None = None


def _import_agents() -> (
    tuple[
        type[AgentOrchestratorType],
        type[GMAgentType],
        type[RulesLawyerAgentType],
        type[LorekeeperAgentType],
    ]
):
    """Lazy import of agents to avoid circular imports."""
    global _AgentOrchestrator, _GMAgent, _RulesLawyerAgent, _LorekeeperAgent
    if _AgentOrchestrator is None:
        from src.engine.agents import (
            AgentOrchestrator,
            GMAgent,
            LorekeeperAgent,
            RulesLawyerAgent,
        )

        _AgentOrchestrator = AgentOrchestrator
        _GMAgent = GMAgent
        _RulesLawyerAgent = RulesLawyerAgent
        _LorekeeperAgent = LorekeeperAgent

    return _AgentOrchestrator, _GMAgent, _RulesLawyerAgent, _LorekeeperAgent  # type: ignore


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

    Phase 3: Can use specialized agents via `use_agents=True`:
    - GM Agent: Orchestration and narrative
    - Rules Lawyer Agent: Mechanical enforcement
    - Lorekeeper Agent: Context retrieval
    """

    dolt: DoltRepository
    neo4j: Neo4jRepository
    config: EngineConfig = field(default_factory=EngineConfig)
    use_agents: bool = False  # Enable Phase 3 agent system

    # Components (initialized in __post_init__)
    intent_parser: HybridIntentParser = field(init=False)
    router: SkillRouter = field(init=False)
    narrator: NarrativeGenerator = field(init=False)

    # Agent system (Phase 3)
    _orchestrator: AgentOrchestratorType | None = field(init=False, default=None)

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

        # Initialize agent system if enabled
        if self.use_agents:
            self._init_agents()

    def _init_agents(self) -> None:
        """Initialize the agent system (Phase 3)."""
        orchestrator_cls, gm_cls, rules_lawyer_cls, lorekeeper_cls = _import_agents()

        gm = gm_cls(
            tone=self.config.tone,
            verbosity=self.config.verbosity,
        )
        rules_lawyer = rules_lawyer_cls(router=self.router)
        lorekeeper = lorekeeper_cls(
            dolt=self.dolt,
            neo4j=self.neo4j,
            max_nearby_entities=self.config.max_nearby_entities,
            max_recent_events=self.config.max_recent_events,
        )

        self._orchestrator = orchestrator_cls(
            gm=gm,
            rules_lawyer=rules_lawyer,
            lorekeeper=lorekeeper,
        )

    def set_llm_provider(self, provider: LLMProvider) -> None:
        """Set the LLM provider for intent parsing."""
        self.intent_parser = HybridIntentParser(llm_provider=provider)
        # Also update agent if using agent system
        if self._orchestrator is not None:
            self._orchestrator.gm.intent_parser = HybridIntentParser(llm_provider=provider)

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
            character_id: The player's character (will be active)
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
            location_id=location_id,
            character_ids=[character_id],
            active_character_id=character_id,
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

    def add_character_to_session(
        self,
        session_id: UUID,
        character_id: UUID,
        make_active: bool = False,
    ) -> bool:
        """
        Add a character to an existing session.

        Args:
            session_id: The session to add to
            character_id: The character to add
            make_active: Whether to make this the active character

        Returns:
            True if added, False if session not found
        """
        session = self._sessions.get(session_id)
        if session is None:
            return False

        session.add_character(character_id, make_active)
        return True

    def switch_active_character(
        self,
        session_id: UUID,
        character_id: UUID,
    ) -> bool:
        """
        Switch the active character in a session.

        Args:
            session_id: The session
            character_id: The character to switch to

        Returns:
            True if switched, False if session or character not found
        """
        session = self._sessions.get(session_id)
        if session is None:
            return False

        return session.switch_character(character_id)

    def remove_character_from_session(
        self,
        session_id: UUID,
        character_id: UUID,
    ) -> bool:
        """
        Remove a character from a session.

        Args:
            session_id: The session
            character_id: The character to remove

        Returns:
            True if removed, False if session or character not found
        """
        session = self._sessions.get(session_id)
        if session is None:
            return False

        return session.remove_character(character_id)

    async def fork_from_here(
        self,
        session_id: UUID,
        reason: str,
        fork_name: str | None = None,
    ) -> ForkResult:
        """
        Fork the timeline at the current point in the session.

        Creates a new universe branching from the current state,
        allowing the player to explore "what if" scenarios.

        Args:
            session_id: The active session to fork from
            reason: Why this fork is being created (e.g., "What if I had attacked?")
            fork_name: Optional name for the new universe

        Returns:
            ForkResult with the new universe and session, or error
        """
        session = self._sessions.get(session_id)
        if session is None:
            return ForkResult(
                success=False,
                error="Session not found",
            )

        # Create multiverse service
        multiverse = MultiverseService(dolt=self.dolt, neo4j=self.neo4j)

        # Generate fork name if not provided
        if fork_name is None:
            fork_name = f"Fork: {reason[:50]}"

        # Get the most recent event ID for the fork point
        recent_events = self.dolt.get_events_at_location(
            session.universe_id,
            session.location_id,
            limit=1,
        )
        fork_point_event_id = recent_events[0].id if recent_events else None

        # Fork the universe
        fork_result = multiverse.fork_universe(
            parent_universe_id=session.universe_id,
            new_universe_name=fork_name,
            fork_reason=reason,
            player_id=session.character_id,
            fork_point_event_id=fork_point_event_id,
        )

        if not fork_result.success or fork_result.universe is None:
            return ForkResult(
                success=False,
                error=fork_result.error or "Failed to fork universe",
            )

        # Create a new session in the forked universe
        new_session = await self.start_session(
            universe_id=fork_result.universe.id,
            character_id=session.character_id,
            location_id=session.location_id,
        )

        return ForkResult(
            success=True,
            new_universe_id=fork_result.universe.id,
            new_session_id=new_session.id,
            fork_reason=reason,
            narrative=f"The timeline splits... You find yourself in a world where {reason}",
        )

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
            # Use agent system if enabled (Phase 3)
            if self.use_agents and self._orchestrator is not None:
                intent, context, skill_results, narrative = await self._orchestrator.process_turn(
                    player_input, session
                )
                turn.intent = intent
                turn.context = context
                turn.skill_results = skill_results
                turn.narrative = narrative
            else:
                # Direct processing (Phase 1/2)
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

                # Phase 5: Generate narrative
                turn.narrative = await self.narrator.generate(
                    turn.intent,
                    turn.context,
                    turn.skill_results,
                )

            # Phase 4: Record events (always done by engine)
            await self._record_events(turn, session)

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
        """
        Build context for the current turn.

        Context Query Flow (per spec):
        1. Get actor from Dolt (by actor_id)
        2. Get location from Dolt (by location_id)
        3. Query Neo4j: entities LOCATED_IN location
        4. Query Neo4j: actor's relationships (KNOWS, FEARS, etc.)
        5. Query Dolt: recent events at this location
        6. Query Neo4j: location atmosphere/mood
        """
        # 1. Get actor
        actor_entity = self.dolt.get_entity(session.character_id, session.universe_id)
        if actor_entity:
            actor = self._entity_to_summary(actor_entity)
        else:
            actor = EntitySummary(
                id=session.character_id,
                name="Unknown",
                type="character",
            )

        # 2. Get location
        location_entity = self.dolt.get_entity(session.location_id, session.universe_id)
        if location_entity:
            location = self._entity_to_summary(location_entity)
        else:
            location = EntitySummary(
                id=session.location_id,
                name="Unknown Location",
                type="location",
            )

        # 3. Get entities in location (LOCATED_IN relationships pointing to this location)
        entities_present = []
        located_in_rels = self.neo4j.get_relationships(
            session.location_id,
            session.universe_id,
            relationship_type="LOCATED_IN",
        )
        for rel in located_in_rels[: self.config.max_nearby_entities]:
            entity = self.dolt.get_entity(rel.from_entity_id, session.universe_id)
            if entity and entity.id != session.character_id:
                entities_present.append(self._entity_to_summary(entity))

        # Get actor inventory (CARRIES, WIELDS, WEARS relationships)
        actor_inventory = await self._get_actor_inventory(session)

        # Get location exits (CONNECTED_TO relationships)
        exits = await self._get_location_exits(session)

        # 4. Get actor's relationships (KNOWS, FEARS, etc.)
        known_entities = await self._get_actor_relationships(session)

        # 5. Get recent events at this location
        recent_events = self.dolt.get_events_at_location(
            session.universe_id,
            session.location_id,
            limit=self.config.max_recent_events,
        )
        event_summaries = [e.narrative_summary for e in recent_events if e.narrative_summary]

        # 6. Get location mood/atmosphere
        mood = await self._get_location_mood(session)

        # Get danger level
        danger_level = 0
        if location_entity and location_entity.location_properties:
            danger_level = location_entity.location_properties.danger_level

        return Context(
            actor=actor,
            actor_inventory=actor_inventory,
            location=location,
            entities_present=entities_present,
            exits=exits,
            known_entities=known_entities,
            recent_events=event_summaries,
            mood=mood,
            danger_level=danger_level,
        )

    async def _get_actor_inventory(self, session: Session) -> list[EntitySummary]:
        """Get items the actor is carrying, wielding, or wearing."""
        inventory = []
        inventory_rel_types = ["CARRIES", "WIELDS", "WEARS"]

        for rel_type in inventory_rel_types:
            rels = self.neo4j.get_relationships(
                session.character_id,
                session.universe_id,
                relationship_type=rel_type,
            )
            for rel in rels:
                # Actor is from_entity, item is to_entity
                item = self.dolt.get_entity(rel.to_entity_id, session.universe_id)
                if item:
                    inventory.append(self._entity_to_summary(item))

        return inventory

    async def _get_location_exits(self, session: Session) -> list[str]:
        """Get available exits from the current location."""
        exits = []
        connected_rels = self.neo4j.get_relationships(
            session.location_id,
            session.universe_id,
            relationship_type="CONNECTED_TO",
        )
        for rel in connected_rels:
            # Get the connected location
            connected_location = self.dolt.get_entity(
                rel.to_entity_id, session.universe_id
            )
            if connected_location:
                # Use description as exit name if available, otherwise use location name
                exit_name = rel.description if rel.description else connected_location.name
                exits.append(exit_name)

        return exits

    async def _get_actor_relationships(self, session: Session) -> list[RelationshipSummary]:
        """Get actor's relationships with other entities (KNOWS, FEARS, etc.)."""
        known_entities = []
        relationship_types = [
            RelationshipType.KNOWS,
            RelationshipType.FEARS,
            RelationshipType.ALLIED_WITH,
            RelationshipType.HOSTILE_TO,
            RelationshipType.LOVES,
            RelationshipType.HATES,
            RelationshipType.RESPECTS,
            RelationshipType.DISTRUSTS,
        ]

        for rel_type in relationship_types:
            rels = self.neo4j.get_relationships(
                session.character_id,
                session.universe_id,
                relationship_type=rel_type.value,
            )
            for rel in rels:
                # Get the related entity
                related_entity = self.dolt.get_entity(
                    rel.to_entity_id, session.universe_id
                )
                if related_entity:
                    known_entities.append(
                        RelationshipSummary(
                            entity=self._entity_to_summary(related_entity),
                            relationship_type=rel.relationship_type.value,
                            strength=rel.strength,
                            trust=rel.trust,
                            description=rel.description,
                        )
                    )

        return known_entities

    async def _get_location_mood(self, session: Session) -> str | None:
        """Get the mood/atmosphere of the current location."""
        atmosphere_rels = self.neo4j.get_relationships(
            session.location_id,
            session.universe_id,
            relationship_type="HAS_ATMOSPHERE",
        )
        if atmosphere_rels:
            # Return the description of the first atmosphere relationship
            return atmosphere_rels[0].description or None
        return None

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
