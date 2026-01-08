"""Tests for core ontology models."""

from __future__ import annotations

from uuid import uuid4

from src.models import (
    AbilityScores,
    EntityType,
    Event,
    EventOutcome,
    EventType,
    RelationshipType,
    UniverseStatus,
    create_character,
    create_combat_event,
    create_dialogue_event,
    create_faction,
    create_fork,
    create_fork_event,
    create_item,
    create_knows_relationship,
    create_located_in,
    create_location,
    create_prime_material,
    create_travel_event,
    create_variant,
)

# --- AbilityScores Tests ---


class TestAbilityScores:
    """Tests for AbilityScores model."""

    def test_default_values(self):
        abilities = AbilityScores()
        assert abilities.str_ == 10
        assert abilities.dex == 10
        assert abilities.con == 10
        assert abilities.int_ == 10
        assert abilities.wis == 10
        assert abilities.cha == 10

    def test_get_ability(self):
        abilities = AbilityScores(str=16, dex=14)
        assert abilities.get("str") == 16
        assert abilities.get("dex") == 14

    def test_modifier_calculation(self):
        abilities = AbilityScores(str=16, dex=8, con=15)
        assert abilities.modifier("str") == 3  # (16-10)//2
        assert abilities.modifier("dex") == -1  # (8-10)//2
        assert abilities.modifier("con") == 2  # (15-10)//2

    def test_alias_works(self):
        # Can use "str" and "int" as field names
        abilities = AbilityScores(**{"str": 18, "int": 14})
        assert abilities.str_ == 18
        assert abilities.int_ == 14


# --- Entity Tests ---


class TestEntity:
    """Tests for Entity model."""

    def test_create_character_factory(self):
        universe_id = uuid4()
        char = create_character(
            universe_id=universe_id,
            name="Gandalf",
            hp_max=45,
            ac=12,
        )

        assert char.type == EntityType.CHARACTER
        assert char.name == "Gandalf"
        assert char.stats is not None
        assert char.stats.hp_max == 45
        assert char.stats.hp_current == 45
        assert char.stats.ac == 12
        assert char.is_character() is True

    def test_create_location_factory(self):
        universe_id = uuid4()
        loc = create_location(
            universe_id=universe_id,
            name="Moria",
            description="An ancient dwarven kingdom",
            terrain="underground",
            danger_level=15,
        )

        assert loc.type == EntityType.LOCATION
        assert loc.name == "Moria"
        assert loc.location_properties is not None
        assert loc.location_properties.terrain == "underground"
        assert loc.location_properties.danger_level == 15
        assert loc.is_location() is True

    def test_create_item_factory(self):
        universe_id = uuid4()
        item = create_item(
            universe_id=universe_id,
            name="Longsword +1",
            value_copper=1500,
            magical=True,
            rarity="uncommon",
        )

        assert item.type == EntityType.ITEM
        assert item.name == "Longsword +1"
        assert item.item_properties is not None
        assert item.item_properties.magical is True
        assert item.item_properties.rarity == "uncommon"
        assert item.is_item() is True

    def test_create_faction_factory(self):
        universe_id = uuid4()
        faction = create_faction(
            universe_id=universe_id,
            name="Harpers",
            alignment="Chaotic Good",
            influence=75,
        )

        assert faction.type == EntityType.FACTION
        assert faction.faction_properties is not None
        assert faction.faction_properties.alignment == "Chaotic Good"
        assert faction.faction_properties.influence == 75
        assert faction.is_faction() is True

    def test_entity_tags(self):
        universe_id = uuid4()
        char = create_character(
            universe_id=universe_id,
            name="Goblin",
            tags=["monster", "humanoid", "hostile"],
        )
        assert "monster" in char.tags
        assert "hostile" in char.tags


# --- Event Tests ---


class TestEvent:
    """Tests for Event model."""

    def test_create_combat_event(self):
        universe_id = uuid4()
        actor_id = uuid4()
        target_id = uuid4()

        event = create_combat_event(
            universe_id=universe_id,
            actor_id=actor_id,
            event_type=EventType.ATTACK,
            target_id=target_id,
            attack_roll=18,
            damage=12,
            damage_type="slashing",
            outcome=EventOutcome.SUCCESS,
        )

        assert event.event_type == EventType.ATTACK
        assert event.actor_id == actor_id
        assert event.target_id == target_id
        assert event.outcome == EventOutcome.SUCCESS
        assert event.roll == 18
        assert event.payload["damage_roll"] == 12
        assert event.is_combat_event() is True

    def test_create_dialogue_event(self):
        universe_id = uuid4()
        speaker_id = uuid4()
        listener_id = uuid4()

        event = create_dialogue_event(
            universe_id=universe_id,
            speaker_id=speaker_id,
            text="You shall not pass!",
            listener_id=listener_id,
            emotion="angry",
        )

        assert event.event_type == EventType.DIALOGUE
        assert event.payload["text"] == "You shall not pass!"
        assert event.payload["emotion"] == "angry"
        assert event.is_social_event() is True

    def test_create_travel_event(self):
        universe_id = uuid4()
        traveler_id = uuid4()
        from_loc = uuid4()
        to_loc = uuid4()

        event = create_travel_event(
            universe_id=universe_id,
            traveler_id=traveler_id,
            from_location_id=from_loc,
            to_location_id=to_loc,
        )

        assert event.event_type == EventType.TRAVEL
        assert event.is_movement_event() is True

    def test_create_fork_event(self):
        parent_id = uuid4()
        child_id = uuid4()
        actor_id = uuid4()

        event = create_fork_event(
            parent_universe_id=parent_id,
            child_universe_id=child_id,
            actor_id=actor_id,
            fork_reason="Player chose to spare the villain",
        )

        assert event.event_type == EventType.FORK
        assert event.payload["parent_universe_id"] == parent_id
        assert event.payload["fork_reason"] == "Player chose to spare the villain"

    def test_event_types_coverage(self):
        """Ensure all expected event types exist."""
        expected_types = [
            "ATTACK",
            "DIALOGUE",
            "TRAVEL",
            "FORK",
            "SHORT_REST",
            "LONG_REST",
            "SKILL_CHECK",
            "SAVING_THROW",
        ]
        for t in expected_types:
            assert hasattr(EventType, t)


# --- Universe Tests ---


class TestUniverse:
    """Tests for Universe model."""

    def test_create_prime_material(self):
        prime = create_prime_material()

        assert prime.name == "Prime Material"
        assert prime.is_prime_material() is True
        assert prime.parent_universe_id is None
        assert prime.depth == 0
        assert prime.dolt_branch == "main"
        assert prime.is_shared is True

    def test_create_fork(self):
        prime = create_prime_material()
        player_id = uuid4()

        forked = create_fork(
            parent=prime,
            name="What if timeline",
            owner_id=player_id,
            fork_reason="Player wanted to explore alternative",
        )

        assert forked.parent_universe_id == prime.id
        assert forked.depth == 1
        assert forked.owner_id == player_id
        assert forked.is_shared is False
        assert "user/" in forked.dolt_branch

    def test_nested_forks_increment_depth(self):
        prime = create_prime_material()
        fork1 = create_fork(prime, "Fork 1")
        fork2 = create_fork(fork1, "Fork 2")
        fork3 = create_fork(fork2, "Fork 3")

        assert fork1.depth == 1
        assert fork2.depth == 2
        assert fork3.depth == 3

    def test_universe_status(self):
        prime = create_prime_material()
        assert prime.status == UniverseStatus.ACTIVE
        assert prime.is_active() is True

        prime.status = UniverseStatus.ARCHIVED
        assert prime.is_active() is False


# --- Relationship Tests ---


class TestRelationship:
    """Tests for Relationship models."""

    def test_create_knows_relationship(self):
        universe_id = uuid4()
        char1 = uuid4()
        char2 = uuid4()

        rel = create_knows_relationship(
            universe_id=universe_id,
            from_id=char1,
            to_id=char2,
            trust=0.8,
            familiarity=0.6,
        )

        assert rel.relationship_type == RelationshipType.KNOWS
        assert rel.from_entity_id == char1
        assert rel.to_entity_id == char2
        assert rel.trust == 0.8
        assert rel.familiarity == 0.6

    def test_create_located_in(self):
        universe_id = uuid4()
        char_id = uuid4()
        location_id = uuid4()

        rel = create_located_in(
            universe_id=universe_id,
            entity_id=char_id,
            location_id=location_id,
        )

        assert rel.relationship_type == RelationshipType.LOCATED_IN
        assert rel.from_entity_id == char_id
        assert rel.to_entity_id == location_id
        assert rel.is_current is True

    def test_create_variant_relationship(self):
        original_id = uuid4()
        variant_id = uuid4()
        universe_id = uuid4()
        event_id = uuid4()

        rel = create_variant(
            original_entity_id=original_id,
            variant_entity_id=variant_id,
            variant_universe_id=universe_id,
            diverged_at_event_id=event_id,
            changes={"is_alive": "false"},
        )

        assert rel.relationship_type == RelationshipType.VARIANT_OF
        assert rel.from_entity_id == variant_id
        assert rel.to_entity_id == original_id
        assert rel.changes_from_original == {"is_alive": "false"}

    def test_relationship_types_coverage(self):
        """Ensure key relationship types exist."""
        expected = [
            "KNOWS",
            "LOCATED_IN",
            "FEARS",
            "DESIRES",
            "VARIANT_OF",
            "CAUSED",
            "HAS_ATMOSPHERE",
        ]
        for t in expected:
            assert hasattr(RelationshipType, t)


# --- Integration Tests ---


class TestOntologyIntegration:
    """Integration tests for the full ontology."""

    def test_character_in_location(self):
        """Test creating a character and placing them in a location."""
        universe_id = uuid4()

        tavern = create_location(
            universe_id=universe_id,
            name="The Prancing Pony",
            terrain="urban",
        )

        strider = create_character(
            universe_id=universe_id,
            name="Strider",
            description="A mysterious ranger",
            location_id=tavern.id,
        )

        assert strider.current_location_id == tavern.id

    def test_event_chain(self):
        """Test creating a chain of causally related events."""
        universe_id = uuid4()
        actor_id = uuid4()
        target_id = uuid4()

        attack = create_combat_event(
            universe_id=universe_id,
            actor_id=actor_id,
            event_type=EventType.ATTACK,
            target_id=target_id,
            attack_roll=20,
            damage=15,
            is_critical=True,
            outcome=EventOutcome.CRITICAL_SUCCESS,
        )

        # Death event caused by the attack
        death = Event(
            universe_id=universe_id,
            event_type=EventType.DEATH,
            actor_id=target_id,  # The one who died
            outcome=EventOutcome.NEUTRAL,
            caused_by_event_id=attack.id,
            narrative_summary="The goblin falls lifeless to the ground.",
        )

        assert death.caused_by_event_id == attack.id

    def test_timeline_fork_with_variant(self):
        """Test forking a universe and creating entity variants."""
        prime = create_prime_material()
        king_id = uuid4()

        # Create a fork where the king dies
        fork = create_fork(
            parent=prime,
            name="King Dies Timeline",
            fork_reason="The assassination succeeded",
        )

        # In the fork, create a variant of the king who is dead
        variant_king_id = uuid4()
        variant_rel = create_variant(
            original_entity_id=king_id,
            variant_entity_id=variant_king_id,
            variant_universe_id=fork.id,
            changes={"is_alive": "false", "cause_of_death": "assassination"},
        )

        assert fork.parent_universe_id == prime.id
        assert variant_rel.changes_from_original["is_alive"] == "false"
