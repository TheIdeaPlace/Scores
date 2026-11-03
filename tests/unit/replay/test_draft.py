"""The NFL draft, from the core API's own pieces, and the fantasy feed's failure paths."""
import pytest

import espn_api

from .support import HTTP_404, HTTP_500, TIMEOUT, load

CORE = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"
BUNDLE = load("draft_NFL_2026.json")


@pytest.fixture
def draft(espn):
    """A real round: rounds, then each pick's athlete and college by their $ref URLs."""
    espn.on(r"/seasons/2026/draft$", BUNDLE["draft"])
    espn.on(r"/seasons/2026/draft/status", BUNDLE["status"])
    espn.on(r"/seasons/2026/draft/rounds", BUNDLE["rounds"])
    espn.on(r"/football/nfl/teams\?limit=50", {"sports": [{"leagues": [{"teams": [
        {"team": {"id": "13", "abbreviation": "LV", "displayName": "Las Vegas Raiders"}},
        {"team": {"id": "20", "abbreviation": "NYJ", "shortDisplayName": "Jets"}},
    ]}]}]})
    for url, athlete in BUNDLE["athletes"].items():
        espn.on(url.replace("?", r"\?"), athlete)
    for url, college in BUNDLE["colleges"].items():
        espn.on(url.replace("?", r"\?"), college)
    return espn


class TestDraft:
    def test_urls(self, draft):
        espn_api.get_draft(2026)
        assert draft.calls[:2] == [f"{CORE}/seasons/2026/draft", f"{CORE}/seasons/2026/draft/rounds"]
        assert draft.calls[2].startswith("http://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2026/draft/status")

    def test_real_draft(self, draft):
        assert espn_api.get_draft("2026") == {
            "year": 2026, "num_rounds": 7, "status": "post",
            "rounds": [{"number": 1, "display_name": "1st Round", "short_name": "1st"},
                       {"number": 2, "display_name": "2nd Round", "short_name": "2nd"}],
        }

    def test_a_draft_in_progress(self, draft):
        draft.on(r"/draft/status", {"type": {"state": "IN"}})
        assert espn_api.get_draft(2026)["status"] == "in"

    @pytest.mark.parametrize("reply", [HTTP_500, TIMEOUT])
    def test_status_failing_assumes_finished(self, draft, reply):
        draft.on(r"/draft/status", reply)
        assert espn_api.get_draft(2026)["status"] == "post"

    def test_rounds_failing_numbers_them_from_the_count(self, draft):
        draft.on(r"/draft/rounds", HTTP_500)
        rounds = espn_api.get_draft(2026)["rounds"]
        assert len(rounds) == 7
        assert rounds[6] == {"number": 7, "display_name": "Round 7", "short_name": "7"}


class TestDraftRound:
    def test_real_picks(self, draft):
        first, second = espn_api.get_draft_round(2026, 1)
        assert first == {
            "overall": 1, "pick": 1, "round": 1, "traded": False, "trade_note": "", "team_abbrev": "LV",
            "team_name": "Las Vegas Raiders", "player_name": "Fernando Mendoza", "position": "QB",
            "status_name": "SELECTION_MADE", "college": "Indiana",
        }
        assert (second["player_name"], second["position"], second["college"]) == ("David Bailey", "EDGE", "Texas Tech")

    def test_the_team_list_is_fetched_once(self, draft):
        espn_api.get_draft_round(2026, 1)
        espn_api.get_draft_round(2026, 1)
        assert len(draft.urls(r"/football/nfl/teams")) == 1
        assert espn_api._DRAFT_TEAM_CACHE["20"] == {"abbrev": "NYJ", "name": "Jets"}

    def test_a_short_display_name_is_used_when_there_is_no_display_name(self, draft):
        assert espn_api.get_draft_round(2026, 1)[1]["team_name"] == "Jets"

    def test_a_round_that_does_not_exist(self, draft):
        assert espn_api.get_draft_round(2026, 99) == []

    @pytest.mark.parametrize("reply", [HTTP_404, TIMEOUT])
    def test_rounds_failing_is_empty(self, draft, reply):
        draft.on(r"/draft/rounds", reply)
        assert espn_api.get_draft_round(2026, 1) == []

    @pytest.mark.parametrize("reply", [HTTP_500, TIMEOUT])
    def test_teams_failing_keeps_the_picks_without_making_up_a_team(self, draft, reply):
        draft.on(r"/football/nfl/teams", reply)
        first = espn_api.get_draft_round(2026, 1)[0]
        assert first["player_name"] == "Fernando Mendoza"
        assert (first["team_abbrev"], first["team_name"]) == ("?", "Unknown")

    @pytest.mark.parametrize("reply", [HTTP_500, TIMEOUT])
    def test_an_athlete_failing_leaves_the_name_blank(self, draft, reply):
        draft.on(r"/draft/athletes/110770", reply)
        picks = {p["overall"]: p for p in espn_api.get_draft_round(2026, 1)}
        assert (picks[1]["player_name"], picks[1]["position"], picks[1]["college"]) == ("", "", "")
        assert picks[2]["player_name"] == "David Bailey"

    @pytest.mark.parametrize("reply", [HTTP_500, TIMEOUT])
    def test_a_college_failing_leaves_it_blank(self, draft, reply):
        draft.on(r"/colleges/84", reply)
        picks = {p["overall"]: p for p in espn_api.get_draft_round(2026, 1)}
        assert picks[1]["college"] == ""
        assert picks[1]["player_name"] == "Fernando Mendoza"
        assert picks[2]["college"] == "Texas Tech"

    def test_a_pick_not_made_yet_has_no_athlete(self, draft):
        rounds = load("draft_NFL_2026.json")["rounds"]
        del rounds["items"][0]["picks"][0]["athlete"]
        draft.on(r"/draft/rounds", rounds)
        assert espn_api.get_draft_round(2026, 1)[0]["player_name"] == ""

    def test_a_college_link_with_no_id_is_ignored(self, draft):
        draft.on(r"/draft/athletes/110770", {"displayName": "A", "college": {"$ref": "http://x/nope"}})
        assert espn_api.get_draft_round(2026, 1)[0]["college"] == ""


class TestFantasyFailures:
    """The cheatsheet's happy paths are in test_fantasy_cheatsheet.py."""

    def player(self, rank=5):
        return {"id": rank, "fullName": f"P{rank}", "defaultPositionId": 1, "active": True, "proTeamId": 12,
                "draftRanksByRankType": {"PPR": {"rank": rank}},
                "stats": [{"seasonId": 2025, "statSourceId": 1, "statSplitTypeId": 0, "scoringPeriodId": 0, "stats": {"3": 100.0}}]}

    def test_url_and_filter_header(self, espn):
        espn.on("/seasons/2026/players", [self.player(r) for r in range(1, 60)])
        espn_api.get_fantasy_cheatsheet(2026)
        assert espn.calls == ["https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/players"
                              "?view=kona_player_info&scoringPeriodId=0"]
        assert "X-Fantasy-Filter" in espn.kwargs[0]["headers"]

    def test_a_404_for_a_new_season_uses_the_last_one(self, espn):
        espn.on("/seasons/2026/players", HTTP_404).on("/seasons/2025/players", [self.player()])
        result = espn_api.get_fantasy_cheatsheet(2026)
        assert result["season"] == 2025
        assert [p["name"] for p in result["players"]] == ["P5"]

    def test_both_seasons_failing_raises_so_the_caller_can_say_so(self, espn):
        espn.on("/players", HTTP_500)
        with pytest.raises(RuntimeError, match="HTTP 500"):
            espn_api.get_fantasy_cheatsheet(2026)

    def test_a_near_empty_pool_tries_the_last_season(self, espn):
        espn.on("/seasons/2026/players", [self.player(1)])
        espn.on("/seasons/2025/players", [self.player(r) for r in range(1, 5)])
        result = espn_api.get_fantasy_cheatsheet(2026)
        assert (result["season"], len(result["players"])) == (2025, 4)

    def test_a_near_empty_pool_stays_if_the_last_season_fails(self, espn):
        espn.on("/seasons/2026/players", [self.player(1)]).on("/seasons/2025/players", TIMEOUT)
        assert espn_api.get_fantasy_cheatsheet(2026)["season"] == 2026

    def test_not_a_list_is_no_players(self, espn):
        espn.on("/players", {"message": "nope"})
        assert espn_api.get_fantasy_cheatsheet(2026) == {"season": 2026, "players": []}
