"""
Tests for archetype models.
"""

from __future__ import annotations

from src.models.archetype import (
    ARCHETYPE_HP_BONUS,
    ASSASSIN_FOCUS,
    BULWARK_FOCUS,
    EVOKER_FOCUS,
    FOCUSES_BY_ARCHETYPE,
    PARADIGM_BONUSES,
    TACTICIAN_FOCUS,
    Archetype,
    CharacterClass,
    Focus,
    FocusBonus,
    Paradigm,
    calculate_hp_bonus,
    generate_class,
    get_focus_by_name,
    get_focuses_for_archetype,
    get_paradigm_bonuses,
)


class TestArchetypeEnum:
    """Tests for the Archetype enum."""

    def test_all_archetypes_exist(self):
        """Test all expected archetypes exist."""
        assert Archetype.GUARDIAN == "guardian"
        assert Archetype.STRIKER == "striker"
        assert Archetype.CONTROLLER == "controller"
        assert Archetype.LEADER == "leader"
        assert Archetype.SPECIALIST == "specialist"

    def test_archetype_count(self):
        """Test there are exactly 5 archetypes."""
        assert len(Archetype) == 5


class TestParadigmEnum:
    """Tests for the Paradigm enum."""

    def test_all_paradigms_exist(self):
        """Test all expected paradigms exist."""
        assert Paradigm.ARCANE == "arcane"
        assert Paradigm.DIVINE == "divine"
        assert Paradigm.PRIMAL == "primal"
        assert Paradigm.PSIONIC == "psionic"
        assert Paradigm.MARTIAL == "martial"
        assert Paradigm.TECH == "tech"
        assert Paradigm.HYBRID == "hybrid"

    def test_paradigm_count(self):
        """Test there are exactly 7 paradigms."""
        assert len(Paradigm) == 7


class TestFocusBonus:
    """Tests for FocusBonus model."""

    def test_focus_bonus_creation(self):
        """Test creating a focus bonus."""
        bonus = FocusBonus(
            name="Test Bonus",
            description="A test bonus",
            stat="attack",
            value=2,
        )
        assert bonus.name == "Test Bonus"
        assert bonus.description == "A test bonus"
        assert bonus.stat == "attack"
        assert bonus.value == 2

    def test_focus_bonus_with_dice(self):
        """Test focus bonus with dice."""
        bonus = FocusBonus(
            name="Extra Damage",
            description="Deal extra damage",
            dice="2d6",
            condition="from_stealth",
        )
        assert bonus.dice == "2d6"
        assert bonus.condition == "from_stealth"

    def test_focus_bonus_defaults(self):
        """Test focus bonus default values."""
        bonus = FocusBonus(name="Simple", description="Simple bonus")
        assert bonus.stat is None
        assert bonus.value is None
        assert bonus.dice is None
        assert bonus.condition is None


class TestFocus:
    """Tests for Focus model."""

    def test_focus_creation(self):
        """Test creating a focus."""
        focus = Focus(
            name="Test Focus",
            description="A test focus",
            archetype=Archetype.STRIKER,
            bonuses=[
                FocusBonus(name="Bonus 1", description="First bonus"),
            ],
        )
        assert focus.name == "Test Focus"
        assert focus.archetype == Archetype.STRIKER
        assert len(focus.bonuses) == 1

    def test_pre_built_focuses_have_bonuses(self):
        """Test pre-built focuses have bonuses."""
        assert len(BULWARK_FOCUS.bonuses) >= 1
        assert len(ASSASSIN_FOCUS.bonuses) >= 1
        assert len(EVOKER_FOCUS.bonuses) >= 1
        assert len(TACTICIAN_FOCUS.bonuses) >= 1


class TestCharacterClass:
    """Tests for CharacterClass model."""

    def test_character_class_creation(self):
        """Test creating a character class."""
        char_class = CharacterClass(
            archetype=Archetype.GUARDIAN,
            paradigm=Paradigm.MARTIAL,
            level=5,
        )
        assert char_class.archetype == Archetype.GUARDIAN
        assert char_class.paradigm == Paradigm.MARTIAL
        assert char_class.level == 5
        assert char_class.focus is None

    def test_character_class_with_focus(self):
        """Test character class with focus."""
        char_class = CharacterClass(
            archetype=Archetype.STRIKER,
            paradigm=Paradigm.ARCANE,
            focus=EVOKER_FOCUS,
            level=3,
        )
        assert char_class.focus is not None
        assert char_class.focus.name == "Evoker"

    def test_character_class_defaults(self):
        """Test character class defaults."""
        char_class = CharacterClass(
            archetype=Archetype.LEADER,
            paradigm=Paradigm.DIVINE,
        )
        assert char_class.level == 1
        assert char_class.hp_bonus == 0
        assert char_class.starting_ability_ids == []


class TestFocusByArchetype:
    """Tests for FOCUSES_BY_ARCHETYPE registry."""

    def test_all_archetypes_have_focuses(self):
        """Test all archetypes have at least one focus."""
        for archetype in Archetype:
            focuses = FOCUSES_BY_ARCHETYPE.get(archetype, [])
            assert len(focuses) >= 1, f"{archetype} has no focuses"

    def test_guardian_focuses(self):
        """Test Guardian focuses."""
        focuses = FOCUSES_BY_ARCHETYPE[Archetype.GUARDIAN]
        focus_names = [f.name for f in focuses]
        assert "Bulwark" in focus_names
        assert "Sentinel" in focus_names
        assert "Warden" in focus_names

    def test_striker_focuses(self):
        """Test Striker focuses."""
        focuses = FOCUSES_BY_ARCHETYPE[Archetype.STRIKER]
        focus_names = [f.name for f in focuses]
        assert "Assassin" in focus_names
        assert "Duelist" in focus_names
        assert "Skirmisher" in focus_names

    def test_controller_focuses(self):
        """Test Controller focuses."""
        focuses = FOCUSES_BY_ARCHETYPE[Archetype.CONTROLLER]
        focus_names = [f.name for f in focuses]
        assert "Enchanter" in focus_names
        assert "Evoker" in focus_names
        assert "Transmuter" in focus_names

    def test_leader_focuses(self):
        """Test Leader focuses."""
        focuses = FOCUSES_BY_ARCHETYPE[Archetype.LEADER]
        focus_names = [f.name for f in focuses]
        assert "Battle Priest" in focus_names
        assert "Tactician" in focus_names
        assert "Inspiring" in focus_names

    def test_specialist_focuses(self):
        """Test Specialist focuses."""
        focuses = FOCUSES_BY_ARCHETYPE[Archetype.SPECIALIST]
        focus_names = [f.name for f in focuses]
        assert "Scout" in focus_names
        assert "Face" in focus_names
        assert "Artificer" in focus_names


class TestGetFocusesForArchetype:
    """Tests for get_focuses_for_archetype function."""

    def test_get_guardian_focuses(self):
        """Test getting Guardian focuses."""
        focuses = get_focuses_for_archetype(Archetype.GUARDIAN)
        assert len(focuses) == 3
        assert all(f.archetype == Archetype.GUARDIAN for f in focuses)

    def test_get_striker_focuses(self):
        """Test getting Striker focuses."""
        focuses = get_focuses_for_archetype(Archetype.STRIKER)
        assert len(focuses) == 3
        assert all(f.archetype == Archetype.STRIKER for f in focuses)


class TestGetFocusByName:
    """Tests for get_focus_by_name function."""

    def test_get_bulwark(self):
        """Test getting Bulwark focus."""
        focus = get_focus_by_name("Bulwark")
        assert focus is not None
        assert focus.name == "Bulwark"
        assert focus.archetype == Archetype.GUARDIAN

    def test_get_assassin_case_insensitive(self):
        """Test case-insensitive lookup."""
        focus = get_focus_by_name("ASSASSIN")
        assert focus is not None
        assert focus.name == "Assassin"

    def test_get_nonexistent_focus(self):
        """Test getting nonexistent focus returns None."""
        focus = get_focus_by_name("Nonexistent")
        assert focus is None


class TestArchetypeHpBonus:
    """Tests for ARCHETYPE_HP_BONUS."""

    def test_guardian_has_highest_hp(self):
        """Test Guardian has highest HP bonus."""
        assert ARCHETYPE_HP_BONUS[Archetype.GUARDIAN] == 2

    def test_controller_has_lowest_hp(self):
        """Test Controller has lowest HP bonus (glass cannon)."""
        assert ARCHETYPE_HP_BONUS[Archetype.CONTROLLER] == -1

    def test_leader_has_moderate_hp(self):
        """Test Leader has moderate HP bonus."""
        assert ARCHETYPE_HP_BONUS[Archetype.LEADER] == 1


class TestCalculateHpBonus:
    """Tests for calculate_hp_bonus function."""

    def test_guardian_level_5(self):
        """Test Guardian at level 5."""
        bonus = calculate_hp_bonus(Archetype.GUARDIAN, 5)
        assert bonus == 10  # 2 * 5

    def test_controller_level_3(self):
        """Test Controller at level 3."""
        bonus = calculate_hp_bonus(Archetype.CONTROLLER, 3)
        assert bonus == -3  # -1 * 3

    def test_striker_level_1(self):
        """Test Striker at level 1."""
        bonus = calculate_hp_bonus(Archetype.STRIKER, 1)
        assert bonus == 0  # 0 * 1


class TestParadigmBonuses:
    """Tests for PARADIGM_BONUSES."""

    def test_arcane_bonuses(self):
        """Test Arcane paradigm bonuses."""
        bonuses = PARADIGM_BONUSES[Paradigm.ARCANE]
        assert "spell_slots" in bonuses
        assert "metamagic_uses" in bonuses

    def test_martial_bonuses(self):
        """Test Martial paradigm bonuses."""
        bonuses = PARADIGM_BONUSES[Paradigm.MARTIAL]
        assert "extra_attacks" in bonuses
        assert "maneuver_dice" in bonuses

    def test_tech_bonuses(self):
        """Test Tech paradigm bonuses."""
        bonuses = PARADIGM_BONUSES[Paradigm.TECH]
        assert "gadget_slots" in bonuses
        assert "overclock_uses" in bonuses


class TestGetParadigmBonuses:
    """Tests for get_paradigm_bonuses function."""

    def test_get_divine_bonuses(self):
        """Test getting Divine paradigm bonuses."""
        bonuses = get_paradigm_bonuses(Paradigm.DIVINE)
        assert "channel_divinity" in bonuses
        assert "healing_bonus" in bonuses

    def test_get_hybrid_returns_empty(self):
        """Test Hybrid paradigm returns empty dict."""
        bonuses = get_paradigm_bonuses(Paradigm.HYBRID)
        assert bonuses == {}


class TestGenerateClass:
    """Tests for generate_class function."""

    def test_generate_specific_class(self):
        """Test generating a specific class."""
        char_class = generate_class(
            archetype=Archetype.GUARDIAN,
            paradigm=Paradigm.MARTIAL,
            focus_name="Bulwark",
            level=5,
        )
        assert char_class.archetype == Archetype.GUARDIAN
        assert char_class.paradigm == Paradigm.MARTIAL
        assert char_class.focus is not None
        assert char_class.focus.name == "Bulwark"
        assert char_class.level == 5
        assert char_class.hp_bonus == 10  # 2 * 5

    def test_generate_random_archetype(self):
        """Test generating with random archetype."""
        char_class = generate_class(paradigm=Paradigm.ARCANE)
        assert char_class.paradigm == Paradigm.ARCANE
        assert char_class.archetype in Archetype

    def test_generate_random_paradigm(self):
        """Test generating with random paradigm."""
        char_class = generate_class(archetype=Archetype.STRIKER)
        assert char_class.archetype == Archetype.STRIKER
        assert char_class.paradigm in Paradigm

    def test_generate_fully_random(self):
        """Test generating fully random class."""
        char_class = generate_class()
        assert char_class.archetype in Archetype
        assert char_class.paradigm in Paradigm
        assert char_class.level == 1

    def test_mismatched_focus_ignored(self):
        """Test that mismatched focus is ignored."""
        # Evoker is a Controller focus, not Guardian
        char_class = generate_class(
            archetype=Archetype.GUARDIAN,
            paradigm=Paradigm.ARCANE,
            focus_name="Evoker",
        )
        assert char_class.archetype == Archetype.GUARDIAN
        # Focus should be None or a different focus since Evoker doesn't match Guardian
        if char_class.focus is not None:
            assert char_class.focus.archetype == Archetype.GUARDIAN


class TestExampleBuilds:
    """Tests for example character builds from the spec."""

    def test_battle_mage(self):
        """Test Battle Mage build."""
        # Archetype: Striker, Paradigm: Arcane, Focus: Evoker
        char_class = generate_class(
            archetype=Archetype.STRIKER,
            paradigm=Paradigm.ARCANE,
            focus_name="Evoker",
        )
        # Note: Evoker is Controller focus, so it won't match
        assert char_class.archetype == Archetype.STRIKER
        assert char_class.paradigm == Paradigm.ARCANE

    def test_tech_knight(self):
        """Test Tech Knight build."""
        char_class = generate_class(
            archetype=Archetype.GUARDIAN,
            paradigm=Paradigm.TECH,
            focus_name="Sentinel",
            level=5,
        )
        assert char_class.archetype == Archetype.GUARDIAN
        assert char_class.paradigm == Paradigm.TECH
        assert char_class.focus is not None
        assert char_class.focus.name == "Sentinel"

    def test_mind_blade(self):
        """Test Mind Blade build."""
        char_class = generate_class(
            archetype=Archetype.STRIKER,
            paradigm=Paradigm.PSIONIC,
            focus_name="Duelist",
        )
        assert char_class.archetype == Archetype.STRIKER
        assert char_class.paradigm == Paradigm.PSIONIC
        assert char_class.focus is not None
        assert char_class.focus.name == "Duelist"

    def test_combat_medic(self):
        """Test Combat Medic build."""
        char_class = generate_class(
            archetype=Archetype.LEADER,
            paradigm=Paradigm.TECH,
            focus_name="Battle Priest",  # Re-flavored
        )
        assert char_class.archetype == Archetype.LEADER
        assert char_class.paradigm == Paradigm.TECH
        assert char_class.focus is not None
        assert char_class.focus.name == "Battle Priest"
