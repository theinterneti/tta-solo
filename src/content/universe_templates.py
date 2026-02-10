"""
Pre-Built Universe Templates for TTA-Solo.

Ready-to-play templates covering major genres.
Each template seeds the LLM generation pipeline with creative direction.
"""

from __future__ import annotations

from src.models.universe_template import FactionSeed, UniverseTemplate

# =============================================================================
# Templates
# =============================================================================

CLASSIC_FANTASY = UniverseTemplate(
    name="The Shattered Kingdoms",
    physics_overlay_key="high_fantasy",
    power_source_flavor="Magic flows through ancient ley lines, concentrated in crystalline nodes",
    tone="adventure",
    genre_tags=["high fantasy", "adventure", "exploration"],
    cultural_premise="Three kingdoms once united under a single crown, now fractured by succession wars",
    economic_premise="Each kingdom controls a vital resource — grain, iron, or arcane crystals",
    geography_hint="Rolling plains, dense forests, and a mountain range splitting the continent",
    era_hint="Two decades after the Sundering, when the High King vanished",
    scarcity="Unity — old alliances crumble as new threats emerge from the wilds",
    faction_seeds=[
        FactionSeed(role_hint="nobility and military", values_hint="order and honor"),
        FactionSeed(role_hint="merchants and artisans", values_hint="prosperity and innovation"),
        FactionSeed(role_hint="druids and rangers", values_hint="nature and balance"),
    ],
)

CYBERPUNK_SPRAWL = UniverseTemplate(
    name="Neon Abyss",
    physics_overlay_key="cyberpunk",
    power_source_flavor="Neural implants channel raw data streams into superhuman abilities",
    tone="noir",
    genre_tags=["cyberpunk", "noir", "corporate espionage"],
    cultural_premise="Megacorps replaced governments; citizenship is a subscription service",
    economic_premise="Data is currency, bandwidth is power, and everyone is surveilled",
    geography_hint="A sprawling megacity of neon towers, flooded lower levels, and orbital stations",
    era_hint="2187 — thirty years after the Corporate Accords dissolved the last nation-states",
    scarcity="Privacy — your thoughts are the last thing they haven't monetized yet",
    faction_seeds=[
        FactionSeed(
            name_hint="Nexus Corp", role_hint="megacorporation", values_hint="profit and control"
        ),
        FactionSeed(role_hint="underground hackers", values_hint="freedom and chaos"),
        FactionSeed(role_hint="street gangs", values_hint="territory and survival"),
    ],
)

COSMIC_HORROR = UniverseTemplate(
    name="The Hollow Shore",
    physics_overlay_key="horror",
    power_source_flavor="Power seeps from cracks in reality — using it costs sanity",
    tone="grimdark",
    genre_tags=["cosmic horror", "mystery", "survival"],
    cultural_premise="A coastal town where the sea whispers secrets and the fog hides things",
    economic_premise="The town depends on fishing, but the catch has been... changing",
    geography_hint="A fog-bound peninsula with a lighthouse, fishing village, and cliffs over a black sea",
    era_hint="1923 — strange tides have been rising for six months",
    scarcity="Sanity — the more you learn, the less you can bear",
    faction_seeds=[
        FactionSeed(role_hint="town council", values_hint="normalcy and denial"),
        FactionSeed(role_hint="cult of the deep", values_hint="transformation and surrender"),
        FactionSeed(role_hint="investigators", values_hint="truth at any cost"),
    ],
)

POLITICAL_INTRIGUE = UniverseTemplate(
    name="The Court of Whispers",
    physics_overlay_key="low_magic",
    power_source_flavor="Magic is rare, subtle, and politically dangerous to wield openly",
    tone="intrigue",
    genre_tags=["political intrigue", "low fantasy", "courtly drama"],
    cultural_premise="Five noble houses compete for the empty throne through marriage, murder, and debt",
    economic_premise="Each house controls a trade route; blocking one starves another",
    geography_hint="A capital city of canals and bridges, surrounded by rival estates",
    era_hint="The Interregnum — the king died without heir, and the succession is open",
    scarcity="Legitimacy — everyone claims the throne, no one can hold it",
    faction_seeds=[
        FactionSeed(role_hint="military aristocracy", values_hint="strength and tradition"),
        FactionSeed(role_hint="merchant princes", values_hint="wealth and influence"),
        FactionSeed(role_hint="religious order", values_hint="piety and secrets"),
        FactionSeed(role_hint="spymaster network", values_hint="information and leverage"),
    ],
)

POST_APOCALYPTIC = UniverseTemplate(
    name="Ashfall",
    physics_overlay_key="post_apocalyptic",
    power_source_flavor="Pre-war tech still hums with power for those who know the codes",
    tone="gritty",
    genre_tags=["post-apocalyptic", "survival", "exploration"],
    cultural_premise="Survivors have formed tribes around pre-war landmarks — a library, a dam, a bunker",
    economic_premise="Clean water, working tech, and medicine are worth killing for",
    geography_hint="A scorched wasteland dotted with ruined cities, toxic zones, and rare oases",
    era_hint="Year 47 After the Flash — some elders still remember the old world",
    scarcity="Clean water — every drop is measured and rationed",
    faction_seeds=[
        FactionSeed(role_hint="vault dwellers", values_hint="knowledge and preservation"),
        FactionSeed(role_hint="wasteland raiders", values_hint="strength and freedom"),
        FactionSeed(role_hint="water merchants", values_hint="control and trade"),
    ],
)

MYTHIC_AGES = UniverseTemplate(
    name="The Age of Titans",
    physics_overlay_key="mythic",
    power_source_flavor="The gods walk among mortals, granting power through divine pacts",
    tone="epic",
    genre_tags=["mythic", "epic fantasy", "divine conflict"],
    cultural_premise="Mortals serve as champions of rival gods in an eternal divine chess game",
    economic_premise="Divine favor is currency — temples are banks, prayers are transactions",
    geography_hint="A mythic landscape of floating mountains, divine forests, and titan graveyards",
    era_hint="The Third Age — two gods have fallen, and their domains are up for grabs",
    scarcity="Divine favor — the gods are fickle and their blessings come with strings",
    faction_seeds=[
        FactionSeed(role_hint="solar priesthood", values_hint="justice and order"),
        FactionSeed(role_hint="trickster cult", values_hint="cunning and freedom"),
        FactionSeed(role_hint="titan worshippers", values_hint="power and restoration"),
    ],
)

WEIRD_WEST = UniverseTemplate(
    name="Devil's Crossing",
    physics_overlay_key="low_magic",
    power_source_flavor="Dark bargains and spirit pacts fuel unnatural abilities",
    tone="western",
    genre_tags=["weird west", "supernatural", "frontier"],
    cultural_premise="The frontier is haunted — every ghost town has real ghosts",
    economic_premise="Gold mines, cattle, and the railroad — but something in the earth fights back",
    geography_hint="Dusty plains, canyon mazes, ghost towns, and a cursed mountain range",
    era_hint="1876 — the railroad is pushing west, and the land doesn't want it",
    scarcity="Trust — everyone has a secret, and most of them involve the dead",
    faction_seeds=[
        FactionSeed(role_hint="railroad company", values_hint="progress and profit"),
        FactionSeed(role_hint="native spirit walkers", values_hint="balance and the old ways"),
        FactionSeed(role_hint="outlaws", values_hint="freedom and revenge"),
    ],
)

BLANK_CANVAS = UniverseTemplate(
    name="The Unknown",
    physics_overlay_key="high_fantasy",
    power_source_flavor="Power manifests in ways unique to this world",
    tone="adventure",
    genre_tags=["original", "experimental"],
    cultural_premise="A world shaped entirely by imagination",
    economic_premise="Resources and trade evolve organically from the culture",
    geography_hint="A landscape born from pure creativity",
    era_hint="A time of beginnings",
    scarcity="The unknown itself — discovery is the greatest currency",
    faction_seeds=[],  # Maximum LLM improv
)

# =============================================================================
# Registry
# =============================================================================

UNIVERSE_TEMPLATES: list[UniverseTemplate] = [
    CLASSIC_FANTASY,
    CYBERPUNK_SPRAWL,
    COSMIC_HORROR,
    POLITICAL_INTRIGUE,
    POST_APOCALYPTIC,
    MYTHIC_AGES,
    WEIRD_WEST,
    BLANK_CANVAS,
]


def get_template_by_name(name: str) -> UniverseTemplate | None:
    """Get a template by name (case-insensitive)."""
    lower = name.lower()
    for t in UNIVERSE_TEMPLATES:
        if t.name.lower() == lower:
            return t
    return None


def get_template_by_index(index: int) -> UniverseTemplate | None:
    """Get a template by 0-based index."""
    if 0 <= index < len(UNIVERSE_TEMPLATES):
        return UNIVERSE_TEMPLATES[index]
    return None
