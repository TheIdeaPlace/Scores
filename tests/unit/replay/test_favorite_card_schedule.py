"""get_favorite_card_schedule: the requests behind a favorite's card on Home, which are the
iPhone's fetchFavoriteCardSchedule (lenient), and what a failure does."""
from datetime import datetime

import pytest

import espn_api
from exceptions import ApiError
from services.api_service import ApiService

from .support import HTTP_404, HTTP_500, TIMEOUT, load

SITE = espn_api.BASE_URL


def by_season_type(**answers):
    """Each season type's answer; an empty list for any not given."""
    def reply(url):
        for season_type, answer in answers.items():
            if f"seasontype={season_type[-1]}" in url:
                return answer
        return {"events": []}
    return reply


class TestRequests:
    def test_the_current_season_one_season_type_at_a_time(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 7, 18))
        espn.on("/schedule", load("schedule_MLB_10_2026_post.json"))
        games = espn_api.get_favorite_card_schedule("MLB", "10")
        # Asked for at once, so in no set order.
        assert sorted(espn.calls) == [f"{SITE}/baseball/mlb/teams/10/schedule?season=2026&seasontype={t}"
                                      for t in (1, 2, 3)]
        assert games and games == sorted(games, key=lambda g: g["start"])

    def test_never_the_scoreboard(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 7, 18))
        espn.on("/schedule", load("schedule_NCAAF_333_live.json"))
        espn_api.get_favorite_card_schedule("NCAAF", "333")
        assert not espn.urls("scoreboard")

    def test_an_empty_season_falls_back_to_the_last_one(self, espn, freeze_now):
        freeze_now(datetime(2027, 3, 10, 12))  # the NFL's 2027 season, not yet published
        espn.on("/schedule", lambda url: load("schedule_NFL_26_post.json") if "season=2026&seasontype=3" in url
                else {"events": []})
        games = espn_api.get_favorite_card_schedule("NFL", "26")
        assert games and espn.urls("season=2027") and espn.urls("season=2026")
        assert not espn.urls("season=2025")

    def test_soccer_asks_for_results_and_games_to_come(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 3, 12))
        results, fixtures = load("schedule_EPL_359_results.json"), load("schedule_EPL_359_fixture.json")
        espn.on("/schedule", lambda url: fixtures if "fixture=true" in url else results)
        games = espn_api.get_favorite_card_schedule("EPL", "359")
        assert len(games) == len(results["events"]) + len(fixtures["events"])
        assert not espn.urls("seasontype")

    def test_a_league_with_no_team_schedule_has_no_card_games(self, espn):
        assert espn_api.get_favorite_card_schedule("PGA", "1") == []
        assert espn_api.get_favorite_card_schedule("XFL", "1") == []
        assert espn.calls == []


class TestFailures:
    @pytest.mark.parametrize("failing", ["seasontype=1", "seasontype=2", "seasontype=3"])
    @pytest.mark.parametrize("reply", [TIMEOUT, HTTP_500], ids=["timeout", "500"])
    def test_one_part_failing_keeps_the_rest(self, espn, freeze_now, failing, reply):
        freeze_now(datetime(2026, 2, 1, 12))
        pre, reg, post = (load(f"schedule_NFL_26_{part}.json") for part in ("pre", "reg", "post"))
        answers = {"seasontype=1": pre, "seasontype=2": reg, "seasontype=3": post}
        espn.on("/schedule", lambda url: next(reply if key == failing else answer
                                              for key, answer in answers.items() if key in url))
        games = espn_api.get_favorite_card_schedule("NFL", "26")
        everything = sum(len(a["events"]) for a in answers.values())
        assert 0 < len(games) < everything

    @pytest.mark.parametrize("reply", [TIMEOUT, HTTP_500], ids=["timeout", "500"])
    def test_every_part_failing_says_so(self, espn, freeze_now, reply):
        freeze_now(datetime(2026, 11, 7, 12))
        espn.on("/schedule", reply)
        with pytest.raises(ApiError, match="ESPN isn't providing the schedule right now"):
            espn_api.get_favorite_card_schedule("MLB", "10")
        assert not espn.urls("season=2025"), "a failure is no reason to show last season"

    @pytest.mark.parametrize("reply", [TIMEOUT, HTTP_500], ids=["timeout", "500"])
    def test_a_failed_part_with_the_rest_empty_says_so_rather_than_show_last_season(self, espn, freeze_now, reply):
        freeze_now(datetime(2026, 7, 15, 12))
        espn.on("/schedule", lambda url: reply if "seasontype=2" in url else {"events": []})
        with pytest.raises(ApiError):
            espn_api.get_favorite_card_schedule("MLB", "10")
        assert not espn.urls("season=2025")

    def test_soccer_with_no_results_yet_and_the_games_to_come_failing_says_so(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 3, 12))
        espn.on("/schedule", lambda url: HTTP_500 if "fixture=true" in url
                else {"events": [], "season": {"year": 2026}})
        with pytest.raises(ApiError):
            espn_api.get_favorite_card_schedule("EPL", "359")
        assert not espn.urls("season=2025")

    def test_a_game_in_two_parts_appears_once(self, espn, freeze_now):
        freeze_now(datetime(2026, 2, 1, 12))
        reg = load("schedule_NFL_26_reg.json")
        espn.on("/schedule", reg)
        assert len(espn_api.get_favorite_card_schedule("NFL", "26")) == len(reg["events"])

    def test_the_service_passes_the_sentence_on(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 7, 12))
        espn.on("/schedule", TIMEOUT)
        with pytest.raises(ApiError) as caught:
            ApiService.get_favorite_card_schedule("MLB", "10")
        assert str(caught.value) == espn_api.SCHEDULE_UNAVAILABLE

    def test_espn_having_nothing_for_any_season_is_no_games_not_a_failure(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 7, 12))
        espn.on("/schedule", HTTP_404)
        assert espn_api.get_favorite_card_schedule("MLB", "10") == []

    def test_soccer_with_the_games_to_come_failing_keeps_the_results(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 3, 12))
        results = load("schedule_EPL_359_results.json")
        espn.on("/schedule", lambda url: HTTP_500 if "fixture=true" in url else results)
        assert len(espn_api.get_favorite_card_schedule("EPL", "359")) == len(results["events"])

    def test_soccer_with_the_results_failing_keeps_the_games_to_come(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 3, 12))
        fixtures = load("schedule_EPL_359_fixture.json")
        espn.on("/schedule", lambda url: fixtures if "fixture=true" in url else TIMEOUT)
        assert len(espn_api.get_favorite_card_schedule("EPL", "359")) == len(fixtures["events"])

    def test_soccer_with_both_failing_says_so(self, espn, freeze_now):
        freeze_now(datetime(2026, 11, 3, 12))
        espn.on("/schedule", TIMEOUT)
        with pytest.raises(ApiError):
            espn_api.get_favorite_card_schedule("EPL", "359")

    def test_the_team_schedule_screen_still_fails_on_any_part(self, espn, freeze_now):
        """lenient is the card's alone: a schedule missing its preseason would look complete."""
        freeze_now(datetime(2026, 2, 1, 12))
        reg = load("schedule_NFL_26_reg.json")
        espn.on("/schedule", lambda url: HTTP_500 if "seasontype=1" in url else reg)
        with pytest.raises(ApiError):
            espn_api.get_team_schedule("NFL", "26")
