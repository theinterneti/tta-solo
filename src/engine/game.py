"""
Game Engine for TTA-Solo.

The main orchestration layer that processes player turns.
Coordinates intent parsing, skill execution, and narrative generation.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol
from uuid import UUID, uuid4

from src.db.interfaces import DoltRepository, Neo4jRepository
from src.engine.intent import HybridIntentParser, LLMProvider
from src.engine.models import (
    Context,
    EngineConfig,
    EngineForkResult,
    EntitySummary,
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
from src.services.llm import LLMService
from src.services.move_executor import MoveExecutor
from src.services.multiverse import MultiverseService
from src.services.npc import NPCService

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

logger = logging.getLogger(__name__)

# Module-level agent classes (lazy loaded)
_AgentOrchestrator: type[AgentOrchestratorType] | None = None
_GMAgent: type[GMAgentType] | None = None
_RulesLawyerAgent: type[RulesLawyerAgentType] | None = None
_LorekeeperAgent: type[LorekeeperAgentType] | None = None


def _import_agents() -> tuple[
    type[AgentOrchestratorType],
    type[GMAgentType],
    type[RulesLawyerAgentType],
    type[LorekeeperAgentType],
]:
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
    npc_service: NPCService = field(init=False)
    move_executor: MoveExecutor = field(init=False)

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
        self.npc_service = NPCService(dolt=self.dolt, neo4j=self.neo4j)
        self.move_executor = MoveExecutor(
            dolt=self.dolt,
            neo4j=self.neo4j,
            npc_service=self.npc_service,
            llm=None,  # Set via set_llm_provider if needed
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

    def set_llm_service(self, llm_service: LLMService) -> None:
        """
        Set the LLM service for move execution.

        This enables LLM-powered NPC generation and environment features.
        Use LLMService with an OpenRouterProvider or MockLLMProvider.
        """
        self.move_executor.llm = llm_service

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
    ) -> EngineForkResult:
        """
        Fork the timeline at the current point in the session.

        Creates a new universe branching from the current state,
        allowing the player to explore "what if" scenarios.

        Args:
            session_id: The active session to fork from
            reason: Why this fork is being created (e.g., "What if I had attacked?")
            fork_name: Optional name for the new universe

        Returns:
            EngineForkResult with the new universe and session, or error
        """
        session = self._sessions.get(session_id)
        if session is None:
            return EngineForkResult(
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
            return EngineForkResult(
                success=False,
                error=fork_result.error or "Failed to fork universe",
            )

        # Create a new session in the forked universe
        new_session = await self.start_session(
            universe_id=fork_result.universe.id,
            character_id=session.character_id,
            location_id=session.location_id,
        )

        return EngineForkResult(
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

                    # Execute GM move if one was triggered (Phase 4 enhancement)
                    if skill_result.gm_move_type:
                        skill_result = await self._execute_gm_move(
                            skill_result, turn.context, session
                        )

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

    async def _execute_gm_move(
        self,
        skill_result: SkillResult,
        context: Context,
        session: Session,
    ) -> SkillResult:
        """
        Execute a GM move that was triggered by the PbtA system.

        Takes the skill result with a gm_move_type, executes the move
        via MoveExecutor, and returns an updated skill result with
        any created entities.

        Args:
            skill_result: The skill result with gm_move_type set
            context: Current game context
            session: Active session

        Returns:
            Updated SkillResult with move execution results
        """
        from src.engine.pbta import GMMove, GMMoveType

        # Reconstruct the GMMove from the skill result
        try:
            move_type = GMMoveType(skill_result.gm_move_type)
        except ValueError:
            # Unknown move type, log warning and return unchanged
            logger.warning(
                "Unknown GM move type %r encountered, skipping execution",
                skill_result.gm_move_type,
            )
            return skill_result

        move = GMMove(
            type=move_type,
            is_hard=move_type.value
            in {"deal_damage", "use_monster_move", "separate_them", "take_away", "capture"},
            description=skill_result.gm_move_description or "",
            damage=skill_result.damage,
        )

        # Execute the move
        exec_result = await self.move_executor.execute(
            move=move,
            context=context,
            session=session,
            trigger_reason="miss",
        )

        # Update skill result with execution results
        updates = {
            "entities_created": exec_result.entities_created,
            "relationships_created": exec_result.relationships_created,
            "move_used_fallback": exec_result.used_fallback,
        }

        # If the move executor generated better narrative, use it
        if exec_result.narrative and exec_result.narrative != move.description:
            # Append the move's narrative to the existing description
            current_desc = skill_result.description or ""
            # Replace the template description with the generated one
            if (
                skill_result.gm_move_description
                and skill_result.gm_move_description in current_desc
            ):
                updates["description"] = current_desc.replace(
                    skill_result.gm_move_description, exec_result.narrative
                )
            else:
                updates["description"] = f"{current_desc} {exec_result.narrative}"
            updates["gm_move_description"] = exec_result.narrative

        return skill_result.model_copy(update=updates)

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
            connected_location = self.dolt.get_entity(rel.to_entity_id, session.universe_id)
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
                related_entity = self.dolt.get_entity(rel.to_entity_id, session.universe_id)
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
        """Record events from the turn and form NPC memories."""
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

            # Form NPC memories for entities present at the location
            await self._form_npc_memories(event, session)

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

    async def _form_npc_memories(self, event: Event, session: Session) -> None:
        """
        Form memories for NPCs present at the event location.

        NPCs who witness events form memories based on their relevance
        and emotional impact. These memories influence future behavior.
        """
        # Get entities at the location (NPCs who could witness the event)
        located_in_rels = self.neo4j.get_relationships(
            session.location_id,
            session.universe_id,
            relationship_type="LOCATED_IN",
        )

        for rel in located_in_rels:
            npc_id = rel.from_entity_id

            # Skip the player character - they don't form NPC memories
            if npc_id == session.character_id:
                continue

            # Note: We DO form memories for the event actor (self-memories).
            # NPCs should remember their own significant actions for self-reflection
            # and behavioral consistency. The memory importance calculation in
            # form_memory() will handle filtering trivial self-actions.

            # Form memory for this NPC witnessing or performing the event
            memory_result = self.npc_service.form_memory(npc_id, event)

            if memory_result.formed and memory_result.memory:
                # Persist the memory to Neo4j
                self.neo4j.create_memory(memory_result.memory)

            # Update relationships based on the event
            # NPC's relationship with the actor
            if event.actor_id and event.actor_id != npc_id:
                self.npc_service.update_relationship(
                    npc_id=npc_id,
                    target_id=event.actor_id,
                    event=event,
                )
            # NPC's relationship with the target (if different from actor and self)
            if event.target_id and event.target_id != npc_id and event.target_id != event.actor_id:
                self.npc_service.update_relationship(
                    npc_id=npc_id,
                    target_id=event.target_id,
                    event=event,
                )

    async def process_npc_combat_turn(
        self,
        npc_id: UUID,
        session: Session,
        escape_routes: int = 1,
    ) -> dict[str, str | UUID | int | bool | None]:
        """
        Process an NPC's combat turn using the combat AI system.

        Determines what action the NPC takes based on personality, situation,
        and relationships, then executes that action.

        Args:
            npc_id: The NPC taking a combat turn
            session: Current game session
            escape_routes: Number of available escape routes

        Returns:
            Dict with combat turn results including action, target, damage, etc.
        """
        from src.models.npc import (
            CombatState,
        )
        from src.models.npc import (
            EntitySummary as NPCEntitySummary,
        )
        from src.models.npc import (
            RelationshipSummary as NPCRelationshipSummary,
        )
        from src.skills.combat import (
            Abilities,
            AttackResult,
            Combatant,
            Weapon,
            resolve_attack,
        )

        # Get NPC entity
        npc_entity = self.dolt.get_entity(npc_id, session.universe_id)
        if not npc_entity:
            return {"success": False, "error": "NPC not found"}

        # Build NPC profile - load from database or create default
        profile = self.npc_service.get_or_create_profile(npc_id)

        # Calculate HP percentage
        hp_percentage = 1.0
        if npc_entity.stats and npc_entity.stats.hp_max > 0:
            hp_percentage = npc_entity.stats.hp_current / npc_entity.stats.hp_max

        # Get entities present
        entities_present: list[NPCEntitySummary] = []
        located_in_rels = self.neo4j.get_relationships(
            session.location_id,
            session.universe_id,
            relationship_type="LOCATED_IN",
        )
        for rel in located_in_rels[: self.config.max_nearby_entities]:
            entity = self.dolt.get_entity(rel.from_entity_id, session.universe_id)
            if entity:
                entities_present.append(
                    NPCEntitySummary(
                        id=entity.id,
                        name=entity.name,
                        entity_type=entity.type.value,
                        is_player=(entity.id == session.character_id),
                        hp_percentage=(
                            entity.stats.hp_current / entity.stats.hp_max
                            if entity.stats and entity.stats.hp_max > 0
                            else 1.0
                        ),
                        apparent_threat=0.7 if entity.id == session.character_id else 0.3,
                    )
                )

        # Get NPC relationships
        relationships: list[NPCRelationshipSummary] = []
        for rel_type in ["KNOWS", "FEARS", "ALLIED_WITH", "HOSTILE_TO", "RESPECTS", "DISTRUSTS"]:
            rels = self.neo4j.get_relationships(
                npc_id,
                session.universe_id,
                relationship_type=rel_type,
            )
            for rel in rels:
                target_entity = self.dolt.get_entity(rel.to_entity_id, session.universe_id)
                target_name = target_entity.name if target_entity else "Unknown"
                relationships.append(
                    NPCRelationshipSummary(
                        target_id=rel.to_entity_id,
                        target_name=target_name,
                        relationship_type=rel_type,
                        strength=rel.strength,
                        trust=rel.trust or 0.0,
                    )
                )

        # Build combat evaluation
        evaluation = self.npc_service.build_combat_evaluation(
            npc_id=npc_id,
            npc_hp_percentage=hp_percentage,
            entities_present=entities_present,
            relationships=relationships,
            escape_routes=escape_routes,
        )

        # Get combat turn action
        combat_turn = self.npc_service.get_npc_combat_turn(
            npc_id=npc_id,
            npc_profile=profile,
            evaluation=evaluation,
            entities_present=entities_present,
            relationships=relationships,
        )

        # Execute the action
        result: dict[str, str | UUID | int | bool | None] = {
            "success": True,
            "npc_id": npc_id,
            "npc_name": npc_entity.name,
            "combat_state": combat_turn.combat_state.value,
            "action": combat_turn.action.value,
            "target_id": combat_turn.target_id,
            "description": combat_turn.description,
            "damage": None,
            "hit": None,
            "critical": None,
        }

        # If the action is an attack and we have a target, resolve it
        if combat_turn.action.value == "attack" and combat_turn.target_id:
            target_entity = self.dolt.get_entity(combat_turn.target_id, session.universe_id)
            if target_entity:
                # Build combatants
                npc_abilities = Abilities(
                    str=npc_entity.stats.abilities.str_ if npc_entity.stats else 10,
                    dex=npc_entity.stats.abilities.dex if npc_entity.stats else 10,
                )
                attacker = Combatant(
                    name=npc_entity.name,
                    ac=npc_entity.stats.ac if npc_entity.stats else 10,
                    abilities=npc_abilities,
                    proficiency_bonus=(
                        npc_entity.stats.proficiency_bonus if npc_entity.stats else 2
                    ),
                    proficient_weapons=["claws", "bite", "sword", "dagger"],
                )

                target_abilities = Abilities(
                    str=target_entity.stats.abilities.str_ if target_entity.stats else 10,
                    dex=target_entity.stats.abilities.dex if target_entity.stats else 10,
                )
                target = Combatant(
                    name=target_entity.name,
                    ac=target_entity.stats.ac if target_entity.stats else 10,
                    abilities=target_abilities,
                )

                # Default weapon (could be customized based on NPC type)
                weapon = Weapon(
                    name="claws",
                    damage_dice="1d6",
                    damage_type="slashing",
                )

                # Resolve the attack
                attack_result: AttackResult = resolve_attack(
                    attacker=attacker,
                    target=target,
                    weapon=weapon,
                )

                result["hit"] = attack_result.hit
                result["critical"] = attack_result.critical
                result["damage"] = attack_result.damage
                result["attack_roll"] = attack_result.attack_roll
                result["target_ac"] = attack_result.target_ac

                # Update description with attack result
                if attack_result.critical:
                    result["description"] = (
                        f"{npc_entity.name} lands a critical hit on {target_entity.name}!"
                    )
                elif attack_result.hit:
                    result["description"] = (
                        f"{npc_entity.name} hits {target_entity.name} for {attack_result.damage} damage"
                    )
                else:
                    result["description"] = f"{npc_entity.name} misses {target_entity.name}"

                # Record combat event
                combat_event = Event(
                    universe_id=session.universe_id,
                    event_type=EventType.ATTACK,
                    actor_id=npc_id,
                    target_id=combat_turn.target_id,
                    location_id=session.location_id,
                    outcome=(
                        EventOutcome.CRITICAL_SUCCESS
                        if attack_result.critical
                        else EventOutcome.SUCCESS
                        if attack_result.hit
                        else EventOutcome.FAILURE
                    ),
                    payload={
                        "damage": attack_result.damage,
                        "attack_roll": attack_result.attack_roll,
                        "combat_state": combat_turn.combat_state.value,
                    },
                    narrative_summary=str(result["description"]),
                )
                self.dolt.append_event(combat_event)

                # Form memories and update relationships for witnesses
                for entity_summary in entities_present:
                    if entity_summary.id != npc_id:
                        # Form memory
                        memory_result = self.npc_service.form_memory(
                            entity_summary.id, combat_event
                        )
                        if memory_result.formed and memory_result.memory:
                            self.neo4j.create_memory(memory_result.memory)

                        # Update relationships
                        self.npc_service.update_relationship(
                            npc_id=entity_summary.id,
                            target_id=npc_id,
                            event=combat_event,
                        )

                # NPC's own relationship with the target also updates
                # The attacker's trust in their target typically doesn't change
                # from attacking them, but witnessing the combat does affect others

        elif combat_turn.combat_state in [CombatState.FLEEING, CombatState.SURRENDERING]:
            # Record flee/surrender event
            event_type = (
                EventType.SKILL_CHECK
                if combat_turn.combat_state == CombatState.FLEEING
                else EventType.DIALOGUE
            )
            flee_event = Event(
                universe_id=session.universe_id,
                event_type=event_type,
                actor_id=npc_id,
                location_id=session.location_id,
                outcome=EventOutcome.SUCCESS,
                payload={"combat_state": combat_turn.combat_state.value},
                narrative_summary=combat_turn.description,
            )
            self.dolt.append_event(flee_event)

        return result

    async def get_npc_reaction(
        self,
        npc_id: UUID,
        session: Session,
        available_actions: list[str] | None = None,
    ) -> dict[str, str | None]:
        """
        Get an NPC's reaction to the current situation.

        Uses the NPC AI decision system to determine what the NPC would do.

        Args:
            npc_id: The NPC to get reaction for
            session: Current game session
            available_actions: Optional filter for available action types

        Returns:
            Dict with 'action' type and 'description'
        """
        from src.models.npc import (
            ActionType,
            NPCDecisionContext,
        )
        from src.models.npc import (
            EntitySummary as NPCEntitySummary,
        )
        from src.models.npc import (
            RelationshipSummary as NPCRelationshipSummary,
        )

        # Get NPC entity
        npc_entity = self.dolt.get_entity(npc_id, session.universe_id)
        if not npc_entity:
            return {"action": None, "description": "NPC not found"}

        # Build NPC profile - load from database or create default
        profile = self.npc_service.get_or_create_profile(npc_id)

        # Get entities present
        entities_present = []
        located_in_rels = self.neo4j.get_relationships(
            session.location_id,
            session.universe_id,
            relationship_type="LOCATED_IN",
        )
        for rel in located_in_rels[: self.config.max_nearby_entities]:
            entity = self.dolt.get_entity(rel.from_entity_id, session.universe_id)
            if entity and entity.id != npc_id:
                entities_present.append(
                    NPCEntitySummary(
                        id=entity.id,
                        name=entity.name,
                        entity_type=entity.type.value,
                        is_player=(entity.id == session.character_id),
                        hp_percentage=(
                            entity.stats.hp_current / entity.stats.hp_max
                            if entity.stats and entity.stats.hp_max > 0
                            else 1.0
                        ),
                    )
                )

        # Get NPC relationships
        relationships = []
        for rel_type in ["KNOWS", "FEARS", "ALLIED_WITH", "HOSTILE_TO", "RESPECTS", "DISTRUSTS"]:
            rels = self.neo4j.get_relationships(
                npc_id,
                session.universe_id,
                relationship_type=rel_type,
            )
            for rel in rels:
                # Get target entity name
                target_entity = self.dolt.get_entity(rel.to_entity_id, session.universe_id)
                target_name = target_entity.name if target_entity else "Unknown"
                relationships.append(
                    NPCRelationshipSummary(
                        target_id=rel.to_entity_id,
                        target_name=target_name,
                        relationship_type=rel_type,
                        strength=rel.strength,
                        trust=rel.trust or 0.0,
                    )
                )

        # Retrieve relevant memories
        location_entity = self.dolt.get_entity(session.location_id, session.universe_id)
        context_desc = f"At {location_entity.name if location_entity else 'unknown location'}"
        memories = self.npc_service.retrieve_memories(npc_id, context_desc, limit=5)

        # Build decision context
        context = NPCDecisionContext(
            npc_id=npc_id,
            npc_profile=profile,
            hp_percentage=(
                npc_entity.stats.hp_current / npc_entity.stats.hp_max
                if npc_entity.stats and npc_entity.stats.hp_max > 0
                else 1.0
            ),
            location_name=location_entity.name if location_entity else "Unknown",
            entities_present=entities_present,
            relationships=relationships,
            relevant_memories=memories,
        )

        # Convert action filter if provided
        action_filter = None
        if available_actions:
            action_filter = [
                ActionType(a) for a in available_actions if a in [at.value for at in ActionType]
            ]

        # Get decision
        result = self.npc_service.decide_action(context, action_filter)

        return {
            "action": result.action.action_type.value,
            "description": result.action.description,
            "target_id": str(result.action.target_id) if result.action.target_id else None,
            "reasoning": result.reasoning,
        }
