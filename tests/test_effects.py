"""
Tests for the Effect Pipeline service.
"""

from __future__ import annotations

from uuid import uuid4

from src.models.ability import (
    ConditionEffect,
    DamageEffect,
    HealingEffect,
    StatModifierEffect,
    Targeting,
    TargetingType,
    create_spell,
)
from src.services.effects import EffectPipeline


class TestEffectPipeline:
    """Tests for EffectPipeline service."""

    def test_get_combat_state_creates(self):
        """Test that get_combat_state creates state if not exists."""
        pipeline = EffectPipeline()
        entity_id = uuid4()
        universe_id = uuid4()

        state = pipeline.get_combat_state(entity_id, universe_id)
        assert state.entity_id == entity_id
        assert state.universe_id == universe_id

    def test_get_combat_state_returns_same(self):
        """Test that get_combat_state returns same state."""
        pipeline = EffectPipeline()
        entity_id = uuid4()
        universe_id = uuid4()

        state1 = pipeline.get_combat_state(entity_id, universe_id)
        state2 = pipeline.get_combat_state(entity_id, universe_id)
        assert state1 is state2


class TestApplyAbilityEffects:
    """Tests for apply_ability_effects method."""

    def test_apply_damage_ability(self):
        """Test applying a damage-dealing ability."""
        pipeline = EffectPipeline()
        caster_id = uuid4()
        target_id = uuid4()
        universe_id = uuid4()

        fireball = create_spell(
            name="Fireball",
            level=3,
            damage=DamageEffect(
                dice="8d6",
                damage_type="fire",
                save_ability="dex",
                save_for_half=True,
            ),
            targeting=Targeting(
                type=TargetingType.AREA_SPHERE,
                range_ft=150,
                area_size_ft=20,
            ),
        )

        result = pipeline.apply_ability_effects(
            ability=fireball,
            caster_id=caster_id,
            target_ids=[target_id],
            universe_id=universe_id,
        )

        assert result.success is True
        assert target_id in result.targets_affected
        assert str(target_id) in result.damage_dealt
        assert result.damage_dealt[str(target_id)] > 0

    def test_apply_healing_ability(self):
        """Test applying a healing ability."""
        pipeline = EffectPipeline()
        caster_id = uuid4()
        target_id = uuid4()
        universe_id = uuid4()

        cure_wounds = create_spell(
            name="Cure Wounds",
            level=1,
            healing=HealingEffect(dice="1d8", flat_amount=3),
            targeting=Targeting(type=TargetingType.SINGLE, range_ft=5),
        )

        result = pipeline.apply_ability_effects(
            ability=cure_wounds,
            caster_id=caster_id,
            target_ids=[target_id],
            universe_id=universe_id,
        )

        assert result.success is True
        assert str(target_id) in result.healing_done
        assert result.healing_done[str(target_id)] >= 4  # 1 + 3 minimum

    def test_apply_condition_ability(self):
        """Test applying an ability that inflicts a condition."""
        pipeline = EffectPipeline()
        caster_id = uuid4()
        target_id = uuid4()
        universe_id = uuid4()

        hold_person = create_spell(
            name="Hold Person",
            level=2,
            conditions=[
                ConditionEffect(
                    condition="paralyzed",
                    duration_type="until_save",
                    save_ability="wis",
                )
            ],
            targeting=Targeting(type=TargetingType.SINGLE, range_ft=60),
            requires_concentration=True,
        )

        # Provide a failing save
        result = pipeline.apply_ability_effects(
            ability=hold_person,
            caster_id=caster_id,
            target_ids=[target_id],
            universe_id=universe_id,
            caster_stat_modifier=3,
            target_saves={target_id: 5},  # Low save, will fail
        )

        assert result.success is True
        assert len(result.conditions_applied) == 1
        assert result.conditions_applied[0].condition_type == "paralyzed"
        assert result.concentration_started is True

    def test_apply_stat_modifier_ability(self):
        """Test applying an ability with stat modifiers."""
        pipeline = EffectPipeline()
        caster_id = uuid4()
        target_id = uuid4()
        universe_id = uuid4()

        shield = create_spell(
            name="Shield",
            level=1,
            stat_modifiers=[
                StatModifierEffect(
                    stat="ac",
                    modifier=5,
                    duration_type="rounds",
                    duration_value=1,
                )
            ],
            action_cost="reaction",
        )

        result = pipeline.apply_ability_effects(
            ability=shield,
            caster_id=caster_id,
            target_ids=[target_id],
            universe_id=universe_id,
        )

        assert result.success is True
        assert len(result.effects_applied) == 1
        assert result.effects_applied[0].stat == "ac"
        assert result.effects_applied[0].modifier == 5

    def test_concentration_replaces_existing(self):
        """Test that new concentration replaces old."""
        pipeline = EffectPipeline()
        caster_id = uuid4()
        target_id = uuid4()
        universe_id = uuid4()

        # First concentration spell
        spell1 = create_spell(
            name="Bless",
            level=1,
            stat_modifiers=[
                StatModifierEffect(stat="attack_rolls", modifier=2, duration_type="concentration")
            ],
            requires_concentration=True,
        )

        result1 = pipeline.apply_ability_effects(
            ability=spell1,
            caster_id=caster_id,
            target_ids=[target_id],
            universe_id=universe_id,
        )
        assert result1.concentration_started is True

        state = pipeline.get_combat_state(caster_id, universe_id)
        first_ability = state.concentrating_on

        # Second concentration spell
        spell2 = create_spell(
            name="Hold Person",
            level=2,
            conditions=[
                ConditionEffect(
                    condition="paralyzed", duration_type="until_save", save_ability="wis"
                )
            ],
            requires_concentration=True,
        )

        _result2 = pipeline.apply_ability_effects(
            ability=spell2,
            caster_id=caster_id,
            target_ids=[target_id],
            universe_id=universe_id,
            target_saves={target_id: 1},  # Failing save
        )

        assert state.concentrating_on != first_ability
        assert state.concentrating_on == spell2.id


class TestApplyCondition:
    """Tests for apply_condition method."""

    def test_apply_condition_no_save(self):
        """Test applying condition without save."""
        pipeline = EffectPipeline()
        entity_id = uuid4()
        universe_id = uuid4()

        condition = ConditionEffect(
            condition="prone",
            duration_type="rounds",
            duration_value=1,
        )

        result = pipeline.apply_condition(
            entity_id=entity_id,
            universe_id=universe_id,
            condition=condition,
        )

        assert result.success is True
        assert result.condition is not None
        assert result.condition.condition_type == "prone"

    def test_apply_condition_save_resisted(self):
        """Test that condition can be resisted with save."""
        pipeline = EffectPipeline()
        entity_id = uuid4()
        universe_id = uuid4()

        condition = ConditionEffect(
            condition="frightened",
            duration_type="until_save",
            save_ability="wis",
        )

        result = pipeline.apply_condition(
            entity_id=entity_id,
            universe_id=universe_id,
            condition=condition,
            save_dc=12,
            target_save=15,  # Beats DC 12
        )

        assert result.success is False
        assert result.resisted is True
        assert result.save_result is not None
        assert result.save_result.success is True


class TestTickCombatRound:
    """Tests for tick_combat_round method."""

    def test_tick_expires_conditions(self):
        """Test that tick expires timed conditions."""
        pipeline = EffectPipeline()
        entity_id = uuid4()
        universe_id = uuid4()

        # Add a condition with 1 round duration
        condition = ConditionEffect(
            condition="prone",
            duration_type="rounds",
            duration_value=1,
        )
        pipeline.apply_condition(entity_id, universe_id, condition)

        result = pipeline.tick_combat_round(entity_id, universe_id)

        assert "prone" in result.conditions_expired

    def test_tick_processes_saves(self):
        """Test that tick allows saves against conditions."""
        pipeline = EffectPipeline()
        entity_id = uuid4()
        universe_id = uuid4()

        # Add an until_save condition
        condition = ConditionEffect(
            condition="paralyzed",
            duration_type="until_save",
            save_ability="con",
        )
        pipeline.apply_condition(entity_id, universe_id, condition, save_dc=10, target_save=1)

        # Tick with high CON modifier to likely succeed save
        result = pipeline.tick_combat_round(entity_id, universe_id, ability_modifiers={"con": 10})

        # Should have attempted a save
        assert len(result.saves_attempted) == 1


class TestConcentration:
    """Tests for concentration mechanics."""

    def test_check_concentration_maintained(self):
        """Test concentration check when maintained."""
        pipeline = EffectPipeline()
        entity_id = uuid4()
        universe_id = uuid4()

        state = pipeline.get_combat_state(entity_id, universe_id)
        state.concentrating_on = uuid4()

        result = pipeline.check_concentration(
            entity_id=entity_id,
            universe_id=universe_id,
            damage_taken=10,  # DC 10
            con_modifier=5,
            proficiency=2,
        )

        # With +7 modifier and DC 10, likely to maintain
        # But we can't guarantee, so just check structure
        assert result.dc == 10
        assert result.modifier == 7

    def test_check_concentration_high_damage(self):
        """Test concentration check with high damage."""
        pipeline = EffectPipeline()
        entity_id = uuid4()
        universe_id = uuid4()
        ability_id = uuid4()

        state = pipeline.get_combat_state(entity_id, universe_id)
        state.concentrating_on = ability_id

        result = pipeline.check_concentration(
            entity_id=entity_id,
            universe_id=universe_id,
            damage_taken=40,  # DC 20
            con_modifier=0,
            proficiency=0,
        )

        assert result.dc == 20
        # Very likely to fail, but can't guarantee

    def test_check_concentration_not_concentrating(self):
        """Test concentration check when not concentrating."""
        pipeline = EffectPipeline()
        entity_id = uuid4()
        universe_id = uuid4()

        result = pipeline.check_concentration(
            entity_id=entity_id,
            universe_id=universe_id,
            damage_taken=50,
        )

        assert result.maintained is True
        assert result.dc == 0


class TestRemoveCondition:
    """Tests for condition removal."""

    def test_remove_condition_by_id(self):
        """Test removing condition by ID."""
        pipeline = EffectPipeline()
        entity_id = uuid4()
        universe_id = uuid4()

        condition = ConditionEffect(condition="prone", duration_type="rounds", duration_value=5)
        result = pipeline.apply_condition(entity_id, universe_id, condition)
        condition_id = result.condition.id

        removed = pipeline.remove_condition(entity_id, universe_id, condition_id)
        assert removed is True

        state = pipeline.get_combat_state(entity_id, universe_id)
        assert state.has_condition("prone") is False

    def test_remove_condition_by_type(self):
        """Test removing condition by type."""
        pipeline = EffectPipeline()
        entity_id = uuid4()
        universe_id = uuid4()

        condition = ConditionEffect(
            condition="frightened", duration_type="rounds", duration_value=3
        )
        pipeline.apply_condition(entity_id, universe_id, condition)

        removed = pipeline.remove_condition_by_type(entity_id, universe_id, "frightened")
        assert removed is True


class TestClearCombatState:
    """Tests for clearing combat state."""

    def test_clear_combat_state(self):
        """Test clearing combat state."""
        pipeline = EffectPipeline()
        entity_id = uuid4()
        universe_id = uuid4()

        # Create some state
        state = pipeline.get_combat_state(entity_id, universe_id)
        state.concentrating_on = uuid4()

        pipeline.clear_combat_state(entity_id, universe_id)

        # Getting state again should create fresh one
        new_state = pipeline.get_combat_state(entity_id, universe_id)
        assert new_state.concentrating_on is None


class TestEndConcentrationEffects:
    """Tests for ending concentration effects."""

    def test_end_all_concentration_effects(self):
        """Test ending all concentration effects from a caster."""
        pipeline = EffectPipeline()
        caster_id = uuid4()
        target1_id = uuid4()
        target2_id = uuid4()
        universe_id = uuid4()

        # Cast a concentration spell on two targets
        bless = create_spell(
            name="Bless",
            level=1,
            stat_modifiers=[
                StatModifierEffect(stat="attack_rolls", modifier=2, duration_type="concentration")
            ],
            requires_concentration=True,
        )

        pipeline.apply_ability_effects(
            ability=bless,
            caster_id=caster_id,
            target_ids=[target1_id, target2_id],
            universe_id=universe_id,
        )

        # End concentration
        affected = pipeline.end_all_concentration_effects(caster_id, universe_id)

        # Both targets should have had effects removed
        assert target1_id in affected
        assert target2_id in affected

        # Verify effects are gone
        state1 = pipeline.get_combat_state(target1_id, universe_id)
        state2 = pipeline.get_combat_state(target2_id, universe_id)
        assert len(state1.active_effects) == 0
        assert len(state2.active_effects) == 0
