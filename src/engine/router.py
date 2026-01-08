"""
Skill Router for TTA-Solo.

Maps Intent types to skill functions and executes them.
This is the "Rules Lawyer" component in the engine architecture.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from src.engine.models import Context, Intent, IntentType, SkillResult
from src.skills.checks import SkillProficiencies, skill_check
from src.skills.combat import Combatant, Weapon, resolve_attack
from src.skills.rest import CharacterResources, HitDice, take_long_rest, take_short_rest

if TYPE_CHECKING:
    pass


class CombatContext(BaseModel):
    """Context needed for combat resolution."""

    attacker: Combatant
    target: Combatant
    weapon: Weapon


class CheckContext(BaseModel):
    """Context needed for skill/ability checks."""

    entity: Combatant
    skill_proficiencies: SkillProficiencies | None = None
    dc: int = 10


class RestContext(BaseModel):
    """Context needed for rest resolution."""

    resources: CharacterResources
    is_long_rest: bool = False


class SkillRouter:
    """
    Routes intents to appropriate skill functions.

    Acts as the "Rules Lawyer" - handles all mechanical resolution.
    """

    def resolve(
        self,
        intent: Intent,
        context: Context,
        extra: dict[str, Any] | None = None,
    ) -> SkillResult:
        """
        Resolve an intent using the appropriate skill.

        Args:
            intent: The parsed player intent
            context: Current game context
            extra: Additional context (combat targets, etc.)

        Returns:
            SkillResult with the outcome
        """
        extra = extra or {}

        # Route to appropriate handler
        if intent.type == IntentType.ATTACK:
            return self._resolve_attack(intent, context, extra)

        elif intent.type in {
            IntentType.PERSUADE,
            IntentType.INTIMIDATE,
            IntentType.DECEIVE,
            IntentType.SEARCH,
        }:
            return self._resolve_skill_check(intent, context, extra)

        elif intent.type == IntentType.REST:
            return self._resolve_rest(intent, context, extra)

        elif intent.type == IntentType.LOOK:
            return self._resolve_look(intent, context)

        elif intent.type == IntentType.MOVE:
            return self._resolve_move(intent, context)

        elif intent.type == IntentType.TALK:
            return self._resolve_talk(intent, context)

        else:
            # For intents without mechanical resolution
            return SkillResult(
                success=True,
                outcome="neutral",
                description=f"Action: {intent.type.value}",
            )

    def _resolve_attack(
        self,
        intent: Intent,
        context: Context,
        extra: dict[str, Any],
    ) -> SkillResult:
        """Resolve an attack action."""
        combat_ctx = extra.get("combat")

        if combat_ctx is None:
            # Build combat context from game context
            # Create attacker from actor stats
            attacker = Combatant(
                name=context.actor.name,
                ac=context.actor.ac or 10,
                proficiency_bonus=2,
                proficient_weapons=["longsword", "shortbow"],  # Default proficiencies
            )

            # Find target in present entities
            target_ac = 10
            target_name = intent.target_name or "target"
            if intent.target_name:
                for entity in context.entities_present:
                    if intent.target_name.lower() in entity.name.lower():
                        target_ac = entity.ac or 10
                        target_name = entity.name
                        break

            target = Combatant(
                name=target_name,
                ac=target_ac,
            )

            # Default weapon
            weapon = Weapon(
                name="longsword",
                damage_dice="1d8",
                damage_type="slashing",
            )

            combat_ctx = CombatContext(attacker=attacker, target=target, weapon=weapon)

        # Resolve the attack
        result = resolve_attack(
            attacker=combat_ctx.attacker,
            target=combat_ctx.target,
            weapon=combat_ctx.weapon,
        )

        return SkillResult(
            success=result.hit,
            outcome="critical_success" if result.critical else ("success" if result.hit else "failure"),
            roll=result.attack_roll,
            total=result.total_attack,
            dc=combat_ctx.target.ac,
            damage=result.damage if result.hit else None,
            description=self._format_attack_result(result, intent),
            is_critical=result.critical,
            is_fumble=result.fumble,
        )

    def _format_attack_result(self, result: Any, intent: Intent) -> str:
        """Format attack result for display."""
        target = intent.target_name or "the target"

        if result.fumble:
            return "Critical miss! The attack goes wildly off target."
        elif result.critical:
            return f"Critical hit on {target}! Rolled {result.attack_roll} (crit). {result.damage} damage!"
        elif result.hit:
            return f"Hit {target}! Rolled {result.total_attack} vs AC {result.target_ac}. {result.damage} damage."
        else:
            return f"Missed {target}. Rolled {result.total_attack} vs AC {result.target_ac}."

    def _resolve_skill_check(
        self,
        intent: Intent,
        context: Context,
        extra: dict[str, Any],
    ) -> SkillResult:
        """Resolve a skill check."""
        check_ctx = extra.get("check")

        # Map intent to skill name
        skill_map = {
            IntentType.PERSUADE: "persuasion",
            IntentType.INTIMIDATE: "intimidation",
            IntentType.DECEIVE: "deception",
            IntentType.SEARCH: "investigation",
        }
        skill_name = skill_map.get(intent.type, "perception")

        if check_ctx is None:
            # Create a default entity for the check
            entity = Combatant(
                name=context.actor.name,
                ac=context.actor.ac or 10,
            )
            check_ctx = CheckContext(
                entity=entity,
                dc=10,
            )

        result = skill_check(
            entity=check_ctx.entity,
            skill=skill_name,
            dc=check_ctx.dc,
            skill_proficiencies=check_ctx.skill_proficiencies,
        )

        # Determine critical success/failure based on roll
        is_critical = result.roll == 20
        is_fumble = result.roll == 1

        return SkillResult(
            success=result.success,
            outcome="critical_success" if is_critical and result.success else (
                "critical_failure" if is_fumble and not result.success else (
                    "success" if result.success else "failure"
                )
            ),
            roll=result.roll,
            total=result.total,
            dc=result.dc,
            description=f"{skill_name.title()} check: {result.total} vs DC {result.dc}. {'Success!' if result.success else 'Failed.'}",
            is_critical=is_critical and result.success,
            is_fumble=is_fumble and not result.success,
        )

    def _resolve_rest(
        self,
        intent: Intent,
        context: Context,
        extra: dict[str, Any],
    ) -> SkillResult:
        """Resolve a rest action."""
        rest_ctx = extra.get("rest")

        if rest_ctx is None:
            # Create default resources
            hp_max = context.actor.hp_max or 10
            rest_ctx = RestContext(
                resources=CharacterResources(
                    hp_current=context.actor.hp_current or hp_max,
                    hp_max=hp_max,
                    hit_dice=HitDice(die_type="d8", total=1, current=1),
                ),
                is_long_rest="long" in intent.original_input.lower(),
            )

        if rest_ctx.is_long_rest:
            result = take_long_rest(rest_ctx.resources)
            rest_type = "long rest"
        else:
            result = take_short_rest(rest_ctx.resources, hit_dice_to_spend=1)
            rest_type = "short rest"

        return SkillResult(
            success=True,
            outcome="success",
            healing=result.hp_healed,
            description=f"Completed a {rest_type}. Healed {result.hp_healed} HP.",
        )

    def _resolve_look(self, intent: Intent, context: Context) -> SkillResult:
        """Resolve a look/examine action."""
        # Build description from context
        parts = []

        if context.location:
            parts.append(f"You are in {context.location.name}.")
            if context.location.description:
                parts.append(context.location.description)

        if context.entities_present:
            entity_names = [e.name for e in context.entities_present]
            parts.append(f"You see: {', '.join(entity_names)}.")

        if context.exits:
            parts.append(f"Exits: {', '.join(context.exits)}.")

        description = " ".join(parts) if parts else "You look around but see nothing notable."

        return SkillResult(
            success=True,
            outcome="neutral",
            description=description,
        )

    def _resolve_move(self, intent: Intent, context: Context) -> SkillResult:
        """Resolve a movement action."""
        destination = intent.destination or "forward"

        # Check if destination is valid
        if context.exits and destination.lower() not in [e.lower() for e in context.exits]:
            return SkillResult(
                success=False,
                outcome="failure",
                description=f"You can't go {destination} from here.",
            )

        return SkillResult(
            success=True,
            outcome="success",
            description=f"You move {destination}.",
        )

    def _resolve_talk(self, intent: Intent, context: Context) -> SkillResult:
        """Resolve a talk/speak action."""
        target = intent.target_name or "no one in particular"
        dialogue = intent.dialogue or "something"

        return SkillResult(
            success=True,
            outcome="neutral",
            description=f'You say to {target}: "{dialogue}"',
        )
