"""
Archetype models for character classification.

Character archetypes define combat role, paradigm (power source), and focus (specialization).
"""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class Archetype(str, Enum):
    """Combat/social role - what you do."""

    GUARDIAN = "guardian"  # Protect allies, control space, absorb damage
    STRIKER = "striker"  # High single-target damage, mobility
    CONTROLLER = "controller"  # Area denial, debuffs, crowd control
    LEADER = "leader"  # Buff allies, healing, tactical coordination
    SPECIALIST = "specialist"  # Unique utility, infiltration, problem-solving


class Paradigm(str, Enum):
    """Power source approach - how you do it."""

    ARCANE = "arcane"  # Arcane magic - spell slots, metamagic
    DIVINE = "divine"  # Divine magic - channel divinity, healing bonus
    PRIMAL = "primal"  # Primal magic - wild shape, nature bonuses
    PSIONIC = "psionic"  # Psionic - focus abilities, stress tolerance
    MARTIAL = "martial"  # Martial - extra attacks, maneuvers
    TECH = "tech"  # Tech - gadget slots, overclock abilities
    HYBRID = "hybrid"  # Mixed sources - varies


class FocusBonus(BaseModel):
    """A specific bonus granted by a focus."""

    name: str
    description: str
    stat: str | None = None  # The stat this bonus applies to
    value: int | None = None  # Numeric bonus value
    dice: str | None = None  # Dice bonus (e.g., "1d6")
    condition: str | None = None  # When this bonus applies


class Focus(BaseModel):
    """Specialization within an archetype+paradigm combination."""

    name: str
    description: str
    archetype: Archetype
    bonuses: list[FocusBonus] = Field(default_factory=list)


class CharacterClass(BaseModel):
    """Complete character classification combining archetype, paradigm, and focus."""

    archetype: Archetype
    paradigm: Paradigm
    focus: Focus | None = None
    level: int = 1

    # Derived stats (computed based on archetype/paradigm)
    hp_bonus: int = 0
    starting_ability_ids: list[UUID] = Field(default_factory=list)


# =============================================================================
# Pre-built Focuses
# =============================================================================

# Guardian Focuses
BULWARK_FOCUS = Focus(
    name="Bulwark",
    description="Maximum defense, immovable",
    archetype=Archetype.GUARDIAN,
    bonuses=[
        FocusBonus(name="Fortified", description="+2 AC when stationary", stat="ac", value=2),
        FocusBonus(name="Immovable", description="Advantage on saves vs forced movement"),
    ],
)

SENTINEL_FOCUS = Focus(
    name="Sentinel",
    description="Reactive, punishes enemy movement",
    archetype=Archetype.GUARDIAN,
    bonuses=[
        FocusBonus(name="Opportunity", description="Reaction attacks stop enemy movement"),
        FocusBonus(name="Watchful", description="+2 to initiative", stat="initiative", value=2),
    ],
)

WARDEN_FOCUS = Focus(
    name="Warden",
    description="Area protection, zone control",
    archetype=Archetype.GUARDIAN,
    bonuses=[
        FocusBonus(name="Protective Aura", description="Allies within 10ft gain +1 AC"),
        FocusBonus(name="Zone Control", description="Difficult terrain around you for enemies"),
    ],
)

# Striker Focuses
ASSASSIN_FOCUS = Focus(
    name="Assassin",
    description="Burst damage from stealth",
    archetype=Archetype.STRIKER,
    bonuses=[
        FocusBonus(
            name="Ambush",
            description="+2d6 damage on first attack from stealth",
            dice="2d6",
            condition="from_stealth",
        ),
        FocusBonus(name="Shadow Strike", description="Advantage on attacks vs unaware targets"),
    ],
)

DUELIST_FOCUS = Focus(
    name="Duelist",
    description="Single combat mastery",
    archetype=Archetype.STRIKER,
    bonuses=[
        FocusBonus(
            name="Riposte",
            description="+2 damage when only one enemy in melee",
            stat="damage",
            value=2,
        ),
        FocusBonus(name="Parry", description="Reaction: reduce incoming melee damage by 1d6"),
    ],
)

SKIRMISHER_FOCUS = Focus(
    name="Skirmisher",
    description="Hit-and-run tactics",
    archetype=Archetype.STRIKER,
    bonuses=[
        FocusBonus(name="Mobile", description="+10ft movement speed", stat="speed", value=10),
        FocusBonus(name="Disengage", description="No opportunity attacks when you move away"),
    ],
)

# Controller Focuses
ENCHANTER_FOCUS = Focus(
    name="Enchanter",
    description="Mind effects, charms",
    archetype=Archetype.CONTROLLER,
    bonuses=[
        FocusBonus(
            name="Beguiling", description="+2 DC on charm effects", stat="charm_dc", value=2
        ),
        FocusBonus(name="Dominate", description="Charmed enemies can be commanded as bonus action"),
    ],
)

EVOKER_FOCUS = Focus(
    name="Evoker",
    description="Damage-dealing AoE",
    archetype=Archetype.CONTROLLER,
    bonuses=[
        FocusBonus(name="Sculpt Spells", description="Allies auto-succeed on AoE saves"),
        FocusBonus(name="Empowered", description="+1 damage die on AoE abilities", dice="1d6"),
    ],
)

TRANSMUTER_FOCUS = Focus(
    name="Transmuter",
    description="Battlefield manipulation",
    archetype=Archetype.CONTROLLER,
    bonuses=[
        FocusBonus(name="Terraform", description="Create difficult terrain as bonus action"),
        FocusBonus(name="Reshape", description="Double duration on terrain-altering effects"),
    ],
)

# Leader Focuses
BATTLE_PRIEST_FOCUS = Focus(
    name="Battle Priest",
    description="Healing and buffs",
    archetype=Archetype.LEADER,
    bonuses=[
        FocusBonus(
            name="Blessed Healer", description="+1d4 healing to all healing abilities", dice="1d4"
        ),
        FocusBonus(name="Divine Shield", description="Grant temp HP equal to healing given"),
    ],
)

TACTICIAN_FOCUS = Focus(
    name="Tactician",
    description="Positioning and coordination",
    archetype=Archetype.LEADER,
    bonuses=[
        FocusBonus(name="Commander", description="Grant ally free 5ft move as reaction"),
        FocusBonus(
            name="Strategic Mind",
            description="+2 to initiative for all allies",
            stat="initiative",
            value=2,
        ),
    ],
)

INSPIRING_FOCUS = Focus(
    name="Inspiring",
    description="Morale and advantage",
    archetype=Archetype.LEADER,
    bonuses=[
        FocusBonus(name="Rally", description="Grant advantage on next attack as bonus action"),
        FocusBonus(name="Indomitable", description="Allies within 30ft gain +2 to fear saves"),
    ],
)

# Specialist Focuses
SCOUT_FOCUS = Focus(
    name="Scout",
    description="Reconnaissance, stealth",
    archetype=Archetype.SPECIALIST,
    bonuses=[
        FocusBonus(
            name="Tracker", description="+5 to tracking and perception", stat="perception", value=5
        ),
        FocusBonus(name="Camouflage", description="Advantage on stealth in natural terrain"),
    ],
)

FACE_FOCUS = Focus(
    name="Face",
    description="Social manipulation",
    archetype=Archetype.SPECIALIST,
    bonuses=[
        FocusBonus(
            name="Silver Tongue",
            description="+5 to persuasion and deception",
            stat="persuasion",
            value=5,
        ),
        FocusBonus(
            name="Read Person", description="Insight check as free action once per conversation"
        ),
    ],
)

ARTIFICER_FOCUS = Focus(
    name="Artificer",
    description="Item creation, gadgets",
    archetype=Archetype.SPECIALIST,
    bonuses=[
        FocusBonus(name="Tinker", description="Create temporary gadgets during short rest"),
        FocusBonus(
            name="Enhance", description="+1 to attacks with crafted items", stat="attack", value=1
        ),
    ],
)


# =============================================================================
# Focus Registry
# =============================================================================

FOCUSES_BY_ARCHETYPE: dict[Archetype, list[Focus]] = {
    Archetype.GUARDIAN: [BULWARK_FOCUS, SENTINEL_FOCUS, WARDEN_FOCUS],
    Archetype.STRIKER: [ASSASSIN_FOCUS, DUELIST_FOCUS, SKIRMISHER_FOCUS],
    Archetype.CONTROLLER: [ENCHANTER_FOCUS, EVOKER_FOCUS, TRANSMUTER_FOCUS],
    Archetype.LEADER: [BATTLE_PRIEST_FOCUS, TACTICIAN_FOCUS, INSPIRING_FOCUS],
    Archetype.SPECIALIST: [SCOUT_FOCUS, FACE_FOCUS, ARTIFICER_FOCUS],
}


def get_focuses_for_archetype(archetype: Archetype) -> list[Focus]:
    """Get all available focuses for a given archetype."""
    return FOCUSES_BY_ARCHETYPE.get(archetype, [])


def get_focus_by_name(name: str) -> Focus | None:
    """Look up a focus by name across all archetypes."""
    for focuses in FOCUSES_BY_ARCHETYPE.values():
        for focus in focuses:
            if focus.name.lower() == name.lower():
                return focus
    return None


# =============================================================================
# Archetype Bonuses
# =============================================================================

ARCHETYPE_HP_BONUS: dict[Archetype, int] = {
    Archetype.GUARDIAN: 2,  # +2 HP per level
    Archetype.STRIKER: 0,
    Archetype.CONTROLLER: -1,  # -1 HP per level (glass cannon)
    Archetype.LEADER: 1,
    Archetype.SPECIALIST: 0,
}

PARADIGM_BONUSES: dict[Paradigm, dict[str, int]] = {
    Paradigm.ARCANE: {"spell_slots": 1, "metamagic_uses": 1},
    Paradigm.DIVINE: {"channel_divinity": 1, "healing_bonus": 2},
    Paradigm.PRIMAL: {"wild_shape_uses": 1, "nature_bonus": 2},
    Paradigm.PSIONIC: {"stress_tolerance": 2, "mental_save_bonus": 2},
    Paradigm.MARTIAL: {"extra_attacks": 1, "maneuver_dice": 4},
    Paradigm.TECH: {"gadget_slots": 2, "overclock_uses": 1},
    Paradigm.HYBRID: {},
}


def calculate_hp_bonus(archetype: Archetype, level: int) -> int:
    """Calculate total HP bonus for a character based on archetype and level."""
    base_bonus = ARCHETYPE_HP_BONUS.get(archetype, 0)
    return base_bonus * level


def get_paradigm_bonuses(paradigm: Paradigm) -> dict[str, int]:
    """Get the bonuses granted by a paradigm."""
    return PARADIGM_BONUSES.get(paradigm, {})


# =============================================================================
# Class Generation
# =============================================================================


def generate_class(
    archetype: Archetype | None = None,
    paradigm: Paradigm | None = None,
    focus_name: str | None = None,
    level: int = 1,
) -> CharacterClass:
    """
    Generate a character class, optionally with random elements.

    Args:
        archetype: The archetype, or None for random
        paradigm: The paradigm, or None for random
        focus_name: The focus name, or None for random/none
        level: Starting level

    Returns:
        A CharacterClass instance
    """
    import random

    # Select archetype
    if archetype is None:
        archetype = random.choice(list(Archetype))

    # Select paradigm
    if paradigm is None:
        paradigm = random.choice(list(Paradigm))

    # Select focus
    focus = None
    if focus_name:
        focus = get_focus_by_name(focus_name)
        # If focus doesn't match archetype, ignore it
        if focus and focus.archetype != archetype:
            focus = None
    elif focus_name is None:
        # Randomly decide whether to have a focus
        if random.random() > 0.3:  # 70% chance of having a focus
            available = get_focuses_for_archetype(archetype)
            if available:
                focus = random.choice(available)

    # Calculate HP bonus
    hp_bonus = calculate_hp_bonus(archetype, level)

    return CharacterClass(
        archetype=archetype,
        paradigm=paradigm,
        focus=focus,
        level=level,
        hp_bonus=hp_bonus,
    )
