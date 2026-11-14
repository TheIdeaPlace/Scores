"""Pure: a pro league's division standings from ESPN's `/standings?level=3`.

Without `level=3`, ESPN answers MLB, the NFL, the NBA and the NHL by conference (or league),
and its `gamesBehind` there counts from the conference leader. Both apps used to split that
answer into divisions from a table of team abbreviations and keep the conference figure, so a
division leader read as games back (Denver 0.5 back while leading the AFC West), and teams
with the same record came out in whatever order the sort left them.

With `level=3`, every division is its own group under its conference and `gamesBehind` counts
from the division leader. MLB also sends `divisionGamesBehind`, the same figure, which is read
first. The teams within a group are not in order (the NBA's come worst first), so they are put
in order by ESPN's `playoffSeed`, which carries the league's tiebreakers.

Nothing here knows which team is in which division: the groups come from the answer. If ESPN
ever answers with conferences only, those are the groups, with their own games back, rather
than nothing.

The iPhone's twin is `Models/DivisionStandings.swift`; `tests/fixtures/division_standings_grid.json`
holds both to the same answers.
"""

# The leagues whose standings are asked for by division, and the query that does it.
DIVISION_LEAGUES = ("MLB", "NFL", "NBA", "NHL")
DIVISIONS_QUERY = "level=3"

# ESPN's leader, and what a missing figure reads as.
NO_GAMES_BACK = "-"

_LEAGUE_PREFIXES = (("American League ", "AL "), ("National League ", "NL "))
_DIVISION_SUFFIX = " Division"


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _dicts(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def division_label(name):
    """The name a division goes by in both apps: "American League East" is "AL East",
    "Atlantic Division" is "Atlantic", and "AFC East" stays as it is."""
    name = name.strip() if isinstance(name, str) else ""
    for long, short in _LEAGUE_PREFIXES:
        if name.startswith(long):
            name = short + name[len(long):]
            break
    if name.endswith(_DIVISION_SUFFIX) and len(name) > len(_DIVISION_SUFFIX):
        name = name[: -len(_DIVISION_SUFFIX)]
    return name


def _stat(entry, name):
    for stat in _dicts(_as_dict(entry).get("stats")):
        if stat.get("name") == name:
            return stat
    return None


def games_back(entry):
    """ESPN's games back for a team, as it writes it ("-", "2.5", "6"): the division figure
    when there is one, otherwise the group's own."""
    for name in ("divisionGamesBehind", "gamesBehind"):
        stat = _stat(entry, name)
        if stat is None:
            continue
        text = stat.get("displayValue")
        text = text.strip() if isinstance(text, str) else ""
        if text:
            return text
    return NO_GAMES_BACK


# What a team needs for the iPhone to read it (Standings.swift's APIStandingsEntry): these four
# as text, and a list of stats that each have a name. Anything less is left out on both apps,
# so the two never list different teams.
_TEAM_FIELDS = ("id", "name", "abbreviation", "displayName")
# A group whose name is missing or blank, with no conference to name it either.
UNNAMED_GROUP = "Standings"


def readable_entry(entry):
    team = _as_dict(_as_dict(entry).get("team"))
    stats = entry.get("stats") if isinstance(entry, dict) else None
    return (all(isinstance(team.get(field), str) for field in _TEAM_FIELDS)
            and isinstance(stats, list)
            and all(isinstance(stat, dict) and isinstance(stat.get("name"), str) for stat in stats))


def _text(value):
    return value if isinstance(value, str) else ""


def _walk(node, conference, depth):
    node = _as_dict(node)
    entries = [e for e in _dicts(_as_dict(node.get("standings")).get("entries")) if readable_entry(e)]
    groups = []
    if entries:
        # A nameless group still needs a name to be read out: its conference's, or a plain word.
        name = division_label(node.get("name")) or conference or UNNAMED_GROUP
        groups.append({"name": name, "conference": conference, "entries": entries})
    # The root is the league; its children are the conferences, and everything below a
    # conference is in it.
    for child in _dicts(node.get("children")):
        groups += _walk(child, _text(child.get("name")).strip() if depth == 0 else conference, depth + 1)
    return groups


def _number(text):
    """"2.5" as 2.5; ESPN's "-" (the leader) and anything unreadable as 0."""
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _seed(entry):
    """ESPN's seed if it sent one as a number; text ("3") counts as none, as on the iPhone."""
    value = (_stat(entry, "playoffSeed") or {}).get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return None
    seed = int(value)
    return seed if seed > 0 else None


def standing_order(entries):
    """A group's teams in standing order. The answer's own order won't do: the NBA's divisions
    come worst first and MLB's in no order at all. ESPN's playoff seed has the league's
    tiebreakers in it, and within one group it ranks the teams as the group does, so it decides;
    a team without one goes after those with one, by games back. Ties keep the answer's order."""
    indexed = list(enumerate(entries))
    indexed.sort(key=lambda pair: (
        _seed(pair[1]) is None,
        _seed(pair[1]) or 0,
        _number(games_back(pair[1])),
        pair[0],
    ))
    return [entry for _, entry in indexed]


def division_groups(data):
    """Every group in the answer that has teams, in ESPN's order of groups, as
    {"name", "conference", "entries"}, each group's teams in standing order. "conference" is
    the conference the group sits under, or the group's own name when it is a conference.
    A team appears once: if ESPN ever repeats one, its first group keeps it."""
    seen = set()
    groups = []
    for group in _walk(data, "", 0):
        kept = []
        for entry in group["entries"]:
            team_id = str(_as_dict(entry.get("team")).get("id") or "")
            if team_id and team_id in seen:
                continue
            seen.add(team_id)
            kept.append(entry)
        if kept:
            groups.append({**group, "entries": standing_order(kept)})
    return groups


def team_divisions(data):
    """Team id to the name of the group it is in."""
    return {str(_as_dict(entry.get("team")).get("id")): group["name"]
            for group in division_groups(data)
            for entry in group["entries"]
            if _as_dict(entry.get("team")).get("id")}


def conference_entries(data, conference):
    """Every team under a conference (an MLB league), whatever level its divisions are at."""
    return [entry for group in division_groups(data) if group["conference"] == conference
            for entry in group["entries"]]
