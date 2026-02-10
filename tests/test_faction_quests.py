"""
Tests for faction quest generation (Phase B).
"""

from __future__ import annotations

import random
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.models.entity import (
    FactionProperties,
    create_character,
    create_faction,
    create_location,
)
from src.models.quest import QuestType
from src.models.relationships import Relationship, RelationshipType
from src.models.universe import Universe
from src.services.quest import (
    _FACTION_QUEST_TEMPLATES,
    FactionTension,
    QuestContext,
    QuestService,
)


@pytest.fixture
def universe_id():
    return uuid4()


@pytest.fixture
def dolt():
    return InMemoryDoltRepository()


@pytest.fixture
def neo4j():
    return InMemoryNeo4jRepository()


@pytest.fixture
def quest_service(dolt, neo4j):
    return QuestService(dolt=dolt, neo4j=neo4j)


def _make_faction(universe_id, name, **kwargs):
    """Helper to create a faction with properties."""
    faction = create_faction(universe_id=universe_id, name=name)
    props = FactionProperties(
        controls_resources=kwargs.get("controls_resources", []),
        produces=kwargs.get("produces", []),
        needs=kwargs.get("needs", []),
        territory_description=kwargs.get("territory_description"),
        core_values=kwargs.get("core_values", []),
    )
    faction.faction_properties = props
    return faction


# =============================================================================
# FactionTension Model Tests
# =============================================================================


class TestFactionTension:
    """Tests for FactionTension model."""

    def test_create_faction_tension(self):
        """FactionTension creates with required fields."""
        tension = FactionTension(
            faction_a_name="Iron Guild",
            faction_b_name="Silver Order",
            faction_a_id=uuid4(),
            faction_b_id=uuid4(),
            relationship_type="COMPETES_WITH",
        )
        assert tension.faction_a_name == "Iron Guild"
        assert tension.faction_b_name == "Silver Order"
        assert tension.relationship_type == "COMPETES_WITH"
        assert tension.description == ""

    def test_faction_tension_with_description(self):
        """FactionTension can include a description."""
        tension = FactionTension(
            faction_a_name="Merchants",
            faction_b_name="Thieves",
            faction_a_id=uuid4(),
            faction_b_id=uuid4(),
            relationship_type="COMPETES_WITH",
            description="Long-standing rivalry over trade routes",
        )
        assert tension.description == "Long-standing rivalry over trade routes"


# =============================================================================
# QuestContext with Faction Data Tests
# =============================================================================


class TestQuestContextFactions:
    """Tests for QuestContext with faction fields."""

    def test_quest_context_defaults_backward_compatible(self):
        """QuestContext without faction data works as before."""
        ctx = QuestContext(
            universe_id=uuid4(),
            location_id=uuid4(),
        )
        assert ctx.controlling_faction is None
        assert ctx.factions_at_location == []
        assert ctx.faction_tensions == []
        assert ctx.world_context_summary == ""

    def test_quest_context_with_faction_data(self, universe_id):
        """QuestContext accepts faction data."""
        faction = _make_faction(universe_id, "Test Faction")
        tension = FactionTension(
            faction_a_name="A",
            faction_b_name="B",
            faction_a_id=uuid4(),
            faction_b_id=uuid4(),
            relationship_type="TRADES_WITH",
        )
        ctx = QuestContext(
            universe_id=universe_id,
            location_id=uuid4(),
            controlling_faction=faction,
            factions_at_location=[faction],
            faction_tensions=[tension],
            world_context_summary="A dark medieval world",
        )
        assert ctx.controlling_faction is not None
        assert len(ctx.factions_at_location) == 1
        assert len(ctx.faction_tensions) == 1
        assert ctx.world_context_summary == "A dark medieval world"


# =============================================================================
# Faction Template Tests
# =============================================================================


class TestFactionTemplates:
    """Tests for faction quest template data."""

    def test_all_relationship_types_have_templates(self):
        """Each expected relationship type has at least one template."""
        expected_types = {"TRADES_WITH", "COMPETES_WITH", "DEPENDS_ON", "CONTROLS", "INFLUENCES"}
        for rel_type in expected_types:
            assert rel_type in _FACTION_QUEST_TEMPLATES, f"Missing templates for {rel_type}"
            assert len(_FACTION_QUEST_TEMPLATES[rel_type]) >= 1

    def test_templates_have_faction_placeholders(self):
        """Faction templates reference {faction_a} and/or {faction_b}."""
        for rel_type, templates in _FACTION_QUEST_TEMPLATES.items():
            for tmpl in templates:
                all_patterns = tmpl.name_patterns + tmpl.description_patterns
                pattern_text = " ".join(all_patterns)
                assert "{faction_a}" in pattern_text or "{faction_b}" in pattern_text, (
                    f"Template for {rel_type} ({tmpl.quest_type}) has no faction placeholders"
                )

    def test_template_count(self):
        """Verify approximate template counts per relationship."""
        assert len(_FACTION_QUEST_TEMPLATES["TRADES_WITH"]) == 2
        assert len(_FACTION_QUEST_TEMPLATES["COMPETES_WITH"]) == 3
        assert len(_FACTION_QUEST_TEMPLATES["DEPENDS_ON"]) == 2
        assert len(_FACTION_QUEST_TEMPLATES["CONTROLS"]) == 2
        assert len(_FACTION_QUEST_TEMPLATES["INFLUENCES"]) == 2


# =============================================================================
# Faction-Aware Template Selection Tests
# =============================================================================


class TestFactionTemplateSelection:
    """Tests for faction-aware template selection."""

    @pytest.mark.asyncio
    async def test_faction_template_selected_when_tensions_exist(self, quest_service, universe_id):
        """With tensions and favorable random, faction templates are selected."""
        faction_a = _make_faction(universe_id, "Iron Guild", controls_resources=["iron"])
        faction_b = _make_faction(universe_id, "Silver Order", controls_resources=["silver"])

        tension = FactionTension(
            faction_a_name="Iron Guild",
            faction_b_name="Silver Order",
            faction_a_id=faction_a.id,
            faction_b_id=faction_b.id,
            relationship_type="COMPETES_WITH",
        )

        context = QuestContext(
            universe_id=universe_id,
            location_id=uuid4(),
            location_type="market",
            location_name="Trade Square",
            faction_tensions=[tension],
            factions_at_location=[faction_a, faction_b],
        )

        # Force faction path by seeding random
        random.seed(42)
        # Generate multiple quests to ensure at least one is faction-based
        found_faction_quest = False
        for _ in range(20):
            result = await quest_service.generate_quest(context)
            assert result.success
            if "faction" in result.quest.tags:
                found_faction_quest = True
                break

        assert found_faction_quest, "Expected at least one faction quest in 20 attempts"

    @pytest.mark.asyncio
    async def test_no_faction_template_when_no_tensions(self, quest_service, universe_id):
        """Without tensions, normal location templates are used."""
        context = QuestContext(
            universe_id=universe_id,
            location_id=uuid4(),
            location_type="tavern",
            location_name="The Rusty Mug",
            faction_tensions=[],
        )

        result = await quest_service.generate_quest(context)
        assert result.success
        assert "faction" not in result.quest.tags

    @pytest.mark.asyncio
    async def test_specific_quest_type_overrides_faction(self, quest_service, universe_id):
        """Specifying a quest_type bypasses faction selection."""
        faction_a = _make_faction(universe_id, "A")
        faction_b = _make_faction(universe_id, "B")

        tension = FactionTension(
            faction_a_name="A",
            faction_b_name="B",
            faction_a_id=faction_a.id,
            faction_b_id=faction_b.id,
            relationship_type="COMPETES_WITH",
        )

        context = QuestContext(
            universe_id=universe_id,
            location_id=uuid4(),
            location_type="forest",
            location_name="Dark Forest",
            faction_tensions=[tension],
            factions_at_location=[faction_a, faction_b],
        )

        result = await quest_service.generate_quest(context, quest_type=QuestType.HUNT)
        assert result.success
        assert result.quest.quest_type == QuestType.HUNT


# =============================================================================
# Template Filling Tests
# =============================================================================


class TestFactionTemplateFilling:
    """Tests for filling faction templates with substitutions."""

    @pytest.mark.asyncio
    async def test_faction_names_substituted(self, quest_service, universe_id):
        """Faction names appear in generated quest text."""
        faction_a = _make_faction(
            universe_id,
            "Iron Guild",
            controls_resources=["iron ore"],
            territory_description="the northern mines",
        )
        faction_b = _make_faction(
            universe_id,
            "Silver Order",
            controls_resources=["silver"],
        )

        tension = FactionTension(
            faction_a_name="Iron Guild",
            faction_b_name="Silver Order",
            faction_a_id=faction_a.id,
            faction_b_id=faction_b.id,
            relationship_type="TRADES_WITH",
        )

        context = QuestContext(
            universe_id=universe_id,
            location_id=uuid4(),
            location_type="market",
            location_name="Trade Square",
            faction_tensions=[tension],
            factions_at_location=[faction_a, faction_b],
        )

        # Force faction template selection
        random.seed(1)
        found = False
        for _ in range(20):
            result = await quest_service.generate_quest(context)
            assert result.success
            quest = result.quest
            text = f"{quest.name} {quest.description}"
            if "Iron Guild" in text or "Silver Order" in text:
                found = True
                break

        assert found, "Expected faction names in quest text"

    @pytest.mark.asyncio
    async def test_resource_substituted_from_faction_properties(self, quest_service, universe_id):
        """Resource from faction properties appears in quest text."""
        faction_a = _make_faction(
            universe_id,
            "Miners",
            controls_resources=["mythril"],
        )
        faction_b = _make_faction(universe_id, "Merchants")

        tension = FactionTension(
            faction_a_name="Miners",
            faction_b_name="Merchants",
            faction_a_id=faction_a.id,
            faction_b_id=faction_b.id,
            relationship_type="TRADES_WITH",
        )

        context = QuestContext(
            universe_id=universe_id,
            location_id=uuid4(),
            location_type="market",
            location_name="Market",
            faction_tensions=[tension],
            factions_at_location=[faction_a, faction_b],
        )

        random.seed(1)
        found_resource = False
        for _ in range(30):
            result = await quest_service.generate_quest(context)
            text = f"{result.quest.name} {result.quest.description}"
            for obj in result.quest.objectives:
                text += f" {obj.description}"
            if "mythril" in text:
                found_resource = True
                break

        assert found_resource, "Expected 'mythril' in quest text from faction resources"


# =============================================================================
# Reputation Rewards Tests
# =============================================================================


class TestFactionReputationRewards:
    """Tests for reputation_changes on faction quest rewards."""

    @pytest.mark.asyncio
    async def test_competitive_quest_has_reputation_changes(self, quest_service, universe_id):
        """COMPETES_WITH quests grant +rep for faction_a, -rep for faction_b."""
        faction_a = _make_faction(universe_id, "Hawks", controls_resources=["weapons"])
        faction_b = _make_faction(universe_id, "Doves", controls_resources=["medicine"])

        tension = FactionTension(
            faction_a_name="Hawks",
            faction_b_name="Doves",
            faction_a_id=faction_a.id,
            faction_b_id=faction_b.id,
            relationship_type="COMPETES_WITH",
        )

        context = QuestContext(
            universe_id=universe_id,
            location_id=uuid4(),
            faction_tensions=[tension],
            factions_at_location=[faction_a, faction_b],
        )

        random.seed(1)
        found = False
        for _ in range(30):
            result = await quest_service.generate_quest(context)
            if "faction" in result.quest.tags:
                rep = result.quest.rewards.reputation_changes
                assert faction_a.id in rep
                assert rep[faction_a.id] > 0
                assert faction_b.id in rep
                assert rep[faction_b.id] < 0
                found = True
                break

        assert found, "Expected a faction quest with reputation changes"

    @pytest.mark.asyncio
    async def test_cooperative_quest_no_negative_rep(self, quest_service, universe_id):
        """TRADES_WITH quests give +rep for faction_a only (no -rep)."""
        faction_a = _make_faction(universe_id, "Farmers", produces=["grain"])
        faction_b = _make_faction(universe_id, "Brewers", needs=["grain"])

        tension = FactionTension(
            faction_a_name="Farmers",
            faction_b_name="Brewers",
            faction_a_id=faction_a.id,
            faction_b_id=faction_b.id,
            relationship_type="TRADES_WITH",
        )

        context = QuestContext(
            universe_id=universe_id,
            location_id=uuid4(),
            faction_tensions=[tension],
            factions_at_location=[faction_a, faction_b],
        )

        random.seed(1)
        found = False
        for _ in range(30):
            result = await quest_service.generate_quest(context)
            if "faction" in result.quest.tags:
                rep = result.quest.rewards.reputation_changes
                assert faction_a.id in rep
                assert rep[faction_a.id] > 0
                # faction_b should not have negative rep for TRADES_WITH
                if faction_b.id in rep:
                    assert rep[faction_b.id] >= 0
                found = True
                break

        assert found, "Expected a faction quest with reputation changes"


# =============================================================================
# Backwards Compatibility Tests
# =============================================================================


class TestBackwardsCompatibility:
    """Tests that existing behavior is unchanged without factions."""

    @pytest.mark.asyncio
    async def test_no_factions_generates_normal_quest(self, quest_service, universe_id, dolt):
        """Without factions, quest generation works as before."""
        location = create_location(
            universe_id=universe_id,
            name="Old Tavern",
            location_type="tavern",
            danger_level=3,
        )
        dolt.save_entity(location)

        context = quest_service.build_quest_context(
            universe_id=universe_id,
            location_id=location.id,
        )

        assert context.faction_tensions == []
        assert context.controlling_faction is None

        result = await quest_service.generate_quest(context)
        assert result.success
        assert result.quest is not None
        assert "faction" not in result.quest.tags

    @pytest.mark.asyncio
    async def test_empty_factions_list_normal_behavior(self, quest_service, universe_id):
        """Explicitly empty faction list doesn't change behavior."""
        context = QuestContext(
            universe_id=universe_id,
            location_id=uuid4(),
            location_type="dungeon",
            location_name="Dark Cave",
            danger_level=10,
            faction_tensions=[],
            factions_at_location=[],
        )

        result = await quest_service.generate_quest(context)
        assert result.success
        assert "faction" not in result.quest.tags


# =============================================================================
# Build Quest Context with Factions Tests
# =============================================================================


class TestBuildQuestContextFactions:
    """Tests for build_quest_context faction gathering."""

    def test_build_context_finds_factions(self, quest_service, universe_id, dolt, neo4j):
        """build_quest_context discovers factions and tensions."""
        # Create location with controlling faction hint
        location = create_location(
            universe_id=universe_id,
            name="Guild Market",
            location_type="market",
            danger_level=3,
        )
        location.location_properties.controlling_faction_hint = "Iron Guild"
        dolt.save_entity(location)

        # Create factions
        faction_a = _make_faction(
            universe_id,
            "Iron Guild",
            controls_resources=["iron"],
            core_values=["strength"],
        )
        faction_b = _make_faction(
            universe_id,
            "Silver Order",
            controls_resources=["silver"],
            core_values=["wisdom"],
        )
        dolt.save_entity(faction_a)
        dolt.save_entity(faction_b)

        # Create faction relationship
        rel = Relationship(
            universe_id=universe_id,
            from_entity_id=faction_a.id,
            to_entity_id=faction_b.id,
            relationship_type=RelationshipType.TRADES_WITH,
            description="They trade iron for silver",
        )
        neo4j.create_relationship(rel)

        context = quest_service.build_quest_context(
            universe_id=universe_id,
            location_id=location.id,
        )

        assert context.controlling_faction is not None
        assert context.controlling_faction.name == "Iron Guild"
        assert len(context.factions_at_location) == 2
        assert len(context.faction_tensions) == 1
        assert context.faction_tensions[0].relationship_type == "TRADES_WITH"
        assert context.faction_tensions[0].faction_a_name == "Iron Guild"
        assert context.faction_tensions[0].faction_b_name == "Silver Order"

    def test_build_context_no_factions(self, quest_service, universe_id, dolt):
        """build_quest_context handles universes without factions."""
        location = create_location(
            universe_id=universe_id,
            name="Empty Field",
            location_type="forest",
        )
        dolt.save_entity(location)

        context = quest_service.build_quest_context(
            universe_id=universe_id,
            location_id=location.id,
        )

        assert context.faction_tensions == []
        assert context.factions_at_location == []
        assert context.controlling_faction is None

    def test_build_context_world_context_summary(self, quest_service, universe_id, dolt):
        """build_quest_context extracts world_context_summary from universe."""
        location = create_location(universe_id=universe_id, name="Somewhere")
        dolt.save_entity(location)

        universe = Universe(
            id=universe_id,
            name="Test Universe",
            world_context={"history": "A world torn by ancient wars"},
        )
        dolt.save_universe(universe)

        context = quest_service.build_quest_context(
            universe_id=universe_id,
            location_id=location.id,
        )

        assert context.world_context_summary == "A world torn by ancient wars"

    def test_build_context_multiple_tensions(self, quest_service, universe_id, dolt, neo4j):
        """build_quest_context finds multiple tensions between factions."""
        location = create_location(universe_id=universe_id, name="Crossroads")
        dolt.save_entity(location)

        faction_a = _make_faction(universe_id, "Alpha")
        faction_b = _make_faction(universe_id, "Beta")
        faction_c = _make_faction(universe_id, "Gamma")
        dolt.save_entity(faction_a)
        dolt.save_entity(faction_b)
        dolt.save_entity(faction_c)

        # A competes with B
        neo4j.create_relationship(
            Relationship(
                universe_id=universe_id,
                from_entity_id=faction_a.id,
                to_entity_id=faction_b.id,
                relationship_type=RelationshipType.COMPETES_WITH,
            )
        )
        # B trades with C
        neo4j.create_relationship(
            Relationship(
                universe_id=universe_id,
                from_entity_id=faction_b.id,
                to_entity_id=faction_c.id,
                relationship_type=RelationshipType.TRADES_WITH,
            )
        )

        context = quest_service.build_quest_context(
            universe_id=universe_id,
            location_id=location.id,
        )

        assert len(context.faction_tensions) == 2
        rel_types = {t.relationship_type for t in context.faction_tensions}
        assert "COMPETES_WITH" in rel_types
        assert "TRADES_WITH" in rel_types


# =============================================================================
# Full Pipeline Test
# =============================================================================


class TestFactionQuestPipeline:
    """End-to-end tests for faction quest generation."""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_factions(self, quest_service, universe_id, dolt, neo4j):
        """Full pipeline: create universe data -> build context -> generate quest."""
        # Create location
        location = create_location(
            universe_id=universe_id,
            name="Border Town",
            location_type="tavern",
            danger_level=5,
        )
        location.location_properties.controlling_faction_hint = "Merchants Guild"
        dolt.save_entity(location)

        # Create factions
        faction_a = _make_faction(
            universe_id,
            "Merchants Guild",
            controls_resources=["spices", "silk"],
            territory_description="the trade quarter",
            core_values=["profit", "order"],
        )
        faction_b = _make_faction(
            universe_id,
            "Thieves Ring",
            controls_resources=["stolen goods"],
            territory_description="the undercity",
            core_values=["freedom", "cunning"],
        )
        dolt.save_entity(faction_a)
        dolt.save_entity(faction_b)

        # Create NPC at location (member of faction_a)
        npc = create_character(
            universe_id=universe_id,
            name="Merchant Kara",
        )
        dolt.save_entity(npc)

        # NPC is at location
        neo4j.create_relationship(
            Relationship(
                universe_id=universe_id,
                from_entity_id=npc.id,
                to_entity_id=location.id,
                relationship_type=RelationshipType.LOCATED_IN,
            )
        )
        # NPC is member of faction_a
        neo4j.create_relationship(
            Relationship(
                universe_id=universe_id,
                from_entity_id=npc.id,
                to_entity_id=faction_a.id,
                relationship_type=RelationshipType.MEMBER_OF,
            )
        )
        # Faction relationship
        neo4j.create_relationship(
            Relationship(
                universe_id=universe_id,
                from_entity_id=faction_a.id,
                to_entity_id=faction_b.id,
                relationship_type=RelationshipType.COMPETES_WITH,
                description="The guild tries to stamp out theft",
            )
        )

        # Build context
        context = quest_service.build_quest_context(
            universe_id=universe_id,
            location_id=location.id,
        )

        assert context.controlling_faction is not None
        assert context.controlling_faction.name == "Merchants Guild"
        assert len(context.faction_tensions) == 1

        # Generate quests repeatedly to get a faction quest
        random.seed(7)
        found_faction = False
        for _ in range(30):
            result = await quest_service.generate_quest(context)
            assert result.success
            if "faction" in result.quest.tags:
                found_faction = True
                quest = result.quest
                assert quest.rewards.reputation_changes
                assert quest.rewards.gold > 0
                break

        assert found_faction, "Expected at least one faction quest"


# =============================================================================
# LLM Enhancement with Faction Context Test
# =============================================================================


class TestFactionLLMEnhancement:
    """Tests for LLM enhancement with faction context."""

    @pytest.mark.asyncio
    async def test_llm_prompt_includes_faction_context(self, dolt, neo4j, universe_id):
        """LLM enhancer receives faction context in prompt."""
        mock_llm = MagicMock()
        mock_llm.is_available = True
        mock_provider = AsyncMock()
        mock_provider.complete = AsyncMock(
            return_value="An enhanced description with rich faction narrative."
        )
        mock_llm.provider = mock_provider

        service = QuestService(dolt=dolt, neo4j=neo4j, llm=mock_llm)

        faction_a = _make_faction(
            universe_id,
            "Sun Court",
            core_values=["honor", "duty"],
            controls_resources=["gold"],
        )
        faction_b = _make_faction(
            universe_id,
            "Moon Circle",
            core_values=["mystery", "magic"],
        )

        tension = FactionTension(
            faction_a_name="Sun Court",
            faction_b_name="Moon Circle",
            faction_a_id=faction_a.id,
            faction_b_id=faction_b.id,
            relationship_type="INFLUENCES",
        )

        context = QuestContext(
            universe_id=universe_id,
            location_id=uuid4(),
            location_type="market",
            location_name="Central Plaza",
            faction_tensions=[tension],
            factions_at_location=[faction_a, faction_b],
            world_context_summary="A realm of eternal twilight",
        )

        # Force faction template
        random.seed(0)
        found = False
        for _ in range(20):
            result = await service.generate_quest(context)
            if result.success and "faction" in result.quest.tags:
                found = True
                # Check the LLM was called with faction context
                call_args = mock_provider.complete.call_args
                messages = (
                    call_args.kwargs.get("messages")
                    or call_args[1].get("messages")
                    or call_args[0][0]
                )
                user_msg = next(m for m in messages if m["role"] == "user")
                assert "Sun Court" in user_msg["content"]
                assert "Moon Circle" in user_msg["content"]
                assert "INFLUENCES" in user_msg["content"]
                assert "eternal twilight" in user_msg["content"]
                break

        assert found, "Expected a faction quest with LLM enhancement"
