"""Pure: the rules both apps follow on ESPN's golf scoreboard.

Both apps ask the same endpoint two ways: `scoreboard?dates=YEAR` for the season with
each finished event's winner, and `scoreboard?dates=YYYYMMDD` (or no date) for one
tournament's leaderboard. A date can answer with two events, in a week with an
opposite-field event, so which one to show is a rule too.

The iPhone's twin is `Models/GolfRules.swift`. `tests/fixtures/golf_grid.json` holds
both to the same answers: `tests/unit/test_golf_grid.py` here and `GolfGridTests.swift`
there. Change both together.

No PyQt and no network, so it is tested on any platform.
"""


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _dicts(value):
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _text(value):
    """A non-blank string, stripped, or "". ESPN sends empty strings as well as nulls."""
    return value.strip() if isinstance(value, str) else ""


def _state_of(holder):
    state = _as_dict(_as_dict(holder.get("status")).get("type")).get("state")
    return _text(state)


def event_state(event):
    """"pre", "in" or "post" for the event, or "" when ESPN doesn't say.

    The event's own status comes first: between rounds ESPN calls the event in progress
    while its competition says play is complete for the day, and the tournament is still
    on. The competition's status is the fallback for an event that has none of its own.
    """
    event = _as_dict(event)
    return _state_of(event) or _state_of((_dicts(event.get("competitions")) or [{}])[0])


def pick_event(events, event_id=None):
    """The event to show from a scoreboard's `events`, or None if there are none.

    The one asked for by id when it is there (a past week can list two events); else the
    first in progress; else the first. Entries that aren't objects are passed over.
    """
    listed = _dicts(events)
    wanted = _text(event_id)
    if wanted:
        for event in listed:
            if _text(event.get("id")) == wanted:
                return event
    for event in listed:
        if event_state(event) == "in":
            return event
    return listed[0] if listed else None


def _order(competitor):
    order = competitor.get("order")
    return order if isinstance(order, int) and not isinstance(order, bool) else None


def by_order(competitors):
    """The competitors that are objects, by ESPN's `order`: one with no order (or one that
    isn't a whole number) goes last, and ties keep ESPN's listed order."""
    listed = _dicts(competitors)
    return [c for _, c in sorted(enumerate(listed),
                                 key=lambda pair: (_order(pair[1]) is None, _order(pair[1]) or 0, pair[0]))]


def competitor_name(competitor):
    """A golfer's name, or a team's in a team event (the Zurich Classic, the Presidents Cup)."""
    athlete = _as_dict(competitor.get("athlete"))
    team = _as_dict(competitor.get("team"))
    for name in (athlete.get("displayName"), athlete.get("fullName"),
                 team.get("displayName"), team.get("name")):
        if _text(name):
            return _text(name)
    return ""


def winner(event):
    """{name, score} for a finished event's winner, or None.

    Only a finished event has one, and only if it has a field: a cancelled event is
    finished with nobody in it. The competitor ESPN marks `winner` comes first (the team
    cups do); else the lowest `order`, which is 1 for the winner of a playoff too. A
    competitor with no order goes last, and ties keep ESPN's listed order. The score is
    ESPN's as it is ("-16"; a cup's points, "17").
    """
    event = _as_dict(event)
    if event_state(event) != "post":
        return None
    ranked = by_order(_as_dict((_dicts(event.get("competitions")) or [{}])[0]).get("competitors"))
    if not ranked:
        return None
    top = next((c for c in ranked if c.get("winner") is True), ranked[0])
    name = competitor_name(top)
    if not name:
        return None
    return {"name": name, "score": _text(top.get("score"))}


def winner_text(found):
    """"Chris Gotterup (-16)", or just the name when there's no score; "" for no winner."""
    if not found:
        return ""
    return f"{found['name']} ({found['score']})" if found.get("score") else found["name"]
