"""Pure: the CFL's own scoreboard feed to what the CFL screens show. Scores by week, the East and
West standings, the teams and each team's season.

ESPN's `football/cfl` scoreboard stopped at the 2022 season, so the CFL comes from the feed behind
cfl.ca's scoreboard (run by Genius Sports), as it does on the iPhone (`CFLAPIService.swift`):

    rounds.json   every week of the season, each with its games ("tournaments")
    squads.json   the teams, each with its wins, losses and draws

No PyQt import, so it is tested on any platform. tests/fixtures/cfl_grid.json holds the two apps
to the same reading (tests/unit/test_cfl.py and CFLGridTests.swift).

What the feed is like, all seen in tests/fixtures/espn/cfl_*:

- It's undocumented and unofficial. It has scores, kickoff times, live status and records, and no
  box score, play-by-play, roster, venue, broadcast or news.
- A game's status is "scheduled", then the quarter it's in ("third_quarter", with activePeriod 3),
  "half_time" between the second and third, and "complete". Halftime has no period and the clock at
  15:00. The round's own status says "playing" while any of its games is. Anything never seen is
  read by whether it has a period or a clock: with one it's under way, and without it hasn't started.
- A game not started has a score of 0 for both teams, which is no score at all.
- A team not yet known, such as a Grey Cup opponent before the conference finals, is squad 0,
  "TBD", which squads.json also lists with a 0-0 record.
- A week (round) has a start and end date, but its end is 23:59Z on its last day and games run past
  it, so the current week is the first that hasn't ended or has a game under way.
- squads.json says nothing about divisions, so East and West are fixed here, as on the iPhone.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from game_labels import local_schedule_datetime

ROUNDS_URL = "https://cflscoreboard.cfl.ca/json/scoreboard/rounds.json"
SQUADS_URL = "https://cflscoreboard.cfl.ca/json/scoreboard/squads.json"

EAST = "East Division"
WEST = "West Division"
# By the feed's abbreviation. A team that isn't West is East, as on the iPhone.
WEST_TEAMS = {"BC", "CGY", "EDM", "SSK", "WPG"}
EAST_TEAMS = {"HAM", "MTL", "OTT", "TOR"}

# A game being played says which quarter it's in: third_quarter was seen with activePeriod 3. The
# others are named the same way; "playing" is what a round under way says, and is kept in case a
# game says it too.
# The iPhone knew only "playing" until November 2026, and showed every live game as Scheduled.
PLAYING_STATUSES = {"first_quarter", "second_quarter", "third_quarter", "fourth_quarter", "overtime", "playing"}
KNOWN_STATUSES = {"scheduled", "half_time", "complete"} | PLAYING_STATUSES

PRESEASON, REGULAR_SEASON, POSTSEASON = 1, 2, 3


def unavailable(what: str) -> str:
    """A failed request, in the iPhone's words: APIError.unavailable(what, source: "The CFL")."""
    return f"The CFL isn't providing {what} right now. Try again in a minute."


def _dicts(value: Any) -> List[Dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def parse_date(text: Any) -> Optional[datetime]:
    """The feed's ISO 8601 times, which carry their offset: "2026-11-07T23:30:00+00:00"."""
    if not isinstance(text, str) or not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def iso(moment: Optional[datetime]) -> str:
    """A time as UTC ISO 8601, as the grid holds it, or "" for none."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if moment else ""


def season_type(round_type: Any) -> int:
    return {"PRE": PRESEASON, "POST": POSTSEASON}.get(round_type, REGULAR_SEASON)


def division(abbreviation: str) -> str:
    return WEST if abbreviation in WEST_TEAMS else EAST


def record_text(wins: int, losses: int, draws: int) -> str:
    """"W-L", or "W-L-D" with draws."""
    return f"{wins}-{losses}-{draws}" if draws > 0 else f"{wins}-{losses}"


def _squads(squads: Any) -> List[Dict[str, Any]]:
    """The real teams: squad 0 is the feed's TBD."""
    teams = []
    for squad in _dicts(squads):
        team_id = _int(squad.get("id"))
        if not team_id:
            continue
        wins, losses, draws = (_int(squad.get(k)) or 0 for k in ("wins", "loss", "draw"))
        abbreviation = str(squad.get("abbreviation") or "")
        teams.append({"id": str(team_id), "name": str(squad.get("name") or abbreviation),
                      "abbreviation": abbreviation, "wins": wins, "losses": losses, "draws": draws,
                      "record": record_text(wins, losses, draws), "division": division(abbreviation)})
    return teams


def _records(squads: Any) -> Dict[str, str]:
    return {team["id"]: team["record"] for team in _squads(squads)}


# ------------------------------------------------------------------ a game

def game_status(game: Dict[str, Any]) -> Dict[str, Any]:
    """state (pre, in or post) and what to say about it: "Final", "Halftime", "Q3 4:12"."""
    status = game.get("status") if isinstance(game.get("status"), str) else ""
    period = _int(game.get("activePeriod"))
    clock = game.get("clock") if isinstance(game.get("clock"), str) else None
    clock = clock.strip() if clock else None
    if status == "complete":
        return {"state": "post", "detail": "Final", "period": None, "clock": None}
    if status == "half_time":
        # The clock says 15:00, for the third quarter; it isn't running.
        return {"state": "in", "detail": "Halftime", "period": None, "clock": None}
    if status in PLAYING_STATUSES:
        if period:
            detail = "OT" if period > 4 else f"Q{period}"
            if clock:
                detail += f" {clock}"
        else:
            detail = clock or "In Progress"
        return {"state": "in", "detail": detail, "period": period, "clock": clock}
    if status == "scheduled" or not status:
        return {"state": "pre", "detail": "Scheduled", "period": None, "clock": None}
    # One the feed hasn't been seen to send: under way if it has a period or a clock.
    detail = status.replace("_", " ").strip().capitalize()
    state = "in" if (period or clock) else "pre"
    return {"state": state, "detail": detail, "period": None, "clock": None}


def _team(squad: Any, records: Dict[str, str], show_score: bool) -> Dict[str, Any]:
    squad = squad if isinstance(squad, dict) else {}
    team_id = str(_int(squad.get("id")) or 0)
    short = str(squad.get("shortName") or "")
    return {"id": team_id, "name": str(squad.get("name") or short or "TBD"), "abbreviation": short,
            "score": _int(squad.get("score")) if show_score else None,
            # Squad 0 is a team not yet known, whose 0-0 isn't a record.
            "record": records.get(team_id) if team_id != "0" else None}


def make_game(game: Dict[str, Any], kind: int, records: Dict[str, str],
              week: str = "") -> Dict[str, Any]:
    status = game_status(game)
    show = status["state"] != "pre"
    away = _team(game.get("awaySquad"), records, show)
    home = _team(game.get("homeSquad"), records, show)
    moment = parse_date(game.get("date"))
    return {"id": str(_int(game.get("id")) or ""), "date": iso(moment), "away": away, "home": home,
            "name": f"{away['name']} at {home['name']}", **status, "season_type": kind, "week": week}


def _week_name(round_: Dict[str, Any], index: int) -> str:
    """The feed has always named its weeks; "Week N" if it ever doesn't, as on the iPhone."""
    name = round_.get("name")
    return name if isinstance(name, str) and name else f"Week {index + 1}"


def _visible(round_: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [g for g in _dicts(round_.get("tournaments")) if not g.get("isHidden")]


def _by_kickoff(games: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # The id settles two games at the same time, so both apps list them the same way.
    return sorted(games, key=lambda g: (g["date"], g["id"]))


# ------------------------------------------------------------------ a week

def current_round_index(rounds: Any, now: Optional[datetime] = None) -> int:
    """The first week that hasn't ended or has a game under way, or the last once the season is
    over. A week whose end can't be read counts as not over.

    A week's end is the last minute of its last day in UTC, 23:59Z, and games kick off as late as
    23:30Z, so a game is still being played after its week has "ended". Going by the end alone
    showed next week's games all evening with the last game live."""
    rounds = _dicts(rounds)
    now = now or datetime.now(timezone.utc)
    for i, round_ in enumerate(rounds):
        end = parse_date(round_.get("endDate"))
        if end is None or end >= now or any(game_status(g)["state"] == "in" for g in _visible(round_)):
            return i
    return max(len(rounds) - 1, 0)


def parse_round(rounds: Any, squads: Any, index: Optional[int] = None,
                now: Optional[datetime] = None) -> Dict[str, Any]:
    """One week's games: `index` into the season's weeks, or None for the current one.
    Returns games, index, label ("Week 5", "Semi-Finals", "113th Grey Cup"), count and is_current."""
    rounds = _dicts(rounds)
    if not rounds:
        return {"games": [], "index": 0, "label": "", "count": 0, "is_current": True}
    current = current_round_index(rounds, now)
    i = min(max(current if index is None else index, 0), len(rounds) - 1)
    round_ = rounds[i]
    label = _week_name(round_, i)
    records = _records(squads)
    kind = season_type(round_.get("type"))
    games = _by_kickoff([make_game(g, kind, records, label) for g in _visible(round_)])
    return {"games": games, "index": i, "label": label, "count": len(rounds), "is_current": i == current}


def all_games(rounds: Any, squads: Any = None) -> List[Dict[str, Any]]:
    records = _records(squads)
    games = []
    for i, round_ in enumerate(_dicts(rounds)):
        kind = season_type(round_.get("type"))
        label = _week_name(round_, i)
        games += [make_game(g, kind, records, label) for g in _visible(round_)]
    return games


def find_game(rounds: Any, squads: Any, game_id: str) -> Optional[Dict[str, Any]]:
    return next((g for g in all_games(rounds, squads) if g["id"] == game_id), None)


# ------------------------------------------------------------------ standings and teams

def win_percent(team: Dict[str, Any]) -> float:
    played = team["wins"] + team["losses"] + team["draws"]
    return (team["wins"] + 0.5 * team["draws"]) / played if played else 0.0


def standings(squads: Any) -> List[Dict[str, Any]]:
    """East, then West, each by win percentage, then wins, then name. The feed has no
    tiebreakers, so teams level on both are in alphabetical order, on both apps."""
    groups = []
    teams = _squads(squads)
    for name in (EAST, WEST):
        entries = sorted((t for t in teams if t["division"] == name),
                         key=lambda t: (-win_percent(t), -t["wins"], t["name"]))
        if entries:
            groups.append({"name": name, "entries": [{**t, "rank": i + 1, "win_percent": win_percent(t)}
                                                      for i, t in enumerate(entries)]})
    return groups


def teams(squads: Any) -> List[Dict[str, Any]]:
    return sorted(_squads(squads), key=lambda t: t["name"])


def team_schedule(rounds: Any, team_id: str, squads: Any = None) -> List[Dict[str, Any]]:
    """Every game the team plays this season, first to last."""
    games = [g for g in all_games(rounds, squads) if team_id in (g["away"]["id"], g["home"]["id"])]
    return _by_kickoff(games)


def ordinal(n: int) -> str:
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


def team_info(rounds: Any, squads: Any, team_id: str,
              now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """The iPhone's Team Hub Info for a CFL team: record, place in its division, next game."""
    team = next((t for t in _squads(squads) if t["id"] == team_id), None)
    if team is None:
        return None
    standing = ""
    for group in standings(squads):
        for entry in group["entries"]:
            if entry["id"] == team_id:
                standing = f"{ordinal(entry['rank'])} in {group['name']}"
    now = now or datetime.now(timezone.utc)
    next_game = next((g for g in team_schedule(rounds, team_id, squads)
                      if g["state"] == "pre" and (parse_date(g["date"]) or now) > now), None)
    return {**team, "standing": standing, "next_game": next_game}


# ------------------------------------------------------------------ what the Windows screens show

def kickoff_text(game: Dict[str, Any]) -> str:
    """Local time: "Saturday, November 7, 6:30 PM"."""
    if not game.get("date"):
        return ""
    moment = local_schedule_datetime(game["date"])
    return f"{moment.strftime('%A, %B')} {moment.day}, {moment.strftime('%I:%M %p').lstrip('0')}"


def score_text(game: Dict[str, Any]) -> str:
    """"WPG 23, MTL 33", away first as the game's name is; nothing before kickoff."""
    away, home = game["away"], game["home"]
    if away["score"] is None or home["score"] is None:
        return ""
    return (f"{away['abbreviation'] or away['name']} {away['score']}, "
            f"{home['abbreviation'] or home['name']} {home['score']}")


SCORE_HEADERS = ["Game", "Score", "Status", "Kickoff"]


def score_rows(games: List[Dict[str, Any]]) -> List[List[str]]:
    return [[g["name"], score_text(g) or "Not started", g["detail"], kickoff_text(g)] for g in games]


def week_summary(week: Dict[str, Any]) -> str:
    """"Conference Finals, 2 games", with "this week" on the current one."""
    n = len(week["games"])
    games = "no games" if n == 0 else f"{n} game" if n == 1 else f"{n} games"
    current = ", this week" if week["is_current"] else ""
    return f"{week['label']}{current}, {games}"


def game_summary(game: Dict[str, Any]) -> str:
    """What the game page says first: "Final. Conference Finals. Saturday, November 7, 3:00 PM."."""
    parts = [game["detail"], game.get("week") or "", kickoff_text(game)]
    return " ".join(f"{p}." for p in parts if p)


GAME_HEADERS = ["Team", "Score", "Record", "Side"]


def game_rows(game: Dict[str, Any]) -> List[List[str]]:
    rows = []
    for side, team in (("Away", game["away"]), ("Home", game["home"])):
        score = "" if team["score"] is None else str(team["score"])
        rows.append([team["name"], score or "Not started", team["record"] or "No record", side])
    return rows


def _percent_text(value: float) -> str:
    text = f"{value:.3f}"
    return text[1:] if text.startswith("0") else text


def standings_headers(groups: List[Dict[str, Any]]) -> List[str]:
    headers = ["Rank", "Team", "Division", "W", "L"]
    if any(e["draws"] for g in groups for e in g["entries"]):
        headers.append("T")
    return headers + ["Pct"]


def standings_rows(groups: List[Dict[str, Any]]) -> List[List[str]]:
    draws = "T" in standings_headers(groups)
    rows = []
    for group in groups:
        for e in group["entries"]:
            row = [str(e["rank"]), e["name"], group["name"], str(e["wins"]), str(e["losses"])]
            if draws:
                row.append(str(e["draws"]))
            rows.append(row + [_percent_text(e["win_percent"])])
    return rows


def standings_team_ids(groups: List[Dict[str, Any]]) -> List[str]:
    return [e["id"] for g in groups for e in g["entries"]]


TEAM_HEADERS = ["Team", "Abbreviation", "Division", "Record"]


def team_rows(team_list: List[Dict[str, Any]]) -> List[List[str]]:
    return [[t["name"], t["abbreviation"], t["division"], t["record"]] for t in team_list]


SCHEDULE_HEADERS = ["Opponent", "Result", "Date", "Week"]


def schedule_result(game: Dict[str, Any], team_id: str) -> str:
    """"W 33-23", "L 23-33", "T 20-20", "Halftime, 9-6", or the status of a game to come. The
    team's own score is first."""
    home = game["home"]["id"] == team_id
    mine, theirs = (game["home"], game["away"]) if home else (game["away"], game["home"])
    if mine["score"] is None or theirs["score"] is None:
        return game["detail"]
    score = f"{mine['score']}-{theirs['score']}"
    if game["state"] == "post":
        letter = "W" if mine["score"] > theirs["score"] else "L" if mine["score"] < theirs["score"] else "T"
        return f"{letter} {score}"
    return f"{game['detail']}, {score}"


def schedule_rows(games: List[Dict[str, Any]], team_id: str) -> List[List[str]]:
    rows = []
    for g in games:
        home = g["home"]["id"] == team_id
        opponent = g["away"] if home else g["home"]
        rows.append([f"{'vs' if home else 'at'} {opponent['name']}", schedule_result(g, team_id),
                     kickoff_text(g), g.get("week") or ""])
    return rows


def schedule_start_row(games: List[Dict[str, Any]]) -> int:
    """The game under way, or the next one, or the last once the season's over."""
    for i, g in enumerate(games):
        if g["state"] != "post":
            return i
    return max(len(games) - 1, 0)


def team_summary(info: Dict[str, Any]) -> str:
    """"13-5, 1st in West Division. Next game: vs BC Lions, Saturday, November 14, 6:30 PM."."""
    parts = [info["record"] + (f", {info['standing']}" if info.get("standing") else "") + "."]
    game = info.get("next_game")
    if game:
        home = game["home"]["id"] == info["id"]
        opponent = game["away"] if home else game["home"]
        parts.append(f"Next game: {'vs' if home else 'at'} {opponent['name']}, {kickoff_text(game)}.")
    return " ".join(parts)
