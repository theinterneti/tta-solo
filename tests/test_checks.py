"""Tests for saving throws and skill checks."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.skills.checks import (
    SKILL_ABILITIES,
    CheckResult,
    SaveResult,
    SkillProficiencies,
    ability_check,
    get_ability_score,
    make_saving_throw,
    skill_check,
)
from src.skills.combat import Abilities, Combatant
from src.skills.dice import DiceResult

# --- Fixtures ---


@pytest.fixture
def fighter() -> Combatant:
    """A typical fighter with varied abilities."""
    return Combatant(
        name="Fighter",
        ac=16,
        abilities=Abilities(str=16, dex=12, con=14, int=10, wis=10, cha=8),
        proficiency_bonus=2,
    )


@pytest.fixture
def rogue() -> Combatant:
    """A typical rogue with high DEX."""
    return Combatant(
        name="Rogue",
        ac=14,
        abilities=Abilities(str=10, dex=18, con=12, int=14, wis=12, cha=14),
        proficiency_bonus=3,
    )


# --- Unit Tests ---


class TestGetAbilityScore:
    """Tests for ability score lookup."""

    def test_get_str(self):
        abilities = Abilities(str=16, dex=12, con=14, int=10, wis=10, cha=8)
        assert get_ability_score(abilities, "str") == 16

    def test_get_dex(self):
        abilities = Abilities(str=10, dex=18)
        assert get_ability_score(abilities, "dex") == 18

    def test_get_con(self):
        abilities = Abilities(con=14)
        assert get_ability_score(abilities, "con") == 14

    def test_get_int(self):
        abilities = Abilities(int=12)
        assert get_ability_score(abilities, "int") == 12

    def test_get_wis(self):
        abilities = Abilities(wis=16)
        assert get_ability_score(abilities, "wis") == 16

    def test_get_cha(self):
        abilities = Abilities(cha=14)
        assert get_ability_score(abilities, "cha") == 14

    def test_invalid_ability_raises(self):
        abilities = Abilities()
        with pytest.raises(ValueError, match="Unknown ability"):
            get_ability_score(abilities, "luck")


class TestMakeSavingThrow:
    """Tests for saving throw resolution."""

    def test_returns_save_result(self, fighter: Combatant):
        result = make_saving_throw(fighter, "str", dc=15)
        assert isinstance(result, SaveResult)

    def test_success_when_total_meets_dc(self, fighter: Combatant):
        """Meeting DC exactly is a success."""
        # DC 15, STR mod +3, need to roll 12
        mock_result = DiceResult(notation="1d20", rolls=[12], total=12)
        with patch("src.skills.checks.roll_dice", return_value=mock_result):
            result = make_saving_throw(fighter, "str", dc=15)

        assert result.success is True
        assert result.total == 15  # 12 + 3
        assert result.margin == 0

    def test_success_when_total_exceeds_dc(self, fighter: Combatant):
        mock_result = DiceResult(notation="1d20", rolls=[15], total=15)
        with patch("src.skills.checks.roll_dice", return_value=mock_result):
            result = make_saving_throw(fighter, "str", dc=15)

        assert result.success is True
        assert result.total == 18  # 15 + 3
        assert result.margin == 3

    def test_failure_when_total_below_dc(self, fighter: Combatant):
        mock_result = DiceResult(notation="1d20", rolls=[5], total=5)
        with patch("src.skills.checks.roll_dice", return_value=mock_result):
            result = make_saving_throw(fighter, "str", dc=15)

        assert result.success is False
        assert result.total == 8  # 5 + 3
        assert result.margin == -7

    def test_proficiency_adds_bonus(self, fighter: Combatant):
        """Proficiency in save adds proficiency bonus."""
        mock_result = DiceResult(notation="1d20", rolls=[10], total=10)
        with patch("src.skills.checks.roll_dice", return_value=mock_result):
            result = make_saving_throw(fighter, "str", dc=15, proficient=True)

        # 10 + 3 (STR) + 2 (prof) = 15
        assert result.total == 15
        assert result.success is True

    def test_uses_correct_ability_modifier(self, fighter: Combatant):
        """Each ability uses its own modifier."""
        mock_result = DiceResult(notation="1d20", rolls=[10], total=10)

        with patch("src.skills.checks.roll_dice", return_value=mock_result):
            # STR 16 = +3
            str_save = make_saving_throw(fighter, "str", dc=15)
            assert str_save.total == 13

        with patch("src.skills.checks.roll_dice", return_value=mock_result):
            # DEX 12 = +1
            dex_save = make_saving_throw(fighter, "dex", dc=15)
            assert dex_save.total == 11

        with patch("src.skills.checks.roll_dice", return_value=mock_result):
            # CHA 8 = -1
            cha_save = make_saving_throw(fighter, "cha", dc=15)
            assert cha_save.total == 9

    def test_advantage_rolls_2d20kh1(self, fighter: Combatant):
        mock_result = DiceResult(notation="2d20kh1", rolls=[5, 15], kept=[15], total=15)
        with patch("src.skills.checks.roll_dice", return_value=mock_result) as mock:
            make_saving_throw(fighter, "dex", dc=15, advantage=True)

        mock.assert_called_with("2d20kh1")

    def test_disadvantage_rolls_2d20kl1(self, fighter: Combatant):
        mock_result = DiceResult(notation="2d20kl1", rolls=[5, 15], kept=[5], total=5)
        with patch("src.skills.checks.roll_dice", return_value=mock_result) as mock:
            make_saving_throw(fighter, "dex", dc=15, disadvantage=True)

        mock.assert_called_with("2d20kl1")

    def test_advantage_and_disadvantage_cancel(self, fighter: Combatant):
        mock_result = DiceResult(notation="1d20", rolls=[10], total=10)
        with patch("src.skills.checks.roll_dice", return_value=mock_result) as mock:
            make_saving_throw(fighter, "dex", dc=15, advantage=True, disadvantage=True)

        mock.assert_called_with("1d20")


class TestSkillCheck:
    """Tests for skill check resolution."""

    def test_returns_check_result(self, rogue: Combatant):
        result = skill_check(rogue, "stealth", dc=15)
        assert isinstance(result, CheckResult)

    def test_uses_correct_ability_for_skill(self, rogue: Combatant):
        """Skills use their mapped ability."""
        mock_result = DiceResult(notation="1d20", rolls=[10], total=10)

        with patch("src.skills.checks.roll_dice", return_value=mock_result):
            # Stealth uses DEX (18 = +4)
            stealth = skill_check(rogue, "stealth", dc=15)
            assert stealth.total == 14
            assert stealth.ability == "dex"

        with patch("src.skills.checks.roll_dice", return_value=mock_result):
            # Investigation uses INT (14 = +2)
            investigation = skill_check(rogue, "investigation", dc=15)
            assert investigation.total == 12
            assert investigation.ability == "int"

        with patch("src.skills.checks.roll_dice", return_value=mock_result):
            # Persuasion uses CHA (14 = +2)
            persuasion = skill_check(rogue, "persuasion", dc=15)
            assert persuasion.total == 12
            assert persuasion.ability == "cha"

    def test_proficiency_adds_bonus(self, rogue: Combatant):
        """Proficiency in skill adds proficiency bonus."""
        mock_result = DiceResult(notation="1d20", rolls=[10], total=10)
        profs = SkillProficiencies(proficient=["stealth"])

        with patch("src.skills.checks.roll_dice", return_value=mock_result):
            result = skill_check(rogue, "stealth", dc=15, skill_proficiencies=profs)

        # 10 + 4 (DEX) + 3 (prof) = 17
        assert result.total == 17
        assert result.success is True

    def test_expertise_doubles_proficiency(self, rogue: Combatant):
        """Expertise adds double proficiency bonus."""
        mock_result = DiceResult(notation="1d20", rolls=[10], total=10)
        profs = SkillProficiencies(expertise=["stealth"])

        with patch("src.skills.checks.roll_dice", return_value=mock_result):
            result = skill_check(rogue, "stealth", dc=15, skill_proficiencies=profs)

        # 10 + 4 (DEX) + 6 (expertise = 2x prof) = 20
        assert result.total == 20

    def test_expertise_overrides_proficiency(self, rogue: Combatant):
        """If skill is in both, expertise takes precedence."""
        mock_result = DiceResult(notation="1d20", rolls=[10], total=10)
        profs = SkillProficiencies(proficient=["stealth"], expertise=["stealth"])

        with patch("src.skills.checks.roll_dice", return_value=mock_result):
            result = skill_check(rogue, "stealth", dc=15, skill_proficiencies=profs)

        # Should use expertise (double), not proficiency
        assert result.total == 20

    def test_unknown_skill_raises(self, rogue: Combatant):
        with pytest.raises(ValueError, match="Unknown skill"):
            skill_check(rogue, "hacking", dc=15)

    def test_skill_name_case_insensitive(self, rogue: Combatant):
        """Skill names should be case insensitive."""
        mock_result = DiceResult(notation="1d20", rolls=[10], total=10)

        with patch("src.skills.checks.roll_dice", return_value=mock_result):
            result1 = skill_check(rogue, "Stealth", dc=15)
            assert result1.skill == "stealth"

        with patch("src.skills.checks.roll_dice", return_value=mock_result):
            result2 = skill_check(rogue, "PERCEPTION", dc=15)
            assert result2.skill == "perception"

    def test_skill_name_with_spaces(self, rogue: Combatant):
        """Skills with spaces should work."""
        mock_result = DiceResult(notation="1d20", rolls=[10], total=10)

        with patch("src.skills.checks.roll_dice", return_value=mock_result):
            result = skill_check(rogue, "sleight of hand", dc=15)
            assert result.skill == "sleight_of_hand"
            assert result.ability == "dex"

    def test_margin_calculation(self, rogue: Combatant):
        """Margin should be total - DC."""
        mock_result = DiceResult(notation="1d20", rolls=[10], total=10)

        with patch("src.skills.checks.roll_dice", return_value=mock_result):
            result = skill_check(rogue, "stealth", dc=12)

        # Total 14, DC 12, margin = 2
        assert result.margin == 2
        assert result.success is True

    def test_advantage_and_disadvantage(self, rogue: Combatant):
        """Advantage and disadvantage work for skill checks."""
        mock_adv = DiceResult(notation="2d20kh1", rolls=[5, 18], kept=[18], total=18)
        with patch("src.skills.checks.roll_dice", return_value=mock_adv) as mock:
            skill_check(rogue, "stealth", dc=15, advantage=True)
        mock.assert_called_with("2d20kh1")

        mock_dis = DiceResult(notation="2d20kl1", rolls=[5, 18], kept=[5], total=5)
        with patch("src.skills.checks.roll_dice", return_value=mock_dis) as mock:
            skill_check(rogue, "stealth", dc=15, disadvantage=True)
        mock.assert_called_with("2d20kl1")


class TestAbilityCheck:
    """Tests for raw ability checks."""

    def test_returns_check_result(self, fighter: Combatant):
        result = ability_check(fighter, "str", dc=15)
        assert isinstance(result, CheckResult)
        assert result.skill is None  # No skill for raw ability check

    def test_uses_correct_modifier(self, fighter: Combatant):
        mock_result = DiceResult(notation="1d20", rolls=[10], total=10)

        with patch("src.skills.checks.roll_dice", return_value=mock_result):
            result = ability_check(fighter, "str", dc=15)

        # STR 16 = +3, so total = 13
        assert result.total == 13
        assert result.ability == "str"

    def test_no_proficiency_on_ability_checks(self, fighter: Combatant):
        """Raw ability checks don't include proficiency."""
        mock_result = DiceResult(notation="1d20", rolls=[10], total=10)

        with patch("src.skills.checks.roll_dice", return_value=mock_result):
            result = ability_check(fighter, "str", dc=15)

        # Just 10 + 3 (mod), no proficiency
        assert result.total == 13


class TestSkillAbilitiesMapping:
    """Tests for the SKILL_ABILITIES constant."""

    def test_all_skills_have_valid_abilities(self):
        valid_abilities = {"str", "dex", "con", "int", "wis", "cha"}
        for skill, ability in SKILL_ABILITIES.items():
            assert ability in valid_abilities, f"{skill} has invalid ability {ability}"

    def test_expected_skills_present(self):
        expected = [
            "athletics",
            "acrobatics",
            "stealth",
            "arcana",
            "perception",
            "persuasion",
            "intimidation",
        ]
        for skill in expected:
            assert skill in SKILL_ABILITIES
