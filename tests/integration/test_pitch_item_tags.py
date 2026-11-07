"""MLB pitch items are tagged when the tree is built, and only the tag counts.

_is_pitch_item used to guess from the item's text ("ball", "strike", "foul", a
pair of numbers in brackets), which basketball's "Jump Ball" and "Loose ball
foul" also match. Now the baseball builder tags every pitch with `is_pitch` and
every at-bat with `is_at_bat`, and the pitch audio reads nothing else.

The trees here are built by the real builders from real ESPN payloads,
borrowed onto a stand-in the same way test_play_audio_wiring.py does it. Qt
runs offscreen; no event loop is started.
"""

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QTreeWidget, QTreeWidgetItem  # noqa: E402

import play_audio_mapper  # noqa: E402
import scores  # noqa: E402
from play_audio_mapper import PlayAudioMapper  # noqa: E402

FIXTURES = Path(__file__).parent.parent / "fixtures" / "espn"
ALT = Qt.KeyboardModifier.AltModifier
View = scores.GameDetailsView


def load_plays(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["plays"]


@pytest.fixture(autouse=True)
def silent(monkeypatch):
    monkeypatch.setattr(play_audio_mapper, "play_in_background", lambda fn, *args: None)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class RecordingPitchMapper:
    """Stands in for the pitch audio mapper; notes what it was asked to play."""

    def __init__(self):
        self.played = []

    def generate_pitch_audio(self, x, y, velocity, pitch_type, batter_hand):
        self.played.append((x, y, velocity, pitch_type, batter_hand))

    def _get_location_description(self, x, y, batter_hand):
        return "somewhere"


class Host:
    """The real tree builders and pitch routing, on an object with only what they touch."""

    # Builders and everything they reach for.
    _build_baseball_tree = View._build_baseball_tree
    _build_basketball_tree = View._build_basketball_tree
    _add_baseball_plays_to_tree_group = View._add_baseball_plays_to_tree_group
    _add_baseball_plays_by_at_bat_id = View._add_baseball_plays_by_at_bat_id
    _add_baseball_plays_by_text_pattern = View._add_baseball_plays_by_text_pattern
    _is_substitution_play = View._is_substitution_play
    _build_pitch_count_summary = View._build_pitch_count_summary
    _build_pitch_tree_item = View._build_pitch_tree_item
    _get_pitch_result_label = View._get_pitch_result_label
    _get_pitch_bg_color = View._get_pitch_bg_color
    _count_at_bats_in_plays = View._count_at_bats_in_plays
    _runs_in_half = View._runs_in_half
    _safe_int = View._safe_int
    _get_basketball_team_labels = View._get_basketball_team_labels
    _apply_basketball_play_styling = View._apply_basketball_play_styling
    _clean_basketball_action_text = View._clean_basketball_action_text
    _extract_basketball_clock_display = View._extract_basketball_clock_display
    _extract_basketball_score_info = View._extract_basketball_score_info
    _extract_play_clock_display = View._extract_play_clock_display
    _format_basketball_play_entry = View._format_basketball_play_entry
    _format_clock_play_entry = View._format_clock_play_entry
    _ordinal_period_label = View._ordinal_period_label
    _parse_basketball_clock = View._parse_basketball_clock
    _tag_play_for_audio = View._tag_play_for_audio
    _label_period_for_audio = View._label_period_for_audio

    # What is under test.
    _is_pitch_item = View._is_pitch_item
    _is_at_bat_item = View._is_at_bat_item
    _pitch_has_location = View._pitch_has_location
    _play_audio_league = View._play_audio_league
    _play_play_audio = View._play_play_audio
    _handle_plays_audio_key = View._handle_plays_audio_key
    _play_pitch_audio = View._play_pitch_audio
    _play_pitch_sequence = View._play_pitch_sequence
    _play_current_pitch_audio = View._play_current_pitch_audio
    _is_mlb_plays = View._is_mlb_plays
    _stop_pitch_sequence = View._stop_pitch_sequence

    def __init__(self, league):
        self.league = league
        self._plays_sport_type = league
        self.play_audio_mapper = PlayAudioMapper()
        self.audio_mapper = RecordingPitchMapper()
        self.announced = []
        self.feedback = []
        self.errors = []
        self.sequence = None

    def _announce_play_audio(self, message):
        self.announced.append(message)

    def _on_audio_feedback(self, message):
        self.feedback.append(message)

    def _on_audio_error(self, message):
        self.errors.append(message)

    def _play_pitch_sequence_with_timing(self, pitch_items, index, token):
        # The real one plays the first and schedules the rest on a QTimer;
        # TestSequenceTiming runs it.
        self.sequence = list(pitch_items)


def walk(tree):
    """Every item in the tree with its depth (0 = top level)."""
    stack = [(tree.topLevelItem(i), 0) for i in reversed(range(tree.topLevelItemCount()))]
    while stack:
        item, depth = stack.pop()
        yield item, depth
        for i in reversed(range(item.childCount())):
            stack.append((item.child(i), depth + 1))


def mlb_tree(host):
    tree = QTreeWidget()
    host._build_baseball_tree(tree, load_plays("plays_MLB_401817091.json"))
    return tree


class TestMlbTreeTags:
    def test_every_pitch_is_tagged_with_what_the_audio_needs(self, qapp):
        host = Host("MLB")
        tree = mlb_tree(host)
        pitches = [item for item, depth in walk(tree) if host._is_pitch_item(item)]
        expected = sum(
            1 for p in load_plays("plays_MLB_401817091.json") if p.get("summaryType") == "P"
        )
        assert len(pitches) == expected > 0
        for item in pitches:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            assert set(data) >= {"x", "y", "velocity", "pitch_type", "batter_hand", "is_pitch"}
            # Inning > half > at-bat > pitch.
            assert host._is_at_bat_item(item.parent())
        # This game has a coordinate on every pitch.
        assert all(host._pitch_has_location(item) for item in pitches)

    def test_pitches_sit_only_at_the_fourth_level(self, qapp):
        host = Host("MLB")
        for item, depth in walk(mlb_tree(host)):
            assert host._is_pitch_item(item) == (depth == 3), item.text(0)

    def test_at_bats_are_tagged_and_are_not_pitches(self, qapp):
        host = Host("MLB")
        tree = mlb_tree(host)
        at_bats = [item for item, _ in walk(tree) if host._is_at_bat_item(item)]
        assert at_bats
        for item in at_bats:
            assert not host._is_pitch_item(item)
        # The at-bat text is full of the old trigger words; the tag decides.
        assert any("swinging" in item.text(0).lower() or "ball" in item.text(0).lower()
                   for item in at_bats)

    def test_innings_halves_and_substitutions_are_neither(self, qapp):
        host = Host("MLB")
        tree = mlb_tree(host)
        rows = list(walk(tree))
        substitutions = [item for item, _ in rows if item.text(0).startswith(">> ")]
        # Inning 8 has a pinch hitter and a relief change.
        assert any("hit for" in item.text(0) for item in substitutions)
        assert any("relieved" in item.text(0) for item in substitutions)
        for item, depth in rows:
            if depth < 2 or item in substitutions:
                assert not host._is_pitch_item(item), item.text(0)
                assert not host._is_at_bat_item(item), item.text(0)

    def test_text_pattern_fallback_tags_too(self, qapp):
        # Older payloads have no atBatId; the fallback grouper must tag the same way.
        host = Host("MLB")
        plays = [
            {k: v for k, v in p.items() if k != "atBatId"}
            for p in load_plays("plays_MLB_401817091.json")
        ]
        tree = QTreeWidget()
        host._build_baseball_tree(tree, plays)
        rows = list(walk(tree))
        assert any(host._is_pitch_item(item) for item, _ in rows)
        assert any(host._is_at_bat_item(item) for item, _ in rows)
        for item, depth in rows:
            if host._is_pitch_item(item):
                assert host._is_at_bat_item(item.parent())


class TestOtherSportsAreNotPitches:
    def test_nba_tree_has_no_pitches(self, qapp):
        host = Host("NBA")
        tree = QTreeWidget()
        host._build_basketball_tree(tree, load_plays("plays_NBA_401909906.json"))
        rows = list(walk(tree))
        # "Loose ball foul" carries two of the old trigger words.
        assert any("loose ball foul" in item.text(0).lower() for item, _ in rows)
        for item, _ in rows:
            assert not host._is_pitch_item(item), item.text(0)
            assert not host._is_at_bat_item(item), item.text(0)

    @pytest.mark.parametrize(
        "text",
        ["Jump Ball won by Toronto", "Personal Foul", "Strike (3, 4)", "95 mph fastball"],
    )
    def test_untagged_items_are_never_pitches(self, qapp, text):
        host = Host("MLB")
        assert not host._is_pitch_item(QTreeWidgetItem([text]))

    def test_none_is_not_a_pitch(self, qapp):
        host = Host("MLB")
        assert not host._is_pitch_item(None)
        assert not host._is_at_bat_item(None)

    def test_truthy_but_not_true_tag_is_not_a_pitch(self, qapp):
        host = Host("MLB")
        item = QTreeWidgetItem(["x"])
        item.setData(0, Qt.ItemDataRole.UserRole, {"is_pitch": "yes"})
        assert not host._is_pitch_item(item)


def first(host, tree, predicate):
    return next(item for item, _ in walk(tree) if predicate(item))


class TestMlbAudioRouting:
    def test_alt_p_on_a_pitch_plays_its_location(self, qapp):
        host = Host("MLB")
        tree = mlb_tree(host)
        pitch = first(host, tree, host._is_pitch_item)
        assert host._handle_plays_audio_key(pitch, Qt.Key.Key_P, ALT)
        data = pitch.data(0, Qt.ItemDataRole.UserRole)
        assert host.audio_mapper.played == [
            (data["x"], data["y"], data["velocity"], data["pitch_type"], data["batter_hand"])
        ]
        assert host.announced == []

    def test_alt_p_on_an_at_bat_says_to_pick_a_pitch(self, qapp):
        host = Host("MLB")
        tree = mlb_tree(host)
        at_bat = first(host, tree, host._is_at_bat_item)
        assert host._handle_plays_audio_key(at_bat, Qt.Key.Key_P, ALT)
        assert host.audio_mapper.played == []
        assert host.announced == ["Select a pitch to play its audio"]

    def test_inning_and_half_headers_say_what_to_select(self, qapp):
        # Silence would sound like a broken key.
        host = Host("MLB")
        tree = mlb_tree(host)
        inning = tree.topLevelItem(0)
        for header in (inning, inning.child(0)):
            assert host._handle_plays_audio_key(header, Qt.Key.Key_P, ALT)
            assert host._handle_plays_audio_key(header, Qt.Key.Key_S, ALT)
        assert host.audio_mapper.played == [] and host.sequence is None
        assert host.announced == [
            "Select a pitch to play its audio",
            "Select an at-bat or a pitch to play its pitches",
        ] * 2

    def test_without_audio_it_says_so(self, qapp):
        host = Host("MLB")
        tree = mlb_tree(host)
        host.audio_mapper = None
        pitch = first(host, tree, host._is_pitch_item)
        assert host._handle_plays_audio_key(pitch, Qt.Key.Key_P, ALT)
        assert host._handle_plays_audio_key(pitch.parent(), Qt.Key.Key_S, ALT)
        tree.setCurrentItem(pitch)
        host._play_current_pitch_audio(tree)
        assert host.announced == ["Pitch audio isn't available"] * 3
        assert host.sequence is None

    def test_football_keys_are_left_alone(self, qapp):
        host = Host("NFL")
        item = QTreeWidgetItem(["Personal Foul, 15 yards"])
        assert not host._handle_plays_audio_key(item, Qt.Key.Key_P, ALT)
        assert not host._handle_plays_audio_key(item, Qt.Key.Key_S, ALT)
        assert host.announced == []

    def test_at_bat_with_no_pitches_says_so(self, qapp):
        host = Host("MLB")
        at_bat = QTreeWidgetItem(["Early pitches to Lindor"])
        at_bat.setData(0, Qt.ItemDataRole.UserRole, {"is_at_bat": True})
        host._play_pitch_sequence(at_bat)
        assert host.sequence is None
        assert host.announced == ["This at-bat has no pitches"]

    def test_alt_s_on_an_at_bat_walks_its_own_pitches(self, qapp):
        host = Host("MLB")
        tree = mlb_tree(host)
        at_bat = first(host, tree, lambda i: host._is_at_bat_item(i) and i.childCount() > 1)
        assert host._handle_plays_audio_key(at_bat, Qt.Key.Key_S, ALT)
        assert host.sequence == [at_bat.child(i) for i in range(at_bat.childCount())]

    def test_alt_s_on_a_pitch_walks_its_at_bat(self, qapp):
        host = Host("MLB")
        tree = mlb_tree(host)
        at_bat = first(host, tree, lambda i: host._is_at_bat_item(i) and i.childCount() > 1)
        assert host._handle_plays_audio_key(at_bat.child(1), Qt.Key.Key_S, ALT)
        assert host.sequence == [at_bat.child(i) for i in range(at_bat.childCount())]

    def test_sequence_skips_pitches_without_a_location(self, qapp):
        host = Host("MLB")
        tree = mlb_tree(host)
        at_bat = first(host, tree, lambda i: host._is_at_bat_item(i) and i.childCount() > 1)
        stripped = dict(at_bat.child(0).data(0, Qt.ItemDataRole.UserRole), x=None, y=None)
        at_bat.child(0).setData(0, Qt.ItemDataRole.UserRole, stripped)
        host._play_pitch_sequence(at_bat)
        assert host.sequence == [at_bat.child(i) for i in range(1, at_bat.childCount())]

    def test_sequence_with_no_located_pitches_says_so(self, qapp):
        host = Host("MLB")
        at_bat = QTreeWidgetItem(["Early pitches to Lindor"])
        at_bat.setData(0, Qt.ItemDataRole.UserRole, {"is_at_bat": True})
        pitch = QTreeWidgetItem(["  #1  [B]"])
        pitch.setData(0, Qt.ItemDataRole.UserRole, {"is_pitch": True, "x": None, "y": None})
        at_bat.addChild(pitch)
        host._play_pitch_sequence(at_bat)
        assert host.sequence is None
        assert host.announced == ["No pitches in this at-bat have a location"]

    def test_pitch_without_a_location_says_so(self, qapp):
        host = Host("MLB")
        pitch = QTreeWidgetItem(["  #1  [B]"])
        pitch.setData(0, Qt.ItemDataRole.UserRole, {"is_pitch": True, "x": None, "y": None})
        host._play_pitch_audio(pitch)
        assert host.audio_mapper.played == []
        assert host.announced == ["This pitch has no location"]

    def test_pitch_audio_ignores_an_untagged_item(self, qapp):
        host = Host("MLB")
        host._play_pitch_audio(QTreeWidgetItem(["Strike (100, 120) 95 mph"]))
        assert host.audio_mapper.played == [] and host.announced == []

    def test_button_follows_the_selection(self, qapp):
        host = Host("MLB")
        tree = mlb_tree(host)
        pitch = first(host, tree, host._is_pitch_item)
        tree.setCurrentItem(pitch)
        host._play_current_pitch_audio(tree)
        assert len(host.audio_mapper.played) == 1

    def test_button_on_an_at_bat_says_to_pick_a_pitch(self, qapp):
        host = Host("MLB")
        tree = mlb_tree(host)
        tree.setCurrentItem(first(host, tree, host._is_at_bat_item))
        host._play_current_pitch_audio(tree)
        assert host.audio_mapper.played == []
        assert host.announced == ["Select a pitch to play its audio"]

    def test_basketball_foul_is_untagged_and_never_reaches_the_pitch_path(self, qapp):
        host = Host("NBA")
        tree = QTreeWidget()
        host._build_basketball_tree(tree, load_plays("plays_NBA_401909906.json"))
        foul = first(host, tree, lambda i: "loose ball foul" in i.text(0).lower())
        assert not host._is_pitch_item(foul)
        host._handle_plays_audio_key(foul, Qt.Key.Key_P, ALT)
        assert host.audio_mapper.played == []


class TimingHost(Host):
    """Host running the real sequence timing, with the QTimer steps held back."""

    _play_pitch_sequence_with_timing = View._play_pitch_sequence_with_timing


class TestSequenceTiming:
    @pytest.fixture
    def scheduled(self, monkeypatch):
        steps = []
        monkeypatch.setattr(scores.QTimer, "singleShot", lambda ms, fn: steps.append(fn))
        return steps

    def run_all(self, steps):
        while steps:
            steps.pop(0)()

    def located_at_bat(self, host):
        tree = mlb_tree(host)
        return tree, first(host, tree, lambda i: host._is_at_bat_item(i) and i.childCount() > 2)

    def test_plays_every_located_pitch_in_order(self, qapp, scheduled):
        host = TimingHost("MLB")
        _, at_bat = self.located_at_bat(host)
        host._play_pitch_sequence(at_bat)
        self.run_all(scheduled)
        expected = [at_bat.child(i).data(0, Qt.ItemDataRole.UserRole)
                    for i in range(at_bat.childCount())]
        assert [p[:2] for p in host.audio_mapper.played] == [(d["x"], d["y"]) for d in expected]
        assert host.announced == []

    def test_stopping_cancels_the_rest(self, qapp, scheduled):
        # What closing the plays dialog does.
        host = TimingHost("MLB")
        _, at_bat = self.located_at_bat(host)
        host._play_pitch_sequence(at_bat)
        host._stop_pitch_sequence()
        self.run_all(scheduled)
        assert len(host.audio_mapper.played) == 1

    def test_a_new_sequence_replaces_the_old(self, qapp, scheduled):
        host = TimingHost("MLB")
        tree, at_bat = self.located_at_bat(host)
        host._play_pitch_sequence(at_bat)
        host.audio_mapper.played.clear()
        host._play_pitch_sequence(at_bat)
        self.run_all(scheduled)
        # Only the second run's pitches, not two runs interleaved.
        assert len(host.audio_mapper.played) == at_bat.childCount()
