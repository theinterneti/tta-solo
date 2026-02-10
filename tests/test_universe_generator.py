"""
Tests for the universe generation system.

Tests cover:
- UniverseTemplate model validation
- FactionSeed model validation
- Enhanced model backwards compatibility
- Fallback generation (no LLM)
- Full pipeline with MockLLMProvider
- JSON parsing edge cases
- Pre-built templates
"""

from __future__ import annotations

import json

import pytest

from src.content.universe_templates import (
    CLASSIC_FANTASY,
    UNIVERSE_TEMPLATES,
    get_template_by_index,
    get_template_by_name,
)
from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.models.entity import (
    FactionProperties,
    LocationProperties,
)
from src.models.relationships import RelationshipType
from src.models.universe import Universe
from src.models.universe_template import FactionSeed, UniverseTemplate
from src.services.llm import LLMService, MockLLMProvider
from src.services.npc import NPCService
from src.services.universe_generator import (
    GenerationResult,
    UniverseGenerator,
    _fallback_factions,
    _fallback_locations,
    _fallback_npcs,
    _fallback_world_context,
    _parse_json,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def dolt():
    return InMemoryDoltRepository()


@pytest.fixture
def neo4j():
    return InMemoryNeo4jRepository()


@pytest.fixture
def npc_service(dolt, neo4j):
    return NPCService(dolt=dolt, neo4j=neo4j)


@pytest.fixture
def generator(dolt, neo4j, npc_service):
    return UniverseGenerator(dolt=dolt, neo4j=neo4j, npc_service=npc_service)


@pytest.fixture
def template():
    return CLASSIC_FANTASY


# =============================================================================
# UniverseTemplate Model Tests
# =============================================================================


class TestUniverseTemplate:
    """Tests for UniverseTemplate model validation."""

    def test_default_template(self):
        """Default template should have valid defaults."""
        t = UniverseTemplate(name="Test")
        assert t.name == "Test"
        assert t.physics_overlay_key == "high_fantasy"
        assert t.tone == "adventure"
        assert t.faction_seeds == []

    def test_template_with_faction_seeds(self):
        """Template should accept faction seeds."""
        t = UniverseTemplate(
            name="Test",
            faction_seeds=[
                FactionSeed(role_hint="rulers", values_hint="order"),
                FactionSeed(name_hint="The Guild", role_hint="merchants"),
            ],
        )
        assert len(t.faction_seeds) == 2
        assert t.faction_seeds[0].name_hint is None
        assert t.faction_seeds[1].name_hint == "The Guild"

    def test_template_name_validation(self):
        """Name must be non-empty."""
        with pytest.raises(ValueError):
            UniverseTemplate(name="")

    def test_template_has_id(self):
        """Each template should get a unique ID."""
        t1 = UniverseTemplate(name="A")
        t2 = UniverseTemplate(name="B")
        assert t1.id != t2.id


class TestFactionSeed:
    """Tests for FactionSeed model."""

    def test_minimal_seed(self):
        """Seed only requires role_hint."""
        seed = FactionSeed(role_hint="rebels")
        assert seed.role_hint == "rebels"
        assert seed.name_hint is None
        assert seed.values_hint is None

    def test_full_seed(self):
        """Seed with all fields."""
        seed = FactionSeed(
            name_hint="The Resistance",
            role_hint="rebels",
            values_hint="freedom",
        )
        assert seed.name_hint == "The Resistance"


# =============================================================================
# Enhanced Model Backwards Compatibility
# =============================================================================


class TestEnhancedModels:
    """Tests that enhanced models are backwards-compatible."""

    def test_faction_properties_backwards_compat(self):
        """Old FactionProperties usage still works."""
        props = FactionProperties(alignment="neutral", influence=50)
        assert props.alignment == "neutral"
        assert props.core_values == []
        assert props.ideology_summary is None
        assert props.governance is None

    def test_faction_properties_new_fields(self):
        """New FactionProperties fields work."""
        props = FactionProperties(
            core_values=["honor", "duty"],
            economic_role="producers",
            governance="monarchy",
            leader_title="King",
        )
        assert props.core_values == ["honor", "duty"]
        assert props.economic_role == "producers"

    def test_location_properties_backwards_compat(self):
        """Old LocationProperties usage still works."""
        props = LocationProperties(location_type="tavern", terrain="urban")
        assert props.controlling_faction_hint is None
        assert props.atmosphere is None

    def test_location_properties_new_fields(self):
        """New LocationProperties fields work."""
        props = LocationProperties(
            controlling_faction_hint="The Crown",
            cultural_flavor="Royal banners everywhere",
            economic_activity="Tax collection",
            atmosphere="Oppressive and formal",
        )
        assert props.controlling_faction_hint == "The Crown"

    def test_universe_backwards_compat(self):
        """Old Universe usage still works."""
        u = Universe(name="Test", branch_name="main")
        assert u.template_id is None
        assert u.physics_overlay_key == "high_fantasy"
        assert u.world_context == {}

    def test_universe_new_fields(self):
        """New Universe fields work."""
        u = Universe(
            name="Test",
            branch_name="main",
            physics_overlay_key="cyberpunk",
            world_context={"history": "A dark future"},
        )
        assert u.physics_overlay_key == "cyberpunk"
        assert u.world_context["history"] == "A dark future"

    def test_new_relationship_types(self):
        """New faction relationship types exist."""
        assert RelationshipType.TRADES_WITH == "TRADES_WITH"
        assert RelationshipType.COMPETES_WITH == "COMPETES_WITH"
        assert RelationshipType.DEPENDS_ON == "DEPENDS_ON"
        assert RelationshipType.CONTROLS == "CONTROLS"
        assert RelationshipType.INFLUENCES == "INFLUENCES"


# =============================================================================
# JSON Parsing
# =============================================================================


class TestParseJSON:
    """Tests for JSON parsing from LLM responses."""

    def test_plain_json(self):
        """Parse plain JSON."""
        result = _parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_markdown_fenced_json(self):
        """Parse JSON wrapped in markdown code fences."""
        raw = '```json\n{"key": "value"}\n```'
        result = _parse_json(raw)
        assert result == {"key": "value"}

    def test_invalid_json(self):
        """Invalid JSON returns None."""
        result = _parse_json("not json at all")
        assert result is None

    def test_empty_string(self):
        """Empty string returns None."""
        result = _parse_json("")
        assert result is None

    def test_nested_json(self):
        """Parse nested JSON structures."""
        data = {"factions": [{"name": "Test", "values": ["a", "b"]}]}
        result = _parse_json(json.dumps(data))
        assert result == data


# =============================================================================
# Fallback Generation
# =============================================================================


class TestFallbacks:
    """Tests for template-based fallback generation."""

    def test_fallback_world_context(self, template):
        """Fallback world context uses template fields."""
        ctx = _fallback_world_context(template)
        assert "history" in ctx
        assert "cosmology" in ctx
        assert "tone_guide" in ctx
        assert ctx["used_fallback"] is True
        assert template.tone in ctx["tone_guide"]

    def test_fallback_factions(self, template):
        """Fallback generates 3 factions with relationships."""
        data = _fallback_factions(template)
        assert len(data["factions"]) == 3
        assert len(data["relationships"]) >= 2

    def test_fallback_factions_uses_seeds(self):
        """Fallback respects faction seeds."""
        t = UniverseTemplate(
            name="Test",
            faction_seeds=[
                FactionSeed(name_hint="My Faction", role_hint="rulers"),
            ],
        )
        data = _fallback_factions(t)
        assert data["factions"][0]["name"] == "My Faction"

    def test_fallback_locations(self, template):
        """Fallback generates 4 locations with connections."""
        data = _fallback_locations(template, ["Faction A", "Faction B"])
        assert len(data["locations"]) == 4
        assert len(data["connections"]) >= 4
        # First location should be a tavern
        assert data["locations"][0]["location_type"] == "tavern"

    def test_fallback_npcs(self):
        """Fallback generates NPCs for locations."""
        data = _fallback_npcs(
            ["Faction A", "Faction B"],
            ["The Inn", "The Market"],
        )
        assert len(data["npcs"]) == 3
        assert data["npcs"][0]["location"] == "The Inn"
        assert data["npcs"][1]["location"] == "The Market"


# =============================================================================
# Full Pipeline (Fallback — No LLM)
# =============================================================================


class TestUniverseGeneratorFallback:
    """Tests for full generation pipeline using fallback (no LLM)."""

    @pytest.mark.asyncio
    async def test_generate_creates_universe(self, generator, template):
        """Generator should create a universe."""
        result = await generator.generate_from_template(template)
        assert isinstance(result, GenerationResult)
        assert result.universe.name == template.name

    @pytest.mark.asyncio
    async def test_generate_creates_factions(self, generator, template):
        """Generator should create faction entities."""
        result = await generator.generate_from_template(template)
        assert len(result.factions) >= 2

    @pytest.mark.asyncio
    async def test_generate_creates_locations(self, generator, template):
        """Generator should create location entities."""
        result = await generator.generate_from_template(template)
        assert len(result.locations) >= 3

    @pytest.mark.asyncio
    async def test_generate_creates_npcs(self, generator, template):
        """Generator should create NPC entities."""
        result = await generator.generate_from_template(template)
        assert len(result.npcs) >= 2

    @pytest.mark.asyncio
    async def test_generate_creates_player(self, generator, template):
        """Generator should create a player character."""
        result = await generator.generate_from_template(template, player_name="TestHero")
        player = generator.dolt.get_entity(result.player_character_id, result.universe.id)
        assert player is not None
        assert player.name == "TestHero"

    @pytest.mark.asyncio
    async def test_generate_sets_player_location(self, generator, template):
        """Player should be at the starting location."""
        result = await generator.generate_from_template(template)
        player = generator.dolt.get_entity(result.player_character_id, result.universe.id)
        assert player is not None
        assert player.current_location_id == result.starting_location_id

    @pytest.mark.asyncio
    async def test_generate_marks_fallback(self, generator, template):
        """Should mark that fallback was used."""
        result = await generator.generate_from_template(template)
        assert result.used_fallback is True

    @pytest.mark.asyncio
    async def test_generate_stores_world_context(self, generator, template):
        """Universe should have world_context."""
        result = await generator.generate_from_template(template)
        assert result.universe.world_context is not None
        assert "history" in result.universe.world_context

    @pytest.mark.asyncio
    async def test_generate_creates_location_connections(self, generator, template):
        """Locations should be connected."""
        result = await generator.generate_from_template(template)
        # Check CONNECTED_TO via first location
        first_loc_id = list(result.locations.values())[0]
        rels = generator.neo4j.get_relationships(
            first_loc_id, result.universe.id, relationship_type=RelationshipType.CONNECTED_TO
        )
        assert len(rels) >= 1

    @pytest.mark.asyncio
    async def test_generate_creates_npc_location_rels(self, generator, template):
        """Player should have LOCATED_IN relationship."""
        result = await generator.generate_from_template(template)
        rels = generator.neo4j.get_relationships(
            result.player_character_id,
            result.universe.id,
            relationship_type=RelationshipType.LOCATED_IN,
        )
        assert len(rels) >= 1

    @pytest.mark.asyncio
    async def test_generate_sets_template_id(self, generator, template):
        """Universe should reference its template."""
        result = await generator.generate_from_template(template)
        assert result.universe.template_id == template.id

    @pytest.mark.asyncio
    async def test_generate_sets_physics_overlay(self, generator, template):
        """Universe should have the template's physics overlay."""
        result = await generator.generate_from_template(template)
        assert result.universe.physics_overlay_key == template.physics_overlay_key


# =============================================================================
# Pipeline with Mock LLM
# =============================================================================


class TestUniverseGeneratorWithMockLLM:
    """Tests for generation pipeline with MockLLMProvider returning canned JSON."""

    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM provider with canned responses."""
        provider = MockLLMProvider()
        return LLMService(provider=provider)

    @pytest.fixture
    def generator_with_llm(self, dolt, neo4j, npc_service, mock_llm):
        return UniverseGenerator(dolt=dolt, neo4j=neo4j, npc_service=npc_service, llm=mock_llm)

    @pytest.mark.asyncio
    async def test_llm_response_parsed(self, generator_with_llm, template):
        """Generator should work even when LLM returns mock response (falls back)."""
        result = await generator_with_llm.generate_from_template(template)
        # Mock returns "[Mock LLM response]" which isn't valid JSON,
        # so it falls back to template generation
        assert isinstance(result, GenerationResult)
        assert len(result.factions) >= 2


# =============================================================================
# Pre-Built Templates
# =============================================================================


class TestPreBuiltTemplates:
    """Tests for pre-built universe templates."""

    def test_all_templates_valid(self):
        """All pre-built templates should be valid UniverseTemplate instances."""
        assert len(UNIVERSE_TEMPLATES) >= 6
        for t in UNIVERSE_TEMPLATES:
            assert isinstance(t, UniverseTemplate)
            assert t.name
            assert t.tone
            assert t.genre_tags

    def test_get_template_by_name(self):
        """Should find template by name (case-insensitive)."""
        t = get_template_by_name("The Shattered Kingdoms")
        assert t is not None
        assert t.name == "The Shattered Kingdoms"

    def test_get_template_by_name_case_insensitive(self):
        """Should be case-insensitive."""
        t = get_template_by_name("the shattered kingdoms")
        assert t is not None

    def test_get_template_by_name_missing(self):
        """Should return None for unknown template."""
        assert get_template_by_name("Nonexistent") is None

    def test_get_template_by_index(self):
        """Should get template by index."""
        t = get_template_by_index(0)
        assert t is not None
        assert t == UNIVERSE_TEMPLATES[0]

    def test_get_template_by_index_out_of_bounds(self):
        """Should return None for invalid index."""
        assert get_template_by_index(-1) is None
        assert get_template_by_index(999) is None

    def test_templates_have_unique_names(self):
        """All templates should have unique names."""
        names = [t.name for t in UNIVERSE_TEMPLATES]
        assert len(names) == len(set(names))

    @pytest.mark.asyncio
    @pytest.mark.parametrize("index", range(len(UNIVERSE_TEMPLATES)))
    async def test_each_template_generates(self, dolt, neo4j, npc_service, index):
        """Each template should generate a valid universe (fallback mode)."""
        template = UNIVERSE_TEMPLATES[index]
        generator = UniverseGenerator(dolt=dolt, neo4j=neo4j, npc_service=npc_service)
        result = await generator.generate_from_template(template)
        assert result.universe.name == template.name
        assert len(result.locations) >= 3
