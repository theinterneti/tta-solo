"""Faction reputation tracking service."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel

from src.db.interfaces import DoltRepository


class ReputationChange(BaseModel):
    """Result of a single reputation change."""

    faction_id: UUID
    faction_name: str
    old_score: int
    new_score: int
    delta: int
    tier: str


class FactionStanding(BaseModel):
    """A character's standing with one faction."""

    faction_id: UUID
    faction_name: str
    score: int
    tier: str


def get_reputation_tier(score: int) -> str:
    """Return the reputation tier label for a given score."""
    if score >= 50:
        return "Honored"
    if score >= 20:
        return "Friendly"
    if score >= -19:
        return "Neutral"
    if score >= -49:
        return "Unfriendly"
    return "Hostile"


@dataclass
class ReputationService:
    """Applies and queries faction reputation for characters."""

    dolt: DoltRepository

    def apply_reputation_changes(
        self,
        character_id: UUID,
        universe_id: UUID,
        changes: dict[UUID, int],
    ) -> list[ReputationChange]:
        """Apply reputation deltas to a character and persist. Returns change details."""
        character = self.dolt.get_entity(character_id, universe_id)
        if character is None or character.stats is None:
            return []

        results: list[ReputationChange] = []
        for faction_id, delta in changes.items():
            fid_str = str(faction_id)
            old_score = character.stats.faction_reputations.get(fid_str, 0)
            new_score = old_score + delta
            character.stats.faction_reputations[fid_str] = new_score

            faction = self.dolt.get_entity(faction_id, universe_id)
            faction_name = faction.name if faction else "Unknown Faction"

            results.append(
                ReputationChange(
                    faction_id=faction_id,
                    faction_name=faction_name,
                    old_score=old_score,
                    new_score=new_score,
                    delta=delta,
                    tier=get_reputation_tier(new_score),
                )
            )

        self.dolt.save_entity(character)
        return results

    def get_standings(
        self,
        character_id: UUID,
        universe_id: UUID,
    ) -> list[FactionStanding]:
        """Get all faction standings for a character."""
        character = self.dolt.get_entity(character_id, universe_id)
        if character is None or character.stats is None:
            return []

        standings: list[FactionStanding] = []
        for fid_str, score in character.stats.faction_reputations.items():
            try:
                faction_id = UUID(fid_str)
            except (ValueError, TypeError):
                continue
            faction = self.dolt.get_entity(faction_id, universe_id)
            faction_name = faction.name if faction else "Unknown Faction"

            standings.append(
                FactionStanding(
                    faction_id=faction_id,
                    faction_name=faction_name,
                    score=score,
                    tier=get_reputation_tier(score),
                )
            )

        return standings
