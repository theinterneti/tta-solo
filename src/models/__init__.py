"""
Core Data Models for TTA-Solo.

These models define the ontology - the structure of game entities,
events, universes, and relationships.

Models are stored in:
- Dolt: Entities, Events, Universes (the "Truth")
- Neo4j: Relationships, Embeddings (the "Context")
"""

from src.models.entity import (
    AbilityScores,
    Entity,
    EntityStats,
    EntityType,
    FactionProperties,
    ItemProperties,
    LocationProperties,
    create_character,
    create_faction,
    create_item,
    create_location,
)
from src.models.event import (
    CheckPayload,
    CombatPayload,
    DialoguePayload,
    Event,
    EventOutcome,
    EventType,
    ForkPayload,
    ItemPayload,
    RestPayload,
    TransactionPayload,
    TravelPayload,
    create_check_event,
    create_combat_event,
    create_dialogue_event,
    create_fork_event,
    create_travel_event,
)
from src.models.npc import (
    MemoryType,
    Motivation,
    NPCMemory,
    NPCProfile,
    PersonalityTraits,
    create_memory,
    create_npc_profile,
)
from src.models.quest import (
    ObjectiveType,
    Quest,
    QuestObjective,
    QuestReward,
    QuestStatus,
    QuestTemplate,
    QuestType,
    create_objective,
    create_quest,
)
from src.models.relationships import (
    FearsRelationship,
    KnowsRelationship,
    LocatedInRelationship,
    Relationship,
    RelationshipType,
    VariantOfRelationship,
    create_knows_relationship,
    create_located_in,
    create_variant,
)
from src.models.universe import (
    Universe,
    UniverseConnection,
    UniverseStatus,
    create_fork,
    create_prime_material,
    create_shared_adventure,
)

__all__ = [
    # Entity
    "Entity",
    "EntityType",
    "EntityStats",
    "AbilityScores",
    "ItemProperties",
    "LocationProperties",
    "FactionProperties",
    "create_character",
    "create_location",
    "create_item",
    "create_faction",
    # NPC
    "PersonalityTraits",
    "Motivation",
    "NPCProfile",
    "MemoryType",
    "NPCMemory",
    "create_npc_profile",
    "create_memory",
    # Event
    "Event",
    "EventType",
    "EventOutcome",
    "CombatPayload",
    "DialoguePayload",
    "TravelPayload",
    "ItemPayload",
    "TransactionPayload",
    "CheckPayload",
    "RestPayload",
    "ForkPayload",
    "create_combat_event",
    "create_dialogue_event",
    "create_travel_event",
    "create_check_event",
    "create_fork_event",
    # Universe
    "Universe",
    "UniverseStatus",
    "UniverseConnection",
    "create_prime_material",
    "create_fork",
    "create_shared_adventure",
    # Relationships
    "Relationship",
    "RelationshipType",
    "KnowsRelationship",
    "LocatedInRelationship",
    "FearsRelationship",
    "VariantOfRelationship",
    "create_knows_relationship",
    "create_located_in",
    "create_variant",
    # Quest
    "Quest",
    "QuestStatus",
    "QuestType",
    "QuestObjective",
    "ObjectiveType",
    "QuestReward",
    "QuestTemplate",
    "create_quest",
    "create_objective",
]
