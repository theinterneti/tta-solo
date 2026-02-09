"""
Universe Template Models for TTA-Solo.

Defines the creative seeds that drive procedural universe generation.
A template provides tone, culture, economy, and faction hints that
the LLM expands into a full living world.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class FactionSeed(BaseModel):
    """Optional hint for faction generation."""

    name_hint: str | None = Field(default=None, description="Suggested faction name")
    role_hint: str = Field(description="Role in the world: rulers, merchants, rebels, etc.")
    values_hint: str | None = Field(default=None, description="Core value: honor, profit, freedom")


class UniverseTemplate(BaseModel):
    """
    Creative seed for procedural universe generation.

    All fields are generative prompts — the LLM fills in the details.
    Templates tie into the existing PhysicsOverlay system via physics_overlay_key.
    """

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=255, description="Template display name")
    physics_overlay_key: str = Field(
        default="high_fantasy", description="Key into OVERLAY_REGISTRY"
    )

    # Creative direction
    power_source_flavor: str = Field(
        default="Magic flows through ancient ley lines",
        description="How power/magic works in this world",
    )
    tone: str = Field(
        default="adventure",
        description="Narrative tone: grimdark, hopeful, noir, whimsical, etc.",
    )
    genre_tags: list[str] = Field(
        default_factory=lambda: ["fantasy", "adventure"],
        description="Genre descriptors for LLM context",
    )

    # World premise
    cultural_premise: str = Field(
        default="A realm of diverse peoples united by shared history",
        description="Core cultural concept that drives the world",
    )
    economic_premise: str = Field(
        default="Trade routes connect rival factions, each controlling vital resources",
        description="Economic structure that creates interdependence",
    )
    geography_hint: str = Field(
        default="A varied landscape of forests, mountains, and coastal towns",
        description="Physical geography of the world",
    )
    era_hint: str = Field(
        default="A time of uneasy peace after a great conflict",
        description="Historical period / era feel",
    )
    scarcity: str = Field(
        default="Trust — old alliances are fracturing",
        description="What's scarce — drives conflict and quests",
    )

    # Faction hints (optional — LLM generates if empty)
    faction_seeds: list[FactionSeed] = Field(
        default_factory=list,
        description="Optional hints for faction generation. Empty = full LLM improv.",
    )
