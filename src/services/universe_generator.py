"""
Universe Generator for TTA-Solo.

LLM-powered procedural universe generation pipeline.
Factions drive worldbuilding: template → world context → factions → locations → NPCs.

Each step has a template-based fallback so the game is always playable without LLM.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from src.db.interfaces import DoltRepository, Neo4jRepository
from src.models.entity import (
    Entity,
    create_character,
    create_faction,
    create_location,
)
from src.models.npc import Motivation, create_npc_profile
from src.models.relationships import Relationship, RelationshipType
from src.models.universe import Universe
from src.models.universe_template import UniverseTemplate
from src.services.npc import NPCService

if TYPE_CHECKING:
    from src.services.llm import LLMService

logger = logging.getLogger(__name__)


# =============================================================================
# Result Model
# =============================================================================


@dataclass
class GenerationResult:
    """Result of universe generation."""

    universe: Universe
    starting_location_id: UUID
    player_character_id: UUID
    factions: dict[str, UUID]
    locations: dict[str, UUID]
    npcs: dict[str, UUID]
    used_fallback: bool = False


# =============================================================================
# LLM Prompt Templates
# =============================================================================

WORLD_CONTEXT_SYSTEM = """You are a world-builder for a tabletop RPG universe.
Given a universe template, generate rich world context as JSON.

Return ONLY a JSON object with these fields:
{
  "history": "2-3 sentence world history",
  "cosmology": "How the world/universe works",
  "naming_conventions": "How people and places are named",
  "tone_guide": "Instructions for maintaining consistent tone",
  "current_tensions": "What conflicts are brewing right now"
}"""

FACTIONS_SYSTEM = """You are a world-builder creating factions for a tabletop RPG.
Given world context, generate interconnected factions as JSON.

Return ONLY a JSON object:
{
  "factions": [
    {
      "name": "Faction Name",
      "description": "2-3 sentence description",
      "alignment": "lawful good / chaotic neutral / etc",
      "influence": 50,
      "core_values": ["value1", "value2"],
      "ideology_summary": "One line ideology",
      "controls_resources": ["resource1"],
      "produces": ["product1"],
      "needs": ["need1"],
      "economic_role": "producers / traders / raiders",
      "cultural_traits": ["trait1"],
      "taboos": ["taboo1"],
      "aesthetic": "Visual style description",
      "governance": "monarchy / council / etc",
      "leader_title": "Title",
      "territory_description": "Where they live",
      "headquarters": "Base name"
    }
  ],
  "relationships": [
    {
      "from_faction": "Faction A",
      "to_faction": "Faction B",
      "type": "TRADES_WITH / COMPETES_WITH / DEPENDS_ON / INFLUENCES",
      "description": "Why this relationship exists"
    }
  ]
}

Generate 2-5 factions with at least 2 inter-faction relationships.
Ensure economic interdependence — no faction should be fully self-sufficient."""

LOCATIONS_SYSTEM = """You are a world-builder creating locations for a tabletop RPG.
Given world context and factions, generate connected locations as JSON.

Return ONLY a JSON object:
{
  "locations": [
    {
      "name": "Location Name",
      "description": "2-3 sentence vivid description",
      "location_type": "tavern / market / dungeon / forest / town / etc",
      "region": "Region name",
      "terrain": "urban / forest / mountain / etc",
      "danger_level": 3,
      "controlling_faction": "Faction Name or null",
      "cultural_flavor": "Visible cultural markers",
      "economic_activity": "What happens here economically",
      "atmosphere": "Mood and vibe"
    }
  ],
  "connections": [
    {
      "from_location": "Location A",
      "to_location": "Location B",
      "direction": "north / south / east / west / etc"
    }
  ]
}

Generate 3-7 locations. The first location should be a safe social hub (tavern/inn).
Include at least one dangerous location. All locations must be connected."""

NPCS_SYSTEM = """You are a world-builder creating NPCs for a tabletop RPG.
Given world context, factions, and locations, generate NPCs as JSON.

Return ONLY a JSON object:
{
  "npcs": [
    {
      "name": "NPC Name",
      "description": "2-3 sentence vivid description",
      "role": "bartender / merchant / guard / scholar / etc",
      "location": "Location Name",
      "faction": "Faction Name or null",
      "hp_max": 20,
      "ac": 12,
      "speech_style": "How they talk",
      "quirks": ["quirk1", "quirk2"],
      "motivations": ["duty", "wealth", "knowledge", "power", "survival"],
      "initial_attitude": "friendly / neutral / hostile"
    }
  ]
}

Generate 1-2 NPCs per location. Include a mix of friendly, neutral, and suspicious NPCs.
Each NPC should have a clear connection to a faction or location."""


# =============================================================================
# Fallback Templates
# =============================================================================


def _fallback_world_context(template: UniverseTemplate) -> dict[str, Any]:
    """Generate world context without LLM."""
    return {
        "history": f"A world defined by {template.cultural_premise}. {template.era_hint}.",
        "cosmology": template.power_source_flavor,
        "naming_conventions": "Names reflect the local culture and faction allegiance.",
        "tone_guide": f"Maintain a {template.tone} tone throughout.",
        "current_tensions": f"Scarcity of {template.scarcity} drives conflict.",
        "used_fallback": True,
    }


def _fallback_factions(template: UniverseTemplate) -> dict[str, Any]:
    """Generate fallback factions without LLM."""
    factions = []
    default_seeds = [
        {"name": "The Iron Covenant", "role": "rulers", "values": "order and tradition"},
        {"name": "The Wandering Exchange", "role": "merchants", "values": "profit and freedom"},
        {"name": "The Ashen Circle", "role": "outcasts", "values": "survival and change"},
    ]

    seeds = template.faction_seeds or []
    for i, default in enumerate(default_seeds):
        seed = seeds[i] if i < len(seeds) else None
        factions.append(
            {
                "name": (seed.name_hint if seed and seed.name_hint else default["name"]),
                "description": f"A faction of {seed.role_hint if seed else default['role']}.",
                "alignment": "neutral",
                "influence": 50,
                "core_values": [
                    seed.values_hint if seed and seed.values_hint else default["values"]
                ],
                "economic_role": default["role"],
                "governance": "council",
                "leader_title": "Elder",
            }
        )

    return {
        "factions": factions,
        "relationships": [
            {
                "from_faction": factions[0]["name"],
                "to_faction": factions[1]["name"],
                "type": "TRADES_WITH",
                "description": "Uneasy trade agreement",
            },
            {
                "from_faction": factions[0]["name"],
                "to_faction": factions[2]["name"],
                "type": "COMPETES_WITH",
                "description": "Competing for territory",
            },
        ],
    }


def _fallback_locations(template: UniverseTemplate, faction_names: list[str]) -> dict[str, Any]:
    """Generate fallback locations without LLM."""
    controlling = faction_names[0] if faction_names else None
    return {
        "locations": [
            {
                "name": "The Hearthstone Inn",
                "description": "A warm tavern where travelers share tales and ale.",
                "location_type": "tavern",
                "terrain": "urban",
                "danger_level": 1,
                "controlling_faction": controlling,
                "atmosphere": "Welcoming and lively",
            },
            {
                "name": "The Crossroads Market",
                "description": "A bustling market where all factions trade.",
                "location_type": "market",
                "terrain": "urban",
                "danger_level": 2,
                "controlling_faction": faction_names[1] if len(faction_names) > 1 else controlling,
                "atmosphere": "Chaotic and colorful",
            },
            {
                "name": "The Whispering Wilds",
                "description": "A dense wilderness on the frontier between territories.",
                "location_type": "forest",
                "terrain": "forest",
                "danger_level": 5,
                "controlling_faction": None,
                "atmosphere": "Mysterious and untamed",
            },
            {
                "name": "The Sunken Vault",
                "description": "Ancient ruins holding forgotten treasures and dangers.",
                "location_type": "dungeon",
                "terrain": "dungeon",
                "danger_level": 10,
                "controlling_faction": None,
                "atmosphere": "Ominous and foreboding",
            },
        ],
        "connections": [
            {
                "from_location": "The Hearthstone Inn",
                "to_location": "The Crossroads Market",
                "direction": "east",
            },
            {
                "from_location": "The Crossroads Market",
                "to_location": "The Hearthstone Inn",
                "direction": "west",
            },
            {
                "from_location": "The Hearthstone Inn",
                "to_location": "The Whispering Wilds",
                "direction": "north",
            },
            {
                "from_location": "The Whispering Wilds",
                "to_location": "The Hearthstone Inn",
                "direction": "south",
            },
            {
                "from_location": "The Whispering Wilds",
                "to_location": "The Sunken Vault",
                "direction": "east",
            },
            {
                "from_location": "The Sunken Vault",
                "to_location": "The Whispering Wilds",
                "direction": "west",
            },
            {
                "from_location": "The Crossroads Market",
                "to_location": "The Whispering Wilds",
                "direction": "north",
            },
            {
                "from_location": "The Whispering Wilds",
                "to_location": "The Crossroads Market",
                "direction": "south",
            },
        ],
    }


def _fallback_npcs(faction_names: list[str], location_names: list[str]) -> dict[str, Any]:
    """Generate fallback NPCs without LLM."""
    npcs = []
    if location_names:
        npcs.append(
            {
                "name": "Kael the Keeper",
                "description": "A weathered innkeeper with a knowing smile and steady hands.",
                "role": "bartender",
                "location": location_names[0],
                "faction": faction_names[0] if faction_names else None,
                "hp_max": 25,
                "ac": 12,
                "speech_style": "warm but cautious",
                "quirks": ["polishes glasses when nervous", "remembers every face"],
                "motivations": ["duty", "belonging"],
                "initial_attitude": "friendly",
            }
        )
    if len(location_names) > 1:
        npcs.append(
            {
                "name": "Zara the Trader",
                "description": "A shrewd merchant draped in colorful silks and jangling bracelets.",
                "role": "merchant",
                "location": location_names[1],
                "faction": faction_names[1] if len(faction_names) > 1 else None,
                "hp_max": 15,
                "ac": 11,
                "speech_style": "enthusiastic and persuasive",
                "quirks": ["exaggerates prices then 'discounts'", "collects stories"],
                "motivations": ["wealth", "knowledge"],
                "initial_attitude": "friendly",
            }
        )
    if len(location_names) > 1:
        npcs.append(
            {
                "name": "The Watcher",
                "description": "A hooded figure who observes from the shadows, rarely speaking.",
                "role": "informant",
                "location": location_names[0],
                "faction": faction_names[2] if len(faction_names) > 2 else None,
                "hp_max": 35,
                "ac": 15,
                "speech_style": "cryptic and measured",
                "quirks": ["appears unexpectedly", "knows things they shouldn't"],
                "motivations": ["knowledge", "survival"],
                "initial_attitude": "neutral",
            }
        )
    return {"npcs": npcs}


# =============================================================================
# Motivation mapping
# =============================================================================

MOTIVATION_MAP: dict[str, Motivation] = {
    "duty": Motivation.DUTY,
    "wealth": Motivation.WEALTH,
    "knowledge": Motivation.KNOWLEDGE,
    "power": Motivation.POWER,
    "survival": Motivation.SURVIVAL,
    "fame": Motivation.FAME,
    "belonging": Motivation.BELONGING,
    "safety": Motivation.SAFETY,
    "respect": Motivation.RESPECT,
    "artistry": Motivation.ARTISTRY,
}

RELATIONSHIP_TYPE_MAP: dict[str, RelationshipType] = {
    "TRADES_WITH": RelationshipType.TRADES_WITH,
    "COMPETES_WITH": RelationshipType.COMPETES_WITH,
    "DEPENDS_ON": RelationshipType.DEPENDS_ON,
    "CONTROLS": RelationshipType.CONTROLS,
    "INFLUENCES": RelationshipType.INFLUENCES,
}


# =============================================================================
# Generator
# =============================================================================


def _parse_json(raw: str) -> dict[str, Any] | None:
    """Try to parse JSON from LLM response, handling markdown fences."""
    text = raw.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last fence lines
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON from LLM response")
        return None


@dataclass
class UniverseGenerator:
    """
    LLM-powered procedural universe generation.

    Pipeline: template → world context → factions → locations → NPCs → DB.
    Falls back to templates if LLM is unavailable.
    """

    dolt: DoltRepository
    neo4j: Neo4jRepository
    npc_service: NPCService
    llm: LLMService | None = None

    async def generate_from_template(
        self,
        template: UniverseTemplate,
        player_name: str = "Hero",
    ) -> GenerationResult:
        """
        Generate a complete universe from a template.

        Args:
            template: The creative seed
            player_name: Name for the player character

        Returns:
            GenerationResult with all created entity IDs
        """
        used_fallback = False

        # Step 1: World Context
        world_context = await self._generate_world_context(template)
        if world_context.get("used_fallback"):
            used_fallback = True

        # Step 2: Create Universe
        universe = Universe(
            name=template.name,
            description=world_context.get("history", template.cultural_premise),
            branch_name="main",
            template_id=template.id,
            physics_overlay_key=template.physics_overlay_key,
            world_context=world_context,
        )
        self.dolt.save_universe(universe)

        # Step 3: Factions
        faction_data = await self._generate_factions(template, world_context)
        if not faction_data.get("factions"):
            used_fallback = True
        faction_entities = self._create_faction_entities(universe.id, faction_data)
        faction_name_to_id = {e.name: e.id for e in faction_entities}
        self._create_faction_relationships(universe.id, faction_data, faction_name_to_id)

        # Step 4: Locations
        faction_names = list(faction_name_to_id.keys())
        location_data = await self._generate_locations(template, world_context, faction_names)
        location_entities = self._create_location_entities(
            universe.id, location_data, faction_name_to_id
        )
        location_name_to_id = {e.name: e.id for e in location_entities}
        self._create_location_connections(universe.id, location_data, location_name_to_id)

        # Step 5: NPCs
        location_names = list(location_name_to_id.keys())
        npc_data = await self._generate_npcs(
            world_context, faction_names, location_names, location_data
        )
        npc_entities = self._create_npc_entities(
            universe.id, npc_data, location_name_to_id, faction_name_to_id
        )
        npc_name_to_id = {e.name: e.id for e in npc_entities}

        # Step 6: Create Player Character
        # Ensure at least one location exists (fallback if pipeline produced none)
        if not location_entities:
            fallback_loc = create_location(
                name="Starting Area",
                description="A quiet clearing. Your adventure begins here.",
                universe_id=universe.id,
                location_type="forest",
            )
            self.dolt.save_entity(fallback_loc)
            location_entities = [fallback_loc]
            location_name_to_id[fallback_loc.name] = fallback_loc.id

        starting_location_id = location_entities[0].id
        player = create_character(
            name=player_name,
            description=f"An adventurer exploring the world of {template.name}.",
            universe_id=universe.id,
            hp_max=12,
            ac=14,
            gold_copper=5000,
        )
        player.current_location_id = starting_location_id
        self.dolt.save_entity(player)

        self.neo4j.create_relationship(
            Relationship(
                universe_id=universe.id,
                from_entity_id=player.id,
                to_entity_id=starting_location_id,
                relationship_type=RelationshipType.LOCATED_IN,
            )
        )

        return GenerationResult(
            universe=universe,
            starting_location_id=starting_location_id,
            player_character_id=player.id,
            factions=faction_name_to_id,
            locations=location_name_to_id,
            npcs=npc_name_to_id,
            used_fallback=used_fallback,
        )

    # =========================================================================
    # Pipeline Steps
    # =========================================================================

    async def _generate_world_context(self, template: UniverseTemplate) -> dict[str, Any]:
        """Step 1: Generate world context from template."""
        if not self.llm or not self.llm.is_available:
            return _fallback_world_context(template)

        user_prompt = f"""Create world context for this universe:

Name: {template.name}
Tone: {template.tone}
Genre: {", ".join(template.genre_tags)}
Power Source: {template.power_source_flavor}
Cultural Premise: {template.cultural_premise}
Economic Premise: {template.economic_premise}
Geography: {template.geography_hint}
Era: {template.era_hint}
Scarcity: {template.scarcity}"""

        try:
            raw = await self.llm.generate_structured(
                system_prompt=WORLD_CONTEXT_SYSTEM,
                user_prompt=user_prompt,
                max_tokens=1024,
            )
            parsed = _parse_json(raw)
            if parsed:
                return parsed
        except Exception:
            logger.exception("LLM world context generation failed")

        return _fallback_world_context(template)

    async def _generate_factions(
        self, template: UniverseTemplate, world_context: dict[str, Any]
    ) -> dict[str, Any]:
        """Step 2: Generate factions from world context."""
        if not self.llm or not self.llm.is_available:
            return _fallback_factions(template)

        seed_text = ""
        if template.faction_seeds:
            seed_lines = []
            for s in template.faction_seeds:
                parts = [f"Role: {s.role_hint}"]
                if s.name_hint:
                    parts.append(f"Name hint: {s.name_hint}")
                if s.values_hint:
                    parts.append(f"Values: {s.values_hint}")
                seed_lines.append(", ".join(parts))
            seed_text = "\n\nFaction Seeds (optional hints):\n" + "\n".join(
                f"- {line}" for line in seed_lines
            )

        user_prompt = f"""Generate factions for this world:

World Context:
{json.dumps(world_context, indent=2)}

Tone: {template.tone}
Economic Premise: {template.economic_premise}
Scarcity: {template.scarcity}{seed_text}"""

        try:
            raw = await self.llm.generate_structured(
                system_prompt=FACTIONS_SYSTEM,
                user_prompt=user_prompt,
                max_tokens=2048,
            )
            parsed = _parse_json(raw)
            if parsed and parsed.get("factions"):
                return parsed
        except Exception:
            logger.exception("LLM faction generation failed")

        return _fallback_factions(template)

    async def _generate_locations(
        self,
        template: UniverseTemplate,
        world_context: dict[str, Any],
        faction_names: list[str],
    ) -> dict[str, Any]:
        """Step 3: Generate locations from world context and factions."""
        if not self.llm or not self.llm.is_available:
            return _fallback_locations(template, faction_names)

        user_prompt = f"""Generate locations for this world:

World Context:
{json.dumps(world_context, indent=2)}

Factions: {", ".join(faction_names)}
Geography: {template.geography_hint}
Tone: {template.tone}"""

        try:
            raw = await self.llm.generate_structured(
                system_prompt=LOCATIONS_SYSTEM,
                user_prompt=user_prompt,
                max_tokens=2048,
            )
            parsed = _parse_json(raw)
            if parsed and parsed.get("locations"):
                return parsed
        except Exception:
            logger.exception("LLM location generation failed")

        return _fallback_locations(template, faction_names)

    async def _generate_npcs(
        self,
        world_context: dict[str, Any],
        faction_names: list[str],
        location_names: list[str],
        location_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Step 4: Generate NPCs from full context."""
        if not self.llm or not self.llm.is_available:
            return _fallback_npcs(faction_names, location_names)

        user_prompt = f"""Generate NPCs for this world:

World Context:
{json.dumps(world_context, indent=2)}

Factions: {", ".join(faction_names)}
Locations: {json.dumps(location_data.get("locations", []), indent=2)}"""

        try:
            raw = await self.llm.generate_structured(
                system_prompt=NPCS_SYSTEM,
                user_prompt=user_prompt,
                max_tokens=2048,
            )
            parsed = _parse_json(raw)
            if parsed and parsed.get("npcs"):
                return parsed
        except Exception:
            logger.exception("LLM NPC generation failed")

        return _fallback_npcs(faction_names, location_names)

    # =========================================================================
    # Entity Creation
    # =========================================================================

    def _create_faction_entities(
        self, universe_id: UUID, faction_data: dict[str, Any]
    ) -> list[Entity]:
        """Create faction entities from generation data."""
        entities = []
        for f in faction_data.get("factions", []):
            entity = create_faction(
                universe_id=universe_id,
                name=f.get("name", "Unknown Faction"),
                description=f.get("description", ""),
                alignment=f.get("alignment"),
                influence=f.get("influence", 50),
            )
            # Set enhanced properties
            if entity.faction_properties:
                props = entity.faction_properties
                props.core_values = f.get("core_values", [])
                props.ideology_summary = f.get("ideology_summary")
                props.controls_resources = f.get("controls_resources", [])
                props.produces = f.get("produces", [])
                props.needs = f.get("needs", [])
                props.economic_role = f.get("economic_role")
                props.cultural_traits = f.get("cultural_traits", [])
                props.taboos = f.get("taboos", [])
                props.aesthetic = f.get("aesthetic")
                props.governance = f.get("governance")
                props.leader_title = f.get("leader_title")
                props.territory_description = f.get("territory_description")
                props.headquarters = f.get("headquarters")

            self.dolt.save_entity(entity)
            entities.append(entity)
        return entities

    def _create_faction_relationships(
        self,
        universe_id: UUID,
        faction_data: dict[str, Any],
        faction_name_to_id: dict[str, UUID],
    ) -> None:
        """Create inter-faction relationships."""
        for rel in faction_data.get("relationships", []):
            from_name = rel.get("from_faction", "")
            to_name = rel.get("to_faction", "")
            from_id = faction_name_to_id.get(from_name)
            to_id = faction_name_to_id.get(to_name)
            if not from_id or not to_id:
                continue

            rel_type = RELATIONSHIP_TYPE_MAP.get(rel.get("type", ""), RelationshipType.ALLIED_WITH)
            self.neo4j.create_relationship(
                Relationship(
                    universe_id=universe_id,
                    from_entity_id=from_id,
                    to_entity_id=to_id,
                    relationship_type=rel_type,
                    description=rel.get("description", ""),
                )
            )

    def _create_location_entities(
        self,
        universe_id: UUID,
        location_data: dict[str, Any],
        faction_name_to_id: dict[str, UUID],
    ) -> list[Entity]:
        """Create location entities from generation data."""
        entities = []
        for loc in location_data.get("locations", []):
            entity = create_location(
                universe_id=universe_id,
                name=loc.get("name", "Unknown Location"),
                description=loc.get("description", ""),
                location_type=loc.get("location_type", "unknown"),
                region=loc.get("region"),
                terrain=loc.get("terrain"),
                danger_level=min(max(loc.get("danger_level", 0), 0), 20),
            )
            # Set enhanced properties
            if entity.location_properties:
                props = entity.location_properties
                props.controlling_faction_hint = loc.get("controlling_faction")
                props.cultural_flavor = loc.get("cultural_flavor")
                props.economic_activity = loc.get("economic_activity")
                props.atmosphere = loc.get("atmosphere")

            self.dolt.save_entity(entity)
            entities.append(entity)

            # Create CONTROLS relationship if faction specified
            controlling = loc.get("controlling_faction")
            if controlling and controlling in faction_name_to_id:
                self.neo4j.create_relationship(
                    Relationship(
                        universe_id=universe_id,
                        from_entity_id=faction_name_to_id[controlling],
                        to_entity_id=entity.id,
                        relationship_type=RelationshipType.CONTROLS,
                        description=f"{controlling} controls {entity.name}",
                    )
                )

        return entities

    def _create_location_connections(
        self,
        universe_id: UUID,
        location_data: dict[str, Any],
        location_name_to_id: dict[str, UUID],
    ) -> None:
        """Create CONNECTED_TO relationships between locations."""
        for conn in location_data.get("connections", []):
            from_name = conn.get("from_location", "")
            to_name = conn.get("to_location", "")
            from_id = location_name_to_id.get(from_name)
            to_id = location_name_to_id.get(to_name)
            if not from_id or not to_id:
                continue

            self.neo4j.create_relationship(
                Relationship(
                    universe_id=universe_id,
                    from_entity_id=from_id,
                    to_entity_id=to_id,
                    relationship_type=RelationshipType.CONNECTED_TO,
                    description=conn.get("direction", ""),
                )
            )

    def _create_npc_entities(
        self,
        universe_id: UUID,
        npc_data: dict[str, Any],
        location_name_to_id: dict[str, UUID],
        faction_name_to_id: dict[str, UUID],
    ) -> list[Entity]:
        """Create NPC entities from generation data."""
        entities = []
        for npc in npc_data.get("npcs", []):
            location_name = npc.get("location", "")
            location_id = location_name_to_id.get(location_name)

            entity = create_character(
                universe_id=universe_id,
                name=npc.get("name", "Unknown NPC"),
                description=npc.get("description", ""),
                hp_max=npc.get("hp_max", 15),
                ac=npc.get("ac", 11),
                location_id=location_id,
                tags=["npc", npc.get("role", "citizen")],
            )
            self.dolt.save_entity(entity)
            entities.append(entity)

            # LOCATED_IN relationship
            if location_id:
                self.neo4j.create_relationship(
                    Relationship(
                        universe_id=universe_id,
                        from_entity_id=entity.id,
                        to_entity_id=location_id,
                        relationship_type=RelationshipType.LOCATED_IN,
                    )
                )

            # MEMBER_OF relationship
            faction_name = npc.get("faction")
            if faction_name and faction_name in faction_name_to_id:
                self.neo4j.create_relationship(
                    Relationship(
                        universe_id=universe_id,
                        from_entity_id=entity.id,
                        to_entity_id=faction_name_to_id[faction_name],
                        relationship_type=RelationshipType.MEMBER_OF,
                        description=npc.get("role", "member"),
                    )
                )

            # Create NPC profile
            motivations = []
            for m in npc.get("motivations", ["duty"]):
                mapped = MOTIVATION_MAP.get(m.lower())
                if mapped:
                    motivations.append(mapped)
            if not motivations:
                motivations = [Motivation.DUTY]

            profile = create_npc_profile(
                entity_id=entity.id,
                speech_style=npc.get("speech_style", "neutral"),
                quirks=npc.get("quirks", []),
                motivations=motivations,
            )
            self.npc_service.save_profile(profile)

        return entities
