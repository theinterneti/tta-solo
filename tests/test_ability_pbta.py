"""
Tests for Ability-specific PbtA system.
"""

from __future__ import annotations

from src.engine.ability_pbta import (
    AbilityComplication,
    AbilityGMMove,
    ComplicationType,
    GMAbilityMoveType,
    apply_ability_pbta,
    get_miss_gm_move,
    get_strong_hit_bonus,
    get_weak_hit_complication,
)
from src.models.ability import AbilitySource


class TestGetWeakHitComplication:
    """Tests for get_weak_hit_complication function."""

    def test_magic_complication(self):
        """Test getting magic complications."""
        complication = get_weak_hit_complication(AbilitySource.MAGIC)
        assert isinstance(complication, AbilityComplication)
        assert complication.type in {
            ComplicationType.SPELL_DRAIN,
            ComplicationType.WILD_MAGIC,
            ComplicationType.CONCENTRATION_STRAIN,
            ComplicationType.ARCANE_ATTENTION,
        }

    def test_tech_complication(self):
        """Test getting tech complications."""
        complication = get_weak_hit_complication(AbilitySource.TECH)
        assert isinstance(complication, AbilityComplication)
        assert complication.type in {
            ComplicationType.OVERHEAT,
            ComplicationType.MALFUNCTION,
            ComplicationType.POWER_SURGE,
            ComplicationType.SYSTEM_ALERT,
        }

    def test_martial_complication(self):
        """Test getting martial complications."""
        complication = get_weak_hit_complication(AbilitySource.MARTIAL)
        assert isinstance(complication, AbilityComplication)
        assert complication.type in {
            ComplicationType.OVEREXTEND,
            ComplicationType.STRAIN,
            ComplicationType.TELEGRAPH,
            ComplicationType.MOMENTUM_LOSS,
        }

    def test_complication_has_description(self):
        """Test that complications have descriptions."""
        for source in AbilitySource:
            complication = get_weak_hit_complication(source)
            assert len(complication.description) > 0
            assert len(complication.mechanical_effect) > 0


class TestGetMissGMMove:
    """Tests for get_miss_gm_move function."""

    def test_magic_gm_move(self):
        """Test getting magic GM moves."""
        gm_move = get_miss_gm_move(AbilitySource.MAGIC)
        assert isinstance(gm_move, AbilityGMMove)
        assert gm_move.type in {
            GMAbilityMoveType.SPELL_BACKFIRE,
            GMAbilityMoveType.MAGICAL_EXHAUSTION,
            GMAbilityMoveType.ATTRACT_ENTITY,
            GMAbilityMoveType.COMPONENT_CONSUMED,
        }

    def test_tech_gm_move(self):
        """Test getting tech GM moves."""
        gm_move = get_miss_gm_move(AbilitySource.TECH)
        assert isinstance(gm_move, AbilityGMMove)
        assert gm_move.type in {
            GMAbilityMoveType.CATASTROPHIC_FAILURE,
            GMAbilityMoveType.FEEDBACK_LOOP,
            GMAbilityMoveType.SECURITY_BREACH,
            GMAbilityMoveType.POWER_DRAIN,
        }

    def test_martial_gm_move(self):
        """Test getting martial GM moves."""
        gm_move = get_miss_gm_move(AbilitySource.MARTIAL)
        assert isinstance(gm_move, AbilityGMMove)
        assert gm_move.type in {
            GMAbilityMoveType.OPENING_GIVEN,
            GMAbilityMoveType.INJURY,
            GMAbilityMoveType.DISARM,
            GMAbilityMoveType.STUMBLE,
        }

    def test_gm_move_has_description(self):
        """Test that GM moves have descriptions."""
        for source in AbilitySource:
            gm_move = get_miss_gm_move(source)
            assert len(gm_move.description) > 0


class TestGetStrongHitBonus:
    """Tests for get_strong_hit_bonus function."""

    def test_magic_bonus(self):
        """Test getting magic bonuses."""
        bonus = get_strong_hit_bonus(AbilitySource.MAGIC)
        assert isinstance(bonus, str)
        assert len(bonus) > 0

    def test_tech_bonus(self):
        """Test getting tech bonuses."""
        bonus = get_strong_hit_bonus(AbilitySource.TECH)
        assert isinstance(bonus, str)
        assert len(bonus) > 0

    def test_martial_bonus(self):
        """Test getting martial bonuses."""
        bonus = get_strong_hit_bonus(AbilitySource.MARTIAL)
        assert isinstance(bonus, str)
        assert len(bonus) > 0


class TestApplyAbilityPbtA:
    """Tests for apply_ability_pbta function."""

    def test_strong_hit_has_bonus(self):
        """Test strong hit gets bonus effect."""
        result = apply_ability_pbta("strong_hit", AbilitySource.MAGIC)
        assert result.outcome == "strong_hit"
        assert result.bonus_effect is not None
        assert result.complication is None
        assert result.gm_move is None

    def test_weak_hit_has_complication(self):
        """Test weak hit gets complication."""
        result = apply_ability_pbta("weak_hit", AbilitySource.TECH)
        assert result.outcome == "weak_hit"
        assert result.complication is not None
        assert result.bonus_effect is None
        assert result.gm_move is None

    def test_miss_has_gm_move(self):
        """Test miss gets GM move."""
        result = apply_ability_pbta("miss", AbilitySource.MARTIAL)
        assert result.outcome == "miss"
        assert result.gm_move is not None
        assert result.bonus_effect is None
        assert result.complication is None

    def test_all_sources_all_outcomes(self):
        """Test all combinations work."""
        for source in AbilitySource:
            for outcome in ["strong_hit", "weak_hit", "miss"]:
                result = apply_ability_pbta(outcome, source)
                assert result.outcome == outcome
