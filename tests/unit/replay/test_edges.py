"""Small branches the replay files above don't reach by themselves."""
import os
import tempfile

import pytest

import espn_api
import game_labels
from exceptions import ApiError
import live_play_format
from services import updater

from .support import HTTP_500, TIMEOUT, load


class TestGameLabels:
    def test_an_unknown_period_uses_the_fallback(self):
        assert game_labels.basketball_period_label("NBA", 0, "Pregame") == "Pregame"
        assert game_labels.basketball_period_label("NBA", 0) == "Period 0"

    @pytest.mark.parametrize("label", ["Quarter x", "Quarter", "xOT", "Halftime"])
    def test_a_label_it_cannot_order_goes_last(self, label):
        assert game_labels.football_period_sort_key(label) == 99

    def test_a_broadcast_that_is_not_a_dict_is_skipped(self):
        assert game_labels.broadcast_names(["text", {"names": ["ESPN"]}]) == ["ESPN"]

    def test_a_group_with_no_entries_is_no_table(self):
        assert game_labels.game_standings_tables({"groups": [{"standings": {"entries": []}}]}) == []


def test_a_live_game_that_cannot_be_laid_out_falls_back_to_one_line(monkeypatch):
    def broken(*args):
        raise ValueError("bad play text")

    monkeypatch.setattr(live_play_format, "format_football", broken)
    teams = [{"name": "Away", "score": "1"}, {"name": "Home", "score": "2"}]
    text = live_play_format.format_live_game("NFL", teams, "Q1", "Touchdown", "Away at Home")
    assert "Touchdown" in text and "\n" not in text


class TestScheduleFailures:
    def test_a_timeout_on_college_basketball_stops_at_the_first_request(self, espn):
        espn.on("/schedule", TIMEOUT)
        with pytest.raises(ApiError):
            espn_api.get_team_schedule("NCAAM", "275", season=2027)
        assert len(espn.calls) == 1

    def test_a_timeout_on_one_college_basketball_season_type_reaches_the_caller(self, espn):
        real = load("schedule_NCAAM_275.json")
        espn.on("/schedule", lambda url: TIMEOUT if "seasontype=1" in url else real)
        with pytest.raises(ApiError):
            espn_api.get_team_schedule("NCAAM", "275", season=2027)

    def test_an_empty_college_football_season_asks_for_no_other(self, espn):
        """Any other season would time out here, so asking for one would raise."""
        espn.on("/schedule", lambda url: {"events": []} if "season=2010" in url else TIMEOUT)
        assert espn_api.get_team_schedule("NCAAF", "333", season=2010) == []


class TestFootballLiveDetail:
    def comp(self, **situation):
        return {"competitors": [
            {"homeAway": "home", "score": "7", "team": {"id": "1", "displayName": "Home", "abbreviation": "HOM"}},
            {"homeAway": "away", "score": "3", "team": {"id": "2", "displayName": "Away", "abbreviation": "AWY"}},
        ], "status": {"displayClock": "4:20", "period": 5}, "situation": situation}

    def test_the_home_team_in_the_red_zone_and_overtime(self):
        detail = espn_api.scoreboard_live_detail("NFL", self.comp(possession="1", isRedZone=True, downDistanceText="1st & Goal"))
        assert detail == "Away 3 at Home 7 (RZ)\n4:20 OT | HOM ball | 1st & Goal"

    def test_only_one_team_listed_has_no_detail(self):
        comp = self.comp(down=1)
        comp["competitors"].pop()
        assert espn_api.scoreboard_live_detail("NFL", comp) is None


class TestWildCardEdges:
    def test_a_league_with_no_race_is_left_out(self, espn):
        espn.on("/mlb/standings", {"children": [{"name": "American League", "standings": {"entries": []}}]})
        assert espn_api.get_mlb_wildcard_standings() == {}

    def test_a_stat_that_is_not_a_number_is_zero_and_a_missing_one_its_default(self):
        entry = {"stats": [{"name": "wins", "value": "many"}]}
        assert espn_api._mlb_stat_value(entry, "wins") == 0.0
        assert espn_api._mlb_stat_value(entry, "losses", 5.0) == 5.0
        assert espn_api._mlb_stat(entry, "streak", "-") == "-"


def test_fresh_nba_standings_cover_the_west_and_an_unknown_team(espn):
    espn.on("/nba/standings", {"children": []})
    espn.on("/nba/teams$", {"sports": [{"leagues": [{"teams": [
        {"team": {"id": "1", "abbreviation": "LAL", "displayName": "Lakers"}},
        {"team": {"id": "2", "abbreviation": "ZZZ", "displayName": "Newcomers"}},
    ]}]}]})
    divisions = {r["team_name"]: r["division"] for r in espn_api.get_standings("NBA")}
    assert divisions == {"Lakers": "Pacific", "Newcomers": "Unknown Conference"}


def test_a_failed_college_football_regular_season_stops_there(espn):
    espn.on("/schedule", HTTP_500)
    with pytest.raises(ApiError):
        espn_api.get_team_schedule("NCAAF", "333", season=2020)
    assert len(espn.calls) == 1


class TestInstallerDownload:
    class Stream:
        status_code = 200
        headers = {"Content-Length": "6"}

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            yield b"abc"
            yield b""
            yield b"def"

    @pytest.fixture
    def stream(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
        monkeypatch.setattr(updater.requests, "get", lambda *a, **k: self.Stream())
        return tmp_path

    def test_it_saves_the_file_and_reports_progress(self, stream):
        progress = []
        path = updater.download_installer("https://x/Scores-Setup.exe", progress=lambda done, total: progress.append((done, total)))
        with open(path, "rb") as f:
            assert f.read() == b"abcdef"
        assert progress == [(3, 6), (6, 6)]
        assert os.path.basename(path) == "Scores-Setup.exe"

    def test_cancelling_removes_the_partial_file(self, stream):
        assert updater.download_installer("https://x/Scores-Setup.exe", should_cancel=lambda: True) is None
        assert not os.path.exists(updater.installer_path("https://x/Scores-Setup.exe"))
