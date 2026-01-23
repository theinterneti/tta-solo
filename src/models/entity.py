"""
Entity Models for TTA-Solo.

Defines the core data structures for game entities:
Characters, Locations, Items, and Factions.

These models represent the "Truth" stored in Dolt.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    """Types of entities in the game world."""

    CHARACTER = "character"
    LOCATION = "location"
    ITEM = "item"
    FACTION = "faction"


class AbilityScores(BaseModel):
    """The six ability scores per SRD 5e."""

    str_: int = Field(default=10, ge=1, le=30, alias="str")
    dex: int = Field(default=10, ge=1, le=30)
    con: int = Field(default=10, ge=1, le=30)
    int_: int = Field(default=10, ge=1, le=30, alias="int")
    wis: int = Field(default=10, ge=1, le=30)
    cha: int = Field(default=10, ge=1, le=30)

    model_config = {"populate_by_name": True}

    def get(self, ability: str) -> int:
        """Get ability score by name."""
        mapping = {
            "str": self.str_,
            "dex": self.dex,
            "con": self.con,
            "int": self.int_,
            "wis": self.wis,
            "cha": self.cha,
        }
        if ability not in mapping:
            raise ValueError(f"Unknown ability: {ability}")
        return mapping[ability]

    def modifier(self, ability: str) -> int:
        """Get ability modifier by name."""
        return (self.get(ability) - 10) // 2


class EntityStats(BaseModel):
    """
    Combat and mechanical stats for an entity.

    Used primarily for characters and monsters.
    """

    srd_block: str | None = Field(
        default=None, description="Reference to SRD 5e statblock, e.g., 'Goblin'"
    )
    hp_current: int = Field(ge=0, description="Current hit points")
    hp_max: int = Field(ge=1, description="Maximum hit points")
    hp_temp: int = Field(default=0, ge=0, description="Temporary hit points")
    ac: int = Field(default=10, ge=0, description="Armor class")
    speed: int = Field(default=30, ge=0, description="Movement speed in feet")
    abilities: AbilityScores = Field(default_factory=AbilityScores)
    proficiency_bonus: int = Field(default=2, ge=0)
    level: int = Field(default=1, ge=1)
    experience: int = Field(default=0, ge=0)
    gold_copper: int = Field(default=0, ge=0, description="Wealth in copper pieces")


class ItemProperties(BaseModel):
    """Properties specific to items."""

    value_copper: int = Field(default=0, ge=0, description="Value in copper pieces")
    weight: float = Field(default=0.0, ge=0, description="Weight in pounds")
    rarity: Literal["common", "uncommon", "rare", "very_rare", "legendary", "artifact"] = "common"
    magical: bool = False
    attunement_required: bool = False
    consumable: bool = False
    quantity: int = Field(default=1, ge=1)


class LocationProperties(BaseModel):
    """Properties specific to locations."""

    location_type: str = "unknown"
    """Type of location: tavern, market, dungeon, forest, crypt, etc."""

    region: str | None = None
    terrain: str | None = None
    climate: str | None = None
    population: int | None = None
    is_dungeon: bool = False
    danger_level: int = Field(default=0, ge=0, le=20, description="0=safe, 20=deadly")


class FactionProperties(BaseModel):
    """Properties specific to factions."""

    alignment: str | None = None
    influence: int = Field(default=0, ge=0, le=100, description="Political influence 0-100")
    wealth: int = Field(default=0, ge=0, description="Faction wealth in gold pieces")
    member_count: int | None = None


class Entity(BaseModel):
    """
    Core entity model - the fundamental game object.

    Represents characters, locations, items, and factions.
    Stored in Dolt's `entities` table.
    """

    id: UUID = Field(default_factory=uuid4)
    universe_id: UUID = Field(description="Which timeline this entity exists in")
    type: EntityType
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", description="Natural language description for embedding")
    tags: list[str] = Field(default_factory=list, description="Categorical tags for filtering")

    # Type-specific properties (only one should be set based on type)
    stats: EntityStats | None = Field(default=None, description="For characters/monsters")
    item_properties: ItemProperties | None = Field(default=None, description="For items")
    location_properties: LocationProperties | None = Field(
        default=None, description="For locations"
    )
    faction_properties: FactionProperties | None = Field(default=None, description="For factions")

    # Relationships (stored as IDs, resolved via Neo4j)
    current_location_id: UUID | None = Field(default=None, description="Where this entity is")
    owner_id: UUID | None = Field(default=None, description="Who owns this (for items)")

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = Field(default=True, description="Soft delete flag")

    def is_character(self) -> bool:
        """Check if this is a character entity."""
        return self.type == EntityType.CHARACTER

    def is_location(self) -> bool:
        """Check if this is a location entity."""
        return self.type == EntityType.LOCATION

    def is_item(self) -> bool:
        """Check if this is an item entity."""
        return self.type == EntityType.ITEM

    def is_faction(self) -> bool:
        """Check if this is a faction entity."""
        return self.type == EntityType.FACTION


def create_character(
    universe_id: UUID,
    name: str,
    description: str = "",
    hp_max: int = 10,
    ac: int = 10,
    abilities: AbilityScores | None = None,
    tags: list[str] | None = None,
    location_id: UUID | None = None,
    gold_copper: int = 0,
) -> Entity:
    """Factory function to create a character entity."""
    return Entity(
        universe_id=universe_id,
        type=EntityType.CHARACTER,
        name=name,
        description=description,
        tags=tags or ["character"],
        stats=EntityStats(
            hp_current=hp_max,
            hp_max=hp_max,
            ac=ac,
            abilities=abilities or AbilityScores(),
            gold_copper=gold_copper,
        ),
        current_location_id=location_id,
    )


def create_location(
    universe_id: UUID,
    name: str,
    description: str = "",
    location_type: str = "unknown",
    region: str | None = None,
    terrain: str | None = None,
    danger_level: int = 0,
    tags: list[str] | None = None,
) -> Entity:
    """Factory function to create a location entity."""
    return Entity(
        universe_id=universe_id,
        type=EntityType.LOCATION,
        name=name,
        description=description,
        tags=tags or ["location"],
        location_properties=LocationProperties(
            location_type=location_type,
            region=region,
            terrain=terrain,
            danger_level=danger_level,
        ),
    )


def create_item(
    universe_id: UUID,
    name: str,
    description: str = "",
    value_copper: int = 0,
    weight: float = 0.0,
    rarity: Literal["common", "uncommon", "rare", "very_rare", "legendary", "artifact"] = "common",
    magical: bool = False,
    tags: list[str] | None = None,
    owner_id: UUID | None = None,
    location_id: UUID | None = None,
) -> Entity:
    """Factory function to create an item entity."""
    return Entity(
        universe_id=universe_id,
        type=EntityType.ITEM,
        name=name,
        description=description,
        tags=tags or ["item"],
        item_properties=ItemProperties(
            value_copper=value_copper,
            weight=weight,
            rarity=rarity,
            magical=magical,
        ),
        owner_id=owner_id,
        current_location_id=location_id,
    )


def create_faction(
    universe_id: UUID,
    name: str,
    description: str = "",
    alignment: str | None = None,
    influence: int = 0,
    tags: list[str] | None = None,
) -> Entity:
    """Factory function to create a faction entity."""
    return Entity(
        universe_id=universe_id,
        type=EntityType.FACTION,
        name=name,
        description=description,
        tags=tags or ["faction"],
        faction_properties=FactionProperties(
            alignment=alignment,
            influence=influence,
        ),
    )
