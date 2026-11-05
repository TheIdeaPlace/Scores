"""What Windows reads from whole summaries, the same payloads and expected values as
iOS/SportsScoresApp/SportsScoresTests/GameSummaryTests.swift."""
import espn_api
import game_labels

from .support import load

FINAL_NFL = "summary_final_NFL_401873036.json"
PRE_NFL = "summary_pre_NFL_401873037.json"
FINAL_EPL = "summary_final_EPL_401879251.json"
OVERTIME_NCAAF = "summary_final_NCAAF_401757313_2OT.json"


def test_weather_before_an_outdoor_kickoff():
    info = espn_api.extract_meaningful_game_info(load(PRE_NFL))
    assert (info["weather"], info["temperature"]) == ("67°F", "67°F")


def test_a_played_game_has_attendance_and_no_weather():
    data = load(FINAL_NFL)
    assert "weather" not in espn_api.extract_meaningful_game_info(data)
    assert espn_api.format_complex_data("gameInfo", data["gameInfo"]).endswith("Attendance: 68,739")
    assert load(FINAL_EPL)["gameInfo"]["attendance"] == 12041


def test_the_tables_of_a_football_game_and_a_whole_league():
    north, west = game_labels.game_standings_tables(load(FINAL_NFL)["standings"])
    assert (north["title"], west["title"]) == ("2026 NFC North Standings", "2026 NFC West Standings")
    assert north["headers"] == ["Team", "L", "PA", "PF", "T", "PCT", "W", "Any"]
    assert north["rows"][0] == ["Minnesota", "1", "93", "140", "0", ".857", "6", "6-1"]
    premier = game_labels.game_standings_tables(load(FINAL_EPL)["standings"])
    assert [t["title"] for t in premier] == ["English Premier League Standings"]
    assert premier[0]["rows"][0] == ["Arsenal", "9", "1", "+9", "24", "0", "8", "1", "8-0-1"]
    assert len(premier[0]["rows"]) == 20


def test_the_line_of_real_games():
    assert game_labels.best_odds(load(FINAL_NFL))["details"] == "SEA -3"
    assert game_labels.best_odds(load(PRE_NFL))["details"] == "JAX -10"
    assert game_labels.best_odds(load(FINAL_EPL))["details"] == "BOU +105"


def test_odds_come_before_pickcenter():
    line = game_labels.best_odds({"odds": [{"details": "A -1"}], "pickcenter": [{"details": "B -2"}]})
    assert line["details"] == "A -1"


def test_scoring_plays_have_only_a_period_number():
    """So the wrap up's headings read Period 1, and the iPhone goes by the sport instead."""
    plays = load(FINAL_NFL)["scoringPlays"]
    assert {tuple(play["period"]) for play in plays} == {("number",)}
    assert [play["period"]["number"] for play in load(OVERTIME_NCAAF)["scoringPlays"]][-3:] == [5, 5, 6]
