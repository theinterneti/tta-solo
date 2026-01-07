"""Tests for combat resolution skills."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.skills.combat import (
    Abilities,
    AttackResult,
    Combatant,
    CoverType,
    Weapon,
    WeaponProperty,
    get_ability_modifier,
    get_attack_ability,
    get_cover_bonus,
    resolve_attack,
)
from src.skills.dice import DiceResult

# --- Fixtures ---


@pytest.fixture
def fighter() -> Combatant:
    """A typical fighter with 16 STR."""
    return Combatant(
        name="Fighter",
        ac=16,
        abilities=Abilities(str=16, dex=12, con=14, int=10, wis=10, cha=10),
        proficiency_bonus=2,
        proficient_weapons=["longsword", "shortbow"],
    )


@pytest.fixture
def goblin() -> Combatant:
    """A typical goblin target."""
    return Combatant(
        name="Goblin",
        ac=12,
        abilities=Abilities(str=8, dex=14, con=10, int=10, wis=8, cha=8),
        proficiency_bonus=2,
        proficient_weapons=["scimitar"],
    )


@pytest.fixture
def longsword() -> Weapon:
    """Standard longsword."""
    return Weapon(
        name="Longsword",
        damage_dice="1d8",
        damage_type="slashing",
        properties=[WeaponProperty.VERSATILE],
    )


@pytest.fixture
def rapier() -> Weapon:
    """Finesse weapon."""
    return Weapon(
        name="Rapier",
        damage_dice="1d8",
        damage_type="piercing",
        properties=[WeaponProperty.FINESSE],
    )


@pytest.fixture
def shortbow() -> Weapon:
    """Ranged weapon."""
    return Weapon(
        name="Shortbow",
        damage_dice="1d6",
        damage_type="piercing",
        properties=[WeaponProperty.RANGED],
    )


# --- Unit Tests ---


class TestAbilityModifier:
    """Tests for ability modifier calculation."""

    def test_modifier_10_is_zero(self):
        assert get_ability_modifier(10) == 0

    def test_modifier_11_is_zero(self):
        assert get_ability_modifier(11) == 0

    def test_modifier_16_is_plus_3(self):
        assert get_ability_modifier(16) == 3

    def test_modifier_8_is_minus_1(self):
        assert get_ability_modifier(8) == -1

    def test_modifier_20_is_plus_5(self):
        assert get_ability_modifier(20) == 5

    def test_modifier_1_is_minus_5(self):
        assert get_ability_modifier(1) == -5


class TestCoverBonus:
    """Tests for cover AC bonus."""

    def test_no_cover(self):
        assert get_cover_bonus(CoverType.NONE) == 0

    def test_half_cover(self):
        assert get_cover_bonus(CoverType.HALF) == 2

    def test_three_quarters_cover(self):
        assert get_cover_bonus(CoverType.THREE_QUARTERS) == 5

    def test_total_cover(self):
        # Should be effectively infinite
        assert get_cover_bonus(CoverType.TOTAL) >= 50


class TestAttackAbility:
    """Tests for determining attack ability."""

    def test_melee_uses_str(self, fighter: Combatant, longsword: Weapon):
        assert get_attack_ability(longsword, fighter) == "str"

    def test_ranged_uses_dex(self, fighter: Combatant, shortbow: Weapon):
        assert get_attack_ability(shortbow, fighter) == "dex"

    def test_finesse_uses_higher(self, rapier: Weapon):
        # Fighter with higher STR
        strong = Combatant(
            name="Strong",
            abilities=Abilities(str=16, dex=12),
        )
        assert get_attack_ability(rapier, strong) == "str"

        # Rogue with higher DEX
        agile = Combatant(
            name="Agile",
            abilities=Abilities(str=10, dex=16),
        )
        assert get_attack_ability(rapier, agile) == "dex"


class TestResolveAttack:
    """Tests for the resolve_attack function."""

    def test_returns_attack_result(self, fighter: Combatant, goblin: Combatant, longsword: Weapon):
        result = resolve_attack(fighter, goblin, longsword)
        assert isinstance(result, AttackResult)

    def test_natural_20_always_crits(
        self, fighter: Combatant, goblin: Combatant, longsword: Weapon
    ):
        """Natural 20 should always hit and be critical."""
        mock_result = DiceResult(notation="1d20", rolls=[20], total=20)
        with patch("src.skills.combat.roll_dice", return_value=mock_result):
            result = resolve_attack(fighter, goblin, longsword)

        assert result.hit is True
        assert result.critical is True
        assert result.fumble is False
        assert result.attack_roll == 20

    def test_natural_1_always_fumbles(
        self, fighter: Combatant, goblin: Combatant, longsword: Weapon
    ):
        """Natural 1 should always miss."""
        mock_result = DiceResult(notation="1d20", rolls=[1], total=1)
        with patch("src.skills.combat.roll_dice", return_value=mock_result):
            result = resolve_attack(fighter, goblin, longsword)

        assert result.hit is False
        assert result.fumble is True
        assert result.critical is False
        assert result.damage is None

    def test_hit_when_total_meets_ac(
        self, fighter: Combatant, goblin: Combatant, longsword: Weapon
    ):
        """Hit when total attack equals or exceeds AC."""
        # Goblin AC 12, Fighter has +3 STR +2 prof = +5
        # Roll 7 + 5 = 12, equals AC
        mock_result = DiceResult(notation="1d20", rolls=[7], total=7)

        def mock_roll(notation: str) -> DiceResult:
            if "d20" in notation:
                return mock_result
            # Damage roll
            return DiceResult(notation=notation, rolls=[4], total=4)

        with patch("src.skills.combat.roll_dice", side_effect=mock_roll):
            result = resolve_attack(fighter, goblin, longsword)

        assert result.hit is True
        assert result.total_attack == 12  # 7 + 3 (STR) + 2 (prof)
        assert result.damage is not None

    def test_miss_when_total_below_ac(
        self, fighter: Combatant, goblin: Combatant, longsword: Weapon
    ):
        """Miss when total attack is below AC."""
        # Roll 4 + 5 = 9, below AC 12
        mock_result = DiceResult(notation="1d20", rolls=[4], total=4)
        with patch("src.skills.combat.roll_dice", return_value=mock_result):
            result = resolve_attack(fighter, goblin, longsword)

        assert result.hit is False
        assert result.total_attack == 9
        assert result.damage is None

    def test_cover_increases_effective_ac(
        self, fighter: Combatant, goblin: Combatant, longsword: Weapon
    ):
        """Cover should add to target's effective AC."""
        # Roll 9 + 5 = 14, hits AC 12 but not AC 14 (half cover)
        mock_result = DiceResult(notation="1d20", rolls=[9], total=9)
        with patch("src.skills.combat.roll_dice", return_value=mock_result):
            result = resolve_attack(fighter, goblin, longsword, cover=CoverType.HALF)

        assert result.target_ac == 14  # 12 + 2 (half cover)
        assert result.hit is True  # 14 >= 14

    def test_damage_includes_ability_modifier(
        self, fighter: Combatant, goblin: Combatant, longsword: Weapon
    ):
        """Damage should include ability modifier."""
        mock_d20 = DiceResult(notation="1d20", rolls=[15], total=15)
        mock_damage = DiceResult(notation="1d8", rolls=[4], total=4)

        call_count = [0]

        def mock_roll(notation: str) -> DiceResult:
            if "d20" in notation:
                return mock_d20
            call_count[0] += 1
            return mock_damage

        with patch("src.skills.combat.roll_dice", side_effect=mock_roll):
            result = resolve_attack(fighter, goblin, longsword)

        # 4 (dice) + 3 (STR mod) = 7
        assert result.damage == 7
        assert result.damage_type == "slashing"

    def test_critical_doubles_damage_dice(
        self, fighter: Combatant, goblin: Combatant, longsword: Weapon
    ):
        """Critical hit should roll damage dice twice."""
        mock_d20 = DiceResult(notation="1d20", rolls=[20], total=20)
        mock_damage = DiceResult(notation="1d8", rolls=[4], total=4)

        damage_rolls = []

        def mock_roll(notation: str) -> DiceResult:
            if "d20" in notation:
                return mock_d20
            damage_rolls.append(notation)
            return mock_damage

        with patch("src.skills.combat.roll_dice", side_effect=mock_roll):
            result = resolve_attack(fighter, goblin, longsword)

        # Should roll damage twice for crit
        assert len(damage_rolls) == 2
        # 4 + 4 (doubled dice) + 3 (STR mod) = 11
        assert result.damage == 11

    def test_proficiency_applies_when_proficient(
        self, fighter: Combatant, goblin: Combatant, longsword: Weapon
    ):
        """Proficiency bonus should be added when proficient."""
        mock_result = DiceResult(notation="1d20", rolls=[10], total=10)
        with patch("src.skills.combat.roll_dice", return_value=mock_result):
            result = resolve_attack(fighter, goblin, longsword)

        # 10 + 3 (STR) + 2 (prof) = 15
        assert result.total_attack == 15

    def test_no_proficiency_when_not_proficient(self, fighter: Combatant, goblin: Combatant):
        """No proficiency bonus when not proficient with weapon."""
        greataxe = Weapon(
            name="Greataxe",
            damage_dice="1d12",
            damage_type="slashing",
            properties=[WeaponProperty.HEAVY, WeaponProperty.TWO_HANDED],
        )
        # Fighter is not proficient with greataxe in our fixture

        mock_result = DiceResult(notation="1d20", rolls=[10], total=10)
        with patch("src.skills.combat.roll_dice", return_value=mock_result):
            result = resolve_attack(fighter, goblin, greataxe)

        # 10 + 3 (STR) + 0 (no prof) = 13
        assert result.total_attack == 13

    def test_minimum_damage_is_one(self, goblin: Combatant, longsword: Weapon):
        """Minimum damage on hit should be 1."""
        # Weak attacker with negative STR mod
        weak = Combatant(
            name="Weakling",
            abilities=Abilities(str=4),  # -3 modifier
            proficient_weapons=["longsword"],
        )
        target = Combatant(name="Target", ac=5)

        mock_d20 = DiceResult(notation="1d20", rolls=[20], total=20)  # Crit to ensure hit
        mock_damage = DiceResult(notation="1d8", rolls=[1], total=1)

        def mock_roll(notation: str) -> DiceResult:
            if "d20" in notation:
                return mock_d20
            return mock_damage

        with patch("src.skills.combat.roll_dice", side_effect=mock_roll):
            result = resolve_attack(weak, target, longsword)

        # 1 + 1 (crit) - 3 (STR) = -1, but minimum 1
        assert result.damage == 1


class TestAdvantageDisadvantage:
    """Tests for advantage and disadvantage."""

    def test_advantage_rolls_2d20kh1(
        self, fighter: Combatant, goblin: Combatant, longsword: Weapon
    ):
        """Advantage should roll 2d20 keep highest."""
        mock_result = DiceResult(notation="2d20kh1", rolls=[5, 15], kept=[15], total=15)

        with patch("src.skills.combat.roll_dice", return_value=mock_result) as mock:
            resolve_attack(fighter, goblin, longsword, advantage=True)

        mock.assert_any_call("2d20kh1")

    def test_disadvantage_rolls_2d20kl1(
        self, fighter: Combatant, goblin: Combatant, longsword: Weapon
    ):
        """Disadvantage should roll 2d20 keep lowest."""
        mock_result = DiceResult(notation="2d20kl1", rolls=[5, 15], kept=[5], total=5)

        with patch("src.skills.combat.roll_dice", return_value=mock_result) as mock:
            resolve_attack(fighter, goblin, longsword, disadvantage=True)

        mock.assert_any_call("2d20kl1")

    def test_advantage_and_disadvantage_cancel(
        self, fighter: Combatant, goblin: Combatant, longsword: Weapon
    ):
        """Advantage and disadvantage together should roll normally."""
        mock_result = DiceResult(notation="1d20", rolls=[10], total=10)

        with patch("src.skills.combat.roll_dice", return_value=mock_result) as mock:
            resolve_attack(fighter, goblin, longsword, advantage=True, disadvantage=True)

        mock.assert_any_call("1d20")
