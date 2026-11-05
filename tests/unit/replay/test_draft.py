"""The NFL draft, from the one request both apps make, and the fantasy feed's failure paths."""
import pytest

import espn_api
from exceptions import ApiError

from .support import HTTP_404, HTTP_500, TIMEOUT, load

URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/draft?season=2026"


@pytest.fixture
def draft(espn):
    espn.on(r"/football/nfl/draft\?season=2026", load("draft_site_NFL_2026.json"))
    return espn


class TestDraft:
    def test_one_request(self, draft):
        espn_api.get_draft(2026)
        espn_api.get_draft_round(2026, 1)
        espn_api.get_draft_round(2026, 2)
        assert draft.calls == [URL]

    def test_it_is_asked_again_after_a_while_for_a_draft_in_progress(self, draft, monkeypatch):
        espn_api.get_draft(2026)
        later = espn_api.time.monotonic() + espn_api.DRAFT_CACHE_SECONDS + 1
        monkeypatch.setattr(espn_api.time, "monotonic", lambda: later)
        espn_api.get_draft(2026)
        assert draft.calls == [URL, URL]

    def test_real_draft(self, draft):
        result = espn_api.get_draft("2026")
        assert (result["year"], result["num_rounds"], result["status"]) == (2026, 7, "post")
        assert result["rounds"][0] == {"number": 1, "display_name": "1st Round", "short_name": "1st"}
        assert result["rounds"][2] == {"number": 3, "display_name": "3rd Round", "short_name": "3rd"}
        assert result["rounds"][6] == {"number": 7, "display_name": "7th Round", "short_name": "7th"}

    def test_a_draft_in_progress(self, espn):
        data = load("draft_site_NFL_2026.json")
        data["status"]["state"] = "IN"
        espn.on("/draft", data)
        assert espn_api.get_draft(2026)["status"] == "in"

    def test_no_status_assumes_finished(self, espn):
        data = load("draft_site_NFL_2026.json")
        del data["status"]
        espn.on("/draft", data)
        assert espn_api.get_draft(2026)["status"] == "post"

    def test_an_empty_body_is_not_a_finished_seven_round_draft(self, espn):
        espn.on("/draft", {})
        assert espn_api.get_draft(2026) is None

    def test_espn_having_none_is_none_and_is_not_kept(self, espn):
        espn.on("/draft", HTTP_404)
        assert espn_api.get_draft(2026) is None
        espn.on("/draft", load("draft_site_NFL_2026.json"))
        assert espn_api.get_draft(2026)["num_rounds"] == 7

    @pytest.mark.parametrize("reply", [HTTP_500, TIMEOUT])
    def test_failing_says_so_and_is_not_kept(self, espn, reply):
        """The dialog would otherwise say the year has no draft."""
        espn.on("/draft", reply)
        with pytest.raises(ApiError, match="the draft"):
            espn_api.get_draft(2026)
        espn.on("/draft", load("draft_site_NFL_2026.json"))
        assert espn_api.get_draft(2026)["num_rounds"] == 7

    def test_ordinals(self):
        assert [espn_api._ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23)] == [
            "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd"]


class TestDraftRound:
    def test_real_picks_in_order(self, draft):
        first, second, sixth = espn_api.get_draft_round(2026, 1)
        assert first == {
            "overall": 1, "pick": 1, "round": 1, "traded": False, "trade_note": "", "team_abbrev": "LV",
            "team_name": "Las Vegas Raiders", "player_name": "Fernando Mendoza", "position": "QB",
            "status_name": "SELECTION_MADE", "college": "Indiana",
        }
        assert (second["player_name"], second["position"], second["college"]) == ("David Bailey", "EDGE", "Texas Tech")
        assert (sixth["overall"], sixth["traded"], sixth["trade_note"]) == (6, True, "From CLE")

    def test_a_school_reads_as_its_name_not_its_short_name(self, draft):
        pick = [pick for pick in espn_api.get_draft_round(2026, 3) if pick["overall"] == 84]
        assert pick[0]["college"] == "Georgia State"

    def test_a_position_an_old_drafts_list_leaves_out(self, espn):
        data = load("draft_site_NFL_2026.json")
        data["picks"][0]["athlete"]["position"]["id"] = "91"
        data["picks"][1]["athlete"]["position"]["id"] = "22"
        data["picks"][4]["athlete"]["position"]["id"] = "99999"
        espn.on("/draft", data)
        by_overall = {pick["overall"]: pick for pick in espn_api.get_draft_round(2026, 1)}
        assert by_overall[1]["position"] == "C"
        assert by_overall[2]["position"] == "PK"
        assert by_overall[6]["position"] == ""

    def test_a_draft_yet_to_happen(self, espn):
        """The real shape: its rounds and status, with no picks and no teams."""
        espn.on("/draft", {"displayName": "2027 NFL Draft", "picks": [], "positions": [], "rounds": 7,
                           "status": {"description": "Scheduled", "name": "SCHEDULED", "round": 1, "state": "pre"},
                           "year": 2027})
        draft = espn_api.get_draft(2026)
        assert (draft["status"], draft["num_rounds"]) == ("pre", 7)
        assert espn_api.get_draft_round(2026, 1) == []

    def test_a_pick_on_the_clock_says_so(self, espn):
        data = load("draft_site_NFL_2026.json")
        del data["picks"][0]["athlete"]
        data["picks"][0]["status"] = "ON_THE_CLOCK"
        espn.on("/draft", data)
        assert espn_api.get_draft_round(2026, 1)[0]["status_name"] == "ON_THE_CLOCK"

    def test_a_round_that_does_not_exist(self, draft):
        assert espn_api.get_draft_round(2026, 99) == []

    def test_espn_having_none_is_empty(self, espn):
        espn.on("/draft", HTTP_404)
        assert espn_api.get_draft_round(2026, 1) == []

    def test_failing_says_so(self, espn):
        espn.on("/draft", TIMEOUT)
        with pytest.raises(ApiError, match="the draft"):
            espn_api.get_draft_round(2026, 1)

    def test_a_team_missing_from_the_list_is_not_made_up(self, espn):
        data = load("draft_site_NFL_2026.json")
        data["teams"] = []
        espn.on("/draft", data)
        first = espn_api.get_draft_round(2026, 1)[0]
        assert first["player_name"] == "Fernando Mendoza"
        assert (first["team_abbrev"], first["team_name"]) == ("?", "Unknown")

    def test_a_pick_not_made_yet_has_no_athlete(self, espn):
        data = load("draft_site_NFL_2026.json")
        del data["picks"][0]["athlete"]
        espn.on("/draft", data)
        first = espn_api.get_draft_round(2026, 1)[0]
        assert (first["player_name"], first["position"], first["college"]) == ("", "", "")
        assert first["team_abbrev"] == "LV"


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
        with pytest.raises(ApiError) as caught:
            espn_api.get_fantasy_cheatsheet(2026)
        assert str(caught.value) == espn_api.FANTASY_UNAVAILABLE

    def test_both_seasons_timing_out_says_so_in_the_same_words(self, espn):
        espn.on("/players", TIMEOUT)
        with pytest.raises(ApiError) as caught:
            espn_api.get_fantasy_cheatsheet(2026)
        assert str(caught.value) == espn_api.FANTASY_UNAVAILABLE

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
