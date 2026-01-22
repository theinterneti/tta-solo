"""
Tests for physics overlay models.
"""

from __future__ import annotations

from src.models.ability import AbilitySource
from src.models.physics_overlay import (
    CYBERPUNK_OVERLAY,
    HIGH_FANTASY_OVERLAY,
    HORROR_OVERLAY,
    LOW_MAGIC_OVERLAY,
    MYTHIC_OVERLAY,
    NEUTRAL_OVERLAY,
    OVERLAY_REGISTRY,
    POST_APOCALYPTIC_OVERLAY,
    ConditionModifier,
    PhysicsOverlay,
    SourceModifier,
    apply_condition_dc_overlay,
    apply_condition_duration_overlay,
    apply_healing_overlay,
    apply_stress_overlay,
    get_overlay,
    get_source_effect,
    list_overlays,
)


class TestSourceModifierEnum:
    """Tests for SourceModifier enum."""

    def test_all_modifiers_exist(self):
        """Test all expected modifiers exist."""
        assert SourceModifier.ENHANCED == "enhanced"
        assert SourceModifier.NORMAL == "normal"
        assert SourceModifier.RESTRICTED == "restricted"
        assert SourceModifier.FORBIDDEN == "forbidden"

    def test_modifier_count(self):
        """Test there are exactly 4 modifiers."""
        assert len(SourceModifier) == 4


class TestConditionModifier:
    """Tests for ConditionModifier model."""

    def test_condition_modifier_defaults(self):
        """Test condition modifier defaults."""
        mod = ConditionModifier()
        assert mod.duration_multiplier == 1.0
        assert mod.save_dc_modifier == 0
        assert mod.effect_intensity == 1.0

    def test_condition_modifier_custom(self):
        """Test custom condition modifier."""
        mod = ConditionModifier(
            duration_multiplier=2.0,
            save_dc_modifier=2,
            effect_intensity=1.5,
        )
        assert mod.duration_multiplier == 2.0
        assert mod.save_dc_modifier == 2
        assert mod.effect_intensity == 1.5


class TestPhysicsOverlay:
    """Tests for PhysicsOverlay model."""

    def test_overlay_creation(self):
        """Test creating an overlay."""
        overlay = PhysicsOverlay(
            name="Test Overlay",
            description="A test overlay",
            source_modifiers={
                AbilitySource.MAGIC: SourceModifier.ENHANCED,
            },
        )
        assert overlay.name == "Test Overlay"
        assert overlay.get_source_modifier(AbilitySource.MAGIC) == SourceModifier.ENHANCED

    def test_overlay_defaults(self):
        """Test overlay default values."""
        overlay = PhysicsOverlay(
            name="Minimal",
            description="Minimal overlay",
        )
        assert overlay.healing_multiplier == 1.0
        assert overlay.stress_multiplier == 1.0
        assert overlay.magic_side_effects is False
        assert overlay.tech_crit_bonus is False
        assert overlay.resource_scarcity is False
        assert overlay.allow_legendary_actions is False

    def test_get_source_modifier_default(self):
        """Test getting source modifier returns NORMAL by default."""
        overlay = PhysicsOverlay(name="Test", description="Test")
        assert overlay.get_source_modifier(AbilitySource.MAGIC) == SourceModifier.NORMAL

    def test_get_condition_modifier_default(self):
        """Test getting condition modifier returns default."""
        overlay = PhysicsOverlay(name="Test", description="Test")
        mod = overlay.get_condition_modifier("frightened")
        assert mod.duration_multiplier == 1.0

    def test_is_source_forbidden(self):
        """Test is_source_forbidden check."""
        overlay = PhysicsOverlay(
            name="Test",
            description="Test",
            source_modifiers={
                AbilitySource.MAGIC: SourceModifier.FORBIDDEN,
            },
        )
        assert overlay.is_source_forbidden(AbilitySource.MAGIC) is True
        assert overlay.is_source_forbidden(AbilitySource.TECH) is False

    def test_is_source_enhanced(self):
        """Test is_source_enhanced check."""
        overlay = PhysicsOverlay(
            name="Test",
            description="Test",
            source_modifiers={
                AbilitySource.TECH: SourceModifier.ENHANCED,
            },
        )
        assert overlay.is_source_enhanced(AbilitySource.TECH) is True
        assert overlay.is_source_enhanced(AbilitySource.MAGIC) is False

    def test_is_source_restricted(self):
        """Test is_source_restricted check."""
        overlay = PhysicsOverlay(
            name="Test",
            description="Test",
            source_modifiers={
                AbilitySource.MARTIAL: SourceModifier.RESTRICTED,
            },
        )
        assert overlay.is_source_restricted(AbilitySource.MARTIAL) is True
        assert overlay.is_source_restricted(AbilitySource.TECH) is False


class TestHighFantasyOverlay:
    """Tests for HIGH_FANTASY_OVERLAY."""

    def test_magic_enhanced(self):
        """Test magic is enhanced."""
        assert HIGH_FANTASY_OVERLAY.is_source_enhanced(AbilitySource.MAGIC)

    def test_healing_bonus(self):
        """Test healing multiplier is increased."""
        assert HIGH_FANTASY_OVERLAY.healing_multiplier == 1.25

    def test_stress_reduced(self):
        """Test stress multiplier is reduced."""
        assert HIGH_FANTASY_OVERLAY.stress_multiplier == 0.75

    def test_fear_duration_reduced(self):
        """Test frightened duration is reduced."""
        mod = HIGH_FANTASY_OVERLAY.get_condition_modifier("frightened")
        assert mod.duration_multiplier == 0.75


class TestLowMagicOverlay:
    """Tests for LOW_MAGIC_OVERLAY."""

    def test_magic_restricted(self):
        """Test magic is restricted."""
        assert LOW_MAGIC_OVERLAY.is_source_restricted(AbilitySource.MAGIC)

    def test_martial_enhanced(self):
        """Test martial is enhanced."""
        assert LOW_MAGIC_OVERLAY.is_source_enhanced(AbilitySource.MARTIAL)

    def test_magic_side_effects_enabled(self):
        """Test magic side effects are enabled."""
        assert LOW_MAGIC_OVERLAY.magic_side_effects is True


class TestCyberpunkOverlay:
    """Tests for CYBERPUNK_OVERLAY."""

    def test_magic_forbidden(self):
        """Test magic is forbidden."""
        assert CYBERPUNK_OVERLAY.is_source_forbidden(AbilitySource.MAGIC)

    def test_tech_enhanced(self):
        """Test tech is enhanced."""
        assert CYBERPUNK_OVERLAY.is_source_enhanced(AbilitySource.TECH)

    def test_tech_crit_bonus_enabled(self):
        """Test tech crit bonus is enabled."""
        assert CYBERPUNK_OVERLAY.tech_crit_bonus is True

    def test_system_shock_extended(self):
        """Test system_shock duration is extended."""
        mod = CYBERPUNK_OVERLAY.get_condition_modifier("system_shock")
        assert mod.duration_multiplier == 1.5


class TestHorrorOverlay:
    """Tests for HORROR_OVERLAY."""

    def test_tech_restricted(self):
        """Test tech is restricted."""
        assert HORROR_OVERLAY.is_source_restricted(AbilitySource.TECH)

    def test_healing_reduced(self):
        """Test healing is reduced."""
        assert HORROR_OVERLAY.healing_multiplier == 0.5

    def test_stress_increased(self):
        """Test stress is increased."""
        assert HORROR_OVERLAY.stress_multiplier == 1.5

    def test_fear_amplified(self):
        """Test frightened condition is amplified."""
        mod = HORROR_OVERLAY.get_condition_modifier("frightened")
        assert mod.duration_multiplier == 2.0
        assert mod.save_dc_modifier == 2


class TestMythicOverlay:
    """Tests for MYTHIC_OVERLAY."""

    def test_magic_and_martial_enhanced(self):
        """Test both magic and martial are enhanced."""
        assert MYTHIC_OVERLAY.is_source_enhanced(AbilitySource.MAGIC)
        assert MYTHIC_OVERLAY.is_source_enhanced(AbilitySource.MARTIAL)

    def test_legendary_actions_allowed(self):
        """Test legendary actions are allowed."""
        assert MYTHIC_OVERLAY.allow_legendary_actions is True

    def test_stress_reduced(self):
        """Test stress is greatly reduced."""
        assert MYTHIC_OVERLAY.stress_multiplier == 0.5


class TestPostApocalypticOverlay:
    """Tests for POST_APOCALYPTIC_OVERLAY."""

    def test_magic_and_tech_restricted(self):
        """Test both magic and tech are restricted."""
        assert POST_APOCALYPTIC_OVERLAY.is_source_restricted(AbilitySource.MAGIC)
        assert POST_APOCALYPTIC_OVERLAY.is_source_restricted(AbilitySource.TECH)

    def test_martial_enhanced(self):
        """Test martial is enhanced."""
        assert POST_APOCALYPTIC_OVERLAY.is_source_enhanced(AbilitySource.MARTIAL)

    def test_resource_scarcity_enabled(self):
        """Test resource scarcity is enabled."""
        assert POST_APOCALYPTIC_OVERLAY.resource_scarcity is True


class TestNeutralOverlay:
    """Tests for NEUTRAL_OVERLAY."""

    def test_all_sources_normal(self):
        """Test all sources are normal."""
        for source in AbilitySource:
            assert NEUTRAL_OVERLAY.get_source_modifier(source) == SourceModifier.NORMAL

    def test_default_multipliers(self):
        """Test all multipliers are default."""
        assert NEUTRAL_OVERLAY.healing_multiplier == 1.0
        assert NEUTRAL_OVERLAY.stress_multiplier == 1.0

    def test_no_special_flags(self):
        """Test no special flags are set."""
        assert NEUTRAL_OVERLAY.magic_side_effects is False
        assert NEUTRAL_OVERLAY.tech_crit_bonus is False
        assert NEUTRAL_OVERLAY.resource_scarcity is False
        assert NEUTRAL_OVERLAY.allow_legendary_actions is False


class TestOverlayRegistry:
    """Tests for OVERLAY_REGISTRY."""

    def test_all_overlays_registered(self):
        """Test all overlays are in registry."""
        assert "high_fantasy" in OVERLAY_REGISTRY
        assert "low_magic" in OVERLAY_REGISTRY
        assert "cyberpunk" in OVERLAY_REGISTRY
        assert "horror" in OVERLAY_REGISTRY
        assert "mythic" in OVERLAY_REGISTRY
        assert "post_apocalyptic" in OVERLAY_REGISTRY
        assert "neutral" in OVERLAY_REGISTRY

    def test_registry_count(self):
        """Test registry has expected count."""
        assert len(OVERLAY_REGISTRY) == 7


class TestGetOverlay:
    """Tests for get_overlay function."""

    def test_get_high_fantasy(self):
        """Test getting high fantasy overlay."""
        overlay = get_overlay("high_fantasy")
        assert overlay is not None
        assert overlay.name == "High Fantasy"

    def test_get_with_spaces(self):
        """Test getting overlay with space-to-underscore conversion."""
        overlay = get_overlay("post apocalyptic")
        assert overlay is not None
        assert overlay.name == "Post-Apocalyptic"

    def test_get_case_insensitive(self):
        """Test case-insensitive lookup."""
        overlay = get_overlay("CYBERPUNK")
        assert overlay is not None
        assert overlay.name == "Cyberpunk"

    def test_get_nonexistent(self):
        """Test getting nonexistent overlay."""
        overlay = get_overlay("nonexistent")
        assert overlay is None


class TestListOverlays:
    """Tests for list_overlays function."""

    def test_lists_all_overlays(self):
        """Test listing all overlays."""
        overlays = list_overlays()
        assert "high_fantasy" in overlays
        assert "cyberpunk" in overlays
        assert len(overlays) == 7


class TestApplyHealingOverlay:
    """Tests for apply_healing_overlay function."""

    def test_high_fantasy_healing(self):
        """Test high fantasy healing boost."""
        result = apply_healing_overlay(10, HIGH_FANTASY_OVERLAY)
        assert result == 12  # 10 * 1.25 = 12.5 -> 12

    def test_horror_healing(self):
        """Test horror healing reduction."""
        result = apply_healing_overlay(10, HORROR_OVERLAY)
        assert result == 5  # 10 * 0.5

    def test_null_overlay(self):
        """Test with null overlay."""
        result = apply_healing_overlay(10, None)
        assert result == 10


class TestApplyStressOverlay:
    """Tests for apply_stress_overlay function."""

    def test_horror_stress(self):
        """Test horror stress increase."""
        result = apply_stress_overlay(4, HORROR_OVERLAY)
        assert result == 6  # 4 * 1.5

    def test_mythic_stress(self):
        """Test mythic stress reduction."""
        result = apply_stress_overlay(4, MYTHIC_OVERLAY)
        assert result == 2  # 4 * 0.5

    def test_null_overlay(self):
        """Test with null overlay."""
        result = apply_stress_overlay(4, None)
        assert result == 4


class TestApplyConditionDurationOverlay:
    """Tests for apply_condition_duration_overlay function."""

    def test_horror_fear_duration(self):
        """Test horror extends fear duration."""
        result = apply_condition_duration_overlay("frightened", 5, HORROR_OVERLAY)
        assert result == 10  # 5 * 2.0

    def test_high_fantasy_fear_duration(self):
        """Test high fantasy shortens fear duration."""
        result = apply_condition_duration_overlay("frightened", 4, HIGH_FANTASY_OVERLAY)
        assert result == 3  # 4 * 0.75

    def test_unmodified_condition(self):
        """Test unmodified condition."""
        result = apply_condition_duration_overlay("poisoned", 5, HORROR_OVERLAY)
        assert result == 5  # No modifier for poisoned

    def test_null_overlay(self):
        """Test with null overlay."""
        result = apply_condition_duration_overlay("frightened", 5, None)
        assert result == 5


class TestApplyConditionDcOverlay:
    """Tests for apply_condition_dc_overlay function."""

    def test_horror_fear_dc(self):
        """Test horror increases fear save DC."""
        result = apply_condition_dc_overlay("frightened", 14, HORROR_OVERLAY)
        assert result == 16  # 14 + 2

    def test_unmodified_condition(self):
        """Test unmodified condition."""
        result = apply_condition_dc_overlay("stunned", 14, HORROR_OVERLAY)
        assert result == 14  # No modifier for stunned

    def test_null_overlay(self):
        """Test with null overlay."""
        result = apply_condition_dc_overlay("frightened", 14, None)
        assert result == 14


class TestGetSourceEffect:
    """Tests for get_source_effect function."""

    def test_forbidden_effect(self):
        """Test forbidden source effect."""
        effect = get_source_effect(AbilitySource.MAGIC, CYBERPUNK_OVERLAY)
        assert effect["forbidden"] is True
        assert effect["advantage"] is False
        assert effect["disadvantage"] is False
        assert effect["damage_dice_bonus"] == 0

    def test_enhanced_effect(self):
        """Test enhanced source effect."""
        effect = get_source_effect(AbilitySource.MAGIC, HIGH_FANTASY_OVERLAY)
        assert effect["forbidden"] is False
        assert effect["advantage"] is True
        assert effect["disadvantage"] is False
        assert effect["damage_dice_bonus"] == 1

    def test_restricted_effect(self):
        """Test restricted source effect."""
        effect = get_source_effect(AbilitySource.TECH, HORROR_OVERLAY)
        assert effect["forbidden"] is False
        assert effect["advantage"] is False
        assert effect["disadvantage"] is True
        assert effect["dc_modifier"] == -2

    def test_normal_effect(self):
        """Test normal source effect."""
        effect = get_source_effect(AbilitySource.MARTIAL, CYBERPUNK_OVERLAY)
        assert effect["forbidden"] is False
        assert effect["advantage"] is False
        assert effect["disadvantage"] is False
        assert effect["damage_dice_bonus"] == 0
        assert effect["dc_modifier"] == 0

    def test_null_overlay(self):
        """Test with null overlay."""
        effect = get_source_effect(AbilitySource.MAGIC, None)
        assert effect["forbidden"] is False
        assert effect["advantage"] is False
        assert effect["disadvantage"] is False


class TestFireballExamples:
    """Tests for the Fireball examples from the spec."""

    def test_fireball_high_fantasy(self):
        """Test fireball in High Fantasy (enhanced magic)."""
        effect = get_source_effect(AbilitySource.MAGIC, HIGH_FANTASY_OVERLAY)
        # Should get +1 damage die
        assert effect["damage_dice_bonus"] == 1
        assert effect["advantage"] is True

    def test_fireball_low_magic(self):
        """Test fireball in Low Magic (restricted magic)."""
        effect = get_source_effect(AbilitySource.MAGIC, LOW_MAGIC_OVERLAY)
        # Should get -2 to save DC
        assert effect["dc_modifier"] == -2
        assert effect["disadvantage"] is True
        # Also has magic side effects
        assert LOW_MAGIC_OVERLAY.magic_side_effects is True

    def test_fireball_cyberpunk(self):
        """Test fireball in Cyberpunk (forbidden magic)."""
        effect = get_source_effect(AbilitySource.MAGIC, CYBERPUNK_OVERLAY)
        # Cannot cast
        assert effect["forbidden"] is True


class TestFearExamples:
    """Tests for the Fear examples from the spec."""

    def test_fear_normal_setting(self):
        """Test fear in normal setting."""
        # Using neutral overlay
        duration = apply_condition_duration_overlay("frightened", 10, NEUTRAL_OVERLAY)
        dc = apply_condition_dc_overlay("frightened", 14, NEUTRAL_OVERLAY)
        assert duration == 10
        assert dc == 14

    def test_fear_horror_setting(self):
        """Test fear in horror setting."""
        duration = apply_condition_duration_overlay("frightened", 10, HORROR_OVERLAY)
        dc = apply_condition_dc_overlay("frightened", 14, HORROR_OVERLAY)
        # Duration: 2x
        assert duration == 20
        # DC: +2
        assert dc == 16
        # Stress: 1.5x
        stress = apply_stress_overlay(2, HORROR_OVERLAY)
        assert stress == 3
