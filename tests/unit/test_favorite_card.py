"""favorite_card.py: what a favorite's card says, on real ESPN schedules and a real /summary.
Which game is live, last and next is in test_favorite_card_grid.py, shared with the iPhone."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import favorite_card

ESPN = Path(__file__).parent.parent / "fixtures" / "espn"
CENTRAL = timezone(timedelta(hours=-6))
NOW = datetime(2026, 11, 7, 23, 0, tzinfo=timezone.utc)


def load(name):
    return json.loads((ESPN / name).read_text(encoding="utf-8"))


def alabama():
    return favorite_card.pick(favorite_card.card_games(load("schedule_NCAAF_333_live.json")["events"]), NOW)


class TestParsing:
    def test_a_game_being_played_has_no_score_on_the_schedule(self):
        live = alabama().live
        assert live["home"]["score"] is None and live["away"]["score"] is None
        assert live["home"]["display_name"] == "LSU Tigers"

    def test_a_postponed_game_keeps_espns_false_completed_and_post_state(self):
        games = favorite_card.card_games(load("schedule_MLB_10_2026_dh.json")["events"])
        postponed = next(g for g in games if g["id"] == "401816157")
        assert favorite_card.is_called_off(postponed)
        assert not favorite_card.is_completed(postponed)

    def test_the_doubleheader_stays_in_order_within_its_day(self):
        games = favorite_card.card_games(load("schedule_MLB_10_2026_dh.json")["events"])
        assert [g["id"] for g in games] == ["401816142", "401816157", "401897386", "401816172"]

    def test_a_game_listed_twice_appears_once_with_the_first_kept(self):
        events = load("schedule_MLB_10_2026_post.json")["events"]
        assert len(favorite_card.card_games(events + events)) == len(events)

    def test_an_event_without_both_teams_or_a_date_is_left_out(self):
        events = load("schedule_MLB_10_2026_post.json")["events"]
        broken = json.loads(json.dumps(events[:2]))
        broken[0]["competitions"][0]["competitors"] = broken[0]["competitions"][0]["competitors"][:1]
        broken[1]["date"] = None
        assert favorite_card.card_games(broken + [None, {}, {"competitions": None}]) == []


class TestNextLine:
    def test_a_set_time_reads_as_a_short_date_and_time(self):
        line = favorite_card.next_line(alabama().next, "333", zone=CENTRAL)
        assert line == "Next: @ VAN, 11/14/26, 11:45 AM, EARLY: Noon - 1pm ET start"

    def test_a_game_with_no_time_set_has_its_date_alone(self):
        game = dict(alabama().next, time_valid=False)
        assert favorite_card.next_line(game, "333") == "Next: @ VAN, 11/14/26, EARLY: Noon - 1pm ET start"

    def test_an_evening_time_is_pm_and_noon_is_twelve(self):
        game = dict(alabama().next, label="")
        evening = dict(game, start=datetime(2026, 11, 15, 1, 5, tzinfo=timezone.utc))
        noon = dict(game, start=datetime(2026, 11, 14, 18, 0, tzinfo=timezone.utc))
        assert favorite_card.next_line(evening, "333", zone=CENTRAL) == "Next: @ VAN, 11/14/26, 7:05 PM"
        assert favorite_card.next_line(noon, "333", zone=CENTRAL) == "Next: @ VAN, 11/14/26, 12:00 PM"


class TestLiveLine:
    def test_the_summary_gives_the_score_and_the_clock(self):
        line = favorite_card.live_line(alabama().live, "333", load("summary_live_NCAAF_401856740.json"))
        assert line == "Live: Alabama Crimson Tide 10 @ LSU Tigers 12, 2:44 - 3rd Quarter"

    def test_without_a_summary_only_the_opponent(self):
        assert favorite_card.live_line(alabama().live, "333") == "Live: @ LSU"
        assert favorite_card.live_line(alabama().live, "333", {}) == "Live: @ LSU"

    def test_without_a_summary_a_schedule_score_is_used_if_there_is_one(self):
        live = alabama().live
        game = dict(live, home=dict(live["home"], score=12), away=dict(live["away"], score=10))
        assert favorite_card.live_line(game, "333") == "Live: @ LSU 10-12"

    def test_a_summary_with_no_status_detail_leaves_it_out(self):
        summary = load("summary_live_NCAAF_401856740.json")
        summary["header"]["competitions"][0]["status"]["type"]["detail"] = ""
        assert favorite_card.live_line(alabama().live, "333", summary) == \
            "Live: Alabama Crimson Tide 10 @ LSU Tigers 12"


# No live baseball /summary can be captured in November. This is the shape the iPhone
# decodes (GameDetails.SummarySituation and GameRoster): a player id on each base and on the
# pitcher and batter, the names in the rosters.
def baseball_summary(**situation):
    summary = load("summary_live_NCAAF_401856740.json")
    summary["header"]["competitions"][0]["status"]["type"]["detail"] = "Top 5th"
    summary["rosters"] = [
        {"homeAway": "home", "roster": [{"athlete": {"id": "1001", "shortName": "G. Cole", "displayName": "Gerrit Cole"}}]},
        {"homeAway": "away", "roster": [{"athlete": {"id": "2002", "displayName": "Rafael Devers"}}]},
    ]
    summary["situation"] = situation
    return summary


class TestBaseballSituation:
    def test_pitcher_batter_bases_count_and_outs(self):
        summary = baseball_summary(balls=1, strikes=2, outs=2, pitcher={"playerId": 1001},
                                   batter={"playerId": 2002}, onFirst={"playerId": 5}, onThird={"playerId": 6})
        assert favorite_card.situation_text(summary) == "P: G. Cole, AB: Rafael Devers, 1st & 3rd, 1-2, 2 outs"
        assert favorite_card.live_line(alabama().live, "333", summary).endswith(
            ", Top 5th, P: G. Cole, AB: Rafael Devers, 1st & 3rd, 1-2, 2 outs")

    def test_bases_empty_and_one_out(self):
        summary = baseball_summary(balls=0, strikes=0, outs=1)
        assert favorite_card.situation_text(summary) == "Bases empty, 0-0, 1 out"

    def test_a_player_not_in_the_rosters_is_left_out(self):
        summary = baseball_summary(balls=3, strikes=1, outs=0, pitcher={"playerId": 999})
        assert favorite_card.situation_text(summary) == "Bases empty, 3-1, 0 outs"

    def test_no_count_and_no_outs_is_no_situation(self):
        assert favorite_card.situation_text(baseball_summary(onFirst={"playerId": 5})) is None
        assert favorite_card.situation_text(load("summary_live_NCAAF_401856740.json")) is None
        assert favorite_card.situation_text(None) is None


class TestResultLine:
    def test_a_missing_score_counts_as_zero_as_on_the_iphone(self):
        last = alabama().last
        game = dict(last, home=dict(last["home"], score=None))
        assert favorite_card.result_line(game, "333") == "Last: L vs TA&M 0-20"
