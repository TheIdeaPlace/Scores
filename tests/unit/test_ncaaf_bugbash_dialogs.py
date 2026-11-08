"""The three Windows screens the Nov 7, 2026 NVDA college football bug bash found wrong:
Bowls & Playoffs (#202), the Team Hub's record (#203) and the Drives tree (#204).
Built on real ESPN payloads. Builds Qt objects but runs no event loop."""
import json
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QLabel, QTreeWidget, QVBoxLayout, QWidget  # noqa: E402

import espn_api  # noqa: E402
import scores  # noqa: E402
import settings  # noqa: E402

from .replay.support import FakeEspn  # noqa: E402

FIXTURES = Path(__file__).parent.parent / "fixtures" / "espn"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "_SETTINGS_DIR", tmp_path / "Scores")
    monkeypatch.setattr(settings, "_SETTINGS_FILE", tmp_path / "Scores" / "settings.json")
    monkeypatch.setattr(settings, "_cache", None)


# --------------------------------------------------------------- Bowls (#202)

@pytest.fixture
def bowls_dialog(app, monkeypatch):
    fake = FakeEspn().on("/scoreboard", load("bowls_NCAAF.json"))
    monkeypatch.setattr(espn_api, "_http_get", fake)
    games = espn_api.get_scores("NCAAF", seasontype=3)
    # The constructor's load runs on a thread; hand the games over as it would.
    monkeypatch.setattr(scores.BowlsAndPlayoffsDialog, "load_bowl_games", lambda self: None)
    dialog = scores.BowlsAndPlayoffsDialog("NCAAF")
    dialog._on_bowl_games_loaded(games)
    yield dialog
    dialog.deleteLater()


def rows(dialog):
    return [dialog.bowl_list.item(i) for i in range(dialog.bowl_list.count())]


class TestBowls:
    def test_the_list_is_named(self, bowls_dialog):
        assert bowls_dialog.bowl_list.accessibleName() == "Bowls & Playoffs"

    def test_headings_are_rows_you_land_on(self, bowls_dialog):
        headings = [r for r in rows(bowls_dialog) if r.data(Qt.ItemDataRole.UserRole) is None]
        assert [h.text() for h in headings] == [
            "Playoff First Round, 1 game",
            "Playoff Quarterfinals, 1 game",
            "Playoff Semifinals, 1 game",
            "National Championship, 1 game",
            "Bowl Games, 1 game",
        ]
        for heading in headings:
            assert heading.flags() & Qt.ItemFlag.ItemIsSelectable
            assert heading.flags() & Qt.ItemFlag.ItemIsEnabled

    def test_first_round_games_have_their_own_heading(self, bowls_dialog):
        texts = [r.text() for r in rows(bowls_dialog)]
        first = texts.index("Playoff First Round, 1 game")
        assert "College Football Playoff First Round Game" in texts[first + 1]
        bowls = texts.index("Bowl Games, 1 game")
        assert texts[bowls + 1].startswith("Cricket Celebration Bowl - ")

    def test_playoff_games_lead_with_their_name_in_brackets(self, bowls_dialog):
        texts = [r.text() for r in rows(bowls_dialog)]
        assert any(t.startswith("[College Football Playoff Quarterfinal at the Vrbo Fiesta Bowl] ") for t in texts)

    def test_the_first_row_is_selected_on_open(self, bowls_dialog):
        assert bowls_dialog.bowl_list.currentRow() == 0
        assert bowls_dialog.bowl_list.currentItem().isSelected()

    def test_enter_opens_a_game_but_not_a_heading(self, bowls_dialog):
        opened = []

        class App:
            def open_game_details(self, game_id):
                opened.append(game_id)

        class Parent:
            parent_app = App()

        bowls_dialog.parent_app = Parent()
        bowls_dialog.on_bowl_game_selected(bowls_dialog.bowl_list.item(0))
        assert opened == []
        game = bowls_dialog.bowl_list.item(1)
        bowls_dialog.on_bowl_game_selected(game)
        assert opened == [game.data(Qt.ItemDataRole.UserRole)]


# ----------------------------------------------------------- Team Hub (#203)

def hub_header_texts(app, monkeypatch, team_data, league):
    monkeypatch.setattr(scores.TeamHubDialog, "_on_tab_changed", lambda self, index: None)
    dialog = scores.TeamHubDialog(team_data, league)
    try:
        return [w.text() for w in dialog.findChildren(QLabel)]
    finally:
        dialog.deleteLater()


class TestTeamHubRecord:
    @pytest.mark.parametrize("wins,losses,ties,league,shown", [
        (8, 0, 0, "NCAAF", "(8-0)"),
        (0, 9, 0, "NCAAF", "(0-9)"),
        (7, 2, 0, "NCAAF", "(7-2)"),
        (10, 6, 1, "NFL", "(10-6-1)"),
        (2, 1, 1, "NCAAWH", "(2-1-1)"),
    ])
    def test_the_record_shows(self, app, monkeypatch, wins, losses, ties, league, shown):
        team = {"team_name": "Miami Hurricanes", "team_id": "2390", "wins": wins, "losses": losses, "ties": ties}
        assert shown in hub_header_texts(app, monkeypatch, team, league)

    def test_no_record_when_it_isnt_known_yet(self, app, monkeypatch):
        team = {"team_name": "Miami Hurricanes", "team_id": "2390", "wins": "", "losses": ""}
        texts = hub_header_texts(app, monkeypatch, team, "NCAAF")
        assert not any(t.startswith("(") and t.endswith(")") for t in texts)


# ------------------------------------------------------------- Drives (#204)

class DrivesHost(QWidget):
    """What the drives method touches. GameDetailsView's constructor starts loading a game."""

    _add_drives_list_to_layout = scores.GameDetailsView._add_drives_list_to_layout
    league = "NCAAF"

    def _export_game_log(self):
        pass


def drive_rows(app, fixture):
    summary = load(fixture)
    host = DrivesHost()
    host.current_raw_details = summary
    layout = QVBoxLayout(host)
    host._add_drives_list_to_layout(layout, summary["drives"])
    tree = host.findChild(QTreeWidget)
    texts = []
    for i in range(tree.topLevelItemCount()):
        quarter = tree.topLevelItem(i)
        texts += [quarter.child(j).text(0) for j in range(quarter.childCount())]
    host.deleteLater()
    return texts


class TestDrives:
    def test_the_missed_field_goal_return_is_credited_to_duke(self, app):
        texts = drive_rows(app, "drives_NCAAF_401858286.json")
        assert "[Duke Blue Devils return TD 7pts] NC State Wolfpack: 5 plays, 37 yards, 0:26" in texts
        assert not any(t.startswith("[TD") and "NC State Wolfpack" in t for t in texts)

    def test_touchdowns_give_the_points_scored(self, app):
        texts = drive_rows(app, "drives_NCAAF_401866682_2OT.json")
        # The walk-off in double overtime: no try.
        assert texts[-1].startswith("[TD 6pts] Towson Tigers: ")
        # A blocked extra point run back for two.
        assert any(t.startswith("[TD 6pts, Towson Tigers 2pts] Sacred Heart Pioneers: ") for t in texts)
        assert sum(t.startswith("[TD 7pts]") for t in texts) == 8

    def test_a_kickoff_returned_for_a_touchdown_says_so(self, app):
        texts = drive_rows(app, "drives_NCAAF_401866682_2OT.json")
        assert "[Towson Tigers return TD 7pts] Kickoff" in texts

    def test_non_scoring_drives_keep_their_badges(self, app):
        texts = drive_rows(app, "drives_NCAAF_401858286.json")
        assert any(t.startswith("[PUNT] ") for t in texts)
        assert any(t.startswith("[4TH DOWN] NC State Wolfpack") for t in texts)

    def test_without_the_summary_header_badges_fall_back_to_espn(self, app):
        summary = load("drives_NCAAF_401858286.json")
        host = DrivesHost()
        host.current_raw_details = None
        layout = QVBoxLayout(host)
        host._add_drives_list_to_layout(layout, summary["drives"])
        tree = host.findChild(QTreeWidget)
        texts = [tree.topLevelItem(i).child(j).text(0)
                 for i in range(tree.topLevelItemCount())
                 for j in range(tree.topLevelItem(i).childCount())]
        host.deleteLater()
        # With no teams known there's no telling who scored: ESPN's result, no points.
        assert "[TD] NC State Wolfpack: 5 plays, 37 yards, 0:26" in texts
        assert "[FG] NC State Wolfpack: 9 plays, 53 yards, 3:46" in texts
        assert not any("pts]" in t for t in texts)
