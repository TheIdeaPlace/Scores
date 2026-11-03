"""One bad field at a time: every data function against its real payload with each
field in turn missing, null, or an empty list. None may raise, and none may turn
the gap into the text "None". ESPN does send nulls, and a field's absence shouldn't
cost the user the rest of the screen.
"""
import datetime

import pytest

import espn_api

from .support import HTTP_404, load, mutations


def case(name, call, fixture, route, others=None):
    return pytest.param(call, fixture, route, others or {}, id=name)


def strings_in(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from strings_in(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from strings_in(item)


CASES = [
    case("get_scores", lambda: espn_api.get_scores("NBA"), "scoreboard_events_by_status.json", "/scoreboard"),
    case("get_world_cup_scores_range",
         lambda: espn_api.get_world_cup_scores_range("WC2026", datetime.date(2026, 6, 20), datetime.date(2026, 6, 20)),
         "worldcup_scoreboard_20260620.json", "/scoreboard"),
]


def payload(spec):
    """"file.json" or "file.json:key" for one piece of a bundle."""
    name, _, key = spec.partition(":")
    data = load(name)
    return data[key] if key else data


@pytest.mark.parametrize("call,fixture,route,others", CASES)
def test_no_single_bad_field_raises_or_reads_none(espn, call, fixture, route, others):
    espn.on(".*", HTTP_404)
    for pattern, spec in others.items():
        espn.on(pattern, payload(spec))
    # The real payload first: the sweep proves nothing if this already comes back empty.
    espn.routes.append((__import__("re").compile(route), payload(fixture)))
    assert call(), "the unmodified payload should produce a result"

    failures = []
    for description, changed in mutations(payload(fixture)):
        espn.routes[-1] = (espn.routes[-1][0], changed)
        try:
            result = call()
        except Exception as e:
            failures.append(f"{description}: raised {type(e).__name__}: {e}")
            continue
        if "None" in strings_in(result):
            failures.append(f"{description}: the text None in {result}")
    assert not failures, "\n".join(failures[:20])
