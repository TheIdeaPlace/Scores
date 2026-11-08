"""The Transactions screen's running list (#188): get_transactions_from on real payloads."""
import pytest

import espn_api
import transactions_paging as paging
from exceptions import ApiError

from .support import HTTP_500, TIMEOUT, FakeResponse, load

SITE = espn_api.BASE_URL
NOW = {"year": 2026, "month": None, "page": 1}
NOTHING = {"status": "success", "count": 0, "pageIndex": 0, "pageSize": 25, "pageCount": 0}
HTTP_400 = FakeResponse({"code": 400, "message": "Team not available for given id"}, status=400)


def one_page(payload):
    """A real payload as the one page of its year."""
    payload["pageCount"] = 1
    return payload


def item(date, description):
    return {"date": date, "description": description, "team": {"id": "1", "abbreviation": "ATL"}}


class TestLeagueWide:
    def test_now_asks_for_this_year_and_goes_on_to_its_next_page(self, espn):
        espn.on("/transactions", load("transactions_NFL.json"))
        load_ = espn_api.get_transactions_from("NFL", NOW)
        assert espn.calls == [f"{SITE}/football/nfl/transactions?limit=50&page=1&season=2026"]
        assert [r["team"] for r in load_["rows"]] == ["ATL", "CLE", "KC"]
        assert load_["rows"][0]["date"] == "2026-11-02"
        assert load_["next"] == {"year": 2026, "month": None, "page": 2}
        assert load_["oldest_year"] == 2026

    def test_a_jump_asks_from_january_to_the_months_end(self, espn):
        espn.on("/transactions", load("transactions_NFL_2025_09.json"))
        cursor = paging.start_cursor(2026, 11, 2025, 9)
        load_ = espn_api.get_transactions_from("NFL", cursor)
        assert espn.calls == [f"{SITE}/football/nfl/transactions?limit=50&page=1&dates=20250101-20250930"]
        assert [r["team"] for r in load_["rows"]] == ["BUF", "CLE", "DAL"]
        assert load_["next"] == {"year": 2025, "month": 9, "page": 2}

    def test_the_next_months_first_day_from_a_ranges_edge_is_left_out(self, espn):
        espn.on("/transactions", {"pageCount": 1, "transactions": [
            item("2025-10-01T07:00Z", "October"), item("2025-09-30T07:00Z", "September")]})
        load_ = espn_api.get_transactions_from("NFL", {"year": 2025, "month": 9, "page": 1})
        assert [r["description"] for r in load_["rows"]] == ["September"]
        assert load_["next"] == {"year": 2024, "month": None, "page": 1}

    def test_an_empty_year_goes_on_to_the_year_before_in_the_same_load(self, espn):
        espn.on(r"season=2026", NOTHING)
        espn.on(r"season=2025", {"pageCount": 3, "transactions": [item("2025-12-30T08:00Z", "last year")]})
        load_ = espn_api.get_transactions_from("NBA", NOW)
        assert espn.urls("season=") == [f"{SITE}/basketball/nba/transactions?limit=50&page=1&season=2026",
                                        f"{SITE}/basketball/nba/transactions?limit=50&page=1&season=2025"]
        assert [r["description"] for r in load_["rows"]] == ["last year"]
        assert load_["next"] == {"year": 2025, "month": None, "page": 2}
        assert load_["oldest_year"] == 2025

    def test_a_league_with_nothing_stops_after_six_requests(self, espn):
        espn.on("/transactions", NOTHING)
        load_ = espn_api.get_transactions_from("NCAAF", NOW)
        assert [u.rsplit("=", 1)[1] for u in espn.calls] == ["2026", "2025", "2024", "2023", "2022", "2021"]
        assert load_ == {"rows": [], "next": {"year": 2020, "month": None, "page": 1}, "oldest_year": 2021, "skipped": []}

    def test_nothing_before_2001(self, espn):
        espn.on("/transactions", NOTHING)
        load_ = espn_api.get_transactions_from("NFL", {"year": 2002, "month": None, "page": 1})
        assert len(espn.calls) == 2
        assert load_ == {"rows": [], "next": None, "oldest_year": 2001, "skipped": []}

    def test_a_400_every_year_is_skipped_each_time_up_to_the_limit(self, espn):
        espn.on("/transactions", HTTP_400)
        load_ = espn_api.get_transactions_from("NFL", NOW, team_id="99999")
        assert load_["rows"] == []
        assert load_["next"] == {"year": 2020, "month": None, "page": 1}
        assert load_["skipped"] == [{"year": y, "below": False} for y in range(2026, 2020, -1)]

    def test_a_404_partway_through_a_year_goes_below_what_was_found(self, espn):
        # NFL 2003: pages that reach into February to August answer 404 at any page size.
        espn.on(r"page=10&season=2003", {"pageCount": 25, "transactions": [item("2003-08-02T07:00Z", "August")]})
        espn.on(r"page=11&season=2003", FakeResponse({"code": 404, "message": "application error"}, status=404))
        load_ = espn_api.get_transactions_from("NFL", {"year": 2003, "month": None, "page": 10})
        assert [r["description"] for r in load_["rows"]] == ["August"]
        assert load_["next"] == {"year": 2003, "month": None, "page": 11}
        espn.on(r"season=2002", {"pageCount": 5, "transactions": [item("2002-12-30T08:00Z", "December 2002")]})
        load_ = espn_api.get_transactions_from("NFL", load_["next"])
        assert [r["description"] for r in load_["rows"]] == ["December 2002"]
        assert load_["skipped"] == [{"year": 2003, "below": False}]
        assert load_["oldest_year"] == 2002

    def test_a_jump_into_a_stretch_espn_cant_give_goes_on_to_the_year_before(self, espn):
        espn.on(r"dates=20030101-20030331", FakeResponse({"code": 404, "message": "application error"}, status=404))
        espn.on(r"season=2002", {"pageCount": 5, "transactions": [item("2002-12-30T08:00Z", "December 2002")]})
        load_ = espn_api.get_transactions_from("NFL", {"year": 2003, "month": 3, "page": 1})
        assert [r["description"] for r in load_["rows"]] == ["December 2002"]
        assert load_["skipped"] == [{"year": 2003, "below": False}]
        assert load_["next"] == {"year": 2002, "month": None, "page": 2}

    def test_a_skip_after_rows_ends_the_load_below_them(self, espn):
        # Only soccer goes on after finding some, to finish its year.
        espn.on(r"page=1&season=2025", {"pageCount": 3, "transactions": [item("2025-01-02T08:00Z", "January")]})
        espn.on(r"page=2&season=2025", FakeResponse({"code": 404, "message": "application error"}, status=404))
        load_ = espn_api.get_transactions_from("EPL", {"year": 2025, "month": None, "page": 1})
        assert [r["description"] for r in load_["rows"]] == ["January"]
        assert load_["skipped"] == [{"year": 2025, "below": True}]
        assert load_["next"] == {"year": 2024, "month": None, "page": 1}
        assert len(espn.calls) == 2

    @pytest.mark.parametrize("failure", [TIMEOUT, HTTP_500])
    def test_a_failure_says_so(self, espn, failure):
        espn.on("/transactions", failure)
        with pytest.raises(ApiError) as caught:
            espn_api.get_transactions_from("NFL", NOW)
        assert str(caught.value) == espn_api.TRANSACTIONS_UNAVAILABLE

    def test_a_failure_after_an_empty_year_still_says_so(self, espn):
        espn.on(r"season=2026", NOTHING)
        espn.on(r"season=2025", TIMEOUT)
        with pytest.raises(ApiError):
            espn_api.get_transactions_from("NFL", NOW)

    def test_a_null_list_is_not_an_answer(self, espn):
        espn.on("/transactions", {"pageCount": 1, "transactions": None})
        with pytest.raises(ApiError):
            espn_api.get_transactions_from("NFL", NOW)

    def test_unknown_league_or_no_cursor_asks_nothing(self, espn):
        assert espn_api.get_transactions_from("CRICKET", NOW)["rows"] == []
        assert espn_api.get_transactions_from("NFL", None) == {"rows": [], "next": None, "oldest_year": None, "skipped": []}
        assert espn.calls == []


class TestTeam:
    def test_a_teams_jump_asks_for_its_year_and_leaves_out_whats_newer(self, espn):
        pages = {"1": {"pageCount": 2, "transactions": [{"date": "2024-12-28T08:00Z", "description": "December"}]},
                 "2": {"pageCount": 2, "transactions": [{"date": "2024-06-20T07:00Z", "description": "June"},
                                                        {"date": "2024-05-02T07:00Z", "description": "May"}]}}
        espn.on("/transactions", lambda url: pages[url.split("page=")[1].split("&")[0]])
        load_ = espn_api.get_transactions_from("NFL", {"year": 2024, "month": 6, "page": 1}, team_id="9")
        assert espn.calls == [f"{SITE}/football/nfl/transactions?limit=50&page=1&season=2024&team=9",
                              f"{SITE}/football/nfl/transactions?limit=50&page=2&season=2024&team=9"]
        assert [r["description"] for r in load_["rows"]] == ["June", "May"]
        assert load_["next"] == {"year": 2023, "month": None, "page": 1}

    def test_a_teams_items_have_no_team(self, espn):
        espn.on("/transactions", load("transactions_NFL_9_2024.json"))
        load_ = espn_api.get_transactions_from("NFL", {"year": 2024, "month": None, "page": 1}, team_id="9")
        assert [r["team"] for r in load_["rows"]] == ["", "", ""]
        assert load_["rows"][0]["description"] == "Elevated S Omar Brown from the practice squad."


class TestSoccer:
    def test_a_soccer_year_in_one_request_described_as_transfers(self, espn):
        espn.on("/transactions", one_page(load("transactions_MLS_2025.json")))
        load_ = espn_api.get_transactions_from("MLS", {"year": 2025, "month": None, "page": 1})
        assert espn.calls == [f"{SITE}/soccer/usa.1/transactions?limit=200&page=1&season=2025"]
        assert load_["rows"][0]["description"] == "Bajung Darboe joins Bayern Munich from LAFC for an undisclosed fee."
        assert load_["rows"][0]["team"] == ""
        assert load_["next"] == {"year": 2024, "month": None, "page": 1}

    def test_a_soccer_year_is_finished_and_put_newest_first(self, espn):
        pages = {"1": {"pageCount": 2, "transactions": [{"date": "2025-01-02T08:00Z", "description": "January"},
                                                        {"date": "2025-03-01T08:00Z", "description": "March"}]},
                 "2": {"pageCount": 2, "transactions": [{"date": "2025-09-01T07:00Z", "description": "September"}]}}
        espn.on("/transactions", lambda url: pages[url.split("page=")[1].split("&")[0]])
        load_ = espn_api.get_transactions_from("EPL", {"year": 2025, "month": None, "page": 1})
        assert len(espn.calls) == 2
        assert [r["description"] for r in load_["rows"]] == ["September", "March", "January"]
        assert load_["next"] == {"year": 2024, "month": None, "page": 1}

    def test_a_soccer_jump_leaves_out_whats_newer(self, espn):
        espn.on("/transactions", {"pageCount": 1, "transactions": [
            {"date": "2025-01-02T08:00Z", "description": "January"}, {"date": "2025-08-01T07:00Z", "description": "August"}]})
        load_ = espn_api.get_transactions_from("EPL", {"year": 2025, "month": 3, "page": 1})
        assert espn.calls == [f"{SITE}/soccer/eng.1/transactions?limit=200&page=1&season=2025"]
        assert [r["description"] for r in load_["rows"]] == ["January"]

    def test_a_soccer_teams_in_and_out(self, espn):
        espn.on("/transactions", one_page(load("transactions_EPL_359_2025.json")))
        load_ = espn_api.get_transactions_from("EPL", {"year": 2025, "month": None, "page": 1}, team_id="359")
        assert espn.calls == [f"{SITE}/soccer/eng.1/transactions?limit=200&page=1&season=2025&team=359"]
        assert [r["description"] for r in load_["rows"]] == [
            "Ayden Heaven joins Manchester United from Arsenal for an undisclosed fee.",
            "Marquinhos joins Cruzeiro from Arsenal on loan.",
            "Josh Robinson joins Wigan Athletic from Arsenal for an undisclosed fee.",
        ]

    def test_dates_on_soccer_answer_nothing_so_they_are_never_sent(self, espn):
        espn.on("/transactions", load("transactions_EPL_dates_empty.json"))
        espn_api.get_transactions_from("EPL", {"year": 2024, "month": 3, "page": 1})
        assert not espn.urls("dates=")


class TestOtherScreensReadTransfers:
    def test_the_team_tab_describes_a_soccer_transfer(self, espn):
        espn.on("/transactions", load("transactions_EPL_359_2025.json"))
        rows = espn_api.get_team_transactions("EPL", "359")
        assert rows[1]["description"] == "Marquinhos joins Cruzeiro from Arsenal on loan."
