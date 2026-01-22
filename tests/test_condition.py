"""
Tests for Condition and Combat State models.
"""

from __future__ import annotations

from uuid import uuid4

from src.models.condition import (
    ActiveEffect,
    ConditionType,
    DurationType,
    ModifierType,
    create_active_effect,
    create_combat_state,
    create_condition,
)


class TestConditionInstance:
    """Tests for ConditionInstance model."""

    def test_create_basic(self):
        """Test creating a basic condition."""
        entity_id = uuid4()
        universe_id = uuid4()

        condition = create_condition(
            entity_id=entity_id,
            universe_id=universe_id,
            condition_type="frightened",
            duration_type=DurationType.ROUNDS,
            duration_rounds=3,
        )

        assert condition.entity_id == entity_id
        assert condition.condition_type == "frightened"
        assert condition.duration_type == DurationType.ROUNDS
        assert condition.duration_remaining == 3

    def test_create_with_save(self):
        """Test creating a condition with save to end."""
        condition = create_condition(
            entity_id=uuid4(),
            universe_id=uuid4(),
            condition_type="stunned",
            duration_type=DurationType.UNTIL_SAVE,
            save_ability="con",
            save_dc=15,
        )

        assert condition.save_ability == "con"
        assert condition.save_dc == 15

    def test_tick_rounds(self):
        """Test ticking a rounds-based condition."""
        condition = create_condition(
            entity_id=uuid4(),
            universe_id=uuid4(),
            condition_type="prone",
            duration_type=DurationType.ROUNDS,
            duration_rounds=2,
        )

        assert condition.tick() is False
        assert condition.duration_remaining == 1

        assert condition.tick() is True  # Expired
        assert condition.duration_remaining == 0

    def test_tick_permanent(self):
        """Test that permanent conditions don't expire."""
        condition = create_condition(
            entity_id=uuid4(),
            universe_id=uuid4(),
            condition_type="petrified",
            duration_type=DurationType.PERMANENT,
        )

        assert condition.tick() is False
        assert condition.tick() is False

    def test_tick_until_save(self):
        """Test that until_save conditions don't auto-expire."""
        condition = create_condition(
            entity_id=uuid4(),
            universe_id=uuid4(),
            condition_type="charmed",
            duration_type=DurationType.UNTIL_SAVE,
            save_ability="wis",
            save_dc=14,
        )

        assert condition.tick() is False

    def test_attempt_save_success(self):
        """Test successful saving throw."""
        condition = create_condition(
            entity_id=uuid4(),
            universe_id=uuid4(),
            condition_type="paralyzed",
            duration_type=DurationType.UNTIL_SAVE,
            save_ability="con",
            save_dc=13,
        )

        # Roll 10 + 5 modifier = 15, beats DC 13
        assert condition.attempt_save(roll=10, modifier=5) is True

    def test_attempt_save_failure(self):
        """Test failed saving throw."""
        condition = create_condition(
            entity_id=uuid4(),
            universe_id=uuid4(),
            condition_type="paralyzed",
            duration_type=DurationType.UNTIL_SAVE,
            save_ability="con",
            save_dc=15,
        )

        # Roll 8 + 3 modifier = 11, fails DC 15
        assert condition.attempt_save(roll=8, modifier=3) is False

    def test_is_incapacitating(self):
        """Test checking if condition is incapacitating."""
        incap = create_condition(
            entity_id=uuid4(),
            universe_id=uuid4(),
            condition_type=ConditionType.STUNNED.value,
            duration_type=DurationType.ROUNDS,
            duration_rounds=1,
        )
        assert incap.is_incapacitating() is True

        prone = create_condition(
            entity_id=uuid4(),
            universe_id=uuid4(),
            condition_type=ConditionType.PRONE.value,
            duration_type=DurationType.ROUNDS,
            duration_rounds=1,
        )
        assert prone.is_incapacitating() is False


class TestActiveEffect:
    """Tests for ActiveEffect model."""

    def test_create_basic(self):
        """Test creating a basic effect."""
        effect = create_active_effect(
            entity_id=uuid4(),
            universe_id=uuid4(),
            stat="ac",
            modifier=2,
            duration_rounds=10,
        )

        assert effect.stat == "ac"
        assert effect.modifier == 2
        assert effect.modifier_type == ModifierType.BONUS
        assert effect.duration_remaining == 10

    def test_create_concentration(self):
        """Test creating a concentration effect."""
        effect = create_active_effect(
            entity_id=uuid4(),
            universe_id=uuid4(),
            stat="speed",
            modifier=10,
            requires_concentration=True,
        )

        assert effect.requires_concentration is True
        assert effect.duration_type == DurationType.CONCENTRATION

    def test_tick_normal(self):
        """Test ticking a normal effect."""
        effect = create_active_effect(
            entity_id=uuid4(),
            universe_id=uuid4(),
            stat="ac",
            modifier=5,
            duration_rounds=2,
        )

        assert effect.tick() is False
        assert effect.duration_remaining == 1

        assert effect.tick() is True  # Expired

    def test_tick_concentration(self):
        """Test that concentration effects don't auto-tick."""
        effect = create_active_effect(
            entity_id=uuid4(),
            universe_id=uuid4(),
            stat="ac",
            modifier=5,
            requires_concentration=True,
        )

        # Concentration effects don't expire on their own
        assert effect.tick() is False
        assert effect.tick() is False

    def test_apply_to_stat_bonus(self):
        """Test applying bonus to stat."""
        effect = ActiveEffect(
            entity_id=uuid4(),
            universe_id=uuid4(),
            stat="ac",
            modifier=3,
            modifier_type=ModifierType.BONUS,
        )
        assert effect.apply_to_stat(15) == 18

    def test_apply_to_stat_penalty(self):
        """Test applying penalty to stat."""
        effect = ActiveEffect(
            entity_id=uuid4(),
            universe_id=uuid4(),
            stat="speed",
            modifier=10,
            modifier_type=ModifierType.PENALTY,
        )
        assert effect.apply_to_stat(30) == 20

    def test_apply_to_stat_set(self):
        """Test setting stat to value."""
        effect = ActiveEffect(
            entity_id=uuid4(),
            universe_id=uuid4(),
            stat="str",
            modifier=19,
            modifier_type=ModifierType.SET,
        )
        assert effect.apply_to_stat(10) == 19


class TestEntityCombatState:
    """Tests for EntityCombatState model."""

    def test_create_basic(self):
        """Test creating a basic combat state."""
        state = create_combat_state(
            entity_id=uuid4(),
            universe_id=uuid4(),
            initiative=15,
        )

        assert state.initiative == 15
        assert len(state.conditions) == 0
        assert len(state.active_effects) == 0
        assert state.has_action is True

    def test_add_condition(self):
        """Test adding a condition."""
        state = create_combat_state(entity_id=uuid4(), universe_id=uuid4())
        condition = create_condition(
            entity_id=state.entity_id,
            universe_id=state.universe_id,
            condition_type="frightened",
            duration_type=DurationType.ROUNDS,
            duration_rounds=2,
        )

        state.add_condition(condition)
        assert state.has_condition("frightened") is True
        assert len(state.conditions) == 1

    def test_add_condition_exhaustion_stacks(self):
        """Test that exhaustion stacks."""
        state = create_combat_state(entity_id=uuid4(), universe_id=uuid4())

        exhaust1 = create_condition(
            entity_id=state.entity_id,
            universe_id=state.universe_id,
            condition_type=ConditionType.EXHAUSTION.value,
            duration_type=DurationType.UNTIL_REST,
        )
        state.add_condition(exhaust1)
        assert state.conditions[0].exhaustion_level == 1

        exhaust2 = create_condition(
            entity_id=state.entity_id,
            universe_id=state.universe_id,
            condition_type=ConditionType.EXHAUSTION.value,
            duration_type=DurationType.UNTIL_REST,
        )
        state.add_condition(exhaust2)
        assert len(state.conditions) == 1  # Still only one exhaustion
        assert state.conditions[0].exhaustion_level == 2

    def test_remove_condition(self):
        """Test removing a condition."""
        state = create_combat_state(entity_id=uuid4(), universe_id=uuid4())
        condition = create_condition(
            entity_id=state.entity_id,
            universe_id=state.universe_id,
            condition_type="prone",
            duration_type=DurationType.ROUNDS,
            duration_rounds=1,
        )
        state.add_condition(condition)

        assert state.remove_condition(condition.id) is True
        assert state.has_condition("prone") is False

    def test_remove_condition_by_type(self):
        """Test removing conditions by type."""
        state = create_combat_state(entity_id=uuid4(), universe_id=uuid4())
        state.add_condition(
            create_condition(
                entity_id=state.entity_id,
                universe_id=state.universe_id,
                condition_type="frightened",
                duration_type=DurationType.ROUNDS,
                duration_rounds=1,
            )
        )

        assert state.remove_condition_by_type("frightened") is True
        assert state.has_condition("frightened") is False

    def test_add_effect(self):
        """Test adding an active effect."""
        state = create_combat_state(entity_id=uuid4(), universe_id=uuid4())
        effect = create_active_effect(
            entity_id=state.entity_id,
            universe_id=state.universe_id,
            stat="ac",
            modifier=5,
            duration_rounds=10,
        )

        state.add_effect(effect)
        assert len(state.active_effects) == 1

    def test_get_stat_modifier(self):
        """Test calculating total stat modifier."""
        state = create_combat_state(entity_id=uuid4(), universe_id=uuid4())

        # Add +2 AC bonus
        state.add_effect(
            create_active_effect(
                entity_id=state.entity_id,
                universe_id=state.universe_id,
                stat="ac",
                modifier=2,
                duration_rounds=10,
            )
        )

        # Add another +3 AC bonus
        state.add_effect(
            create_active_effect(
                entity_id=state.entity_id,
                universe_id=state.universe_id,
                stat="ac",
                modifier=3,
                duration_rounds=10,
            )
        )

        assert state.get_stat_modifier("ac") == 5
        assert state.get_stat_modifier("speed") == 0

    def test_concentration(self):
        """Test concentration tracking."""
        state = create_combat_state(entity_id=uuid4(), universe_id=uuid4())
        ability_id = uuid4()

        state.concentrating_on = ability_id
        assert state.is_concentrating() is True

        lost = state.break_concentration()
        assert lost == ability_id
        assert state.is_concentrating() is False

    def test_is_incapacitated(self):
        """Test checking if entity is incapacitated."""
        state = create_combat_state(entity_id=uuid4(), universe_id=uuid4())
        assert state.is_incapacitated() is False

        state.add_condition(
            create_condition(
                entity_id=state.entity_id,
                universe_id=state.universe_id,
                condition_type=ConditionType.STUNNED.value,
                duration_type=DurationType.ROUNDS,
                duration_rounds=1,
            )
        )
        assert state.is_incapacitated() is True

    def test_start_turn(self):
        """Test resetting action economy."""
        state = create_combat_state(entity_id=uuid4(), universe_id=uuid4())
        state.has_action = False
        state.has_bonus_action = False
        state.has_reaction = False

        state.start_turn()
        assert state.has_action is True
        assert state.has_bonus_action is True
        assert state.has_reaction is True

    def test_end_turn(self):
        """Test processing end of turn."""
        state = create_combat_state(entity_id=uuid4(), universe_id=uuid4())

        # Add a condition that will expire
        condition = create_condition(
            entity_id=state.entity_id,
            universe_id=state.universe_id,
            condition_type="prone",
            duration_type=DurationType.ROUNDS,
            duration_rounds=1,
        )
        state.add_condition(condition)

        # Add an effect that will expire
        effect = create_active_effect(
            entity_id=state.entity_id,
            universe_id=state.universe_id,
            stat="ac",
            modifier=2,
            duration_rounds=1,
        )
        state.add_effect(effect)

        expired = state.end_turn()

        assert len(expired) == 1
        assert expired[0].condition_type == "prone"
        assert len(state.conditions) == 0
        assert len(state.active_effects) == 0

    def test_death_saves(self):
        """Test death save tracking."""
        state = create_combat_state(entity_id=uuid4(), universe_id=uuid4())

        state.death_saves_success = 2
        state.death_saves_failure = 1

        assert state.death_saves_success == 2
        assert state.death_saves_failure == 1
