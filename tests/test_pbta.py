"""Tests for the PbtA move system."""

from __future__ import annotations

from uuid import uuid4

import pytest

from src.engine import (
    Context,
    EntitySummary,
    GMMoveType,
    Intent,
    IntentType,
    PbtAOutcome,
    SkillRouter,
    calculate_pbta_outcome,
    get_strong_hit_bonus,
    get_weak_hit_complication,
    select_gm_move,
)


class TestPbtAOutcomeCalculation:
    """Tests for PbtA outcome calculation."""

    def test_critical_always_strong_hit(self):
        """Natural 20 should always be a strong hit."""
        outcome = calculate_pbta_outcome(total=20, dc=25, is_critical=True)
        assert outcome == PbtAOutcome.STRONG_HIT

    def test_fumble_always_miss(self):
        """Natural 1 should always be a miss."""
        outcome = calculate_pbta_outcome(total=15, dc=10, is_fumble=True)
        assert outcome == PbtAOutcome.MISS

    def test_beat_dc_by_5_strong_hit(self):
        """Beating DC by 5+ should be strong hit."""
        outcome = calculate_pbta_outcome(total=15, dc=10)
        assert outcome == PbtAOutcome.STRONG_HIT

    def test_beat_dc_exactly_weak_hit(self):
        """Meeting DC exactly should be weak hit."""
        outcome = calculate_pbta_outcome(total=10, dc=10)
        assert outcome == PbtAOutcome.WEAK_HIT

    def test_beat_dc_by_less_than_5_weak_hit(self):
        """Beating DC by less than 5 should be weak hit."""
        outcome = calculate_pbta_outcome(total=13, dc=10)
        assert outcome == PbtAOutcome.WEAK_HIT

    def test_fail_dc_miss(self):
        """Failing DC should be miss."""
        outcome = calculate_pbta_outcome(total=8, dc=10)
        assert outcome == PbtAOutcome.MISS

    def test_no_dc_high_total_strong_hit(self):
        """Without DC, high total (15+) should be strong hit."""
        outcome = calculate_pbta_outcome(total=15, dc=None)
        assert outcome == PbtAOutcome.STRONG_HIT

    def test_no_dc_medium_total_weak_hit(self):
        """Without DC, medium total (10-14) should be weak hit."""
        outcome = calculate_pbta_outcome(total=12, dc=None)
        assert outcome == PbtAOutcome.WEAK_HIT

    def test_no_dc_low_total_miss(self):
        """Without DC, low total (<10) should be miss."""
        outcome = calculate_pbta_outcome(total=7, dc=None)
        assert outcome == PbtAOutcome.MISS


class TestGMMove:
    """Tests for GM move selection."""

    def test_select_gm_move_returns_move(self):
        """Should return a valid GM move."""
        move = select_gm_move()
        assert move.type in GMMoveType
        assert move.description

    def test_high_danger_favors_hard_moves(self):
        """High danger should favor hard moves."""
        hard_count = 0
        for _ in range(50):
            move = select_gm_move(danger_level=15)
            if move.is_hard:
                hard_count += 1
        # Should be mostly hard moves
        assert hard_count > 25

    def test_low_danger_favors_soft_moves(self):
        """Low danger should favor soft moves."""
        soft_count = 0
        for _ in range(50):
            move = select_gm_move(danger_level=0, recent_soft_moves=0)
            if not move.is_hard:
                soft_count += 1
        # Should be mostly soft moves
        assert soft_count > 25

    def test_combat_includes_damage_option(self):
        """Combat should include damage moves."""
        damage_count = 0
        for _ in range(100):
            move = select_gm_move(danger_level=10, is_combat=True)
            if move.type == GMMoveType.DEAL_DAMAGE:
                damage_count += 1
        # Should get damage moves in combat
        assert damage_count > 0

    def test_damage_move_has_damage(self):
        """Damage moves should have damage value."""
        for _ in range(100):
            move = select_gm_move(danger_level=10, is_combat=True)
            if move.type == GMMoveType.DEAL_DAMAGE:
                assert move.damage is not None
                assert move.damage > 0
                break


class TestPbtAEffects:
    """Tests for strong hit bonuses and weak hit complications."""

    def test_strong_hit_bonus_attack(self):
        """Attack should have a strong hit bonus."""
        bonus = get_strong_hit_bonus("attack")
        assert bonus
        assert isinstance(bonus, str)

    def test_weak_hit_complication_attack(self):
        """Attack should have a weak hit complication."""
        complication = get_weak_hit_complication("attack")
        assert complication
        assert isinstance(complication, str)

    def test_strong_hit_bonus_persuade(self):
        """Persuade should have a strong hit bonus."""
        bonus = get_strong_hit_bonus("persuade")
        assert "convince" in bonus.lower() or "help" in bonus.lower()

    def test_weak_hit_complication_persuade(self):
        """Persuade should have a weak hit complication."""
        complication = get_weak_hit_complication("persuade")
        assert "return" in complication.lower() or "want" in complication.lower()

    def test_unknown_intent_has_default(self):
        """Unknown intent should have default bonus/complication."""
        bonus = get_strong_hit_bonus("unknown_action")
        complication = get_weak_hit_complication("unknown_action")
        assert bonus
        assert complication


class TestSkillRouterPbtA:
    """Tests for PbtA integration in SkillRouter."""

    @pytest.fixture
    def router(self) -> SkillRouter:
        return SkillRouter(use_pbta=True)

    @pytest.fixture
    def router_no_pbta(self) -> SkillRouter:
        return SkillRouter(use_pbta=False)

    @pytest.fixture
    def basic_context(self) -> Context:
        return Context(
            actor=EntitySummary(
                id=uuid4(),
                name="Hero",
                type="character",
                hp_current=20,
                hp_max=20,
                ac=15,
            ),
            location=EntitySummary(
                id=uuid4(),
                name="Tavern",
                type="location",
            ),
            entities_present=[
                EntitySummary(
                    id=uuid4(),
                    name="Goblin",
                    type="character",
                    ac=12,
                ),
            ],
            exits=["north", "south"],
            danger_level=5,
        )

    def test_attack_includes_pbta_outcome(self, router: SkillRouter, basic_context: Context):
        """Attack should include PbtA outcome."""
        intent = Intent(
            type=IntentType.ATTACK,
            confidence=0.9,
            target_name="goblin",
            original_input="I attack the goblin",
        )
        result = router.resolve(intent, basic_context)

        assert result.pbta_outcome is not None
        assert result.pbta_outcome in ["strong_hit", "weak_hit", "miss"]

    def test_skill_check_includes_pbta_outcome(self, router: SkillRouter, basic_context: Context):
        """Skill check should include PbtA outcome."""
        intent = Intent(
            type=IntentType.PERSUADE,
            confidence=0.9,
            original_input="I try to persuade",
        )
        result = router.resolve(intent, basic_context)

        assert result.pbta_outcome is not None
        assert result.pbta_outcome in ["strong_hit", "weak_hit", "miss"]

    def test_pbta_disabled_no_outcome(self, router_no_pbta: SkillRouter, basic_context: Context):
        """With PbtA disabled, no pbta_outcome should be set."""
        intent = Intent(
            type=IntentType.ATTACK,
            confidence=0.9,
            target_name="goblin",
            original_input="I attack the goblin",
        )
        result = router_no_pbta.resolve(intent, basic_context)

        assert result.pbta_outcome is None

    def test_look_no_pbta(self, router: SkillRouter, basic_context: Context):
        """Look (no roll) should not have PbtA outcome."""
        intent = Intent(
            type=IntentType.LOOK,
            confidence=0.9,
            original_input="I look around",
        )
        result = router.resolve(intent, basic_context)

        # Look doesn't have a roll, so no PbtA
        assert result.pbta_outcome is None

    def test_strong_hit_has_bonus(self, router: SkillRouter, basic_context: Context):
        """Strong hit should have bonus effect."""
        intent = Intent(
            type=IntentType.ATTACK,
            confidence=0.9,
            target_name="goblin",
            original_input="I attack the goblin",
        )

        # Run many times to ensure we get some strong hits
        found_strong_hit = False
        for _ in range(100):
            result = router.resolve(intent, basic_context)
            if result.pbta_outcome == "strong_hit":
                assert result.strong_hit_bonus is not None
                found_strong_hit = True
                break

        assert found_strong_hit, "Expected at least one strong_hit in 100 rolls"

    def test_weak_hit_has_complication(self, router: SkillRouter, basic_context: Context):
        """Weak hit should have complication."""
        intent = Intent(
            type=IntentType.PERSUADE,
            confidence=0.9,
            original_input="I try to persuade",
        )

        # Run many times to ensure we get some weak hits
        found_weak_hit = False
        for _ in range(100):
            result = router.resolve(intent, basic_context)
            if result.pbta_outcome == "weak_hit":
                assert result.weak_hit_complication is not None
                found_weak_hit = True
                break

        assert found_weak_hit, "Expected at least one weak_hit in 100 rolls"

    def test_miss_has_gm_move(self, router: SkillRouter, basic_context: Context):
        """Miss should have GM move."""
        intent = Intent(
            type=IntentType.ATTACK,
            confidence=0.9,
            target_name="goblin",
            original_input="I attack the goblin",
        )

        # Run many times to ensure we get some misses
        found_miss = False
        for _ in range(100):
            result = router.resolve(intent, basic_context)
            if result.pbta_outcome == "miss":
                assert result.gm_move_type is not None
                assert result.gm_move_description is not None
                found_miss = True
                break

        assert found_miss, "Expected at least one miss in 100 rolls"

    def test_high_danger_miss_deals_damage(self, router: SkillRouter):
        """Miss in high danger should sometimes deal damage."""
        high_danger_context = Context(
            actor=EntitySummary(
                id=uuid4(),
                name="Hero",
                type="character",
                ac=15,
            ),
            location=EntitySummary(
                id=uuid4(),
                name="Dragon's Lair",
                type="location",
            ),
            danger_level=15,  # High danger
        )

        intent = Intent(
            type=IntentType.ATTACK,
            confidence=0.9,
            target_name="dragon",
            original_input="I attack the dragon",
        )

        damage_on_miss = False
        for _ in range(200):
            result = router.resolve(intent, high_danger_context)
            if result.pbta_outcome == "miss" and result.gm_move_type == "deal_damage":
                damage_on_miss = True
                break

        assert damage_on_miss, "Expected some misses to deal damage in high danger"
