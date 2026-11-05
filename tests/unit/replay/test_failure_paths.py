"""Every public data function against a timeout, a 404, a 500, an empty body and a
body that isn't JSON. Nothing is invented from any of them, a failed request raises ApiError
with a sentence a screen can read out, and only ESPN having nothing reads as nothing.
"""
import json
from datetime import date
from pathlib import Path

import pytest
import requests

import espn_api
from exceptions import ApiError, SOMETHING_WENT_WRONG, plain_message
from services.api_service import ApiService
from text_utils import text_processor

from .support import EMPTY_JSON, HTTP_404, HTTP_500, NOT_JSON, TIMEOUT, FakeResponse

DAY = date(2026, 6, 20)
RAW = "HTTPSConnectionPool(host='site.api.espn.com', port=443): Max retries exceeded with url: /apis/site/v2"

# name, call, what it returns when ESPN has nothing there, and what it says when a request failed.
FAILING = [
    ("get_scores", lambda: espn_api.get_scores("NBA"), [], espn_api.SCORES_UNAVAILABLE),
    ("get_scores NCAAF", lambda: espn_api.get_scores("NCAAF"), [], espn_api.SCORES_UNAVAILABLE),
    ("get_news", lambda: espn_api.get_news("NFL"), [], espn_api.NEWS_UNAVAILABLE),
    ("get_game_details", lambda: espn_api.get_game_details("NFL", "1"), {}, espn_api.GAME_UNAVAILABLE),
    ("get_standings NFL", lambda: espn_api.get_standings("NFL"), [], espn_api.STANDINGS_UNAVAILABLE),
    ("get_standings MLB", lambda: espn_api.get_standings("MLB"), [], espn_api.STANDINGS_UNAVAILABLE),
    ("get_standings NHL", lambda: espn_api.get_standings("NHL"), [], espn_api.STANDINGS_UNAVAILABLE),
    ("the slow standings path", lambda: espn_api._get_standings_original("NBA"), [], espn_api.STANDINGS_UNAVAILABLE),
    ("get_rankings", lambda: espn_api.get_rankings("NCAAF"), {"polls": []}, espn_api.POLLS_UNAVAILABLE),
    ("get_team_info", lambda: espn_api.get_team_info("NFL", "9"), {}, espn_api.TEAM_UNAVAILABLE),
    ("get_team_roster", lambda: espn_api.get_team_roster("NFL", "9"), [], espn_api.ROSTER_UNAVAILABLE),
    ("get_team_news", lambda: espn_api.get_team_news("NFL", "9"), [], espn_api.NEWS_UNAVAILABLE),
    ("get_transactions", lambda: espn_api.get_transactions("NFL"), ([], False), espn_api.TRANSACTIONS_UNAVAILABLE),
    ("get_team_transactions", lambda: espn_api.get_team_transactions("NFL", "9"), [], espn_api.TRANSACTIONS_UNAVAILABLE),
    ("get_draft", lambda: espn_api.get_draft(2026), None, espn_api.DRAFT_UNAVAILABLE),
    ("get_draft_round", lambda: espn_api.get_draft_round(2026, 1), [], espn_api.DRAFT_UNAVAILABLE),
    ("get_golf_leaderboard", lambda: espn_api.get_golf_leaderboard("PGA"), None, espn_api.LEADERBOARD_UNAVAILABLE),
    ("get_golf_schedule", lambda: espn_api.get_golf_schedule("PGA"), [], espn_api.SCHEDULE_UNAVAILABLE),
    ("get_live_golf_tournament", lambda: espn_api.get_live_golf_tournament("PGA"), None, espn_api.LEADERBOARD_UNAVAILABLE),
    ("get_world_cup_standings", lambda: espn_api.get_world_cup_standings("WC2026"), [], espn_api.STANDINGS_UNAVAILABLE),
]

# And what a screen gets at them through the service, which leaves their words alone.
THROUGH_THE_SERVICE = [
    ("get_scores", lambda: ApiService.get_scores("NBA"), espn_api.SCORES_UNAVAILABLE),
    ("get_news", lambda: ApiService.get_news("NFL"), espn_api.NEWS_UNAVAILABLE),
    ("get_game_details", lambda: ApiService.get_game_details("NFL", "1"), espn_api.GAME_UNAVAILABLE),
    ("get_standings", lambda: ApiService.get_standings("NFL"), espn_api.STANDINGS_UNAVAILABLE),
    ("get_rankings", lambda: ApiService.get_rankings("NCAAF"), espn_api.POLLS_UNAVAILABLE),
    ("get_team_info", lambda: ApiService.get_team_info("NFL", "9"), espn_api.TEAM_UNAVAILABLE),
    ("get_team_roster", lambda: ApiService.get_team_roster("NFL", "9"), espn_api.ROSTER_UNAVAILABLE),
    ("get_team_news", lambda: ApiService.get_team_news("NFL", "9"), espn_api.NEWS_UNAVAILABLE),
    ("get_transactions", lambda: ApiService.get_transactions("NFL"), espn_api.TRANSACTIONS_UNAVAILABLE),
    ("get_team_transactions", lambda: ApiService.get_team_transactions("NFL", "9"), espn_api.TRANSACTIONS_UNAVAILABLE),
    ("get_draft", lambda: ApiService.get_draft(2026), espn_api.DRAFT_UNAVAILABLE),
    ("get_draft_round", lambda: ApiService.get_draft_round(2026, 1), espn_api.DRAFT_UNAVAILABLE),
    ("get_golf_leaderboard", lambda: ApiService.get_golf_leaderboard("PGA"), espn_api.LEADERBOARD_UNAVAILABLE),
    ("get_golf_schedule", lambda: ApiService.get_golf_schedule("PGA"), espn_api.SCHEDULE_UNAVAILABLE),
    ("get_world_cup_standings", lambda: ApiService.get_world_cup_standings("WC2026"), espn_api.STANDINGS_UNAVAILABLE),
    ("get_world_cup_scores_range", lambda: ApiService.get_world_cup_scores_range("WC2026", DAY, DAY), espn_api.SCORES_UNAVAILABLE),
    ("get_team_schedule", lambda: ApiService.get_team_schedule("NBA", "15"), espn_api.SCHEDULE_UNAVAILABLE),
    ("get_team_schedule_and_season", lambda: ApiService.get_team_schedule_and_season("NBA", "15"), espn_api.SCHEDULE_UNAVAILABLE),
]

FAILED_REQUESTS = [("timeout", TIMEOUT), ("connection", requests.ConnectionError(RAW)), ("500", HTTP_500),
                   ("503", FakeResponse({}, status=503)), ("403", FakeResponse({}, status=403)),
                   ("429", FakeResponse({}, status=429)), ("not_json", NOT_JSON)]
FAILED_IDS = [name for name, _ in FAILED_REQUESTS]
FAILED_REPLIES = [reply for _, reply in FAILED_REQUESTS]


def failing(cases):
    return [pytest.param(*case[1:], id=case[0]) for case in cases]


@pytest.mark.parametrize("reply", FAILED_REPLIES, ids=FAILED_IDS)
@pytest.mark.parametrize("call,nothing,sentence", failing(FAILING))
def test_a_failed_request_says_so_in_a_sentence(espn, call, nothing, sentence, reply):
    espn.on(".*", reply)
    with pytest.raises(ApiError) as caught:
        call()
    assert str(caught.value) == sentence
    assert sentence.endswith("Try again in a minute.")


@pytest.mark.parametrize("reply", [TIMEOUT, requests.ConnectionError(RAW), HTTP_500, NOT_JSON],
                         ids=["timeout", "connection", "500", "not_json"])
@pytest.mark.parametrize("call,sentence", failing(THROUGH_THE_SERVICE))
def test_the_service_keeps_those_words(espn, call, sentence, reply):
    espn.on(".*", reply)
    with pytest.raises(ApiError) as caught:
        call()
    assert str(caught.value) == sentence
    assert "HTTPSConnectionPool" not in str(caught.value)
    assert "read timed out" not in str(caught.value)


@pytest.mark.parametrize("reply", [HTTP_404, FakeResponse({}, status=400), EMPTY_JSON], ids=["404", "400", "empty"])
@pytest.mark.parametrize("call,nothing,sentence", failing(FAILING))
def test_espn_having_nothing_reads_as_nothing(espn, call, nothing, sentence, reply):
    espn.on(".*", reply)
    assert call() == nothing


@pytest.mark.parametrize("route,payload,call,sentence", [
    ("/scoreboard", {"events": None}, lambda: espn_api.get_scores("NBA"), espn_api.SCORES_UNAVAILABLE),
    ("/scoreboard", {"events": None}, lambda: espn_api.get_scores("NCAAF"), espn_api.SCORES_UNAVAILABLE),
    ("/news", {"articles": None}, lambda: espn_api.get_news("NFL"), espn_api.NEWS_UNAVAILABLE),
    ("/news", {"articles": None}, lambda: espn_api.get_team_news("NFL", "9"), espn_api.NEWS_UNAVAILABLE),
    ("/schedule", {"events": None}, lambda: espn_api.get_team_schedule("NFL", "9", season=2026), espn_api.SCHEDULE_UNAVAILABLE),
    ("/schedule", {"events": None}, lambda: espn_api.get_team_schedule("NBA", "15", season=2027), espn_api.SCHEDULE_UNAVAILABLE),
    ("/schedule", {"events": None}, lambda: espn_api.get_team_schedule("EPL", "359", season=2026), espn_api.SCHEDULE_UNAVAILABLE),
    ("/rankings", {"rankings": None}, lambda: espn_api.get_rankings("NCAAF"), espn_api.POLLS_UNAVAILABLE),
    ("/roster", {"athletes": None}, lambda: espn_api.get_team_roster("NFL", "9"), espn_api.ROSTER_UNAVAILABLE),
    ("/transactions", {"transactions": None}, lambda: espn_api.get_transactions("NFL"), espn_api.TRANSACTIONS_UNAVAILABLE),
    ("/transactions", {"items": None}, lambda: espn_api.get_team_transactions("NFL", "9"), espn_api.TRANSACTIONS_UNAVAILABLE),
    ("/scoreboard", {"events": None}, lambda: espn_api.get_golf_leaderboard("PGA"), espn_api.LEADERBOARD_UNAVAILABLE),
    ("/scoreboard", {"events": None}, lambda: espn_api.get_golf_schedule("PGA"), espn_api.SCHEDULE_UNAVAILABLE),
    ("/standings", {"children": None}, lambda: espn_api.get_world_cup_standings("WC2026"), espn_api.STANDINGS_UNAVAILABLE),
    ("/standings", {"children": None}, lambda: espn_api.get_standings("MLB"), espn_api.STANDINGS_UNAVAILABLE),
    ("/standings", {"children": None}, lambda: espn_api.get_standings("NFL"), espn_api.STANDINGS_UNAVAILABLE),
    ("/standings", {"children": None}, lambda: espn_api.get_standings("NBA"), espn_api.STANDINGS_UNAVAILABLE),
    ("/standings", {"children": None}, lambda: espn_api.get_standings("NHL"), espn_api.STANDINGS_UNAVAILABLE),
    ("/standings", {"children": None}, lambda: espn_api.get_standings("WNBA"), espn_api.STANDINGS_UNAVAILABLE),
    ("/standings", {"children": None}, lambda: espn_api.get_standings("NCAAM"), espn_api.STANDINGS_UNAVAILABLE),
    ("/standings", {"children": None}, lambda: espn_api.get_standings("EPL"), espn_api.STANDINGS_UNAVAILABLE),
    ("/teams", {"sports": None}, lambda: espn_api._get_standings_original("NBA"), espn_api.STANDINGS_UNAVAILABLE),
    (".*", {"sports": None}, lambda: espn_api.get_soccer_teams("EPL"), espn_api.TEAMS_UNAVAILABLE),
    ("/draft", {"year": 2026, "picks": None}, lambda: espn_api.get_draft(2026), espn_api.DRAFT_UNAVAILABLE),
    ("/draft", {"year": 2026, "picks": None}, lambda: espn_api.get_draft_round(2026, 1), espn_api.DRAFT_UNAVAILABLE),
], ids=["scores", "scores_ncaaf", "news", "team_news", "schedule_nfl", "schedule_nba", "schedule_soccer", "rankings",
        "roster", "transactions", "team_transactions", "golf_leaderboard", "golf_schedule", "world_cup_standings",
        "standings_mlb", "standings_nfl", "standings_nba", "standings_nhl", "standings_wnba", "standings_ncaam",
        "standings_soccer", "standings_slow_path", "soccer_teams", "draft", "draft_round"])
def test_a_null_list_is_told_apart_from_an_empty_one(espn, route, payload, call, sentence):
    """A null where the whole answer's list should be isn't an answer."""
    espn.on(route, payload)
    with pytest.raises(ApiError) as caught:
        call()
    assert str(caught.value) == sentence


@pytest.mark.parametrize("reply", [FakeResponse(None), [], "text", 5], ids=["null", "a_list", "text", "a_number"])
@pytest.mark.parametrize("call,nothing,sentence", failing(FAILING))
def test_a_200_with_no_object_in_it_is_not_no_data(espn, call, nothing, sentence, reply):
    """None from _espn_answer means a 400 or 404, so a 200 can't come out as it."""
    espn.on(".*", reply)
    with pytest.raises(ApiError) as caught:
        call()
    assert str(caught.value) == sentence


@pytest.mark.parametrize("reply", [FakeResponse(None), []], ids=["null", "a_list"])
def test_a_soccer_league_with_a_null_body_is_not_a_league_with_no_table(espn, reply):
    """A cup with no table says so, and that would be untrue here."""
    espn.on("/standings", reply)
    with pytest.raises(ApiError) as caught:
        espn_api.get_standings("EPL")
    assert str(caught.value) == espn_api.STANDINGS_UNAVAILABLE
    with pytest.raises(ApiError):
        espn_api.get_soccer_teams("EPL")
    assert not espn.urls("/teams")


def test_a_draft_with_a_null_list_of_picks_is_not_kept(espn):
    espn.on("/draft", {"year": 2026, "rounds": 7, "picks": None})
    with pytest.raises(ApiError):
        espn_api.get_draft(2026)
    assert espn_api._DRAFT_CACHE == {}


class TestOneBadFieldKeepsTheRest:
    def test_a_transaction_page_with_a_null_page_count_keeps_its_rows(self, espn):
        row = {"date": "2026-11-01T12:00Z", "description": "Signed someone", "team": {"abbreviation": "GB"}}
        espn.on("/transactions", {"transactions": [row], "pageCount": None})
        rows, more = espn_api.get_transactions("NFL")
        assert [r["description"] for r in rows] == ["Signed someone"]
        assert more is False

    @pytest.mark.parametrize("count,more", [(3, True), (1, False), ("3", True), ("many", False)])
    def test_the_page_count(self, espn, count, more):
        espn.on("/transactions", {"transactions": [], "pageCount": count})
        assert espn_api.get_transactions("NFL")[1] is more

    @pytest.mark.parametrize("when", [None, 5, "not a date"], ids=["null", "a_number", "text"])
    def test_a_transaction_with_a_bad_date_keeps_its_row(self, espn, when):
        espn.on("/transactions", {"transactions": [{"date": when, "description": "Signed someone"}]})
        assert espn_api.get_transactions("NFL")[0][0]["description"] == "Signed someone"
        assert espn_api.get_team_transactions("NFL", "9")[0]["description"] == "Signed someone"

    def test_a_world_cup_stat_with_a_null_value_keeps_every_group(self, espn):
        def stat(name, value, text):
            return {"name": name, "value": value, "displayValue": text}

        espn.on("/standings", {"children": [{"id": "1", "name": "Group A", "standings": {"entries": [
            {"team": {"id": "9", "displayName": "Brazil"}, "stats": [stat("points", None, "7"), stat("wins", None, None), None]},
        ]}}, {"id": "2", "name": "Group B", "standings": {"entries": [
            {"team": {"id": "8", "displayName": "Spain"}, "stats": [stat("points", 3, "3")]},
        ]}}]})
        groups = espn_api.get_world_cup_standings("WC2026")
        assert [g["name"] for g in groups] == ["Group A", "Group B"]
        brazil = groups[0]["teams"][0]
        assert (brazil["team_name"], brazil["points"], brazil["wins"], brazil["rank"]) == ("Brazil", 7, 0, 1)

    @pytest.mark.parametrize("call,broken", [
        (lambda: ApiService.get_golf_leaderboard("PGA"), "golf_total_to_par"),
        (lambda: ApiService.get_team_info("NFL", "9"), "_shown_standing"),
        (lambda: ApiService.get_team_roster("NFL", "9"), "format_height"),
    ], ids=["golf", "team", "roster"])
    def test_a_bug_while_reading_an_answer_is_not_no_data(self, espn, monkeypatch, call, broken):
        """What's left after the sweep in test_missing_fields, which the service reports."""
        monkeypatch.setattr(espn_api, broken, lambda *a: 1 / 0)
        monkeypatch.setattr("error_log._write", lambda text: None)
        competitor = {"athlete": {"displayName": "A"}}
        espn.on(".*", HTTP_404)
        espn.on("/scoreboard", {"events": [{"competitions": [{"competitors": [competitor]}]}]})
        espn.on("/teams/9$", {"team": {"displayName": "Packers"}})
        espn.on("/roster", {"athletes": [{"displayName": "A", "height": 70}]})
        espn.on("/season$", {"year": 2026})
        with pytest.raises(ApiError) as caught:
            call()
        assert str(caught.value) == SOMETHING_WENT_WRONG


class TestOneBadArticle:
    BAD = {"headline": "H", "description": "\x01 scored", "leaders": [{"leaders": [
        {"name": "passingYards", "leaders": [{"athlete": {"displayName": 5}}]}]}]}

    def test_it_keeps_its_own_words_and_the_others_keep_theirs(self, espn):
        espn.on("/news", {"articles": [self.BAD, {"headline": "G", "description": "Fine."}]})
        articles = espn_api.get_team_news("NFL", "9")
        assert [a["description"] for a in articles] == ["\x01 scored", "Fine."]

    @pytest.mark.parametrize("article", [
        {"leaders": None}, {"leaders": 5}, {"leaders": [None]}, {"leaders": [{"leaders": None}]},
        {"leaders": [{"leaders": [{"name": None}]}]}, {"boxscore": None}, {"boxscore": {"players": None}},
        {"boxscore": {"players": [{"statistics": None}]}},
        {"boxscore": {"players": [{"statistics": [{"name": "passing", "athletes": None}]}]}},
    ], ids=str)
    def test_a_hole_in_an_article_is_just_no_names(self, article):
        assert text_processor.clean_description("\x01 scored", article) == "[Player 1] scored"


@pytest.mark.parametrize("reply", [TIMEOUT, HTTP_404, HTTP_500, NOT_JSON, EMPTY_JSON],
                         ids=["timeout", "404", "500", "not_json", "empty"])
def test_the_wild_card_tab_says_unavailable_for_all_of_them(espn, reply):
    """{} reads as "unavailable", with a way to try again, so it's honest as it is."""
    espn.on(".*", reply)
    assert espn_api.get_mlb_wildcard_standings() == {}


class TestBothAppsSayTheSameThing:
    """tests/fixtures/failed_request_wording.json, which FailedRequestWordingTests holds the iPhone to."""

    WORDING = json.loads((Path(__file__).parents[2] / "fixtures" / "failed_request_wording.json").read_text(encoding="utf-8"))

    def test_each_sentence(self):
        for what, sentence in self.WORDING["unavailable"].items():
            assert espn_api._unavailable(what) == sentence

    def test_every_sentence_this_app_says_is_in_the_file(self):
        said = {value for name, value in vars(espn_api).items()
                if name.endswith("_UNAVAILABLE") and value.endswith("Try again in a minute.")}
        assert said == set(self.WORDING["unavailable"].values())

    @pytest.mark.parametrize("case", WORDING["live"])
    def test_the_live_scores_row(self, case):
        assert espn_api.live_scores_failure_text(case["failed"], case["showing"]) == case["text"]


class TestPlainMessage:
    def test_an_api_errors_words_are_kept(self):
        assert plain_message(ApiError(espn_api.NEWS_UNAVAILABLE)) == espn_api.NEWS_UNAVAILABLE

    @pytest.mark.parametrize("error", [requests.ConnectionError(RAW), KeyError("polls"), ApiError(""), ApiError()])
    def test_anything_else_is_never_read_out(self, error):
        assert plain_message(error) == SOMETHING_WENT_WRONG

    def test_a_bug_through_the_service_reads_plainly_and_is_logged(self, monkeypatch):
        logged = []
        monkeypatch.setattr(espn_api, "get_news", lambda *a: 1 / 0)
        monkeypatch.setattr("error_log._write", logged.append)
        with pytest.raises(ApiError) as caught:
            ApiService.get_news("NFL")
        assert str(caught.value) == SOMETHING_WENT_WRONG
        assert isinstance(caught.value.__cause__, ZeroDivisionError)
        assert "ZeroDivisionError" in logged[0]

    def test_a_request_failure_is_not_logged_as_a_bug(self, espn, monkeypatch):
        logged = []
        monkeypatch.setattr("error_log._write", logged.append)
        espn.on(".*", TIMEOUT)
        with pytest.raises(ApiError):
            ApiService.get_news("NFL")
        assert logged == []


class TestLiveScoresKeepWhatTheyHave:
    """The pure part of what Live Scores does when a league fails. The view is in test_league_live_games.py."""

    GAMES = [{"league": "NBA", "id": "1"}, {"league": "NHL", "id": "2"}]

    def test_a_failed_league_keeps_the_rows_last_shown(self):
        fresh = [{"league": "NHL", "id": "3"}]
        kept = espn_api.with_failed_leagues_kept(fresh, self.GAMES, ["NBA"])
        assert kept == [{"league": "NHL", "id": "3"}, {"league": "NBA", "id": "1"}]

    def test_a_league_that_answered_has_only_what_it_said(self):
        assert espn_api.with_failed_leagues_kept([], self.GAMES, ["MLB"]) == []

    def test_nothing_failed_is_only_what_came_back(self):
        assert espn_api.with_failed_leagues_kept([{"league": "NBA", "id": "9"}], self.GAMES, []) == [{"league": "NBA", "id": "9"}]

    def test_golf_goes_by_tour(self):
        last = [{"tour": "PGA"}, {"tour": "LPGA"}]
        assert espn_api.with_failed_leagues_kept([], last, ["PGA"], field="tour") == [{"tour": "PGA"}]

    @pytest.mark.parametrize("failed,who", [
        (["NBA"], "Scores for NBA"),
        (["NHL", "NBA"], "Scores for NBA and NHL"),
        (["MLB", "NHL", "NBA"], "Scores for MLB, NBA and NHL"),
        (["MLB", "NHL", "NBA", "NFL"], "Scores for MLB, NBA, NFL and NHL"),
        (["MLB", "NHL", "NBA", "NFL", "WNBA"], "Some leagues' scores"),
    ])
    def test_the_row_names_a_few_leagues(self, failed, who):
        assert espn_api.live_scores_failure_text(failed, showing=True) == (
            f"{who} may be missing or out of date. ESPN isn't providing them right now. Try again in a minute.")

    def test_a_few_failing_with_nothing_showing_still_names_them(self):
        assert espn_api.live_scores_failure_text(["NBA"], showing=False).startswith("Scores for NBA may be missing")

    def test_every_league_failing_with_nothing_showing_is_one_sentence(self):
        leagues = espn_api.get_leagues()
        assert espn_api.live_scores_failure_text(leagues, showing=False) == espn_api.SCORES_UNAVAILABLE


@pytest.mark.parametrize("league,team,season", [
    ("NFL", "9", 2026), ("NCAAF", "333", 2026), ("NBA", "15", 2027), ("NHL", "1", 2027), ("MLB", "10", 2026),
    ("WNBA", "8", 2026), ("NCAAM", "275", 2027), ("NCAAWB", "275", 2027), ("NCAAH", "1", 2027), ("NCAAWH", "1", 2027),
    ("EPL", "359", 2026),
])
class TestScheduleFailures:
    """A schedule with a part missing looks complete, and one with everything missing looks
    like an off-season, so a failure reaches the dialog. ESPN saying it has nothing doesn't."""

    @pytest.mark.parametrize("reply", [HTTP_500, FakeResponse({}, status=503), FakeResponse({}, status=403),
                                       FakeResponse({}, status=429), NOT_JSON],
                             ids=["500", "503", "403", "429", "not_json"])
    def test_a_failure_comes_out_and_the_service_wraps_it(self, espn, league, team, season, reply):
        espn.on(".*", reply)
        with pytest.raises(ApiError, match="the schedule"):
            espn_api.get_team_schedule(league, team, season=season)
        with pytest.raises(ApiError, match="the schedule"):
            ApiService.get_team_schedule(league, team, season=season)

    @pytest.mark.parametrize("reply", [HTTP_404, FakeResponse({}, status=400), EMPTY_JSON], ids=["404", "400", "empty"])
    def test_nothing_there_is_empty(self, espn, league, team, season, reply):
        espn.on(".*", reply)
        assert espn_api.get_team_schedule(league, team, season=season) == []


class TestGetDraft:
    def test_an_empty_body_is_no_draft(self, espn):
        """Not a finished seven-round one. The dialog says the year isn't available."""
        espn.on(".*", EMPTY_JSON)
        assert espn_api.get_draft(2026) is None
        assert len(espn.calls) == 1


@pytest.mark.parametrize("reply", [TIMEOUT, requests.ConnectionError("refused"), HTTP_404, HTTP_500, NOT_JSON],
                         ids=["timeout", "connection", "404", "500", "not_json"])
def test_standings_with_no_fallback_say_a_failed_request_failed(espn, reply):
    """Not as no data, and not with the text of a requests exception, through the service too."""
    espn.on(".*", reply)
    with pytest.raises(ApiError, match="Try again"):
        espn_api.get_standings("NCAAM")
    with pytest.raises(ApiError, match="Try again"):
        ApiService.get_standings("NCAAM")


@pytest.mark.parametrize("reply", [TIMEOUT, requests.ConnectionError("refused"), HTTP_404, HTTP_500, NOT_JSON, EMPTY_JSON],
                         ids=["timeout", "connection", "404", "500", "not_json", "empty"])
def test_statistics_say_a_failed_request_failed(espn, reply, monkeypatch):
    """The Statistics dialog has a row for it, which says to try again."""
    monkeypatch.setattr(espn_api.time, "sleep", lambda seconds: None)
    espn.on(".*", reply)
    for name in ("get_player_statistics", "get_team_statistics"):
        with pytest.raises(ApiError, match="Try again"):
            getattr(espn_api, name)("NBA")
        with pytest.raises(ApiError, match="Try again"):
            getattr(ApiService, name)("NBA")


@pytest.mark.parametrize("reply", [FakeResponse(None), [], "text", 5], ids=["null", "a_list", "text", "a_number"])
@pytest.mark.parametrize("name", ["get_player_statistics", "get_team_statistics"])
def test_statistics_with_no_object_in_the_answer_do_not_step_back_a_season(espn, name, reply, monkeypatch):
    """None and {} both mean ESPN has no such season, and a null body is neither."""
    monkeypatch.setattr(espn_api, "core_season", lambda path, *a, **k: {"year": 2027, "type": {"type": 2}})
    espn.on(".*", reply)
    with pytest.raises(ApiError) as caught:
        getattr(espn_api, name)("NBA")
    assert str(caught.value) == espn_api.STATISTICS_UNAVAILABLE
    asked = espn.urls("/leaders") + espn.urls("/statistics/byteam")
    assert asked and not [url for url in asked if "2026" in url]


@pytest.mark.parametrize("reply", [FakeResponse(None), {"players": []}, "text"], ids=["null", "an_object", "text"])
def test_a_fantasy_board_that_is_not_a_list_is_not_an_unpublished_season(espn, reply):
    espn.on(".*", reply)
    with pytest.raises(ApiError) as caught:
        espn_api.get_fantasy_cheatsheet(2026)
    assert str(caught.value) == espn_api.FANTASY_UNAVAILABLE


def test_a_fantasy_board_of_no_players_still_falls_back_a_season(espn):
    espn.on(".*", [])
    assert espn_api.get_fantasy_cheatsheet(2026)["players"] == []


@pytest.mark.parametrize("reply", [FakeResponse(None), [], "text"], ids=["null", "a_list", "text"])
def test_a_team_page_with_no_object_in_it_says_the_record_failed(espn, reply, monkeypatch):
    monkeypatch.setattr(espn_api, "core_season", lambda path, *a, **k: {"year": 2026, "type": {"type": 4}})
    espn.on(".*", reply)
    record, standing, failed, _ = espn_api._team_record_and_standing("basketball/nba", "1", {})
    assert (record, standing, failed) == (None, None, True)


def test_a_team_page_that_answers_with_no_record_has_not_failed(espn, monkeypatch):
    monkeypatch.setattr(espn_api, "core_season", lambda path, *a, **k: {"year": 2026, "type": {"type": 4}})
    espn.on(".*", {"team": {}})
    assert espn_api._team_record_and_standing("basketball/nba", "1", {})[2] is False


@pytest.mark.parametrize("description", [5, {"x": 1}, ["a"], True], ids=str)
def test_a_description_that_is_not_text_costs_only_itself(description):
    assert text_processor.clean_description(description) == ""


@pytest.mark.parametrize("reply", [TIMEOUT, HTTP_500, NOT_JSON], ids=["timeout", "500", "not_json"])
def test_soccer_standings_and_teams_say_so(espn, reply):
    espn.on(".*", reply)
    for call in (espn_api.get_standings, espn_api.get_soccer_teams):
        with pytest.raises(ApiError) as caught:
            call("EPL")
        assert str(caught.value) == espn_api.STANDINGS_UNAVAILABLE


def test_a_soccer_league_with_no_table_failing_its_team_list_says_so(espn):
    espn.on("/standings", {"children": []}).on("/teams", HTTP_500)
    with pytest.raises(ApiError) as caught:
        espn_api.get_soccer_teams("EPL")
    assert str(caught.value) == espn_api.TEAMS_UNAVAILABLE


def test_an_empty_summary_has_no_details():
    assert espn_api.extract_meaningful_game_info({}) == {}


def test_an_nba_404_is_no_standings(espn):
    espn.on(".*", HTTP_404)
    assert espn_api.get_standings("NBA") == []


@pytest.mark.parametrize("reply", [TIMEOUT, HTTP_500], ids=["timeout", "500"])
def test_an_nba_failure_says_so(espn, reply):
    espn.on(".*", reply)
    with pytest.raises(ApiError, match="Try again"):
        espn_api.get_standings("NBA")


def test_world_cup_scores_with_every_day_failing_say_so(espn):
    espn.on(".*", TIMEOUT)
    with pytest.raises(ApiError, match="Try again"):
        espn_api.get_world_cup_scores_range("WC2026", DAY, DAY)
    assert len(espn.calls) == 1


def test_world_cup_scores_with_a_failed_day_and_nothing_else_say_so(espn):
    """The games could have been on the day that failed."""
    espn.on("dates=20260620", {"events": []}).on("dates=20260621", HTTP_500)
    with pytest.raises(ApiError, match="Try again"):
        espn_api.get_world_cup_scores_range("WC2026", DAY, date(2026, 6, 21))


def test_a_world_cup_range_with_nothing_on_it_is_empty(espn):
    espn.on("/scoreboard", {"events": []})
    assert espn_api.get_world_cup_scores_range("WC2026", DAY, DAY) == []


def test_every_espn_request_has_a_timeout(monkeypatch):
    """One stalled response without one would block its caller forever."""
    seen = {}

    def fake_get(url, **kwargs):
        seen.update(kwargs)
        return FakeResponse({})

    monkeypatch.setattr(requests, "get", fake_get)
    espn_api._http_get("https://example.invalid/")
    assert seen["timeout"] == espn_api.DEFAULT_TIMEOUT
    espn_api._http_get("https://example.invalid/", timeout=90)
    assert seen["timeout"] == 90


def test_the_guard_stops_a_real_request():
    """The harness itself: without a stub, a request fails rather than reaching ESPN."""
    with pytest.raises(AssertionError, match="reached the network"):
        requests.get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard", timeout=1)


def test_the_harness_records_an_unstubbed_url(espn):
    from .support import UnstubbedRequest
    with pytest.raises(UnstubbedRequest):
        espn_api._http_get("https://example.invalid/never-stubbed")
    assert espn.unstubbed == ["https://example.invalid/never-stubbed"]
    espn.unstubbed.clear()  # expected here; the fixture fails the test otherwise
