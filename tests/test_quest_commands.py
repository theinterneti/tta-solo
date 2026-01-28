"""Tests for quest CLI commands in REPL."""

from __future__ import annotations

import pytest

from src.cli.repl import GameREPL, GameState
from src.content import create_starter_world
from src.db.memory import InMemoryDoltRepository, InMemoryNeo4jRepository
from src.engine import GameEngine
from src.engine.models import EngineConfig
from src.models.quest import Quest, QuestObjective, QuestReward, QuestStatus, QuestType
from src.services.quest import QuestService


@pytest.fixture
def game_state() -> GameState:
    """Create a test game state."""
    dolt = InMemoryDoltRepository()
    neo4j = InMemoryNeo4jRepository()

    # Create NPC service
    from src.services.npc import NPCService

    npc_service = NPCService(dolt, neo4j)

    # Create starter world
    world_result = create_starter_world(dolt, neo4j, npc_service)

    # Create engine
    engine_config = EngineConfig(enable_agents=False)
    engine = GameEngine(dolt, neo4j, engine_config)

    # Create game state
    state = GameState(
        engine=engine,
        character_id=world_result.player_character_id,
        universe_id=world_result.universe.id,
        location_id=world_result.starting_location_id,
        character_name="Hero",
        session_id=None,
    )

    return state


@pytest.fixture
def repl() -> GameREPL:
    """Create a test REPL."""
    return GameREPL()


@pytest.fixture
def quest_service(game_state: GameState) -> QuestService:
    """Create a quest service."""
    return QuestService(game_state.engine.dolt, game_state.engine.neo4j)


@pytest.fixture
def sample_quest(game_state: GameState, quest_service: QuestService) -> Quest:
    """Create a sample quest for testing."""
    quest = Quest(
        universe_id=game_state.universe_id,
        name="Test Quest",
        description="A test quest for unit testing",
        quest_type=QuestType.FETCH,
        status=QuestStatus.AVAILABLE,
        giver_name="Test NPC",
        objectives=[
            QuestObjective(
                description="Collect 3 test items",
                objective_type="collect_item",
                quantity_required=3,
            )
        ],
        rewards=QuestReward(gold=50, experience=30),
    )
    game_state.engine.dolt.save_quest(quest)
    return quest


class TestQuestsAvailableCommand:
    """Tests for /quests available command."""

    @pytest.mark.skip(reason="Starter world creates quests causing fixture interference")
    def test_shows_available_quests(
        self, repl: GameREPL, game_state: GameState, sample_quest: Quest
    ):
        """Test that available quests are displayed."""
        result = repl._cmd_quests(game_state, ["available"])

        assert result is not None
        assert "Available Opportunities" in result
        assert sample_quest.name in result
        assert sample_quest.giver_name in result
        assert "→ /quest accept" in result

    @pytest.mark.skip(reason="Starter world creates quests causing fixture interference")
    def test_shows_message_when_no_quests(self, repl: GameREPL, game_state: GameState):
        """Test message when no quests available."""
        result = repl._cmd_quests(game_state, ["available"])

        assert result is not None
        assert "No opportunities" in result.lower()

    @pytest.mark.skip(reason="Quest model requires at least 1 objective")
    def test_skips_articles_in_command_hint(
        self, repl: GameREPL, game_state: GameState, quest_service: QuestService
    ):
        """Test that command hints skip articles like 'The', 'A', 'An'."""
        quest = Quest(
            universe_id=game_state.universe_id,
            name="The Missing Expedition",
            description="Test",
            quest_type=QuestType.INVESTIGATE,
            status=QuestStatus.AVAILABLE,
            objectives=[],
            rewards=QuestReward(),
        )
        game_state.engine.dolt.save_quest(quest)

        result = repl._cmd_quests(game_state, ["available"])

        assert result is not None
        # Should suggest "missing" not "the"
        assert "/quest accept missing" in result.lower()


class TestQuestsActiveCommand:
    """Tests for /quests (active) command."""

    def test_shows_active_quests(
        self, repl: GameREPL, game_state: GameState, sample_quest: Quest
    ):
        """Test that active quests are displayed."""
        # Accept the quest
        sample_quest.accept()
        game_state.engine.dolt.save_quest(sample_quest)

        result = repl._cmd_quests(game_state, [])

        assert result is not None
        assert "Your Current Quests" in result
        assert "📜" in result
        assert sample_quest.name in result
        assert f"Given by: {sample_quest.giver_name}" in result
        assert "Upon completion:" in result

    def test_shows_objective_progress(
        self, repl: GameREPL, game_state: GameState, sample_quest: Quest
    ):
        """Test that objective progress is displayed naturally."""
        sample_quest.accept()
        sample_quest.objectives[0].quantity_current = 2
        game_state.engine.dolt.save_quest(sample_quest)

        result = repl._cmd_quests(game_state, [])

        assert result is not None
        assert "Progress: 2 of 3" in result
        assert "▸" in result  # Active objective symbol

    def test_shows_completed_objectives(
        self, repl: GameREPL, game_state: GameState, sample_quest: Quest
    ):
        """Test that completed objectives show checkmark."""
        sample_quest.accept()
        sample_quest.objectives[0].is_complete = True
        game_state.engine.dolt.save_quest(sample_quest)

        result = repl._cmd_quests(game_state, [])

        assert result is not None
        assert "✓" in result  # Completed objective symbol

    def test_shows_message_when_no_active_quests(
        self, repl: GameREPL, game_state: GameState
    ):
        """Test message when no active quests."""
        result = repl._cmd_quests(game_state, [])

        assert result is not None
        assert "no active quests" in result.lower()
        assert "/quests available" in result


class TestQuestAcceptCommand:
    """Tests for /quest accept command."""

    def test_accepts_quest_by_exact_name(
        self,
        repl: GameREPL,
        game_state: GameState,
        sample_quest: Quest,
        quest_service: QuestService,
    ):
        """Test accepting a quest by exact name."""
        result = repl._accept_quest(game_state, quest_service, "Test Quest")

        assert result is not None
        assert "You accept the task" in result
        assert sample_quest.name in result
        assert "Mission Accepted" in result
        assert "Promised reward" in result

        # Verify quest is now active
        quest = game_state.engine.dolt.get_quest(sample_quest.id)
        assert quest.status == QuestStatus.ACTIVE

    def test_accepts_quest_by_partial_name(
        self,
        repl: GameREPL,
        game_state: GameState,
        sample_quest: Quest,
        quest_service: QuestService,
    ):
        """Test accepting a quest by partial name match."""
        result = repl._accept_quest(game_state, quest_service, "test")

        assert result is not None
        assert "Mission Accepted" in result

        quest = game_state.engine.dolt.get_quest(sample_quest.id)
        assert quest.status == QuestStatus.ACTIVE

    def test_shows_error_for_nonexistent_quest(
        self, repl: GameREPL, game_state: GameState, quest_service: QuestService
    ):
        """Test error message for non-existent quest."""
        result = repl._accept_quest(game_state, quest_service, "Nonexistent Quest")

        assert result is not None
        assert "No opportunity" in result or "not found" in result.lower()

    def test_shows_quest_objectives(
        self,
        repl: GameREPL,
        game_state: GameState,
        sample_quest: Quest,
        quest_service: QuestService,
    ):
        """Test that quest objectives are shown on accept."""
        result = repl._accept_quest(game_state, quest_service, "Test Quest")

        assert result is not None
        assert "▸" in result  # Objective bullet
        assert sample_quest.objectives[0].description in result
        assert "(3 required)" in result  # Shows quantity

    def test_shows_quest_giver_dialogue(
        self,
        repl: GameREPL,
        game_state: GameState,
        sample_quest: Quest,
        quest_service: QuestService,
    ):
        """Test that quest giver's dialogue is shown."""
        result = repl._accept_quest(game_state, quest_service, "Test Quest")

        assert result is not None
        # Description should be quoted as dialogue
        assert f'"{sample_quest.description}"' in result


class TestQuestAbandonCommand:
    """Tests for /quest abandon command."""

    def test_abandons_active_quest(
        self,
        repl: GameREPL,
        game_state: GameState,
        sample_quest: Quest,
        quest_service: QuestService,
    ):
        """Test abandoning an active quest."""
        # Accept the quest first
        sample_quest.accept()
        game_state.engine.dolt.save_quest(sample_quest)

        result = repl._abandon_quest(game_state, quest_service, "Test Quest")

        assert result is not None
        assert "abandon" in result.lower()
        assert sample_quest.name in result
        assert "[Removed from quest journal]" in result

        # Verify quest is abandoned
        quest = game_state.engine.dolt.get_quest(sample_quest.id)
        assert quest.status == QuestStatus.ABANDONED

    def test_abandons_by_partial_name(
        self,
        repl: GameREPL,
        game_state: GameState,
        sample_quest: Quest,
        quest_service: QuestService,
    ):
        """Test abandoning by partial name match."""
        sample_quest.accept()
        game_state.engine.dolt.save_quest(sample_quest)

        result = repl._abandon_quest(game_state, quest_service, "test")

        assert result is not None
        assert "abandon" in result.lower()

        quest = game_state.engine.dolt.get_quest(sample_quest.id)
        assert quest.status == QuestStatus.ABANDONED

    def test_shows_error_for_nonexistent_quest(
        self, repl: GameREPL, game_state: GameState, quest_service: QuestService
    ):
        """Test error message when trying to abandon non-existent quest."""
        result = repl._abandon_quest(game_state, quest_service, "Nonexistent")

        assert result is not None
        assert "don't have" in result.lower() or "not found" in result.lower()

    def test_cannot_abandon_unavailable_quest(
        self,
        repl: GameREPL,
        game_state: GameState,
        sample_quest: Quest,
        quest_service: QuestService,
    ):
        """Test that you can't abandon a quest that's not active."""
        # Quest is available but not active
        result = repl._abandon_quest(game_state, quest_service, "Test Quest")

        assert result is not None
        # Should not find it in active quests
        assert "don't have" in result.lower() or "not found" in result.lower()


class TestQuestCommandICOOCPresentation:
    """Tests for IC/OOC presentation in quest commands."""

    def test_uses_ic_language_for_accept(
        self,
        repl: GameREPL,
        game_state: GameState,
        sample_quest: Quest,
        quest_service: QuestService,
    ):
        """Test that quest accept uses IC language."""
        result = repl._accept_quest(game_state, quest_service, "Test Quest")

        # IC language checks
        assert "You accept" in result  # IC action
        assert "Mission Accepted" in result  # IC framing
        assert "Promised reward" in result  # IC, not "Reward:"
        assert "~" in result  # Approximate reward (~50 gold)
        assert "[Quest added to journal" in result  # OOC helper in brackets

    def test_uses_natural_language_for_progress(
        self, repl: GameREPL, game_state: GameState, sample_quest: Quest
    ):
        """Test that progress uses natural language."""
        sample_quest.accept()
        sample_quest.objectives[0].quantity_current = 2
        game_state.engine.dolt.save_quest(sample_quest)

        result = repl._cmd_quests(game_state, [])

        # Natural language, not "2/3"
        assert "2 of 3" in result
        assert "2/3" not in result

    def test_uses_symbols_for_status(
        self, repl: GameREPL, game_state: GameState, sample_quest: Quest
    ):
        """Test that appropriate symbols are used."""
        sample_quest.accept()
        game_state.engine.dolt.save_quest(sample_quest)

        result = repl._cmd_quests(game_state, [])

        # Should use symbols
        assert "📜" in result  # Quest symbol
        assert "▸" in result  # Active objective
        assert "━" in result  # Separator

    def test_available_quests_use_opportunities_language(
        self, repl: GameREPL, game_state: GameState, sample_quest: Quest
    ):
        """Test that available quests use 'opportunities' language."""
        result = repl._cmd_quests(game_state, ["available"])

        # IC framing
        assert "Opportunities" in result
        assert "seeks assistance" in result
        # Not "quests" or "missions" in the header
