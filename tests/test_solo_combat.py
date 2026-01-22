"""
Tests for Solo Combat Balance mechanics.
"""

from __future__ import annotations

from uuid import uuid4

from src.skills.solo_combat import (
    DefyDeathConfig,
    FrayDieConfig,
    SoloCombatConfig,
    calculate_threshold_damage,
    defy_death,
    get_fray_die_for_level,
    resolve_solo_round_start,
    roll_fray_die,
    use_heroic_action,
)


class TestFrayDie:
    """Tests for Fray Die mechanics."""

    def test_get_fray_die_level_1(self):
        """Test fray die at level 1."""
        die = get_fray_die_for_level(1)
        assert die == "1d6"

    def test_get_fray_die_level_5(self):
        """Test fray die at level 5."""
        die = get_fray_die_for_level(5)
        assert die == "1d8"

    def test_get_fray_die_level_9(self):
        """Test fray die at level 9."""
        die = get_fray_die_for_level(9)
        assert die == "1d10"

    def test_get_fray_die_level_13(self):
        """Test fray die at level 13+."""
        die = get_fray_die_for_level(13)
        assert die == "1d12"

    def test_get_fray_die_no_scaling(self):
        """Test fray die without level scaling."""
        config = FrayDieConfig(level_scaling=False, die="d8")
        die = get_fray_die_for_level(1, config)
        assert die == "1d8"

    def test_roll_fray_die_basic(self):
        """Test rolling fray die."""
        enemies = [(uuid4(), 1), (uuid4(), 2)]
        result = roll_fray_die(actor_level=5, enemies=enemies)

        assert result.damage >= 1
        assert result.damage <= 8  # 1d8 at level 5
        assert result.die_used == "1d8"

    def test_roll_fray_die_mooks_only(self):
        """Test fray die only affects mooks."""
        mook_id = uuid4()
        boss_id = uuid4()
        enemies = [
            (mook_id, 1),  # Mook (HD 1 <= level 5)
            (boss_id, 10),  # Boss (HD 10 > level 5)
        ]

        # Run multiple times to ensure boss never gets hit
        for _ in range(20):
            result = roll_fray_die(actor_level=5, enemies=enemies)
            assert str(boss_id) not in result.damage_per_target

    def test_roll_fray_die_can_split(self):
        """Test fray die can split damage."""
        enemies = [
            (uuid4(), 1),
            (uuid4(), 1),
            (uuid4(), 1),
        ]
        config = FrayDieConfig(can_split=True, die="d12")

        # With high roll, should hit multiple targets
        result = roll_fray_die(actor_level=5, enemies=enemies, config=config)

        if result.damage > 1:
            # Damage should be distributed
            total_dealt = sum(result.damage_per_target.values())
            assert total_dealt <= result.damage

    def test_roll_fray_die_no_split(self):
        """Test fray die without splitting."""
        enemies = [(uuid4(), 1), (uuid4(), 1)]
        config = FrayDieConfig(can_split=False)

        result = roll_fray_die(actor_level=5, enemies=enemies, config=config)

        # Should only hit one target
        assert len(result.targets_hit) <= 1

    def test_roll_fray_die_no_valid_targets(self):
        """Test fray die with no valid targets."""
        enemies = [(uuid4(), 10)]  # HD 10 > level 5

        result = roll_fray_die(actor_level=5, enemies=enemies)

        assert len(result.targets_hit) == 0
        assert result.overflow == result.damage


class TestDamageThresholds:
    """Tests for damage threshold system."""

    def test_miss(self):
        """Test miss (roll below AC)."""
        result = calculate_threshold_damage(
            attack_roll=10,
            target_ac=15,
        )
        assert result.threshold_level == 0
        assert result.description == "Miss"

    def test_light_hit(self):
        """Test light hit (beat AC by 0-4)."""
        result = calculate_threshold_damage(
            attack_roll=15,
            target_ac=15,
        )
        assert result.threshold_level == 1
        assert result.description == "Light hit"

    def test_solid_hit(self):
        """Test solid hit (beat AC by 5-9)."""
        result = calculate_threshold_damage(
            attack_roll=20,
            target_ac=15,
        )
        assert result.threshold_level == 2
        assert result.description == "Solid hit"

    def test_heavy_hit(self):
        """Test heavy hit (beat AC by 10+)."""
        result = calculate_threshold_damage(
            attack_roll=25,
            target_ac=15,
        )
        assert result.threshold_level == 4
        assert result.description == "Heavy hit"
        assert result.is_kill_threshold is True

    def test_critical_bonus(self):
        """Test critical hit adds threshold."""
        result = calculate_threshold_damage(
            attack_roll=15,
            target_ac=15,
            is_critical=True,
        )
        # Light hit (1) + critical (2) = 3
        assert result.threshold_level == 3

    def test_heavy_weapon_bonus(self):
        """Test heavy weapon adds threshold."""
        result = calculate_threshold_damage(
            attack_roll=15,
            target_ac=15,
            weapon_weight="heavy",
        )
        # Light hit (1) + heavy (1) = 2
        assert result.threshold_level == 2

    def test_light_weapon_penalty(self):
        """Test light weapon reduces threshold."""
        result = calculate_threshold_damage(
            attack_roll=20,
            target_ac=15,
            weapon_weight="light",
        )
        # Solid hit (2) - light (1) = 1
        assert result.threshold_level == 1

    def test_devastating_hit(self):
        """Test devastating hit."""
        result = calculate_threshold_damage(
            attack_roll=30,
            target_ac=15,
            is_critical=True,
            weapon_weight="heavy",
        )
        # Heavy (4) + crit (2) + heavy (1) = 7
        assert result.threshold_level >= 6
        assert "Devastating" in result.description


class TestDefyDeath:
    """Tests for Defy Death mechanic."""

    def test_defy_death_success_possible(self):
        """Test that Defy Death can succeed."""
        # Run multiple times to find a success
        successes = 0
        for _ in range(100):
            result = defy_death(
                con_modifier=5,
                damage_taken_this_round=5,
                uses_today=0,
            )
            if result.survived:
                successes += 1
                assert result.exhaustion_gained == 1

        # With +5 and DC 15, should succeed sometimes
        assert successes > 0

    def test_defy_death_failure_possible(self):
        """Test that Defy Death can fail."""
        failures = 0
        for _ in range(100):
            result = defy_death(
                con_modifier=-2,
                damage_taken_this_round=20,
                uses_today=2,
            )
            if not result.survived:
                failures += 1

        # With high DC and low modifier, should fail sometimes
        assert failures > 0

    def test_defy_death_dc_increases(self):
        """Test DC increases with uses."""
        config = DefyDeathConfig(dc_increase_per_use=5)

        result1 = defy_death(con_modifier=0, damage_taken_this_round=0, uses_today=0, config=config)
        result2 = defy_death(con_modifier=0, damage_taken_this_round=0, uses_today=2, config=config)

        assert result2.dc > result1.dc
        assert result2.dc == result1.dc + 10  # 2 uses * 5 increase

    def test_defy_death_max_uses(self):
        """Test max uses per day."""
        config = DefyDeathConfig(max_uses_per_day=2)

        result = defy_death(
            con_modifier=10,
            damage_taken_this_round=0,
            uses_today=3,  # Already exceeded
            config=config,
        )

        assert result.survived is False
        assert result.uses_remaining == 0

    def test_defy_death_no_exhaustion_option(self):
        """Test option to not grant exhaustion."""
        config = DefyDeathConfig(grants_exhaustion=False)

        # Run until we get a success
        for _ in range(100):
            result = defy_death(
                con_modifier=10,
                damage_taken_this_round=0,
                uses_today=0,
                config=config,
            )
            if result.survived:
                assert result.exhaustion_gained == 0
                break


class TestHeroicAction:
    """Tests for Heroic Action mechanic."""

    def test_heroic_action_momentum_success(self):
        """Test heroic action with sufficient momentum."""
        config = SoloCombatConfig(heroic_action_cost="momentum", heroic_action_amount=1)

        result, new_momentum, new_stress = use_heroic_action(
            current_momentum=3,
            current_stress=0,
            stress_max=10,
            config=config,
        )

        assert result.success is True
        assert result.cost_type == "momentum"
        assert new_momentum == 2

    def test_heroic_action_momentum_insufficient(self):
        """Test heroic action with insufficient momentum."""
        config = SoloCombatConfig(heroic_action_cost="momentum", heroic_action_amount=2)

        result, new_momentum, new_stress = use_heroic_action(
            current_momentum=1,
            current_stress=0,
            stress_max=10,
            config=config,
        )

        assert result.success is False
        assert "Insufficient" in result.reason
        assert new_momentum == 1  # Unchanged

    def test_heroic_action_stress_cost(self):
        """Test heroic action with stress cost."""
        config = SoloCombatConfig(heroic_action_cost="stress")

        result, new_momentum, new_stress = use_heroic_action(
            current_momentum=0,
            current_stress=2,
            stress_max=10,
            config=config,
        )

        # Should succeed if stress cost doesn't exceed max
        if result.success:
            assert new_stress >= 3  # At least 1d4 = 1 stress added
            assert new_stress <= 6  # At most 1d4 = 4 stress added

    def test_heroic_action_free(self):
        """Test heroic action with no cost."""
        config = SoloCombatConfig(heroic_action_cost="free")

        result, new_momentum, new_stress = use_heroic_action(
            current_momentum=0,
            current_stress=0,
            stress_max=10,
            config=config,
        )

        assert result.success is True
        assert new_momentum == 0
        assert new_stress == 0

    def test_heroic_action_disabled(self):
        """Test heroic action when disabled."""
        config = SoloCombatConfig(heroic_action_enabled=False)

        result, _, _ = use_heroic_action(
            current_momentum=10,
            current_stress=0,
            stress_max=10,
            config=config,
        )

        assert result.success is False
        assert "disabled" in result.reason


class TestSoloRoundStart:
    """Tests for solo round start resolution."""

    def test_round_start_momentum_gain(self):
        """Test gaining momentum at round start."""
        config = SoloCombatConfig(combat_momentum_gain=1, use_fray_die=False)

        result, new_momentum = resolve_solo_round_start(
            actor_level=5,
            enemies=[],
            current_momentum=2,
            momentum_max=5,
            config=config,
        )

        assert result.momentum_gained == 1
        assert new_momentum == 3

    def test_round_start_momentum_capped(self):
        """Test momentum doesn't exceed max."""
        config = SoloCombatConfig(combat_momentum_gain=3, use_fray_die=False)

        result, new_momentum = resolve_solo_round_start(
            actor_level=5,
            enemies=[],
            current_momentum=4,
            momentum_max=5,
            config=config,
        )

        assert result.momentum_gained == 1  # Only gained 1 (capped)
        assert new_momentum == 5

    def test_round_start_with_fray(self):
        """Test round start with fray die."""
        enemies = [(uuid4(), 1), (uuid4(), 2)]
        config = SoloCombatConfig(use_fray_die=True)

        result, _ = resolve_solo_round_start(
            actor_level=5,
            enemies=enemies,
            current_momentum=0,
            momentum_max=5,
            config=config,
        )

        assert result.fray_result is not None
        assert result.fray_result.damage >= 1

    def test_round_start_no_fray_no_enemies(self):
        """Test round start without enemies."""
        config = SoloCombatConfig(use_fray_die=True)

        result, _ = resolve_solo_round_start(
            actor_level=5,
            enemies=[],
            current_momentum=0,
            momentum_max=5,
            config=config,
        )

        assert result.fray_result is None

    def test_round_start_message(self):
        """Test round start builds message."""
        enemies = [(uuid4(), 1)]
        config = SoloCombatConfig(combat_momentum_gain=1, use_fray_die=True)

        result, _ = resolve_solo_round_start(
            actor_level=5,
            enemies=enemies,
            current_momentum=0,
            momentum_max=5,
            config=config,
        )

        assert "momentum" in result.message.lower() or "fray" in result.message.lower()
