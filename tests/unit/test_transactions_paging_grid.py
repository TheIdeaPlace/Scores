"""transactions_paging.py against tests/fixtures/transactions_paging_grid.json, the grid the
iPhone's TransactionPaging.swift is held to (TransactionPagingGridTests.swift)."""
import json
from pathlib import Path

import pytest

import transactions_paging as paging

GRID = json.loads((Path(__file__).parent.parent / "fixtures" / "transactions_paging_grid.json")
                  .read_text(encoding="utf-8"))


def named(section):
    return pytest.mark.parametrize("case", GRID[section], ids=[c.get("name", str(i)) for i, c in enumerate(GRID[section])])


def test_constants():
    assert paging.EARLIEST_YEAR == GRID["earliest_year"]
    assert paging.PAGE_SIZE == GRID["page_size"]
    assert paging.WHOLE_YEAR_PAGE_SIZE == GRID["whole_year_page_size"]
    assert paging.MAX_REQUESTS_PER_LOAD == GRID["max_requests_per_load"]


@named("labels")
def test_labels(case):
    assert paging.month_label(case["year"], case["month"]) == case["label"]


@named("months_back")
def test_months_back(case):
    months = [list(m) for m in paging.months_back(*case["today"])]
    assert len(months) == case["count"]
    assert months[:len(case["first"])] == case["first"]
    assert months[-len(case["last"]):] == case["last"]
    if case["around_new_year"]:
        first = case["around_new_year"][0]
        at = months.index(first)
        assert months[at:at + 2] == case["around_new_year"]


@named("start")
def test_start(case):
    jump = case["jump"] or [None, None]
    assert paging.start_cursor(*case["today"], *jump) == case["cursor"]


@named("requests")
def test_requests(case):
    params = paging.request_params(case["cursor"], case["league"], case["team"])
    assert params == case["params"]
    assert list(params) == list(case["params"]), "sent in the grid's order"


@named("keeps")
def test_keeps(case):
    assert paging.keeps(case["cursor"], case["date"]) is case["keeps"]


@named("newest_first")
def test_newest_first(case):
    assert paging.newest_first(case["dates"]) == case["order"]


@named("next")
def test_next(case):
    assert paging.next_cursor(case["cursor"], case["has_more"]) == case["next"]


@named("jump_notice")
def test_jump_notice(case):
    assert paging.jump_notice(*case["jump"], case["dates"], case["team"]) == case["text"]


@named("nothing_found")
def test_nothing_found(case):
    jump = tuple(case["jump"]) if case["jump"] else None
    assert paging.nothing_found(case["oldest_year"], jump, case["team"]) == case["text"]


@named("after_no_answer")
def test_after_no_answer(case):
    assert paging.after_no_answer(case["cursor"]) == case["next"]


@named("skipped_text")
def test_skipped_text(case):
    assert paging.skipped_text(case["year"], case["team"]) == case["text"]


@named("nothing_older")
def test_nothing_older(case):
    assert paging.nothing_older(case["oldest_year"], case["team"]) == case["text"]


@named("end_text")
def test_end_text(case):
    assert paging.end_text(case["team"]) == case["text"]


@named("load_continues")
def test_load_continues(case):
    assert paging.load_continues(case["found"], case["requests"], case["cursor"], case["following"],
                                 case["league"]) is case["continues"]


@named("transaction_items")
def test_transaction_items(case):
    assert [i["description"] for i in paging.transaction_items(case["listed"])] == case["descriptions"]


@named("describe")
def test_describe(case):
    assert paging.describe(case["item"]) == case["text"]


def test_a_walk_from_a_jump_reaches_2001_and_stops():
    """From any month, following has_more=False year after year ends at 2001, never loops."""
    cursor = paging.start_cursor(2026, 11, 2003, 3)
    seen = []
    while cursor:
        seen.append(cursor["year"])
        cursor = paging.next_cursor(cursor, False)
    assert seen == [2003, 2002, 2001]
