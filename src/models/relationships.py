"""
Relationship Models for TTA-Solo.

Defines the relationship types used in Neo4j for the "soft state" -
connections, feelings, and context that enhance narrative retrieval.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class RelationshipType(StrEnum):
    """Types of relationships between entities in Neo4j."""

    # Character-to-Character
    KNOWS = "KNOWS"  # Basic acquaintance
    ALLIED_WITH = "ALLIED_WITH"
    HOSTILE_TO = "HOSTILE_TO"
    SERVES = "SERVES"  # Subordinate relationship
    COMMANDS = "COMMANDS"  # Superior relationship
    RELATED_TO = "RELATED_TO"  # Family
    LOVES = "LOVES"
    HATES = "HATES"
    FEARS = "FEARS"
    RESPECTS = "RESPECTS"
    DISTRUSTS = "DISTRUSTS"

    # Character-to-Location
    LOCATED_IN = "LOCATED_IN"
    TRAPPED_IN = "TRAPPED_IN"  # Character is trapped and cannot leave
    BORN_IN = "BORN_IN"
    LIVES_IN = "LIVES_IN"
    WORKS_IN = "WORKS_IN"
    OWNS = "OWNS"  # Also Item-to-Character (reversed)
    VISITED = "VISITED"

    # Character-to-Item
    CARRIES = "CARRIES"
    WIELDS = "WIELDS"
    WEARS = "WEARS"
    CREATED = "CREATED"
    SEEKS = "SEEKS"
    SELLS = "SELLS"  # Merchant sells item (shop inventory)

    # Character-to-Faction
    MEMBER_OF = "MEMBER_OF"
    LEADS = "LEADS"
    OPPOSES = "OPPOSES"

    # Faction-to-Faction
    TRADES_WITH = "TRADES_WITH"
    COMPETES_WITH = "COMPETES_WITH"
    DEPENDS_ON = "DEPENDS_ON"
    CONTROLS = "CONTROLS"
    INFLUENCES = "INFLUENCES"

    # Character-to-Concept
    BELIEVES_IN = "BELIEVES_IN"
    DESIRES = "DESIRES"
    SKILLED_IN = "SKILLED_IN"

    # Location-to-Location
    CONNECTED_TO = "CONNECTED_TO"
    CONTAINS = "CONTAINS"  # Nested locations
    NEAR = "NEAR"
    BORDERS = "BORDERS"

    # Location-to-Concept
    HAS_ATMOSPHERE = "HAS_ATMOSPHERE"  # Mood/vibe

    # Event-to-Event
    CAUSED = "CAUSED"
    PRECEDED = "PRECEDED"
    FOLLOWED = "FOLLOWED"

    # Entity-to-Entity (cross-timeline)
    VARIANT_OF = "VARIANT_OF"  # Same entity, different universe


class Relationship(BaseModel):
    """
    A relationship between two entities in Neo4j.

    Relationships capture the "soft state" - feelings, connections,
    and context that help the AI find relevant information.
    """

    id: UUID = Field(default_factory=uuid4)
    universe_id: UUID = Field(description="Which timeline this relationship exists in")
    relationship_type: RelationshipType
    from_entity_id: UUID
    to_entity_id: UUID

    # Relationship properties
    strength: float = Field(
        default=1.0, ge=0.0, le=1.0, description="How strong the relationship is (0-1)"
    )
    trust: float | None = Field(default=None, ge=-1.0, le=1.0, description="Trust level (-1 to 1)")
    description: str = Field(default="", description="Narrative description")

    # Metadata
    established_at: datetime = Field(default_factory=datetime.utcnow)
    last_interaction: datetime | None = None
    is_active: bool = Field(default=True)

    # For temporal relationships
    started_event_id: UUID | None = Field(
        default=None, description="Event that created this relationship"
    )
    ended_event_id: UUID | None = Field(
        default=None, description="Event that ended this relationship"
    )


class KnowsRelationship(Relationship):
    """Extended model for KNOWS relationships with additional properties."""

    relationship_type: RelationshipType = RelationshipType.KNOWS
    trust: float = Field(default=0.5, ge=-1.0, le=1.0)
    familiarity: float = Field(
        default=0.5, ge=0.0, le=1.0, description="How well they know each other"
    )
    last_met_location_id: UUID | None = None


class LocatedInRelationship(Relationship):
    """Extended model for LOCATED_IN relationships."""

    relationship_type: RelationshipType = RelationshipType.LOCATED_IN
    is_current: bool = Field(default=True, description="Is this their current location?")
    arrived_at: datetime = Field(default_factory=datetime.utcnow)


class FearsRelationship(Relationship):
    """Extended model for FEARS relationships to concepts or entities."""

    relationship_type: RelationshipType = RelationshipType.FEARS
    intensity: float = Field(default=0.5, ge=0.0, le=1.0, description="Fear intensity")
    is_phobia: bool = Field(default=False, description="Is this an irrational fear?")
    origin_event_id: UUID | None = Field(default=None, description="What caused this fear")


class VariantOfRelationship(Relationship):
    """
    Extended model for VARIANT_OF relationships (cross-timeline entities).

    When an entity diverges between timelines, we create a variant node
    rather than duplicating the entire graph.
    """

    relationship_type: RelationshipType = RelationshipType.VARIANT_OF
    diverged_at_event_id: UUID | None = Field(
        default=None, description="The fork event where divergence occurred"
    )
    changes_from_original: dict[str, str] = Field(
        default_factory=dict, description="What changed from the original"
    )


def create_knows_relationship(
    universe_id: UUID,
    from_id: UUID,
    to_id: UUID,
    trust: float = 0.5,
    familiarity: float = 0.5,
    description: str = "",
) -> KnowsRelationship:
    """Create a KNOWS relationship between two characters."""
    return KnowsRelationship(
        universe_id=universe_id,
        from_entity_id=from_id,
        to_entity_id=to_id,
        trust=trust,
        familiarity=familiarity,
        description=description,
    )


def create_located_in(
    universe_id: UUID,
    entity_id: UUID,
    location_id: UUID,
) -> LocatedInRelationship:
    """Create a LOCATED_IN relationship."""
    return LocatedInRelationship(
        universe_id=universe_id,
        from_entity_id=entity_id,
        to_entity_id=location_id,
        is_current=True,
    )


def create_variant(
    original_entity_id: UUID,
    variant_entity_id: UUID,
    variant_universe_id: UUID,
    diverged_at_event_id: UUID | None = None,
    changes: dict[str, str] | None = None,
) -> VariantOfRelationship:
    """
    Create a VARIANT_OF relationship for cross-timeline entities.

    Used when an entity in a forked timeline diverges from its original.
    """
    return VariantOfRelationship(
        universe_id=variant_universe_id,
        from_entity_id=variant_entity_id,
        to_entity_id=original_entity_id,
        diverged_at_event_id=diverged_at_event_id,
        changes_from_original=changes or {},
    )
