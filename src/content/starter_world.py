"""
Starter World for TTA-Solo.

Provides a pre-built world with locations, NPCs, and items
for players to immediately start exploring.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from src.db.interfaces import DoltRepository, Neo4jRepository
from src.models import (
    AbilityScores,
    Universe,
    create_character,
    create_item,
    create_location,
)
from src.models.npc import Motivation, create_npc_profile
from src.models.quest import (
    ObjectiveType,
    QuestReward,
    QuestType,
    create_objective,
    create_quest,
)
from src.models.relationships import Relationship, RelationshipType
from src.services.npc import NPCService


@dataclass
class StarterWorldResult:
    """Result of creating a starter world."""

    universe: Universe
    starting_location_id: UUID
    player_character_id: UUID
    locations: dict[str, UUID]  # name -> id
    npcs: dict[str, UUID]  # name -> id
    items: dict[str, UUID]  # name -> id


def create_starter_world(
    dolt: DoltRepository,
    neo4j: Neo4jRepository,
    npc_service: NPCService,
    player_name: str = "Hero",
) -> StarterWorldResult:
    """
    Create a complete starter world for immediate gameplay.

    Returns a world with:
    - A cozy tavern as the starting location
    - Connected locations (market, alley, forest path, crypt entrance)
    - Several NPCs with personalities
    - Starter items for the player

    Args:
        dolt: Dolt repository for entities
        neo4j: Neo4j repository for relationships
        npc_service: NPC service for profiles
        player_name: Name for the player character

    Returns:
        StarterWorldResult with all created entity IDs
    """
    locations: dict[str, UUID] = {}
    npcs: dict[str, UUID] = {}
    items: dict[str, UUID] = {}

    # =========================================================================
    # Create Universe
    # =========================================================================
    universe = Universe(
        name="Eldoria",
        description="A realm of mystery, magic, and adventure.",
        branch_name="main",
    )
    dolt.save_universe(universe)

    # =========================================================================
    # Create Locations
    # =========================================================================

    # Starting location - The Rusty Dragon Inn
    tavern = create_location(
        name="The Rusty Dragon Inn",
        description=(
            "A warm and inviting tavern with a roaring fireplace at its heart. "
            "The smell of roasted meat and fresh bread mingles with pipe smoke. "
            "Adventurers and locals alike gather here to share tales and ale."
        ),
        universe_id=universe.id,
        danger_level=1,
        terrain="urban",
        tags=["inn", "tavern", "safe", "social"],
    )
    dolt.save_entity(tavern)
    locations["tavern"] = tavern.id

    # Town Market
    market = create_location(
        name="Sandpoint Market Square",
        description=(
            "A bustling marketplace filled with colorful stalls and merchants "
            "hawking their wares. The sound of haggling and the smell of exotic "
            "spices fill the air."
        ),
        universe_id=universe.id,
        danger_level=2,
        terrain="urban",
        tags=["market", "shops", "crowded"],
    )
    dolt.save_entity(market)
    locations["market"] = market.id

    # Dark Alley
    alley = create_location(
        name="Shadow Alley",
        description=(
            "A narrow, dimly lit passage between buildings. Refuse piles "
            "against the walls, and the shadows seem to move on their own. "
            "This is not a place for the unwary."
        ),
        universe_id=universe.id,
        danger_level=6,
        terrain="urban",
        tags=["alley", "dark", "dangerous", "urban"],
    )
    dolt.save_entity(alley)
    locations["alley"] = alley.id

    # Forest Path
    forest = create_location(
        name="Tickwood Forest Path",
        description=(
            "A winding trail through ancient trees. Dappled sunlight filters "
            "through the canopy, and birdsong echoes through the woods. "
            "The path leads deeper into the wilderness."
        ),
        universe_id=universe.id,
        danger_level=5,
        terrain="forest",
        tags=["forest", "wilderness", "path"],
    )
    dolt.save_entity(forest)
    locations["forest"] = forest.id

    # Crypt Entrance
    crypt = create_location(
        name="The Old Crypt",
        description=(
            "Ancient stone doors stand ajar, leading into darkness below. "
            "Cold air seeps from within, carrying the musty scent of ages past. "
            "Worn carvings depict forgotten gods and heroes."
        ),
        universe_id=universe.id,
        danger_level=10,
        terrain="dungeon",
        tags=["crypt", "dungeon", "undead", "dangerous"],
    )
    dolt.save_entity(crypt)
    locations["crypt"] = crypt.id

    # Create location connections (CONNECTED_TO relationships)
    connections = [
        (tavern.id, market.id, "east"),
        (market.id, tavern.id, "west"),
        (market.id, alley.id, "north"),
        (alley.id, market.id, "south"),
        (tavern.id, forest.id, "north"),
        (forest.id, tavern.id, "south"),
        (forest.id, crypt.id, "east"),
        (crypt.id, forest.id, "west"),
    ]

    for from_id, to_id, direction in connections:
        rel = Relationship(
            universe_id=universe.id,
            from_entity_id=from_id,
            to_entity_id=to_id,
            relationship_type=RelationshipType.CONNECTED_TO,
            description=direction,
        )
        neo4j.create_relationship(rel)

    # =========================================================================
    # Create NPCs
    # =========================================================================

    # Bartender - Ameiko Kaijitsu
    bartender = create_character(
        name="Ameiko Kaijitsu",
        description=(
            "A striking woman with long black hair and keen eyes. "
            "She moves with the grace of a trained warrior but speaks "
            "with the warmth of a lifelong innkeeper."
        ),
        universe_id=universe.id,
        hp_max=28,
        ac=14,
        abilities=AbilityScores.model_validate(
            {
                "str": 10,
                "dex": 14,
                "con": 12,
                "int": 13,
                "wis": 14,
                "cha": 16,
            }
        ),
    )
    bartender.current_location_id = tavern.id
    dolt.save_entity(bartender)
    npcs["ameiko"] = bartender.id

    # Create NPC profile
    ameiko_profile = create_npc_profile(
        entity_id=bartender.id,
        openness=70,
        conscientiousness=65,
        extraversion=75,
        agreeableness=60,
        neuroticism=30,
        motivations=[Motivation.DUTY, Motivation.BELONGING, Motivation.KNOWLEDGE],
        speech_style="warm but witty",
        quirks=["tells stories of her adventuring days", "protective of regulars"],
    )
    npc_service.save_profile(ameiko_profile)

    # LOCATED_IN for bartender
    neo4j.create_relationship(
        Relationship(
            universe_id=universe.id,
            from_entity_id=bartender.id,
            to_entity_id=tavern.id,
            relationship_type=RelationshipType.LOCATED_IN,
        )
    )

    # Mysterious Stranger
    stranger = create_character(
        name="Hooded Stranger",
        description=(
            "A cloaked figure sitting alone in the corner. Their face is "
            "hidden in shadow, but you can feel their gaze following you. "
            "They nurse a single drink that never seems to empty."
        ),
        universe_id=universe.id,
        hp_max=45,
        ac=16,
        abilities=AbilityScores.model_validate(
            {
                "str": 14,
                "dex": 16,
                "con": 14,
                "int": 16,
                "wis": 15,
                "cha": 10,
            }
        ),
    )
    stranger.current_location_id = tavern.id
    dolt.save_entity(stranger)
    npcs["stranger"] = stranger.id

    stranger_profile = create_npc_profile(
        entity_id=stranger.id,
        openness=40,
        conscientiousness=80,
        extraversion=20,
        agreeableness=35,
        neuroticism=45,
        motivations=[Motivation.KNOWLEDGE, Motivation.POWER, Motivation.SURVIVAL],
        speech_style="cryptic and measured",
        quirks=["speaks in riddles", "knows things they shouldn't"],
    )
    npc_service.save_profile(stranger_profile)

    neo4j.create_relationship(
        Relationship(
            universe_id=universe.id,
            from_entity_id=stranger.id,
            to_entity_id=tavern.id,
            relationship_type=RelationshipType.LOCATED_IN,
        )
    )

    # Market Merchant
    merchant = create_character(
        name="Vorvashali Voon",
        description=(
            "A jovial Varisian merchant with an impressive mustache and "
            "an even more impressive collection of exotic goods. His cart "
            "seems to hold far more than should be physically possible."
        ),
        universe_id=universe.id,
        hp_max=15,
        ac=11,
        abilities=AbilityScores.model_validate(
            {
                "str": 9,
                "dex": 12,
                "con": 10,
                "int": 14,
                "wis": 13,
                "cha": 17,
            }
        ),
    )
    merchant.current_location_id = market.id
    dolt.save_entity(merchant)
    npcs["merchant"] = merchant.id

    merchant_profile = create_npc_profile(
        entity_id=merchant.id,
        openness=85,
        conscientiousness=50,
        extraversion=90,
        agreeableness=70,
        neuroticism=25,
        motivations=[Motivation.WEALTH, Motivation.FAME, Motivation.BELONGING],
        speech_style="enthusiastic and theatrical",
        quirks=["exaggerates wildly", "always has 'just the thing'"],
    )
    npc_service.save_profile(merchant_profile)

    neo4j.create_relationship(
        Relationship(
            universe_id=universe.id,
            from_entity_id=merchant.id,
            to_entity_id=market.id,
            relationship_type=RelationshipType.LOCATED_IN,
        )
    )

    # Alley Thief
    thief = create_character(
        name="Quick-Fingers",
        description=(
            "A wiry figure in patched leather, perpetually glancing over "
            "their shoulder. Despite their nervous energy, their hands are "
            "remarkably steady."
        ),
        universe_id=universe.id,
        hp_max=22,
        ac=15,
        abilities=AbilityScores.model_validate(
            {
                "str": 10,
                "dex": 18,
                "con": 12,
                "int": 13,
                "wis": 11,
                "cha": 14,
            }
        ),
    )
    thief.current_location_id = alley.id
    dolt.save_entity(thief)
    npcs["thief"] = thief.id

    thief_profile = create_npc_profile(
        entity_id=thief.id,
        openness=55,
        conscientiousness=35,
        extraversion=45,
        agreeableness=40,
        neuroticism=65,
        motivations=[Motivation.SURVIVAL, Motivation.WEALTH, Motivation.SAFETY],
        speech_style="nervous and quick",
        quirks=["fidgets constantly", "knows all the shortcuts"],
    )
    npc_service.save_profile(thief_profile)

    neo4j.create_relationship(
        Relationship(
            universe_id=universe.id,
            from_entity_id=thief.id,
            to_entity_id=alley.id,
            relationship_type=RelationshipType.LOCATED_IN,
        )
    )

    # Blacksmith - Grimjaw the Smith
    blacksmith = create_character(
        name="Grimjaw the Smith",
        description=(
            "A broad-shouldered dwarf with arms like tree trunks and a magnificent "
            "braided beard. Soot and sweat cover his leather apron, and the ring "
            "of his hammer echoes from the nearby forge."
        ),
        universe_id=universe.id,
        hp_max=35,
        ac=13,
        abilities=AbilityScores.model_validate(
            {
                "str": 18,
                "dex": 10,
                "con": 16,
                "int": 12,
                "wis": 14,
                "cha": 10,
            }
        ),
    )
    blacksmith.current_location_id = market.id
    dolt.save_entity(blacksmith)
    npcs["blacksmith"] = blacksmith.id

    blacksmith_profile = create_npc_profile(
        entity_id=blacksmith.id,
        openness=30,
        conscientiousness=90,
        extraversion=35,
        agreeableness=55,
        neuroticism=20,
        motivations=[Motivation.DUTY, Motivation.ARTISTRY, Motivation.RESPECT],
        speech_style="gruff but fair",
        quirks=["judges people by their weapons", "respects hard work"],
    )
    npc_service.save_profile(blacksmith_profile)

    neo4j.create_relationship(
        Relationship(
            universe_id=universe.id,
            from_entity_id=blacksmith.id,
            to_entity_id=market.id,
            relationship_type=RelationshipType.LOCATED_IN,
        )
    )

    # =========================================================================
    # Create Items
    # =========================================================================

    # Starter weapon
    sword = create_item(
        universe_id=universe.id,
        name="Rusty Shortsword",
        description="A well-worn but serviceable blade. It's seen better days, but it'll do.",
        value_copper=100,
        weight=2.0,
        rarity="common",
        tags=["weapon", "sword", "melee"],
    )
    dolt.save_entity(sword)
    items["sword"] = sword.id

    # Healing potion
    potion = create_item(
        universe_id=universe.id,
        name="Potion of Healing",
        description="A small vial of red liquid that glows faintly. Restores 2d4+2 HP.",
        value_copper=500,
        weight=0.5,
        rarity="common",
        magical=True,
        tags=["potion", "healing", "consumable"],
    )
    dolt.save_entity(potion)
    items["potion"] = potion.id

    # Torch
    torch = create_item(
        universe_id=universe.id,
        name="Torch",
        description="A wooden shaft wrapped in oil-soaked cloth. Burns for about an hour.",
        value_copper=1,
        weight=1.0,
        rarity="common",
        tags=["light", "consumable", "tool"],
    )
    dolt.save_entity(torch)
    items["torch"] = torch.id

    # Rope
    rope = create_item(
        universe_id=universe.id,
        name="Hemp Rope (50 ft)",
        description="Fifty feet of sturdy hemp rope. Essential for any adventurer.",
        value_copper=10,
        weight=10.0,
        rarity="common",
        tags=["tool", "rope", "utility"],
    )
    dolt.save_entity(rope)
    items["rope"] = rope.id

    # =========================================================================
    # Create Shop Items (owned by merchants)
    # =========================================================================

    # Blacksmith items
    longsword = create_item(
        universe_id=universe.id,
        name="Steel Longsword",
        description="A finely crafted longsword with a keen edge. Grimjaw's finest work.",
        value_copper=1500,  # 15 gp
        weight=3.0,
        rarity="common",
        tags=["weapon", "sword", "melee", "shop"],
    )
    dolt.save_entity(longsword)
    items["longsword"] = longsword.id

    chainmail = create_item(
        universe_id=universe.id,
        name="Chainmail Armor",
        description="Interlocking metal rings providing solid protection. AC 16.",
        value_copper=7500,  # 75 gp
        weight=55.0,
        rarity="common",
        tags=["armor", "heavy", "shop"],
    )
    dolt.save_entity(chainmail)
    items["chainmail"] = chainmail.id

    shield = create_item(
        universe_id=universe.id,
        name="Wooden Shield",
        description="A sturdy wooden shield reinforced with iron bands. +2 AC.",
        value_copper=1000,  # 10 gp
        weight=6.0,
        rarity="common",
        tags=["armor", "shield", "shop"],
    )
    dolt.save_entity(shield)
    items["shield"] = shield.id

    # Merchant items
    rations = create_item(
        universe_id=universe.id,
        name="Rations (1 day)",
        description="Dried meat, hard cheese, and hardtack. Enough for one day.",
        value_copper=50,  # 5 sp
        weight=2.0,
        rarity="common",
        tags=["food", "consumable", "shop"],
    )
    dolt.save_entity(rations)
    items["rations"] = rations.id

    backpack = create_item(
        universe_id=universe.id,
        name="Adventurer's Backpack",
        description="A sturdy leather backpack with multiple compartments.",
        value_copper=200,  # 2 gp
        weight=5.0,
        rarity="common",
        tags=["container", "utility", "shop"],
    )
    dolt.save_entity(backpack)
    items["backpack"] = backpack.id

    lantern = create_item(
        universe_id=universe.id,
        name="Hooded Lantern",
        description="A brass lantern with a hood to direct light. Burns oil.",
        value_copper=500,  # 5 gp
        weight=2.0,
        rarity="common",
        tags=["light", "tool", "shop"],
    )
    dolt.save_entity(lantern)
    items["lantern"] = lantern.id

    antitoxin = create_item(
        universe_id=universe.id,
        name="Antitoxin",
        description="A vial of murky liquid. Grants advantage on poison saves for 1 hour.",
        value_copper=500,  # 5 gp
        weight=0.1,
        rarity="common",
        tags=["potion", "consumable", "shop"],
    )
    dolt.save_entity(antitoxin)
    items["antitoxin"] = antitoxin.id

    # Create shop inventory relationships (merchants SELLS items)
    # Blacksmith sells weapons and armor
    for item_key in ["longsword", "chainmail", "shield"]:
        neo4j.create_relationship(
            Relationship(
                universe_id=universe.id,
                from_entity_id=blacksmith.id,
                to_entity_id=items[item_key],
                relationship_type=RelationshipType.SELLS,
                description="shop inventory",
            )
        )

    # Merchant sells supplies and consumables
    # Note: potion, torch, rope are in player's starting inventory, so we don't sell those
    for item_key in ["rations", "backpack", "lantern", "antitoxin"]:
        neo4j.create_relationship(
            Relationship(
                universe_id=universe.id,
                from_entity_id=merchant.id,
                to_entity_id=items[item_key],
                relationship_type=RelationshipType.SELLS,
                description="shop inventory",
            )
        )

    # =========================================================================
    # Create Player Character
    # =========================================================================

    player = create_character(
        name=player_name,
        description="A brave adventurer seeking fortune and glory in the world of Eldoria.",
        universe_id=universe.id,
        hp_max=12,
        ac=14,
        abilities=AbilityScores.model_validate(
            {
                "str": 14,
                "dex": 13,
                "con": 14,
                "int": 10,
                "wis": 12,
                "cha": 11,
            }
        ),
        gold_copper=5000,  # 50 gold pieces starting money
    )
    player.current_location_id = tavern.id
    dolt.save_entity(player)

    # Player location relationship
    neo4j.create_relationship(
        Relationship(
            universe_id=universe.id,
            from_entity_id=player.id,
            to_entity_id=tavern.id,
            relationship_type=RelationshipType.LOCATED_IN,
        )
    )

    # Player inventory relationships
    for item_id in [sword.id, potion.id, torch.id, rope.id]:
        neo4j.create_relationship(
            Relationship(
                universe_id=universe.id,
                from_entity_id=player.id,
                to_entity_id=item_id,
                relationship_type=RelationshipType.CARRIES,
            )
        )

    # =========================================================================
    # Create Starter Quests
    # =========================================================================

    # Quest 1: "Welcome to Sandpoint" - Tutorial/introduction quest
    welcome_quest = create_quest(
        universe_id=universe.id,
        name="Welcome to Sandpoint",
        description=(
            "Ameiko has suggested you familiarize yourself with the town. "
            "Explore the market and meet some of the locals."
        ),
        quest_type=QuestType.EXPLORE,
        objectives=[
            create_objective(
                description="Visit the Market Square",
                objective_type=ObjectiveType.REACH_LOCATION,
                target_location_id=market.id,
            ),
            create_objective(
                description="Talk to the merchant Vorvashali Voon",
                objective_type=ObjectiveType.TALK_TO_NPC,
                target_entity_id=merchant.id,
                target_entity_name=merchant.name,
            ),
        ],
        giver_id=bartender.id,
        giver_name=bartender.name,
        rewards=QuestReward(
            gold=25,
            experience=50,
        ),
        difficulty=1,
        tags=["tutorial", "introduction", "exploration"],
    )
    dolt.save_quest(welcome_quest)

    # Quest 2: "The Hooded Stranger's Request" - Mystery quest
    stranger_quest = create_quest(
        universe_id=universe.id,
        name="The Hooded Stranger's Request",
        description=(
            "The mysterious stranger in the corner has been watching you. "
            "Perhaps they have work for a capable adventurer?"
        ),
        quest_type=QuestType.INVESTIGATE,
        objectives=[
            create_objective(
                description="Speak with the Hooded Stranger",
                objective_type=ObjectiveType.TALK_TO_NPC,
                target_entity_id=stranger.id,
                target_entity_name=stranger.name,
            ),
            create_objective(
                description="Investigate the Old Crypt",
                objective_type=ObjectiveType.REACH_LOCATION,
                target_location_id=crypt.id,
            ),
        ],
        giver_id=stranger.id,
        giver_name=stranger.name,
        rewards=QuestReward(
            gold=100,
            experience=150,
        ),
        difficulty=3,
        tags=["mystery", "exploration", "danger"],
    )
    dolt.save_quest(stranger_quest)

    # Quest 3: "Goblin Trouble" - Combat quest
    goblin_quest = create_quest(
        universe_id=universe.id,
        name="Goblin Trouble in the Woods",
        description=(
            "Vorvashali has heard reports of goblins in Tickwood Forest "
            "harassing travelers. Clear them out and make the road safe."
        ),
        quest_type=QuestType.HUNT,
        objectives=[
            create_objective(
                description="Travel to Tickwood Forest",
                objective_type=ObjectiveType.REACH_LOCATION,
                target_location_id=forest.id,
            ),
            create_objective(
                description="Defeat the goblin raiders (0/3)",
                objective_type=ObjectiveType.DEFEAT_ENEMY,
                quantity=3,
                target_entity_name="Goblin",
            ),
        ],
        giver_id=merchant.id,
        giver_name=merchant.name,
        rewards=QuestReward(
            gold=75,
            experience=200,
        ),
        difficulty=2,
        tags=["combat", "goblins", "forest"],
    )
    dolt.save_quest(goblin_quest)

    return StarterWorldResult(
        universe=universe,
        starting_location_id=tavern.id,
        player_character_id=player.id,
        locations=locations,
        npcs=npcs,
        items=items,
    )
