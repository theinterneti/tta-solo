"""Tests for /use ability command."""

from __future__ import annotations

from src.models.ability import (
    Ability,
    AbilitySource,
    ConditionEffect,
    DamageEffect,
    HealingEffect,
    MechanismType,
    StatModifierEffect,
    Targeting,
    TargetingType,
)
from src.models.resources import CooldownTracker, EntityResources, StressMomentumPool


class TestEntityResourcesAbilities:
    """Test ability lookup and management in EntityResources."""

    def test_get_ability_exact_match(self):
        """Test exact name match (case-insensitive)."""
        ability = Ability(
            name="Second Wind",
            description="Heal yourself",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.FREE,
            mechanism_details={},
            targeting=Targeting(type=TargetingType.SELF),
        )
        resources = EntityResources(abilities=[ability])

        assert resources.get_ability("Second Wind") is ability
        assert resources.get_ability("second wind") is ability
        assert resources.get_ability("SECOND WIND") is ability

    def test_get_ability_prefix_match(self):
        """Test prefix matching."""
        ability = Ability(
            name="Power Strike",
            description="Attack with power",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.FREE,
            mechanism_details={},
            targeting=Targeting(type=TargetingType.SINGLE, range_ft=5),
        )
        resources = EntityResources(abilities=[ability])

        assert resources.get_ability("power") is ability
        assert resources.get_ability("Power St") is ability

    def test_get_ability_not_found(self):
        """Test ability not found."""
        ability = Ability(
            name="Fireball",
            description="Throw fire",
            source=AbilitySource.MAGIC,
            mechanism=MechanismType.SLOTS,
            mechanism_details={"level": 3},
            targeting=Targeting(type=TargetingType.AREA_SPHERE, range_ft=150, area_size_ft=20),
        )
        resources = EntityResources(abilities=[ability])

        assert resources.get_ability("Lightning Bolt") is None
        assert resources.get_ability("Bolt") is None  # Doesn't match start of "Fireball"

    def test_list_abilities(self):
        """Test listing ability names."""
        abilities = [
            Ability(
                name="Second Wind",
                description="Heal",
                source=AbilitySource.MARTIAL,
                mechanism=MechanismType.FREE,
                mechanism_details={},
                targeting=Targeting(type=TargetingType.SELF),
            ),
            Ability(
                name="Power Strike",
                description="Attack",
                source=AbilitySource.MARTIAL,
                mechanism=MechanismType.FREE,
                mechanism_details={},
                targeting=Targeting(type=TargetingType.SINGLE, range_ft=5),
            ),
        ]
        resources = EntityResources(abilities=abilities)

        names = resources.list_abilities()
        assert names == ["Second Wind", "Power Strike"]

    def test_empty_abilities(self):
        """Test resources with no abilities."""
        resources = EntityResources()

        assert resources.get_ability("anything") is None
        assert resources.list_abilities() == []


class TestAbilityResourceTracking:
    """Test resource consumption for abilities."""

    def test_spell_slots_consumed(self):
        """Test spell slot consumption."""
        from src.models.resources import SpellSlotTracker

        resources = EntityResources(
            spell_slots={
                1: SpellSlotTracker(level=1, max_slots=4, current_slots=4),
                3: SpellSlotTracker(level=3, max_slots=2, current_slots=2),
            }
        )

        assert resources.has_spell_slot(1) is True
        assert resources.has_spell_slot(3) is True

        resources.use_spell_slot(3)
        assert resources.spell_slots[3].current_slots == 1

        resources.use_spell_slot(3)
        assert resources.spell_slots[3].current_slots == 0
        assert resources.has_spell_slot(3) is False

    def test_cooldown_tracking(self):
        """Test cooldown usage tracking."""
        cooldown = CooldownTracker(max_uses=1, current_uses=1, recharge_on_rest="short")
        resources = EntityResources(cooldowns={"Second Wind": cooldown})

        cd = resources.get_cooldown("Second Wind")
        assert cd is not None
        assert cd.has_uses() is True

        cd.use()
        assert cd.has_uses() is False

    def test_momentum_consumption(self):
        """Test momentum spending."""
        pool = StressMomentumPool(momentum=3, momentum_max=5)
        resources = EntityResources(stress_momentum=pool)

        assert resources.stress_momentum.spend_momentum(2) is True
        assert resources.stress_momentum.momentum == 1

        assert resources.stress_momentum.spend_momentum(2) is False
        assert resources.stress_momentum.momentum == 1  # Unchanged

    def test_stress_accumulation(self):
        """Test stress accumulation."""
        pool = StressMomentumPool(stress=0, stress_max=10)
        resources = EntityResources(stress_momentum=pool)

        resources.stress_momentum.add_stress(3)
        assert resources.stress_momentum.stress == 3

        resources.stress_momentum.add_stress(2)
        assert resources.stress_momentum.stress == 5


class TestNarrativeAbilities:
    """Test narrative-first abilities - universe-agnostic names and effects."""

    # =========================================================================
    # Recovery Abilities
    # =========================================================================

    def test_catch_your_breath_ability(self):
        """Test Catch Your Breath - recovery ability."""
        ability = Ability(
            name="Catch Your Breath",
            description="Draw on your inner reserves to recover from injury.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.COOLDOWN,
            mechanism_details={"max_uses": 1, "recharge_on_rest": "short"},
            healing=HealingEffect(dice="1d10", flat_amount=1),
            targeting=Targeting(type=TargetingType.SELF),
            action_cost="bonus",
            tags=["recovery", "healing", "self"],
        )

        assert ability.name == "Catch Your Breath"
        assert ability.mechanism == MechanismType.COOLDOWN
        assert ability.healing is not None
        assert ability.healing.dice == "1d10"
        assert "recovery" in ability.tags

    def test_steel_your_nerves_ability(self):
        """Test Steel Your Nerves - stress recovery ability."""
        ability = Ability(
            name="Steel Your Nerves",
            description="Center yourself and shake off fear and doubt.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.COOLDOWN,
            mechanism_details={"max_uses": 1, "recharge_on_rest": "short"},
            targeting=Targeting(type=TargetingType.SELF),
            action_cost="action",
            tags=["recovery", "stress", "mental"],
        )

        assert ability.name == "Steel Your Nerves"
        assert ability.mechanism == MechanismType.COOLDOWN
        assert "stress" in ability.tags
        assert "recovery" in ability.tags

    # =========================================================================
    # Offensive Abilities
    # =========================================================================

    def test_mighty_blow_ability(self):
        """Test Mighty Blow - powerful attack."""
        ability = Ability(
            name="Mighty Blow",
            description="Channel everything into a devastating strike.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.FREE,
            mechanism_details={},
            damage=DamageEffect(dice="1d8", damage_type="bludgeoning"),
            targeting=Targeting(type=TargetingType.SINGLE, range_ft=5),
            action_cost="action",
            tags=["attack", "power", "melee"],
        )

        assert ability.name == "Mighty Blow"
        assert ability.damage is not None
        assert ability.damage.dice == "1d8"
        assert "attack" in ability.tags

    def test_sweeping_strike_ability(self):
        """Test Sweeping Strike - multi-target attack."""
        ability = Ability(
            name="Sweeping Strike",
            description="A wide attack catching multiple foes.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.MOMENTUM,
            mechanism_details={"momentum_cost": 2},
            damage=DamageEffect(dice="1d8", damage_type="slashing"),
            targeting=Targeting(type=TargetingType.MULTIPLE, range_ft=5, max_targets=2),
            action_cost="action",
            tags=["attack", "area", "momentum"],
        )

        assert ability.name == "Sweeping Strike"
        assert ability.mechanism == MechanismType.MOMENTUM
        assert ability.mechanism_details["momentum_cost"] == 2
        assert ability.targeting.type == TargetingType.MULTIPLE
        assert ability.targeting.max_targets == 2
        assert "area" in ability.tags

    def test_exploit_weakness_ability(self):
        """Test Exploit Weakness - precision damage."""
        ability = Ability(
            name="Exploit Weakness",
            description="Find the gap and strike true.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.FREE,
            mechanism_details={},
            damage=DamageEffect(dice="2d6", damage_type="piercing"),
            targeting=Targeting(type=TargetingType.SINGLE, range_ft=5),
            action_cost="free",
            tags=["attack", "precision", "tactical"],
            prerequisites=["Target must be distracted or vulnerable"],
        )

        assert ability.name == "Exploit Weakness"
        assert ability.damage is not None
        assert ability.damage.dice == "2d6"
        assert "precision" in ability.tags
        assert len(ability.prerequisites) == 1

    # =========================================================================
    # Defensive Abilities
    # =========================================================================

    def test_brace_for_impact_ability(self):
        """Test Brace for Impact - defensive stance."""
        ability = Ability(
            name="Brace for Impact",
            description="Prepare to absorb punishment.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.FREE,
            mechanism_details={},
            stat_modifiers=[
                StatModifierEffect(
                    stat="ac",
                    modifier=2,
                    duration_type="rounds",
                    duration_value=1,
                )
            ],
            targeting=Targeting(type=TargetingType.SELF),
            action_cost="bonus",
            tags=["defensive", "protection", "stance"],
        )

        assert ability.name == "Brace for Impact"
        assert len(ability.stat_modifiers) == 1
        assert ability.stat_modifiers[0].stat == "ac"
        assert ability.stat_modifiers[0].modifier == 2
        assert "defensive" in ability.tags

    def test_slip_away_ability(self):
        """Test Slip Away - evasion ability."""
        ability = Ability(
            name="Slip Away",
            description="Extract yourself from danger.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.FREE,
            mechanism_details={},
            targeting=Targeting(type=TargetingType.SELF),
            action_cost="bonus",
            tags=["defensive", "movement", "evasion"],
        )

        assert ability.name == "Slip Away"
        assert ability.action_cost == "bonus"
        assert "movement" in ability.tags
        assert "evasion" in ability.tags

    # =========================================================================
    # Control Abilities
    # =========================================================================

    def test_dirty_trick_ability(self):
        """Test Dirty Trick - control/stun ability."""
        ability = Ability(
            name="Dirty Trick",
            description="Fight without honor when survival demands it.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.MOMENTUM,
            mechanism_details={"momentum_cost": 3},
            conditions=[
                ConditionEffect(
                    condition="stunned",
                    duration_type="rounds",
                    duration_value=1,
                    save_ability="con",
                )
            ],
            targeting=Targeting(type=TargetingType.SINGLE, range_ft=5),
            action_cost="action",
            tags=["control", "debuff", "tactical"],
        )

        assert ability.name == "Dirty Trick"
        assert ability.mechanism == MechanismType.MOMENTUM
        assert ability.mechanism_details["momentum_cost"] == 3
        assert len(ability.conditions) == 1
        assert ability.conditions[0].condition == "stunned"
        assert "control" in ability.tags


class TestStressRecovery:
    """Test stress recovery mechanics."""

    def test_stress_reduces(self):
        """Test that stress can be reduced."""
        pool = StressMomentumPool(stress=3, stress_max=10)
        reduced = pool.reduce_stress(1)

        assert reduced == 1
        assert pool.stress == 2

    def test_stress_at_zero(self):
        """Test stress reduction when already at zero."""
        pool = StressMomentumPool(stress=0, stress_max=10)
        reduced = pool.reduce_stress(1)

        assert reduced == 0
        assert pool.stress == 0


class TestMultiTargetAbilities:
    """Test multi-target ability mechanics (Sweeping Strike)."""

    def test_sweeping_strike_targets_multiple(self):
        """Test that Sweeping Strike can target multiple enemies."""
        ability = Ability(
            name="Sweeping Strike",
            description="Attack up to 2 enemies.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.MOMENTUM,
            mechanism_details={"momentum_cost": 2},
            damage=DamageEffect(dice="1d8", damage_type="slashing"),
            targeting=Targeting(type=TargetingType.MULTIPLE, range_ft=5, max_targets=2),
            action_cost="action",
        )

        assert ability.targeting.type == TargetingType.MULTIPLE
        assert ability.targeting.max_targets == 2

    def test_sweeping_strike_momentum_cost(self):
        """Test that Sweeping Strike costs 2 momentum."""
        pool = StressMomentumPool(momentum=3, momentum_max=5)

        success = pool.spend_momentum(2)

        assert success
        assert pool.momentum == 1

    def test_sweeping_strike_insufficient_momentum(self):
        """Test that Sweeping Strike fails without enough momentum."""
        pool = StressMomentumPool(momentum=1, momentum_max=5)

        success = pool.spend_momentum(2)

        assert not success
        assert pool.momentum == 1


class TestControlAbilities:
    """Test control ability mechanics (Dirty Trick)."""

    def test_dirty_trick_stun(self):
        """Test Dirty Trick applies stun condition."""
        ability = Ability(
            name="Dirty Trick",
            description="Stun your opponent.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.MOMENTUM,
            mechanism_details={"momentum_cost": 3},
            conditions=[
                ConditionEffect(
                    condition="stunned",
                    duration_type="rounds",
                    duration_value=1,
                    save_ability="con",
                )
            ],
            targeting=Targeting(type=TargetingType.SINGLE, range_ft=5),
            action_cost="action",
            tags=["control", "debuff", "tactical"],
        )

        assert ability.name == "Dirty Trick"
        assert ability.mechanism == MechanismType.MOMENTUM
        assert ability.mechanism_details["momentum_cost"] == 3
        assert len(ability.conditions) == 1
        assert ability.conditions[0].condition == "stunned"
        assert "control" in ability.tags

    def test_dirty_trick_costs_3_momentum(self):
        """Test that Dirty Trick requires 3 momentum."""
        pool = StressMomentumPool(momentum=4, momentum_max=5)

        success = pool.spend_momentum(3)

        assert success
        assert pool.momentum == 1

    def test_dirty_trick_insufficient_momentum(self):
        """Test Dirty Trick fails without enough momentum."""
        pool = StressMomentumPool(momentum=2, momentum_max=5)

        success = pool.spend_momentum(3)

        assert not success
        assert pool.momentum == 2

    def test_dirty_trick_exactly_3_momentum(self):
        """Test Dirty Trick with exactly 3 momentum."""
        pool = StressMomentumPool(momentum=3, momentum_max=5)

        success = pool.spend_momentum(3)

        assert success
        assert pool.momentum == 0
