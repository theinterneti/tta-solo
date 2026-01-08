"""
Agent System for TTA-Solo.

Implements the three-agent architecture:
- GM (Game Master): Orchestrates, parses intents, generates narrative
- Rules Lawyer (RL): Mechanical enforcer, executes skills
- Lorekeeper (LK): Context provider, queries world state

Agents communicate via AgentMessage protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol
from uuid import UUID, uuid4

from src.db.interfaces import DoltRepository, Neo4jRepository
from src.engine.intent import HybridIntentParser, LLMProvider
from src.engine.models import (
    Context,
    EntitySummary,
    Intent,
    IntentType,
    RelationshipSummary,
    Session,
    SkillResult,
)
from src.engine.router import SkillRouter
from src.models import Entity, RelationshipType


class AgentRole(str, Enum):
    """Roles for specialized agents."""

    GM = "gm"  # Game Master - orchestration and narrative
    RULES_LAWYER = "rules_lawyer"  # Mechanical enforcement
    LOREKEEPER = "lorekeeper"  # Context retrieval


class MessageType(str, Enum):
    """Types of inter-agent messages."""

    # Requests
    REQUEST_CONTEXT = "request_context"
    REQUEST_RESOLUTION = "request_resolution"
    REQUEST_NARRATIVE = "request_narrative"

    # Responses
    CONTEXT_RESPONSE = "context_response"
    RESOLUTION_RESPONSE = "resolution_response"
    NARRATIVE_RESPONSE = "narrative_response"

    # Coordination
    DELEGATE = "delegate"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class AgentMessage:
    """
    Message for inter-agent communication.

    Agents communicate by sending messages with typed payloads.
    This enables loose coupling and clear boundaries between agents.
    """

    id: UUID = field(default_factory=uuid4)
    type: MessageType = MessageType.DELEGATE
    from_agent: AgentRole = AgentRole.GM
    to_agent: AgentRole | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    correlation_id: UUID | None = None  # Links request/response pairs

    def reply(
        self,
        type: MessageType,
        payload: dict[str, Any],
        from_agent: AgentRole,
    ) -> AgentMessage:
        """Create a reply message linked to this one."""
        return AgentMessage(
            type=type,
            from_agent=from_agent,
            to_agent=self.from_agent,
            payload=payload,
            correlation_id=self.id,
        )


class Agent(Protocol):
    """Protocol for all agents in the system."""

    role: AgentRole

    async def handle(self, message: AgentMessage) -> AgentMessage:
        """Handle an incoming message and return a response."""
        ...


@dataclass
class LorekeeperAgent:
    """
    Context provider agent.

    Responsibilities:
    - Query Neo4j for relevant entities/relationships
    - Provide world context to GM
    - Track NPC memories and relationships
    - Surface relevant history

    Never does: Make decisions, generate new content
    """

    role: AgentRole = AgentRole.LOREKEEPER
    dolt: DoltRepository = field(default=None)  # type: ignore
    neo4j: Neo4jRepository = field(default=None)  # type: ignore
    max_nearby_entities: int = 10
    max_recent_events: int = 5

    async def handle(self, message: AgentMessage) -> AgentMessage:
        """Handle context retrieval requests."""
        if message.type != MessageType.REQUEST_CONTEXT:
            return message.reply(
                type=MessageType.ERROR,
                payload={"error": f"Lorekeeper cannot handle {message.type}"},
                from_agent=self.role,
            )

        session = message.payload.get("session")
        if not session:
            return message.reply(
                type=MessageType.ERROR,
                payload={"error": "No session provided"},
                from_agent=self.role,
            )

        context = await self.retrieve_context(session)

        return message.reply(
            type=MessageType.CONTEXT_RESPONSE,
            payload={"context": context},
            from_agent=self.role,
        )

    async def retrieve_context(self, session: Session) -> Context:
        """
        Retrieve full world context for the current turn.

        Context Query Flow:
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

        # 3. Get entities in location
        entities_present = await self._get_entities_at_location(session)

        # Get actor inventory
        actor_inventory = await self._get_actor_inventory(session)

        # Get location exits
        exits = await self._get_location_exits(session)

        # 4. Get actor's relationships
        known_entities = await self._get_actor_relationships(session)

        # 5. Get recent events at this location
        recent_events = self.dolt.get_events_at_location(
            session.universe_id,
            session.location_id,
            limit=self.max_recent_events,
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

    async def _get_entities_at_location(self, session: Session) -> list[EntitySummary]:
        """Get entities at the current location."""
        entities_present = []
        located_in_rels = self.neo4j.get_relationships(
            session.location_id,
            session.universe_id,
            relationship_type="LOCATED_IN",
        )
        for rel in located_in_rels[: self.max_nearby_entities]:
            entity = self.dolt.get_entity(rel.from_entity_id, session.universe_id)
            if entity and entity.id != session.character_id:
                entities_present.append(self._entity_to_summary(entity))
        return entities_present

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
            connected_location = self.dolt.get_entity(
                rel.to_entity_id, session.universe_id
            )
            if connected_location:
                exit_name = rel.description if rel.description else connected_location.name
                exits.append(exit_name)

        return exits

    async def _get_actor_relationships(self, session: Session) -> list[RelationshipSummary]:
        """Get actor's relationships with other entities."""
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


@dataclass
class RulesLawyerAgent:
    """
    Mechanical enforcer agent.

    Responsibilities:
    - Call skills for dice rolls
    - Validate actions against rules
    - Calculate outcomes (damage, DCs, etc.)
    - Enforce SRD 5e constraints

    Never does: Generate narrative, make story decisions
    """

    role: AgentRole = AgentRole.RULES_LAWYER
    router: SkillRouter = field(default_factory=SkillRouter)

    async def handle(self, message: AgentMessage) -> AgentMessage:
        """Handle resolution requests."""
        if message.type != MessageType.REQUEST_RESOLUTION:
            return message.reply(
                type=MessageType.ERROR,
                payload={"error": f"Rules Lawyer cannot handle {message.type}"},
                from_agent=self.role,
            )

        intent = message.payload.get("intent")
        context = message.payload.get("context")
        extra = message.payload.get("extra", {})

        if not intent or not context:
            return message.reply(
                type=MessageType.ERROR,
                payload={"error": "Missing intent or context"},
                from_agent=self.role,
            )

        result = await self.resolve(intent, context, extra)

        return message.reply(
            type=MessageType.RESOLUTION_RESPONSE,
            payload={"result": result},
            from_agent=self.role,
        )

    async def resolve(
        self,
        intent: Intent,
        context: Context,
        extra: dict[str, Any] | None = None,
    ) -> SkillResult:
        """Resolve an intent using the skill router."""
        return self.router.resolve(intent, context, extra or {})

    def validate_action(self, intent: Intent, context: Context) -> tuple[bool, str]:
        """
        Validate if an action is legal per SRD 5e rules.

        Returns (is_valid, reason).
        """
        # Check if target exists for targeted actions
        targeted_actions = {IntentType.ATTACK, IntentType.TALK, IntentType.GIVE}
        if (
            intent.type in targeted_actions
            and intent.target_name
            and not self._find_target(intent, context)
        ):
            return False, f"Cannot find target: {intent.target_name}"

        # Check if movement is valid
        if (
            intent.type == IntentType.MOVE
            and intent.destination
            and intent.destination not in context.exits
        ):
            valid_exits = ", ".join(context.exits) if context.exits else "none"
            return False, f"Cannot go {intent.destination}. Valid exits: {valid_exits}"

        return True, "Action is valid"

    def _find_target(self, intent: Intent, context: Context) -> bool:
        """Check if target exists in context."""
        if not intent.target_name:
            return False

        target_lower = intent.target_name.lower()
        return any(target_lower in entity.name.lower() for entity in context.entities_present)


@dataclass
class GMAgent:
    """
    Game Master agent - the orchestrator.

    Responsibilities:
    - Parse player intent from natural language
    - Coordinate other agents (delegate)
    - Generate narrative responses
    - Make story pacing decisions

    Never does: Dice math, rule lookups, inventing lore
    """

    role: AgentRole = AgentRole.GM
    intent_parser: HybridIntentParser = field(default=None)  # type: ignore
    llm: LLMProvider | None = None
    tone: str = "adventure"
    verbosity: str = "normal"

    def __post_init__(self) -> None:
        """Initialize intent parser if not provided."""
        if self.intent_parser is None:
            self.intent_parser = HybridIntentParser(llm_provider=self.llm)

    async def handle(self, message: AgentMessage) -> AgentMessage:
        """Handle GM requests (parsing, narrative generation)."""
        if message.type == MessageType.REQUEST_NARRATIVE:
            return await self._handle_narrative_request(message)

        return message.reply(
            type=MessageType.ERROR,
            payload={"error": f"GM cannot handle {message.type} directly"},
            from_agent=self.role,
        )

    async def parse_intent(self, player_input: str) -> Intent:
        """Parse player input into an Intent."""
        return await self.intent_parser.parse(player_input)

    async def generate_narrative(
        self,
        intent: Intent,
        context: Context,
        skill_results: list[SkillResult],
    ) -> str:
        """Generate narrative response from intent and skill results."""
        parts = []

        # Add skill result descriptions
        for result in skill_results:
            if result.description:
                parts.append(result.description)

        # Add default narrative if no skill results
        if not parts:
            parts.append(self._default_narrative(intent, context))

        narrative = " ".join(parts)

        # Add relationship awareness
        narrative = self._add_relationship_context(narrative, intent, context)

        # Add mood/atmosphere
        if context.mood and self.verbosity == "verbose":
            narrative = f"The atmosphere is {context.mood}. {narrative}"

        # Add prompt for next action if verbose
        if self.verbosity == "verbose":
            narrative += "\n\nWhat do you do?"

        return narrative

    async def _handle_narrative_request(self, message: AgentMessage) -> AgentMessage:
        """Handle a narrative generation request."""
        intent = message.payload.get("intent")
        context = message.payload.get("context")
        skill_results = message.payload.get("skill_results", [])

        if not intent or not context:
            return message.reply(
                type=MessageType.ERROR,
                payload={"error": "Missing intent or context"},
                from_agent=self.role,
            )

        narrative = await self.generate_narrative(intent, context, skill_results)

        return message.reply(
            type=MessageType.NARRATIVE_RESPONSE,
            payload={"narrative": narrative},
            from_agent=self.role,
        )

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

    def _add_relationship_context(
        self,
        narrative: str,
        intent: Intent,
        context: Context,
    ) -> str:
        """Add relationship context to narrative when relevant."""
        if intent.type != IntentType.TALK:
            return narrative

        # Find relationship with talk target
        if intent.target_name:
            target_lower = intent.target_name.lower()
            for rel in context.known_entities:
                if target_lower in rel.entity.name.lower():
                    # Add relationship flavor
                    if rel.relationship_type == "KNOWS" and rel.trust:
                        if rel.trust > 0.7:
                            return f"{narrative} They seem pleased to see you."
                        elif rel.trust < 0.3:
                            return f"{narrative} They regard you with suspicion."
                    elif rel.relationship_type == "FEARS":
                        return f"{narrative} They seem nervous in your presence."
                    elif rel.relationship_type == "HOSTILE_TO":
                        return f"{narrative} Hostility radiates from them."

        return narrative


@dataclass
class AgentOrchestrator:
    """
    Coordinates communication between specialized agents.

    The orchestrator routes messages between agents and manages
    the turn processing flow.
    """

    gm: GMAgent
    rules_lawyer: RulesLawyerAgent
    lorekeeper: LorekeeperAgent

    async def process_turn(
        self,
        player_input: str,
        session: Session,
    ) -> tuple[Intent, Context, list[SkillResult], str]:
        """
        Process a complete turn using all agents.

        Returns (intent, context, skill_results, narrative).
        """
        # 1. GM parses intent
        intent = await self.gm.parse_intent(player_input)

        # 2. Lorekeeper retrieves context
        context_msg = AgentMessage(
            type=MessageType.REQUEST_CONTEXT,
            from_agent=AgentRole.GM,
            to_agent=AgentRole.LOREKEEPER,
            payload={"session": session},
        )
        context_response = await self.lorekeeper.handle(context_msg)
        context = context_response.payload.get("context")

        if not context:
            raise RuntimeError("Failed to retrieve context")

        # 3. Rules Lawyer validates and resolves
        is_valid, reason = self.rules_lawyer.validate_action(intent, context)

        skill_results = []
        if is_valid:
            resolution_msg = AgentMessage(
                type=MessageType.REQUEST_RESOLUTION,
                from_agent=AgentRole.GM,
                to_agent=AgentRole.RULES_LAWYER,
                payload={"intent": intent, "context": context},
            )
            resolution_response = await self.rules_lawyer.handle(resolution_msg)
            result = resolution_response.payload.get("result")
            if result:
                skill_results.append(result)
        else:
            # Invalid action - create a failure result
            skill_results.append(
                SkillResult(
                    success=False,
                    outcome="failure",
                    description=reason,
                )
            )

        # 4. GM generates narrative
        narrative = await self.gm.generate_narrative(intent, context, skill_results)

        return intent, context, skill_results, narrative
