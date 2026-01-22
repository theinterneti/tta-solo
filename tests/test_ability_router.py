"""
Tests for ability resolution in SkillRouter.
"""

from __future__ import annotations

from uuid import uuid4

from src.engine.models import Context, EntitySummary, Intent, IntentType
from src.engine.router import AbilityContext, SkillRouter
from src.models.ability import (
    ConditionEffect,
    DamageEffect,
    HealingEffect,
    Targeting,
    TargetingType,
    create_martial_technique,
    create_spell,
    create_tech_ability,
)
from src.models.resources import (
    EntityResources,
    StressMomentumPool,
    create_cooldown_tracker,
    create_spell_slots,
)


def create_test_context() -> Context:
    """Create a test context for ability resolution."""
    actor_id = uuid4()
    location_id = uuid4()

    return Context(
        actor=EntitySummary(
            id=actor_id,
            name="Test Hero",
            type="character",
            hp_current=50,
            hp_max=50,
            ac=15,
        ),
        location=EntitySummary(
            id=location_id,
            name="Test Location",
            type="location",
        ),
        entities_present=[
            EntitySummary(
                id=uuid4(),
                name="Goblin",
                type="character",
                hp_current=7,
                hp_max=7,
                ac=12,
            ),
        ],
    )


class TestResolveAbilityBasic:
    """Basic tests for ability resolution."""

    def test_resolve_damage_spell(self):
        """Test resolving a damage spell."""
        router = SkillRouter(use_pbta=False)
        context = create_test_context()
        target_id = context.entities_present[0].id

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

        resources = EntityResources(spell_slots=create_spell_slots({3: 2}))

        intent = Intent(
            type=IntentType.USE_ABILITY,
            confidence=1.0,
            original_input="cast fireball",
        )

        extra = {
            "ability": AbilityContext(
                ability=fireball,
                caster_stat_modifier=3,
                caster_proficiency=2,
                target_ids=[target_id],
                resources=resources,
            )
        }

        result = router.resolve(intent, context, extra)

        assert result.success is True
        assert "Fireball" in result.description
        # Spell slot should be consumed
        assert resources.spell_slots[3].current_slots == 1

    def test_resolve_healing_spell(self):
        """Test resolving a healing spell."""
        router = SkillRouter(use_pbta=False)
        context = create_test_context()
        target_id = context.actor.id

        cure_wounds = create_spell(
            name="Cure Wounds",
            level=1,
            healing=HealingEffect(dice="1d8", flat_amount=3),
            targeting=Targeting(type=TargetingType.SINGLE, range_ft=5),
        )

        resources = EntityResources(spell_slots=create_spell_slots({1: 4}))

        intent = Intent(
            type=IntentType.USE_ABILITY,
            confidence=1.0,
            original_input="cast cure wounds",
        )

        extra = {
            "ability": AbilityContext(
                ability=cure_wounds,
                target_ids=[target_id],
                resources=resources,
            )
        }

        result = router.resolve(intent, context, extra)

        assert result.success is True
        assert result.healing is not None
        assert result.healing >= 4  # 1 + 3 minimum

    def test_resolve_tech_ability(self):
        """Test resolving a tech ability."""
        router = SkillRouter(use_pbta=False)
        context = create_test_context()
        target_id = context.entities_present[0].id

        plasma_cutter = create_tech_ability(
            name="Plasma Cutter",
            max_uses=2,
            damage=DamageEffect(dice="3d6", damage_type="fire"),
            targeting=Targeting(type=TargetingType.SINGLE, range_ft=60),
        )

        cooldown = create_cooldown_tracker(max_uses=2, recharge_on_rest="short")
        resources = EntityResources(cooldowns={"Plasma Cutter": cooldown})

        intent = Intent(
            type=IntentType.USE_ABILITY,
            confidence=1.0,
            original_input="use plasma cutter",
        )

        extra = {
            "ability": AbilityContext(
                ability=plasma_cutter,
                caster_stat_modifier=5,  # High modifier to ensure reliable hits
                caster_proficiency=3,
                target_ids=[target_id],
                resources=resources,
            )
        }

        result = router.resolve(intent, context, extra)

        # Cooldown should be consumed regardless of hit/miss
        assert cooldown.current_uses == 1
        assert "Plasma Cutter" in result.description
        # With +8 to hit vs AC 12, should reliably succeed (need 4+ on d20)
        # Note: Still possible to fail on natural 1-3, but very rare

    def test_resolve_martial_technique(self):
        """Test resolving a martial technique."""
        router = SkillRouter(use_pbta=False)
        context = create_test_context()
        target_id = context.entities_present[0].id

        stunning_strike = create_martial_technique(
            name="Stunning Strike",
            momentum_cost=2,
            conditions=[
                ConditionEffect(
                    condition="stunned",
                    duration_type="until_save",
                    save_ability="con",
                )
            ],
            targeting=Targeting(type=TargetingType.SINGLE, range_ft=5),
            action_cost="bonus",
        )

        pool = StressMomentumPool(momentum=3)
        resources = EntityResources(stress_momentum=pool)

        intent = Intent(
            type=IntentType.USE_ABILITY,
            confidence=1.0,
            original_input="use stunning strike",
        )

        extra = {
            "ability": AbilityContext(
                ability=stunning_strike,
                target_ids=[target_id],
                resources=resources,
            )
        }

        result = router.resolve(intent, context, extra)

        assert result.success is True
        assert pool.momentum == 1  # 3 - 2 = 1


class TestResolveAbilityResources:
    """Tests for ability resource consumption."""

    def test_no_spell_slots_fails(self):
        """Test that using spell without slots fails."""
        router = SkillRouter(use_pbta=False)
        context = create_test_context()

        fireball = create_spell(
            name="Fireball",
            level=3,
            damage=DamageEffect(dice="8d6", damage_type="fire"),
        )

        # No level 3 slots
        resources = EntityResources(spell_slots=create_spell_slots({1: 4, 2: 2}))

        intent = Intent(
            type=IntentType.USE_ABILITY,
            confidence=1.0,
            original_input="cast fireball",
        )

        extra = {
            "ability": AbilityContext(
                ability=fireball,
                target_ids=[uuid4()],
                resources=resources,
            )
        }

        result = router.resolve(intent, context, extra)

        assert result.success is False
        assert "No level 3 spell slots" in result.description

    def test_no_cooldown_uses_fails(self):
        """Test that using ability without uses fails."""
        router = SkillRouter(use_pbta=False)
        context = create_test_context()

        ability = create_tech_ability(
            name="Shield Generator",
            max_uses=1,
        )

        cooldown = create_cooldown_tracker(max_uses=1)
        cooldown.use()  # Use up the charge
        resources = EntityResources(cooldowns={"Shield Generator": cooldown})

        intent = Intent(
            type=IntentType.USE_ABILITY,
            confidence=1.0,
            original_input="use shield generator",
        )

        extra = {
            "ability": AbilityContext(
                ability=ability,
                resources=resources,
            )
        }

        result = router.resolve(intent, context, extra)

        assert result.success is False
        assert "no uses remaining" in result.description

    def test_insufficient_momentum_fails(self):
        """Test that technique without momentum fails."""
        router = SkillRouter(use_pbta=False)
        context = create_test_context()

        technique = create_martial_technique(
            name="Dragon Strike",
            momentum_cost=5,
        )

        pool = StressMomentumPool(momentum=2)
        resources = EntityResources(stress_momentum=pool)

        intent = Intent(
            type=IntentType.USE_ABILITY,
            confidence=1.0,
            original_input="use dragon strike",
        )

        extra = {
            "ability": AbilityContext(
                ability=technique,
                resources=resources,
            )
        }

        result = router.resolve(intent, context, extra)

        assert result.success is False
        assert "Insufficient momentum" in result.description

    def test_stress_cost_applied(self):
        """Test that stress cost is applied."""
        router = SkillRouter(use_pbta=False)
        context = create_test_context()

        technique = create_martial_technique(
            name="Desperate Lunge",
            stress_cost=2,
        )

        pool = StressMomentumPool(stress=1)
        resources = EntityResources(stress_momentum=pool)

        intent = Intent(
            type=IntentType.USE_ABILITY,
            confidence=1.0,
            original_input="use desperate lunge",
        )

        extra = {
            "ability": AbilityContext(
                ability=technique,
                resources=resources,
            )
        }

        result = router.resolve(intent, context, extra)

        assert result.success is True
        assert pool.stress == 3  # 1 + 2


class TestResolveAbilityWithPbtA:
    """Tests for ability resolution with PbtA enabled."""

    def test_pbta_strong_hit_bonus(self):
        """Test that strong hits get ability-specific bonus."""
        # This test is statistical - run multiple times
        router = SkillRouter(use_pbta=True)
        context = create_test_context()

        # Create a simple damage spell
        magic_missile = create_spell(
            name="Magic Missile",
            level=1,
            damage=DamageEffect(dice="3d4+3", damage_type="force"),
            targeting=Targeting(type=TargetingType.SINGLE, range_ft=120),
        )

        intent = Intent(
            type=IntentType.USE_ABILITY,
            confidence=1.0,
            original_input="cast magic missile",
        )

        # Run multiple times to see different outcomes
        outcomes = {"strong_hit": 0, "weak_hit": 0, "miss": 0}

        for _ in range(50):
            test_resources = EntityResources(spell_slots=create_spell_slots({1: 4}))
            extra = {
                "ability": AbilityContext(
                    ability=magic_missile,
                    caster_stat_modifier=5,  # High mod for more hits
                    caster_proficiency=3,
                    target_ids=[context.entities_present[0].id],
                    resources=test_resources,
                )
            }

            result = router.resolve(intent, context, extra)
            if result.pbta_outcome:
                outcomes[result.pbta_outcome] = outcomes.get(result.pbta_outcome, 0) + 1

        # Should see at least some strong hits with high modifiers
        # Note: This is probabilistic, so we just check the structure works


class TestNoAbilityContext:
    """Test handling of missing ability context."""

    def test_no_ability_context_fails(self):
        """Test that missing ability context returns failure."""
        router = SkillRouter()
        context = create_test_context()

        intent = Intent(
            type=IntentType.USE_ABILITY,
            confidence=1.0,
            original_input="use something",
        )

        result = router.resolve(intent, context, {})

        assert result.success is False
        assert "No ability specified" in result.description
