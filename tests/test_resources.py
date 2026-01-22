"""
Tests for the Resource System.

Tests for UsageDie, CooldownTracker, StressMomentumPool, and related skills.
"""

from __future__ import annotations

import pytest

from src.models.resources import (
    CooldownTracker,
    EntityResources,
    SpellSlotTracker,
    StressMomentumPool,
    UsageDie,
    create_cooldown_tracker,
    create_spell_slots,
    create_usage_die,
)
from src.skills.resources import (
    apply_rest_to_resources,
    apply_technique_stress,
    check_stress_effects,
    process_round_start_recharges,
    reduce_stress_on_rest,
    roll_usage_die,
    spend_momentum_for_technique,
    try_recharge_ability,
)


class TestUsageDie:
    """Tests for UsageDie model."""

    def test_create_default(self):
        """Test creating a default usage die."""
        die = UsageDie()
        assert die.current_die == "d12"
        assert die.current_index == 4
        assert die.depleted is False

    def test_create_at_specific_die(self):
        """Test creating a die at a specific size."""
        die = create_usage_die("d8")
        assert die.current_die == "d8"
        assert die.current_index == 2

    def test_die_size(self):
        """Test getting numeric die size."""
        die = create_usage_die("d10")
        assert die.die_size() == 10

    def test_degrade(self):
        """Test die degradation."""
        die = create_usage_die("d10")
        depleted = die.degrade()
        assert depleted is False
        assert die.current_die == "d8"

    def test_degrade_to_depletion(self):
        """Test degradation to depletion."""
        die = create_usage_die("d4")
        depleted = die.degrade()
        assert depleted is True
        assert die.depleted is True
        assert die.current_die == "depleted"

    def test_restore(self):
        """Test restoring a degraded die."""
        die = create_usage_die("d6")
        die.restore(2)
        assert die.current_die == "d10"

    def test_restore_from_depleted(self):
        """Test restoring a depleted die."""
        die = create_usage_die("d4")
        die.degrade()  # Deplete it
        assert die.depleted is True

        die.restore(1)
        assert die.depleted is False
        assert die.current_die == "d4"

    def test_restore_full(self):
        """Test fully restoring a die."""
        die = create_usage_die("d6")
        die.restore_full()
        assert die.current_die == "d12"

    def test_custom_degrade_values(self):
        """Test custom degradation values."""
        die = UsageDie(degrade_on=[1, 2, 3])
        assert die.degrade_on == [1, 2, 3]

    def test_invalid_index(self):
        """Test that invalid index raises error."""
        with pytest.raises(ValueError, match="out of bounds"):
            UsageDie(current_index=10)


class TestCooldownTracker:
    """Tests for CooldownTracker model."""

    def test_create_basic(self):
        """Test creating a basic cooldown tracker."""
        tracker = CooldownTracker(max_uses=2, current_uses=2)
        assert tracker.max_uses == 2
        assert tracker.current_uses == 2
        assert tracker.has_uses() is True

    def test_create_with_factory(self):
        """Test creating with factory function."""
        tracker = create_cooldown_tracker(max_uses=3, recharge_on_rest="short")
        assert tracker.max_uses == 3
        assert tracker.current_uses == 3
        assert tracker.recharge_on_rest == "short"

    def test_use(self):
        """Test using an ability."""
        tracker = create_cooldown_tracker(max_uses=2)
        assert tracker.use() is True
        assert tracker.current_uses == 1
        assert tracker.use() is True
        assert tracker.current_uses == 0
        assert tracker.use() is False  # No uses left

    def test_restore_use(self):
        """Test restoring uses."""
        tracker = create_cooldown_tracker(max_uses=3)
        tracker.use()
        tracker.use()
        restored = tracker.restore_use(1)
        assert restored == 1
        assert tracker.current_uses == 2

    def test_restore_use_capped(self):
        """Test that restore doesn't exceed max."""
        tracker = create_cooldown_tracker(max_uses=2)
        tracker.use()
        restored = tracker.restore_use(5)
        assert restored == 1
        assert tracker.current_uses == 2

    def test_restore_on_short_rest(self):
        """Test restoring on short rest."""
        tracker = create_cooldown_tracker(max_uses=2, recharge_on_rest="short")
        tracker.use()
        tracker.use()
        restored = tracker.restore_on_rest("short")
        assert restored == 2
        assert tracker.current_uses == 2

    def test_restore_on_long_rest_when_short(self):
        """Test that long rest also restores short-rest abilities."""
        tracker = create_cooldown_tracker(max_uses=2, recharge_on_rest="short")
        tracker.use()
        restored = tracker.restore_on_rest("long")
        assert restored == 1

    def test_no_restore_on_wrong_rest(self):
        """Test that wrong rest type doesn't restore."""
        tracker = create_cooldown_tracker(max_uses=2, recharge_on_rest="long")
        tracker.use()
        restored = tracker.restore_on_rest("short")
        assert restored == 0
        assert tracker.current_uses == 1

    def test_recharge_die_size(self):
        """Test getting recharge die size."""
        tracker = CooldownTracker(
            max_uses=1, current_uses=1, recharge_die="d8", recharge_on=[7, 8]
        )
        assert tracker.recharge_die_size() == 8

    def test_invalid_uses(self):
        """Test that current > max raises error."""
        with pytest.raises(ValueError, match="cannot exceed"):
            CooldownTracker(max_uses=2, current_uses=5)


class TestStressMomentumPool:
    """Tests for StressMomentumPool model."""

    def test_create_default(self):
        """Test creating a default pool."""
        pool = StressMomentumPool()
        assert pool.stress == 0
        assert pool.stress_max == 10
        assert pool.momentum == 0
        assert pool.momentum_max == 5

    def test_add_stress(self):
        """Test adding stress."""
        pool = StressMomentumPool()
        result = pool.add_stress(3)
        assert result.new_stress == 3
        assert result.change == 3
        assert result.at_breaking_point is False

    def test_add_stress_to_breaking_point(self):
        """Test adding stress to breaking point."""
        pool = StressMomentumPool(stress=8)
        result = pool.add_stress(5)
        assert result.new_stress == 10  # Capped
        assert result.at_breaking_point is True

    def test_reduce_stress(self):
        """Test reducing stress."""
        pool = StressMomentumPool(stress=5)
        reduced = pool.reduce_stress(3)
        assert reduced == 3
        assert pool.stress == 2

    def test_reduce_stress_floor(self):
        """Test stress doesn't go below 0."""
        pool = StressMomentumPool(stress=2)
        reduced = pool.reduce_stress(5)
        assert reduced == 2
        assert pool.stress == 0

    def test_add_momentum(self):
        """Test adding momentum."""
        pool = StressMomentumPool()
        result = pool.add_momentum(2)
        assert result.new_momentum == 2
        assert result.at_max is False

    def test_add_momentum_capped(self):
        """Test momentum caps at max."""
        pool = StressMomentumPool(momentum=4)
        result = pool.add_momentum(3)
        assert result.new_momentum == 5
        assert result.at_max is True

    def test_spend_momentum(self):
        """Test spending momentum."""
        pool = StressMomentumPool(momentum=3)
        success = pool.spend_momentum(2)
        assert success is True
        assert pool.momentum == 1

    def test_spend_momentum_insufficient(self):
        """Test spending more momentum than available."""
        pool = StressMomentumPool(momentum=1)
        success = pool.spend_momentum(3)
        assert success is False
        assert pool.momentum == 1  # Unchanged

    def test_take_damage_reset(self):
        """Test momentum reset on damage."""
        pool = StressMomentumPool(momentum=4)
        lost = pool.take_damage_reset()
        assert lost == 4
        assert pool.momentum == 0

    def test_stress_penalty(self):
        """Test stress penalty calculation."""
        pool = StressMomentumPool(stress=2)
        assert pool.stress_penalty() == 0

        pool.stress = 5
        assert pool.stress_penalty() == -1

        pool.stress = 8
        assert pool.stress_penalty() == -2

    def test_is_at_breaking_point(self):
        """Test breaking point check."""
        pool = StressMomentumPool(stress=9)
        assert pool.is_at_breaking_point() is False

        pool.stress = 10
        assert pool.is_at_breaking_point() is True


class TestSpellSlotTracker:
    """Tests for SpellSlotTracker model."""

    def test_create_basic(self):
        """Test creating a basic tracker."""
        tracker = SpellSlotTracker(level=3, max_slots=2, current_slots=2)
        assert tracker.level == 3
        assert tracker.has_slots() is True

    def test_use_slot(self):
        """Test using a slot."""
        tracker = SpellSlotTracker(level=1, max_slots=4, current_slots=4)
        success = tracker.use_slot()
        assert success is True
        assert tracker.current_slots == 3

    def test_use_slot_empty(self):
        """Test using slot when empty."""
        tracker = SpellSlotTracker(level=1, max_slots=2, current_slots=0)
        success = tracker.use_slot()
        assert success is False

    def test_restore_slots(self):
        """Test restoring slots."""
        tracker = SpellSlotTracker(level=1, max_slots=4, current_slots=1)
        restored = tracker.restore_slots(2)
        assert restored == 2
        assert tracker.current_slots == 3

    def test_restore_all_slots(self):
        """Test restoring all slots."""
        tracker = SpellSlotTracker(level=1, max_slots=4, current_slots=1)
        restored = tracker.restore_slots()
        assert restored == 3
        assert tracker.current_slots == 4

    def test_create_spell_slots(self):
        """Test factory for multiple levels."""
        slots = create_spell_slots({1: 4, 2: 3, 3: 2})
        assert 1 in slots
        assert 2 in slots
        assert 3 in slots
        assert slots[1].max_slots == 4
        assert slots[2].max_slots == 3


class TestEntityResources:
    """Tests for EntityResources composite model."""

    def test_create_empty(self):
        """Test creating empty resources."""
        resources = EntityResources()
        assert len(resources.usage_dice) == 0
        assert len(resources.cooldowns) == 0
        assert resources.stress_momentum is None
        assert resources.spell_slots is None

    def test_has_spell_slot(self):
        """Test checking spell slot availability."""
        resources = EntityResources(spell_slots=create_spell_slots({1: 2, 2: 1}))
        assert resources.has_spell_slot(1) is True
        assert resources.has_spell_slot(3) is False

    def test_use_spell_slot(self):
        """Test using a spell slot."""
        resources = EntityResources(spell_slots=create_spell_slots({1: 2}))
        success = resources.use_spell_slot(1)
        assert success is True
        assert resources.spell_slots[1].current_slots == 1

    def test_get_cooldown(self):
        """Test getting a cooldown tracker."""
        tracker = create_cooldown_tracker(max_uses=2)
        resources = EntityResources(cooldowns={"fire_breath": tracker})
        assert resources.get_cooldown("fire_breath") is tracker
        assert resources.get_cooldown("nonexistent") is None

    def test_restore_on_long_rest(self):
        """Test long rest restoration."""
        tracker = create_cooldown_tracker(max_uses=2, recharge_on_rest="short")
        tracker.use()
        usage_die = create_usage_die("d8")
        usage_die.degrade()

        resources = EntityResources(
            cooldowns={"ability": tracker},
            usage_dice={"ammo": usage_die},
            spell_slots=create_spell_slots({1: 2, 2: 1}),
            stress_momentum=StressMomentumPool(stress=5),
        )
        resources.use_spell_slot(1)

        restored = resources.restore_on_rest("long")

        assert "cooldown:ability" in restored
        assert "stress_reduced" in restored
        assert resources.stress_momentum.stress == 0
        assert resources.spell_slots[1].current_slots == 2


class TestRollUsageDie:
    """Tests for roll_usage_die skill function."""

    def test_roll_active_die(self):
        """Test rolling an active die."""
        die = create_usage_die("d12")
        result = roll_usage_die(die)
        assert result.die_used == "d12"
        assert 1 <= result.roll <= 12
        assert result.depleted is False

    def test_roll_depleted_die(self):
        """Test rolling a depleted die."""
        die = create_usage_die("d4")
        die.degrade()  # Deplete it
        result = roll_usage_die(die)
        assert result.roll == 0
        assert result.die_used == "depleted"
        assert result.depleted is True

    def test_roll_can_degrade(self):
        """Test that rolling can cause degradation (statistical)."""
        # Run multiple times to increase chance of seeing degradation
        degraded_count = 0

        for _ in range(100):
            test_die = create_usage_die("d4")
            result = roll_usage_die(test_die)
            if result.degraded:
                degraded_count += 1

        # With d4, 50% chance of 1 or 2, so we should see some degradation
        assert degraded_count > 0


class TestTryRechargeAbility:
    """Tests for try_recharge_ability skill function."""

    def test_no_recharge_mechanism(self):
        """Test ability without recharge mechanism."""
        tracker = create_cooldown_tracker(max_uses=1, recharge_on_rest="short")
        result = try_recharge_ability(tracker, "test")
        assert result.recharged is False
        assert result.roll is None

    def test_recharge_at_max(self):
        """Test no recharge when at max uses."""
        tracker = CooldownTracker(
            max_uses=2, current_uses=2, recharge_on=[5, 6], recharge_die="d6"
        )
        result = try_recharge_ability(tracker)
        assert result.recharged is False

    def test_recharge_roll(self):
        """Test recharge rolling (statistical)."""
        # With [5, 6] on d6, 33% chance of recharge
        recharged_count = 0

        for _ in range(100):
            tracker = CooldownTracker(
                max_uses=2, current_uses=0, recharge_on=[5, 6], recharge_die="d6"
            )
            result = try_recharge_ability(tracker, "test_ability")
            if result.recharged:
                recharged_count += 1

        # Should see some recharges over 100 trials
        assert recharged_count > 0


class TestProcessRoundStartRecharges:
    """Tests for process_round_start_recharges skill function."""

    def test_process_multiple(self):
        """Test processing multiple cooldowns."""
        cooldowns = {
            "ability1": CooldownTracker(
                max_uses=2, current_uses=0, recharge_on=[5, 6], recharge_die="d6"
            ),
            "ability2": CooldownTracker(
                max_uses=1, current_uses=0, recharge_on=[6], recharge_die="d6"
            ),
            "ability3": create_cooldown_tracker(max_uses=2),  # No recharge_on
        }

        result = process_round_start_recharges(cooldowns)
        # Should have results for abilities with recharge_on
        assert len(result.results) == 2


class TestStressFunctions:
    """Tests for stress-related skill functions."""

    def test_check_stress_effects_normal(self):
        """Test normal stress level effects."""
        pool = StressMomentumPool(stress=2)
        result = check_stress_effects(pool)
        assert result.penalty == 0
        assert result.at_breaking_point is False

    def test_check_stress_effects_moderate(self):
        """Test moderate stress effects."""
        pool = StressMomentumPool(stress=5)
        result = check_stress_effects(pool)
        assert result.penalty == -1
        assert "Disadvantage" in result.description

    def test_check_stress_effects_high(self):
        """Test high stress effects."""
        pool = StressMomentumPool(stress=8)
        result = check_stress_effects(pool)
        assert result.penalty == -2
        assert "-2 to all" in result.description

    def test_check_stress_effects_breaking_point(self):
        """Test breaking point effects."""
        pool = StressMomentumPool(stress=10)
        result = check_stress_effects(pool)
        assert result.at_breaking_point is True
        assert "Breaking Point" in result.description

    def test_apply_technique_stress(self):
        """Test applying stress from technique."""
        pool = StressMomentumPool(stress=3)
        result = apply_technique_stress(pool, 2)
        assert result.stress_added == 2
        assert result.new_stress == 5
        assert result.at_breaking_point is False

    def test_apply_technique_stress_triggers_breaking_point(self):
        """Test stress triggering breaking point."""
        pool = StressMomentumPool(stress=8)
        result = apply_technique_stress(pool, 3)
        assert result.new_stress == 10
        assert result.at_breaking_point is True
        assert result.triggered_breaking_point is True


class TestMomentumFunctions:
    """Tests for momentum-related skill functions."""

    def test_spend_momentum_success(self):
        """Test successfully spending momentum."""
        pool = StressMomentumPool(momentum=3)
        result = spend_momentum_for_technique(pool, 2)
        assert result.success is True
        assert result.amount_spent == 2
        assert result.remaining == 1

    def test_spend_momentum_insufficient(self):
        """Test spending with insufficient momentum."""
        pool = StressMomentumPool(momentum=1)
        result = spend_momentum_for_technique(pool, 3)
        assert result.success is False
        assert result.insufficient is True
        assert result.remaining == 1


class TestRestFunctions:
    """Tests for rest-related skill functions."""

    def test_reduce_stress_long_rest(self):
        """Test stress reduction on long rest."""
        pool = StressMomentumPool(stress=7)
        reduced = reduce_stress_on_rest(pool, "long")
        assert reduced == 7
        assert pool.stress == 0

    def test_reduce_stress_short_rest(self):
        """Test stress reduction on short rest (1d4)."""
        pool = StressMomentumPool(stress=5)
        reduced = reduce_stress_on_rest(pool, "short")
        assert 1 <= reduced <= 4

    def test_apply_rest_to_resources(self):
        """Test comprehensive rest application."""
        resources = EntityResources(
            cooldowns={
                "breath": create_cooldown_tracker(max_uses=1, recharge_on_rest="short")
            },
            spell_slots=create_spell_slots({1: 4, 2: 2}),
            stress_momentum=StressMomentumPool(stress=5),
        )
        resources.cooldowns["breath"].use()
        resources.use_spell_slot(1)
        resources.use_spell_slot(2)

        result = apply_rest_to_resources(resources, "long")

        assert result.rest_type == "long"
        assert "breath" in result.resources_restored
        assert result.stress_reduced == 5
        assert 1 in result.spell_slots_restored
