"""Tests for /use ability command."""

from __future__ import annotations

from src.models.ability import (
    Ability,
    AbilitySource,
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


class TestStarterAbilities:
    """Test that starter abilities are properly configured."""

    def test_second_wind_ability(self):
        """Test Second Wind ability properties."""
        second_wind = Ability(
            name="Second Wind",
            description="Draw on your stamina to heal yourself.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.COOLDOWN,
            mechanism_details={"max_uses": 1, "recharge_on_rest": "short"},
            healing=HealingEffect(dice="1d10", flat_amount=1),
            targeting=Targeting(type=TargetingType.SELF),
            action_cost="bonus",
        )

        assert second_wind.name == "Second Wind"
        assert second_wind.source == AbilitySource.MARTIAL
        assert second_wind.mechanism == MechanismType.COOLDOWN
        assert second_wind.healing is not None
        assert second_wind.healing.dice == "1d10"
        assert second_wind.healing.flat_amount == 1
        assert second_wind.targeting.type == TargetingType.SELF

    def test_power_strike_ability(self):
        """Test Power Strike ability properties."""
        power_strike = Ability(
            name="Power Strike",
            description="A powerful melee attack that deals extra damage.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.FREE,
            mechanism_details={},
            damage=DamageEffect(dice="1d8", damage_type="bludgeoning"),
            targeting=Targeting(type=TargetingType.SINGLE, range_ft=5),
            action_cost="action",
        )

        assert power_strike.name == "Power Strike"
        assert power_strike.source == AbilitySource.MARTIAL
        assert power_strike.mechanism == MechanismType.FREE
        assert power_strike.damage is not None
        assert power_strike.damage.dice == "1d8"
        assert power_strike.damage.damage_type == "bludgeoning"
        assert power_strike.targeting.range_ft == 5

    def test_shield_wall_ability(self):
        """Test Shield Wall ability properties - defensive stance with +2 AC."""
        shield_wall = Ability(
            name="Shield Wall",
            description="Raise your shield in a defensive stance, gaining +2 AC until your next turn.",
            source=AbilitySource.MARTIAL,
            subtype="stance",
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
            tags=["martial", "defensive", "stance"],
        )

        assert shield_wall.name == "Shield Wall"
        assert shield_wall.source == AbilitySource.MARTIAL
        assert shield_wall.mechanism == MechanismType.FREE
        assert shield_wall.action_cost == "bonus"
        assert len(shield_wall.stat_modifiers) == 1
        assert shield_wall.stat_modifiers[0].stat == "ac"
        assert shield_wall.stat_modifiers[0].modifier == 2
        assert shield_wall.stat_modifiers[0].duration_type == "rounds"
        assert shield_wall.stat_modifiers[0].duration_value == 1
        assert "defensive" in shield_wall.tags

    def test_cleave_ability(self):
        """Test Cleave ability properties - multi-target attack costing momentum."""
        cleave = Ability(
            name="Cleave",
            description="Swing your weapon in a wide arc, striking up to 2 adjacent enemies.",
            source=AbilitySource.MARTIAL,
            subtype="maneuver",
            mechanism=MechanismType.MOMENTUM,
            mechanism_details={"momentum_cost": 2},
            damage=DamageEffect(dice="1d8", damage_type="slashing"),
            targeting=Targeting(type=TargetingType.MULTIPLE, range_ft=5, max_targets=2),
            action_cost="action",
            tags=["martial", "attack", "aoe"],
        )

        assert cleave.name == "Cleave"
        assert cleave.source == AbilitySource.MARTIAL
        assert cleave.mechanism == MechanismType.MOMENTUM
        assert cleave.mechanism_details["momentum_cost"] == 2
        assert cleave.damage is not None
        assert cleave.damage.dice == "1d8"
        assert cleave.damage.damage_type == "slashing"
        assert cleave.targeting.type == TargetingType.MULTIPLE
        assert cleave.targeting.max_targets == 2
        assert "aoe" in cleave.tags

    def test_rally_ability(self):
        """Test Rally ability properties - stress recovery ability."""
        rally = Ability(
            name="Rally",
            description="Steel your nerves and recover from the stress of battle.",
            source=AbilitySource.MARTIAL,
            subtype="maneuver",
            mechanism=MechanismType.COOLDOWN,
            mechanism_details={"max_uses": 1, "recharge_on_rest": "short"},
            targeting=Targeting(type=TargetingType.SELF),
            action_cost="action",
            tags=["martial", "recovery", "stress"],
        )

        assert rally.name == "Rally"
        assert rally.source == AbilitySource.MARTIAL
        assert rally.mechanism == MechanismType.COOLDOWN
        assert rally.mechanism_details["max_uses"] == 1
        assert rally.mechanism_details["recharge_on_rest"] == "short"
        assert rally.targeting.type == TargetingType.SELF
        assert "stress" in rally.tags
        assert "recovery" in rally.tags


class TestRallyStressRecovery:
    """Test Rally ability's stress recovery functionality."""

    def test_rally_reduces_stress(self):
        """Test that Rally reduces stress by 1."""
        pool = StressMomentumPool(stress=3, stress_max=10)
        reduced = pool.reduce_stress(1)

        assert reduced == 1
        assert pool.stress == 2

    def test_rally_at_zero_stress(self):
        """Test Rally when already at zero stress."""
        pool = StressMomentumPool(stress=0, stress_max=10)
        reduced = pool.reduce_stress(1)

        assert reduced == 0
        assert pool.stress == 0


class TestCleaveMultiTarget:
    """Test Cleave ability's multi-target mechanics."""

    def test_cleave_targets_multiple(self):
        """Test that Cleave can target multiple enemies."""
        cleave = Ability(
            name="Cleave",
            description="Attack up to 2 enemies.",
            source=AbilitySource.MARTIAL,
            mechanism=MechanismType.MOMENTUM,
            mechanism_details={"momentum_cost": 2},
            damage=DamageEffect(dice="1d8", damage_type="slashing"),
            targeting=Targeting(type=TargetingType.MULTIPLE, range_ft=5, max_targets=2),
            action_cost="action",
        )

        assert cleave.targeting.type == TargetingType.MULTIPLE
        assert cleave.targeting.max_targets == 2

    def test_cleave_momentum_cost(self):
        """Test that Cleave costs 2 momentum."""
        pool = StressMomentumPool(momentum=3, momentum_max=5)

        # Spend momentum for Cleave
        success = pool.spend_momentum(2)

        assert success
        assert pool.momentum == 1

    def test_cleave_insufficient_momentum(self):
        """Test that Cleave fails without enough momentum."""
        pool = StressMomentumPool(momentum=1, momentum_max=5)

        # Try to spend 2 momentum with only 1
        success = pool.spend_momentum(2)

        assert not success
        assert pool.momentum == 1  # Unchanged
