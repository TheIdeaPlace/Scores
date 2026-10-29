"""Checks the play-audio wiring in GameDetailsView against real tree items.

The geometry and the tone have their own unit tests; what this covers is the
part between them and the UI — tagging a tree item with its play, finding that
play again from the item the user has selected, and walking a period. These are
the places a wiring mistake would hide, because the mapping would still look
correct in isolation.

Qt runs offscreen so this needs no display.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem  # noqa: E402

import scores  # noqa: E402
from play_audio_mapper import PlayAudioMapper  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class Host:
    """The four methods under test, on an object carrying only what they touch.

    GameDetailsView's constructor builds a whole game view, so the methods are
    borrowed onto a stand-in instead. They are taken from the real class, so a
    change to either side still shows up here.
    """

    _tag_play_for_audio = scores.GameDetailsView._tag_play_for_audio
    _play_audio_league = scores.GameDetailsView._play_audio_league
    _play_play_audio = scores.GameDetailsView._play_play_audio
    _play_play_sequence = scores.GameDetailsView._play_play_sequence
    _play_current_play_audio = scores.GameDetailsView._play_current_play_audio
    _announce_play_audio = scores.GameDetailsView._announce_play_audio
    _on_audio_feedback = scores.GameDetailsView._on_audio_feedback

    def __init__(self, league):
        self._plays_sport_type = league
        self.play_audio_mapper = PlayAudioMapper()
        self.announced = []

    # Capture what the screen reader would have been told.
    def _announce_play_audio(self, message):  # noqa: F811
        self.announced.append(message)


def located(x, y, text="Jump Shot"):
    return {"text": text, "type": {"text": text}, "coordinate": {"x": x, "y": y}}


def unlocated(text="Substitution"):
    return {
        "text": text,
        "type": {"text": text},
        "coordinate": {"x": -214748340, "y": -214748365},
    }


def build_period(host, plays, label="1st Quarter"):
    """A period header with one child per play, tagged the way the tree does."""
    tree = QTreeWidget()
    period = QTreeWidgetItem([label])
    tree.addTopLevelItem(period)
    for play in plays:
        item = QTreeWidgetItem([play["text"]])
        host._tag_play_for_audio(item, play)
        period.addChild(item)
    return tree, period


class TestTagging:
    def test_tags_a_supported_league(self, qapp):
        host = Host("NBA")
        item = QTreeWidgetItem(["Jump Shot"])
        host._tag_play_for_audio(item, located(25, 3))
        data = item.data(0, Qt.ItemDataRole.UserRole)
        assert data["play_audio_league"] == "NBA"
        assert data["play"]["coordinate"] == {"x": 25, "y": 3}

    @pytest.mark.parametrize("league", ["MLB", "NFL", "Soccer", None])
    def test_leaves_other_sports_untagged(self, qapp, league):
        # Baseball keeps its own `is_pitch` dict in this slot; nothing here may
        # overwrite it, and football has no coordinates to tag.
        host = Host(league)
        item = QTreeWidgetItem(["Some play"])
        host._tag_play_for_audio(item, located(25, 3))
        assert item.data(0, Qt.ItemDataRole.UserRole) is None


class TestLeagueLookup:
    def test_play_item_reports_its_own_league(self, qapp):
        host = Host("NHL")
        _, period = build_period(host, [located(85, 0, "Goal")], "1st Period")
        assert host._play_audio_league(period.child(0)) == "NHL"

    def test_period_header_falls_back_to_the_tree_league(self, qapp):
        # This is what lets Alt+S work on a period header, which carries no tag.
        host = Host("NBA")
        _, period = build_period(host, [located(25, 3)])
        assert host._play_audio_league(period) == "NBA"

    def test_unsupported_league_is_not_sonifiable(self, qapp):
        host = Host("NFL")
        _, period = build_period(host, [located(25, 3)])
        assert host._play_audio_league(period) is None
        assert host._play_audio_league(period.child(0)) is None

    def test_none_item(self, qapp):
        assert Host("NBA")._play_audio_league(None) is None


class TestSinglePlay:
    def test_announces_the_location(self, qapp):
        host = Host("NBA")
        _, period = build_period(host, [located(25, 3, "Layup Shot")])
        host._play_play_audio(period.child(0))
        assert host.announced == ["at the rim"]

    def test_says_so_when_a_play_has_no_location(self, qapp):
        host = Host("NBA")
        _, period = build_period(host, [unlocated()])
        host._play_play_audio(period.child(0))
        assert host.announced == ["This play has no location"]

    def test_period_header_has_nothing_to_play(self, qapp):
        host = Host("NBA")
        _, period = build_period(host, [located(25, 3)])
        host._play_play_audio(period)
        assert host.announced == ["No play selected"]

    def test_hockey_play(self, qapp):
        host = Host("NHL")
        _, period = build_period(host, [located(85, 0, "Goal")], "1st Period")
        host._play_play_audio(period.child(0))
        assert host.announced == ["far end, in the slot"]


class TestSequence:
    def test_walks_the_period_from_its_header(self, qapp):
        host = Host("NBA")
        plays = [located(25, 3), unlocated(), located(3, 3), located(25, 27)]
        _, period = build_period(host, plays)
        host._play_play_sequence(period)
        assert host.announced == ["Playing 3 of 4 plays in 1st Quarter"]

    def test_walks_the_period_a_play_belongs_to(self, qapp):
        host = Host("NBA")
        plays = [located(25, 3), located(3, 3)]
        _, period = build_period(host, plays)
        host._play_play_sequence(period.child(1))
        assert host.announced == ["Playing 2 of 2 plays in 1st Quarter"]

    def test_period_with_no_located_plays(self, qapp):
        host = Host("NBA")
        _, period = build_period(host, [unlocated(), unlocated("Full Timeout")])
        host._play_play_sequence(period)
        assert host.announced == ["No plays in this period have a location"]

    def test_empty_period(self, qapp):
        host = Host("NBA")
        _, period = build_period(host, [])
        host._play_play_sequence(period)
        assert host.announced == ["No plays to play"]


class TestButton:
    def test_uses_the_tree_selection(self, qapp):
        host = Host("NBA")
        tree, period = build_period(host, [located(25, 3), located(3, 3)])
        tree.setCurrentItem(period.child(1))
        host._play_current_play_audio(tree)
        assert host.announced == ["from three, left side"]

    def test_nothing_selected(self, qapp):
        host = Host("NBA")
        tree, _ = build_period(host, [located(25, 3)])
        tree.setCurrentItem(None)
        host._play_current_play_audio(tree)
        assert host.announced == ["No play selected"]


class TestTreeBuildersTagTheirPlays:
    """The builders have to call _tag_play_for_audio or none of the above fires."""

    # The two builders plus everything they reach for, transitively.
    HELPERS = (
        "_apply_basketball_play_styling",
        "_build_basketball_tree",
        "_build_generic_tree",
        "_clean_basketball_action_text",
        "_extract_basketball_clock_display",
        "_extract_basketball_score_info",
        "_extract_play_clock_display",
        "_format_basketball_play_entry",
        "_format_clock_play_entry",
        "_get_basketball_team_labels",
        "_ordinal_period_label",
        "_parse_basketball_clock",
        "_safe_int",
    )

    @pytest.mark.parametrize(
        "builder,league",
        [
            ("_build_basketball_tree", "NBA"),
            ("_build_generic_tree", "NHL"),
        ],
    )
    def test_builder_tags_play_items(self, qapp, builder, league):
        host = Host(league)
        # Borrow the real builder and the formatting helpers it calls. Named
        # explicitly rather than swept from dir(), because Qt's own __getattr__
        # rejects a non-QObject receiver.
        for name in self.HELPERS:
            setattr(Host, name, getattr(scores.GameDetailsView, name))

        plays = [
            {
                "text": "Jump Shot",
                "type": {"text": "Jump Shot"},
                "period": {"number": 1, "displayValue": "1st Quarter"},
                "clock": "11:38",
                "coordinate": {"x": 25, "y": 3},
                "awayScore": 2,
                "homeScore": 0,
            }
        ]
        tree = QTreeWidget()
        getattr(host, builder)(tree, plays)

        period = tree.topLevelItem(0)
        assert period is not None
        assert period.childCount() == 1
        data = period.child(0).data(0, Qt.ItemDataRole.UserRole)
        assert data is not None, f"{builder} did not tag its play items"
        assert data["play_audio_league"] == league
