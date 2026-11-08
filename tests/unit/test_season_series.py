"""season_series.py against the shared grid the iPhone's SeasonSeries.swift is held to,
and the game rows Windows shows from a real MLB summary."""

import json
from pathlib import Path

import pytest

import season_series as ss

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
GRID = json.loads((FIXTURES / "season_series_grid.json").read_text(encoding="utf-8"))


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _summary(case):
    return _load(case["fixture"]) if "fixture" in case else case["summary"]


@pytest.mark.parametrize("case", GRID["cases"], ids=lambda c: c["name"])
def test_grid(case):
    summary = _summary(case)
    shown = ss.series(summary, case["names"])
    assert [{k: s[k] for k in ("label", "text", "games")} for s in shown] == case["expected"]
    if "fixture" in case:
        assert ss.team_names(summary) == case["names"]
        assert ss.summary_line(summary) == case["expected_line"]
    elif shown:
        assert f"{shown[0]['label']}: {shown[0]['text']}" == case["expected_line"]
    else:
        assert ss.summary_line(summary) == ""


def test_game_rows_mark_this_game_and_extra_innings():
    summary = _load("espn/summary_final_MLB_401817091.json")
    regular = ss.series(summary)[0]["entry"]
    rows = ss.game_rows(regular, ss.team_names(summary), "401817091")
    assert len(rows) == 13
    assert all(len(row) == len(ss.GAME_HEADERS) for row in rows)
    games = [row[1:] for row in rows]
    assert ["Mets 16 at Nationals 7", "Mets", "Final/12"] in games
    assert ["Mets 7 at Nationals 1", "Mets", "Final, this game"] in games
    assert sum(1 for row in rows if row[3].endswith("this game")) == 1
    assert all(row[0] for row in rows)


def test_a_game_to_come_shows_its_start_time():
    entry = {"events": [{"id": "9", "date": "2026-09-30T23:05Z", "timeValid": True,
                         "statusType": {"completed": False, "state": "pre", "detail": "9/30 - 7:05 PM EDT"},
                         "competitors": [{"homeAway": "home", "team": {"id": "1"}, "winner": True},
                                         {"homeAway": "away", "team": {"id": "2", "displayName": "Reds"}}]}]}
    [row] = ss.game_rows(entry, {"1": "Cubs"})
    assert row[1] == "Reds at Cubs"
    assert row[2] == ""  # not finished, so no winner whatever the flag says
    assert row[3].endswith("M") and ":" in row[3]  # a local time such as 6:05 PM


def test_a_neutral_site_is_vs_and_bad_dates_are_blank():
    entry = {"events": [{"id": "1", "date": "junk", "neutralSite": True, "statusType": {"completed": True,
                                                                                         "detail": "Final"},
                         "competitors": [{"homeAway": "home", "team": {"id": "1"}, "score": "3", "winner": True},
                                         {"homeAway": "away", "team": {"id": "2"}, "score": "2"}]}]}
    assert ss.game_rows(entry, {"1": "Cubs", "2": "Reds"}) == [["", "Reds 2 vs Cubs 3", "Cubs", "Final"]]


@pytest.mark.parametrize("summary", [None, [], "junk", {"seasonseries": "x"}, {"seasonseries": [None, 4]}])
def test_bad_shapes_are_nothing(summary):
    assert ss.series(summary) == []
    assert ss.summary_line(summary) == ""


def test_bad_events_are_no_games():
    entry = {"type": "season", "title": "Regular Season Series", "events": [None, "x", {"competitors": "x"}]}
    assert ss.record_text(entry, {}) == "No games played yet"
    assert ss.game_rows({"events": "x"}, {}) == []
