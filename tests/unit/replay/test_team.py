"""The team dialog's data: info, roster, news and transactions on real payloads."""
import pytest

import espn_api

from .support import load

SITE = espn_api.BASE_URL


class TestTeamInfo:
    def info(self, espn, league="NFL", team="9", fixture="team_NFL_9.json"):
        espn.on(f"/teams/{team}$", load(fixture))
        return espn_api.get_team_info(league, team)

    def test_url(self, espn):
        self.info(espn)
        assert espn.calls == [f"{SITE}/football/nfl/teams/9"]

    def test_names(self, espn):
        info = self.info(espn)
        assert (info["name"], info["abbreviation"], info["nickname"], info["location"]) == (
            "Green Bay Packers", "GB", "Packers", "Green Bay")

    def test_venue_lives_under_franchise(self, espn):
        assert "venue" not in load("team_NFL_9.json")["team"]
        info = self.info(espn)
        assert (info["venue_name"], info["venue_location"]) == ("Lambeau Field", "Green Bay, WI")

    def test_a_venue_directly_on_the_team_wins(self, espn):
        data = load("team_NFL_9.json")
        data["team"]["venue"] = {"displayName": "Dome", "address": {"state": "IN"}}
        espn.on("/teams/9$", data)
        info = espn_api.get_team_info("NFL", "9")
        assert (info["venue_name"], info["venue_location"]) == ("Dome", "IN")

    def test_no_venue_leaves_it_blank(self, espn):
        data = load("team_NFL_9.json")
        del data["team"]["franchise"]
        espn.on("/teams/9$", data)
        info = espn_api.get_team_info("NFL", "9")
        assert (info["venue_name"], info["venue_location"]) == ("", "")

    def test_record_splits(self, espn):
        info = self.info(espn)
        assert (info["record_overall"], info["record_home"], info["record_road"]) == ("5-3", "3-1", "2-2")

    def test_hockey_overall_includes_overtime_losses(self, espn):
        info = self.info(espn, "NHL", "129764", "team_NHL_utah.json")
        assert load("team_NHL_utah.json")["team"]["record"]["items"][0]["summary"] == "9-6"
        assert info["record_overall"] == "9-6-0"

    def test_football_ot_losses_stat_does_not_add_a_part(self, espn):
        """Football's OTLosses is capitalised and isn't part of its record."""
        assert self.info(espn)["record_overall"].count("-") == 1

    def test_a_soccer_three_part_summary_is_left_alone(self, espn):
        assert self.info(espn, "EPL", "359", "team_EPL_359.json")["record_overall"] == "8-0-1"

    def test_standing(self, espn):
        assert self.info(espn)["standing"] == "7th in National Football Conference"

    def test_the_payload_has_no_division_or_coach_so_neither_is_invented(self, espn):
        info = self.info(espn, "NHL", "129764", "team_NHL_utah.json")
        assert (info["division"], info["conference"]) == ("", "")
        assert "head_coach" not in info

    def test_groups_and_coach_when_present(self, espn):
        data = load("team_NFL_9.json")
        data["team"]["groups"] = {"name": "NFC North", "parent": {"name": "NFC"}}
        data["team"]["coaches"] = [{"firstName": "Matt", "lastName": "LaFleur"}]
        espn.on("/teams/9$", data)
        info = espn_api.get_team_info("NFL", "9")
        assert (info["division"], info["conference"], info["head_coach"]) == ("NFC North", "NFC", "Matt LaFleur")

    class TestNextGame:
        def test_a_finished_game_is_not_the_next_game(self, espn):
            """For a while after a game ESPN's nextEvent is still that game."""
            data = load("team_NFL_9.json")
            state = data["team"]["nextEvent"][0]["competitions"][0]["status"]["type"]["state"]
            assert state == "post"
            espn.on("/teams/9$", data)
            info = espn_api.get_team_info("NFL", "9")
            assert not {"next_game_opponent", "next_game_home_away", "next_game_date"} & set(info)

        def test_away(self, espn):
            espn.on("/teams/129764$", load("team_NHL_utah.json"))
            info = espn_api.get_team_info("NHL", "129764")
            assert (info["next_game_opponent"], info["next_game_home_away"]) == ("Toronto Maple Leafs", "@")

        def test_home(self, espn):
            espn.on("/teams/21$", load("team_NHL_utah.json"))
            info = espn_api.get_team_info("NHL", "21")
            assert (info["next_game_opponent"], info["next_game_home_away"]) == ("Utah Mammoth", "vs")

        @pytest.mark.parametrize("offset,day", [(-6, "Tue, Nov 3"), (9, "Wed, Nov 4")])
        def test_the_date_is_local(self, espn, local_zone, offset, day):
            local_zone(offset)
            data = load("team_NHL_utah.json")
            assert data["team"]["nextEvent"][0]["date"] == "2026-11-04T00:00Z"
            espn.on("/teams/129764$", data)
            assert espn_api.get_team_info("NHL", "129764")["next_game_date"] == day

        def test_a_leading_zero_day_is_trimmed(self, espn, local_zone):
            local_zone(0)
            data = load("team_NHL_utah.json")
            data["team"]["nextEvent"][0]["date"] = "2026-11-05T12:00Z"
            espn.on("/teams/129764$", data)
            assert espn_api.get_team_info("NHL", "129764")["next_game_date"] == "Thu, Nov 5"

        def test_an_unreadable_date_falls_back_to_its_first_ten_characters(self, espn):
            data = load("team_NHL_utah.json")
            data["team"]["nextEvent"][0]["date"] = "2026-11-04 sometime"
            espn.on("/teams/129764$", data)
            assert espn_api.get_team_info("NHL", "129764")["next_game_date"] == "2026-11-04"

    def test_no_team_id_requests_nothing(self, espn):
        assert espn_api.get_team_info("NFL", "") == {}
        assert espn_api.get_team_info("CRICKET", "1") == {}
        assert espn.calls == []


class TestRoster:
    def test_url(self, espn):
        espn.on("/roster", load("roster_NFL_9.json"))
        espn_api.get_team_roster("NFL", "9")
        assert espn.calls == [f"{SITE}/football/nfl/teams/9/roster"]

    def test_grouped_shape_with_float_heights_and_weights(self, espn):
        raw = load("roster_NFL_9.json")["athletes"]
        assert isinstance(raw[0]["items"][0]["height"], float)
        espn.on("/roster", {"athletes": raw})
        players = espn_api.get_team_roster("NFL", "9")
        assert players[0] == {"jersey": "65", "name": "Aaron Banks", "position": "G", "age": "29",
                              "height": "6'5\"", "weight": "325 lbs"}
        assert len(players) == sum(len(group["items"]) for group in raw)

    def test_flat_shape(self, espn):
        raw = load("roster_NBA_15.json")["athletes"]
        assert "items" not in raw[0]
        espn.on("/roster", {"athletes": raw})
        players = espn_api.get_team_roster("NBA", "15")
        assert players[0] == {"jersey": "15", "name": "Nate Ament", "position": "F", "age": "19",
                              "height": "6'10\"", "weight": "211 lbs"}
        assert len(players) == len(raw)

    def test_no_height_stays_blank_not_0_0(self, espn):
        espn.on("/roster", {"athletes": [{"displayName": "A", "position": "QB", "height": 0, "weight": None}]})
        player = espn_api.get_team_roster("NFL", "9")[0]
        assert (player["position"], player["height"], player["weight"]) == ("QB", "", "")

    def test_no_team_requests_nothing(self, espn):
        assert espn_api.get_team_roster("NFL", "") == []
        assert espn.calls == []


class TestTeamNews:
    def test_the_url_is_news_with_a_team_parameter(self, espn):
        """/teams/9/news answers 200 with {}; only /news?team=9 has articles."""
        espn.on("/news", load("team_news_NFL_9.json"))
        espn_api.get_team_news("NFL", "9")
        assert espn.calls == [f"{SITE}/football/nfl/news?team=9&limit=15"]

    def test_articles(self, espn):
        espn.on("/news", load("team_news_NFL_9.json"))
        first, second = espn_api.get_team_news("NFL", "9", limit=2)
        assert first["headline"] == "Stephen A.: Right now, the Bears look like the NFL's best team"
        assert first["web_url"] == "https://www.espn.com/video/clip/_/id/50369297/right-now-bears-look-nfl-best-team"
        assert first["published"] == "2026-11-03T15:50:13Z"
        assert second["byline"] == "NFL Nation"
        assert second["description"].startswith("How does every NFL team stack up")
        assert espn.calls == [f"{SITE}/football/nfl/news?team=9&limit=2"]

    def test_no_team_requests_nothing(self, espn):
        assert espn_api.get_team_news("NFL", "") == []
        assert espn.calls == []


class TestTransactions:
    def test_league_url_and_paging(self, espn):
        espn.on("/transactions", load("transactions_NFL.json"))
        rows, has_more = espn_api.get_transactions("NFL", limit=5, page=2)
        assert espn.calls == [f"{SITE}/football/nfl/transactions?limit=5&page=2"]
        assert has_more is True
        assert rows[0] == {"date": "2026-11-02", "team": "ATL",
                           "description": "Waived OLB Jared Ivey. Released OLB Drake Jackson from the practice squad.",
                           "type": "", "player": "", "position": ""}

    def test_the_last_page_has_no_more(self, espn):
        espn.on("/transactions", load("transactions_NFL.json"))
        assert espn_api.get_transactions("NFL", page=407)[1] is False

    def test_team_filter(self, espn):
        espn.on("/transactions", load("transactions_NFL_9.json"))
        rows, _ = espn_api.get_transactions("NFL", team_id="9", limit=5)
        assert espn.calls == [f"{SITE}/football/nfl/transactions?limit=5&page=1&team=9"]
        assert rows[0]["team"] == ""  # ESPN leaves it off a team-filtered list
        assert rows[0]["date"] == "2026-10-26"

    def test_items_key_and_a_bad_date(self, espn):
        espn.on("/transactions", {"items": [{"timestamp": "bad-date-here", "description": "x", "team": "text"}]})
        rows, has_more = espn_api.get_transactions("NFL")
        assert (rows[0]["date"], rows[0]["team"], has_more) == ("bad-date-h", "", False)

    def test_unknown_league(self, espn):
        assert espn_api.get_transactions("CRICKET") == ([], False)
        assert espn.calls == []


class TestTeamTransactions:
    def test_url_and_rows(self, espn):
        espn.on("/transactions", load("transactions_NFL_9.json"))
        rows = espn_api.get_team_transactions("NFL", "9", limit=5)
        assert espn.calls == [f"{SITE}/football/nfl/transactions?team=9&limit=5"]
        assert rows[0]["date"] == "2026-10-26"
        assert rows[1]["description"].startswith("Activated RB Josh Jacobs")

    def test_a_bad_date_keeps_what_it_can(self, espn):
        espn.on("/transactions", {"transactions": [{"date": "bad-date-here", "description": "x"}, {"description": "y"}]})
        assert [r["date"] for r in espn_api.get_team_transactions("NFL", "9")] == ["bad-date-h", ""]

    def test_no_team_requests_nothing(self, espn):
        assert espn_api.get_team_transactions("NFL", "") == []
        assert espn.calls == []
