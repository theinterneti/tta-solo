"""
Effect Pipeline Service for TTA-Solo.

Handles application and management of conditions, effects, and combat state.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from uuid import UUID

from pydantic import BaseModel, Field

from src.models.ability import Ability, ConditionEffect, StatModifierEffect
from src.models.condition import (
    ActiveEffect,
    ConditionInstance,
    DurationType,
    EntityCombatState,
    ModifierType,
    create_active_effect,
    create_condition,
)
from src.skills.dice import roll_dice

# =============================================================================
# Result Models
# =============================================================================


class SaveAttemptResult(BaseModel):
    """Result of a saving throw attempt."""

    entity_id: UUID
    save_type: str  # "end_condition", "avoid_effect", etc.
    ability: str
    roll: int
    modifier: int
    total: int
    dc: int
    success: bool
    condition_type: str | None = None


class ConditionApplicationResult(BaseModel):
    """Result of applying a condition."""

    success: bool
    condition: ConditionInstance | None = None
    resisted: bool = Field(default=False, description="True if target saved against it")
    save_result: SaveAttemptResult | None = None
    already_has_condition: bool = False


class EffectApplicationResult(BaseModel):
    """Result of applying an ability's effects to targets."""

    success: bool
    ability_name: str
    targets_affected: list[UUID] = Field(default_factory=list)
    damage_dealt: dict[str, int] = Field(
        default_factory=dict, description="UUID str -> damage amount"
    )
    healing_done: dict[str, int] = Field(
        default_factory=dict, description="UUID str -> healing amount"
    )
    conditions_applied: list[ConditionInstance] = Field(default_factory=list)
    effects_applied: list[ActiveEffect] = Field(default_factory=list)
    saves_made: dict[str, bool] = Field(
        default_factory=dict, description="UUID str -> save success"
    )
    concentration_started: bool = False
    error: str | None = None


class RoundTickResult(BaseModel):
    """Result of processing a round tick for an entity."""

    entity_id: UUID
    conditions_expired: list[str] = Field(default_factory=list)
    effects_expired: list[str] = Field(default_factory=list)
    saves_attempted: list[SaveAttemptResult] = Field(default_factory=list)
    dot_damage: int = Field(default=0, description="Damage over time taken")


class ConcentrationCheckResult(BaseModel):
    """Result of a concentration check."""

    maintained: bool
    roll: int
    modifier: int
    total: int
    dc: int
    ability_lost: UUID | None = None
    ability_name: str | None = None


# =============================================================================
# Effect Pipeline Service
# =============================================================================


@dataclass
class EffectPipeline:
    """
    Service for applying and managing effects, conditions, and combat state.

    This is the core service for resolving ability effects on targets.
    """

    # Combat states are stored by (entity_id, universe_id) key
    combat_states: dict[tuple[UUID, UUID], EntityCombatState] = field(default_factory=dict)

    def get_combat_state(
        self,
        entity_id: UUID,
        universe_id: UUID,
    ) -> EntityCombatState:
        """
        Get or create combat state for an entity.

        Args:
            entity_id: Entity to get state for
            universe_id: Universe context

        Returns:
            EntityCombatState for the entity
        """
        key = (entity_id, universe_id)
        if key not in self.combat_states:
            self.combat_states[key] = EntityCombatState(
                entity_id=entity_id,
                universe_id=universe_id,
            )
        return self.combat_states[key]

    def apply_ability_effects(
        self,
        ability: Ability,
        caster_id: UUID,
        target_ids: list[UUID],
        universe_id: UUID,
        caster_stat_modifier: int = 0,
        caster_proficiency: int = 2,
        target_saves: dict[UUID, int] | None = None,
        target_modifiers: dict[UUID, int] | None = None,
    ) -> EffectApplicationResult:
        """
        Apply all effects from an ability to targets.

        Args:
            ability: The ability being used
            caster_id: Entity using the ability
            target_ids: Entities being targeted
            universe_id: Universe context
            caster_stat_modifier: Caster's spellcasting/ability modifier
            caster_proficiency: Caster's proficiency bonus
            target_saves: Pre-rolled saves for each target (UUID -> total)
            target_modifiers: Save modifiers for each target (UUID -> modifier)

        Returns:
            EffectApplicationResult with all effects applied
        """
        result = EffectApplicationResult(
            success=True,
            ability_name=ability.name,
        )

        # Calculate save DC if needed
        save_dc = 8 + caster_proficiency + caster_stat_modifier

        target_saves = target_saves or {}
        target_modifiers = target_modifiers or {}

        for target_id in target_ids:
            target_affected = False

            # Apply damage
            if ability.damage is not None:
                damage = self._resolve_damage(
                    ability,
                    target_id,
                    save_dc,
                    target_saves.get(target_id),
                    target_modifiers.get(target_id, 0),
                )
                if damage > 0:
                    result.damage_dealt[str(target_id)] = damage
                    target_affected = True

                    # Check for saves
                    if ability.damage.save_ability and target_id in target_saves:
                        save_total = target_saves[target_id]
                        result.saves_made[str(target_id)] = save_total >= save_dc

            # Apply healing
            if ability.healing is not None:
                healing = self._resolve_healing(ability)
                if healing > 0:
                    result.healing_done[str(target_id)] = healing
                    target_affected = True

            # Apply conditions
            for condition_effect in ability.conditions:
                condition_result = self.apply_condition(
                    entity_id=target_id,
                    universe_id=universe_id,
                    condition=condition_effect,
                    source_ability_id=ability.id,
                    source_entity_id=caster_id,
                    save_dc=save_dc,
                    target_save=target_saves.get(target_id),
                    target_modifier=target_modifiers.get(target_id, 0),
                )
                if condition_result.success and condition_result.condition:
                    result.conditions_applied.append(condition_result.condition)
                    target_affected = True

            # Apply stat modifiers
            for stat_mod in ability.stat_modifiers:
                effect = self._apply_stat_modifier(
                    entity_id=target_id,
                    universe_id=universe_id,
                    stat_mod=stat_mod,
                    source_ability_id=ability.id,
                    source_entity_id=caster_id,
                    requires_concentration=ability.requires_concentration,
                )
                result.effects_applied.append(effect)
                target_affected = True

            if target_affected:
                result.targets_affected.append(target_id)

        # Handle concentration
        if ability.requires_concentration and result.targets_affected:
            caster_state = self.get_combat_state(caster_id, universe_id)
            # Break existing concentration
            if caster_state.is_concentrating():
                caster_state.break_concentration()
            # Start new concentration
            caster_state.concentrating_on = ability.id
            caster_state.concentration_source = caster_id
            result.concentration_started = True

        return result

    def _resolve_damage(
        self,
        ability: Ability,
        target_id: UUID,
        save_dc: int,
        target_save: int | None,
        target_modifier: int,
    ) -> int:
        """Resolve damage for a single target."""
        if ability.damage is None:
            return 0

        # Roll damage
        damage_result = roll_dice(ability.damage.dice)
        damage = damage_result.total

        # Check for save
        if ability.damage.save_ability and target_save is not None:
            if target_save >= save_dc:
                # Save succeeded
                if ability.damage.save_for_half:
                    damage = damage // 2
                else:
                    damage = 0

        return damage

    def _resolve_healing(self, ability: Ability) -> int:
        """Resolve healing amount."""
        if ability.healing is None:
            return 0

        total = ability.healing.flat_amount

        if ability.healing.dice:
            healing_result = roll_dice(ability.healing.dice)
            total += healing_result.total

        return total

    def apply_condition(
        self,
        entity_id: UUID,
        universe_id: UUID,
        condition: ConditionEffect,
        source_ability_id: UUID | None = None,
        source_entity_id: UUID | None = None,
        save_dc: int | None = None,
        target_save: int | None = None,
        target_modifier: int = 0,
    ) -> ConditionApplicationResult:
        """
        Apply a condition to an entity.

        Args:
            entity_id: Entity to affect
            universe_id: Universe context
            condition: Condition effect to apply
            source_ability_id: Ability that caused this
            source_entity_id: Entity that applied this
            save_dc: DC for initial save (if any)
            target_save: Pre-rolled save total
            target_modifier: Target's save modifier

        Returns:
            ConditionApplicationResult
        """
        # Check for initial save
        if condition.save_ability and save_dc:
            # Roll save if not provided
            if target_save is None:
                save_roll = secrets.randbelow(20) + 1
                target_save = save_roll + target_modifier
            else:
                save_roll = target_save - target_modifier

            save_result = SaveAttemptResult(
                entity_id=entity_id,
                save_type="avoid_effect",
                ability=condition.save_ability,
                roll=save_roll,
                modifier=target_modifier,
                total=target_save,
                dc=save_dc,
                success=target_save >= save_dc,
                condition_type=condition.condition,
            )

            if target_save >= save_dc:
                # Save succeeded, condition not applied
                return ConditionApplicationResult(
                    success=False,
                    resisted=True,
                    save_result=save_result,
                )

        # Map condition effect duration_type to model DurationType
        duration_type_map = {
            "rounds": DurationType.ROUNDS,
            "minutes": DurationType.MINUTES,
            "until_save": DurationType.UNTIL_SAVE,
            "permanent": DurationType.PERMANENT,
        }
        duration_type = duration_type_map.get(condition.duration_type, DurationType.ROUNDS)

        # Create the condition instance
        condition_instance = create_condition(
            entity_id=entity_id,
            universe_id=universe_id,
            condition_type=condition.condition,
            duration_type=duration_type,
            duration_rounds=condition.duration_value,
            save_ability=condition.save_ability,
            save_dc=save_dc,
            source_ability_id=source_ability_id,
            source_entity_id=source_entity_id,
        )

        # Add to combat state
        state = self.get_combat_state(entity_id, universe_id)
        state.add_condition(condition_instance)

        return ConditionApplicationResult(
            success=True,
            condition=condition_instance,
        )

    def _apply_stat_modifier(
        self,
        entity_id: UUID,
        universe_id: UUID,
        stat_mod: StatModifierEffect,
        source_ability_id: UUID | None = None,
        source_entity_id: UUID | None = None,
        requires_concentration: bool = False,
    ) -> ActiveEffect:
        """Apply a stat modifier effect."""
        # Map duration type
        duration_type_map = {
            "rounds": DurationType.ROUNDS,
            "minutes": DurationType.MINUTES,
            "concentration": DurationType.CONCENTRATION,
        }
        duration_type = duration_type_map.get(stat_mod.duration_type, DurationType.ROUNDS)

        # Determine modifier type (positive = bonus, negative = penalty)
        mod_type = ModifierType.BONUS if stat_mod.modifier >= 0 else ModifierType.PENALTY

        effect = create_active_effect(
            entity_id=entity_id,
            universe_id=universe_id,
            stat=stat_mod.stat,
            modifier=abs(stat_mod.modifier),
            duration_rounds=stat_mod.duration_value,
            modifier_type=mod_type,
            requires_concentration=requires_concentration
            or duration_type == DurationType.CONCENTRATION,
            source_ability_id=source_ability_id,
            source_entity_id=source_entity_id,
        )

        state = self.get_combat_state(entity_id, universe_id)
        state.add_effect(effect)

        return effect

    def tick_combat_round(
        self,
        entity_id: UUID,
        universe_id: UUID,
        ability_modifiers: dict[str, int] | None = None,
    ) -> RoundTickResult:
        """
        Process start-of-turn effects for an entity.

        Args:
            entity_id: Entity whose turn is starting
            universe_id: Universe context
            ability_modifiers: Modifiers for each ability (str -> int)

        Returns:
            RoundTickResult with effects processed
        """
        result = RoundTickResult(entity_id=entity_id)
        state = self.get_combat_state(entity_id, universe_id)
        ability_modifiers = ability_modifiers or {}

        # Process DoT damage
        for condition in state.conditions:
            if condition.dot_damage:
                dot_result = roll_dice(condition.dot_damage)
                result.dot_damage += dot_result.total

        # Process saves to end conditions
        for condition in state.conditions[:]:  # Copy for iteration
            if condition.duration_type == DurationType.UNTIL_SAVE and condition.save_ability:
                # Roll save
                save_roll = secrets.randbelow(20) + 1
                modifier = ability_modifiers.get(condition.save_ability, 0)
                total = save_roll + modifier

                save_result = SaveAttemptResult(
                    entity_id=entity_id,
                    save_type="end_condition",
                    ability=condition.save_ability,
                    roll=save_roll,
                    modifier=modifier,
                    total=total,
                    dc=condition.save_dc or 10,
                    success=total >= (condition.save_dc or 10),
                    condition_type=condition.condition_type,
                )
                result.saves_attempted.append(save_result)

                if save_result.success:
                    state.remove_condition(condition.id)
                    result.conditions_expired.append(condition.condition_type)

        # Tick all conditions for duration expiry
        for condition in state.conditions[:]:
            if condition.tick():
                result.conditions_expired.append(condition.condition_type)
                state.conditions.remove(condition)

        # Tick all effects for duration expiry
        for effect in state.active_effects[:]:
            if effect.tick():
                result.effects_expired.append(effect.stat)
                state.active_effects.remove(effect)

        # Increment round counter
        state.current_round += 1

        return result

    def check_concentration(
        self,
        entity_id: UUID,
        universe_id: UUID,
        damage_taken: int,
        con_modifier: int = 0,
        proficiency: int = 0,
    ) -> ConcentrationCheckResult:
        """
        Check if concentration is maintained after taking damage.

        Args:
            entity_id: Entity to check
            universe_id: Universe context
            damage_taken: Amount of damage taken
            con_modifier: Constitution modifier
            proficiency: Proficiency bonus (if proficient in CON saves)

        Returns:
            ConcentrationCheckResult
        """
        state = self.get_combat_state(entity_id, universe_id)

        if not state.is_concentrating():
            return ConcentrationCheckResult(
                maintained=True,
                roll=0,
                modifier=0,
                total=0,
                dc=0,
            )

        # DC is 10 or half damage, whichever is higher
        dc = max(10, damage_taken // 2)

        # Roll CON save
        roll = secrets.randbelow(20) + 1
        modifier = con_modifier + proficiency
        total = roll + modifier

        maintained = total >= dc
        ability_lost = None

        if not maintained:
            ability_lost = state.break_concentration()

        return ConcentrationCheckResult(
            maintained=maintained,
            roll=roll,
            modifier=modifier,
            total=total,
            dc=dc,
            ability_lost=ability_lost,
        )

    def remove_condition(
        self,
        entity_id: UUID,
        universe_id: UUID,
        condition_id: UUID,
    ) -> bool:
        """
        Remove a specific condition from an entity.

        Args:
            entity_id: Entity to modify
            universe_id: Universe context
            condition_id: Condition to remove

        Returns:
            True if condition was removed, False if not found
        """
        state = self.get_combat_state(entity_id, universe_id)
        return state.remove_condition(condition_id)

    def remove_condition_by_type(
        self,
        entity_id: UUID,
        universe_id: UUID,
        condition_type: str,
    ) -> bool:
        """
        Remove all conditions of a specific type from an entity.

        Args:
            entity_id: Entity to modify
            universe_id: Universe context
            condition_type: Type of condition to remove

        Returns:
            True if any conditions were removed
        """
        state = self.get_combat_state(entity_id, universe_id)
        return state.remove_condition_by_type(condition_type)

    def clear_combat_state(
        self,
        entity_id: UUID,
        universe_id: UUID,
    ) -> None:
        """
        Clear combat state for an entity (e.g., after combat ends).

        Args:
            entity_id: Entity to clear
            universe_id: Universe context
        """
        key = (entity_id, universe_id)
        if key in self.combat_states:
            del self.combat_states[key]

    def end_all_concentration_effects(
        self,
        caster_id: UUID,
        universe_id: UUID,
    ) -> list[UUID]:
        """
        End all effects that require concentration from a caster.

        Called when concentration is broken.

        Args:
            caster_id: Entity whose concentration ended
            universe_id: Universe context

        Returns:
            List of entity IDs that had effects removed
        """
        affected: list[UUID] = []

        for (entity_id, uid), state in self.combat_states.items():
            if uid != universe_id:
                continue

            # Remove effects from this caster that require concentration
            initial_count = len(state.active_effects)
            state.active_effects = [
                e
                for e in state.active_effects
                if not (e.requires_concentration and e.source_entity_id == caster_id)
            ]

            if len(state.active_effects) < initial_count:
                affected.append(entity_id)

            # Remove conditions from this caster's abilities
            initial_cond_count = len(state.conditions)
            state.conditions = [c for c in state.conditions if c.source_entity_id != caster_id]

            if len(state.conditions) < initial_cond_count and entity_id not in affected:
                affected.append(entity_id)

        return affected
