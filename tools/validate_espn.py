#!/usr/bin/env python3
"""Check ESPN and the app's other data sources against what both apps rely on.

Nothing documents these feeds, and they change without notice: ESPN began rejecting
`dates=A-B` ranges in September 2026, which broke the iPhone's football week arrows for
weeks before anyone noticed. This calls every endpoint either app uses, checks the shape
each one relies on, and runs the real Windows parsers on the live data.

    python tools/validate_espn.py                     every league
    python tools/validate_espn.py --league NCAAM      just one (repeat for more)
    python tools/validate_espn.py --report out.md     also write the report to a file

It opens no windows, so it is safe to run anywhere. It only reads. It exits 1 if anything
FAILed. `.github/workflows/validate-espn.yml` runs it on demand and every night.

What the results mean:
    PASS  it did what the apps need
    WARN  worth a look, but not proof of a break: often the off-season, or an endpoint the
          apps cope without
    FAIL  something the apps rely on is gone or wrong, or our parser got it wrong

Being out of season isn't a failure. A league with no games today is fine, and to check a
game's details it looks back for the most recent final, however long ago that was.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import pytz
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SITE = "https://site.api.espn.com/apis/site/v2/sports"
STANDINGS = "https://site.api.espn.com/apis/v2/sports"
CORE = "https://sports.core.api.espn.com/v2/sports"
WEB = "https://site.web.api.espn.com/apis/common/v3/sports"

FOOTBALL, BASKETBALL, HOCKEY, BASEBALL, SOCCER = "football", "basketball", "hockey", "baseball", "soccer"
PASS, WARN, FAIL = "PASS", "WARN", "FAIL"

# Numbers that are invented if they appear, from the fallbacks the app used to have.
INVENTED = ("sample player", "sample stat", "team1")

MONTHS_TO_SEARCH = 14


@dataclass(frozen=True)
class League:
    key: str
    path: str
    family: str
    scoreboard_params: str = ""
    # What ESPN is known to offer here, so a missing one isn't reported as a break.
    box_score: bool = True
    plays: bool = True
    rankings: bool = False
    transactions: bool = True
    player_stats: bool = True
    team_stats: bool = True

    @property
    def is_college(self) -> bool:
        return self.key.startswith("NCAA")


LEAGUES = [
    League("NFL", "football/nfl", FOOTBALL),
    League("NCAAF", "football/college-football", FOOTBALL, "groups=90&limit=400", rankings=True, transactions=False),
    League("NBA", "basketball/nba", BASKETBALL, player_stats=False),
    League("WNBA", "basketball/wnba", BASKETBALL, player_stats=False),
    League("NCAAM", "basketball/mens-college-basketball", BASKETBALL, "groups=50&limit=400",
           rankings=True, transactions=False),
    League("NCAAWB", "basketball/womens-college-basketball", BASKETBALL, "groups=50&limit=400",
           rankings=True, transactions=False, player_stats=False),
    League("NHL", "hockey/nhl", HOCKEY),
    # ESPN sends college hockey no box scores or plays at all.
    League("NCAAH", "hockey/mens-college-hockey", HOCKEY, box_score=False, plays=False,
           rankings=True, transactions=False, player_stats=False, team_stats=False),
    League("NCAAWH", "hockey/womens-college-hockey", HOCKEY, box_score=False, plays=False,
           rankings=True, transactions=False, player_stats=False, team_stats=False),
    League("MLB", "baseball/mlb", BASEBALL),
    League("EPL", "soccer/eng.1", SOCCER, transactions=False, player_stats=False, team_stats=False),
    League("MLS", "soccer/usa.1", SOCCER, transactions=False, player_stats=False, team_stats=False),
]
LEAGUE_KEYS = {league.key: league for league in LEAGUES}

# The app maps teams to divisions itself. A team it doesn't know lands outside them, as Utah did.
EXPECTED_DIVISIONS = {"NFL": 8, "NBA": 6, "NHL": 4, "MLB": 6}


@dataclass
class Check:
    source: str
    name: str
    status: str
    detail: str = ""
    url: str = ""


@dataclass
class Report:
    checks: list = field(default_factory=list)

    def add(self, source, name, status, detail="", url=""):
        self.checks.append(Check(source, name, status, detail, url))

    def ok(self, source, name, detail="", url=""):
        self.add(source, name, PASS, detail, url)

    def warn(self, source, name, detail, url=""):
        self.add(source, name, WARN, detail, url)

    def fail(self, source, name, detail, url=""):
        self.add(source, name, FAIL, detail, url)

    def count(self, status):
        return sum(1 for c in self.checks if c.status == status)

    @property
    def failed(self):
        return self.count(FAIL) > 0


class Http:
    """GET with retries, because a single 503 from ESPN isn't news."""

    def __init__(self, attempts=3, pause=4.0, timeout=30):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "Mozilla/5.0 (Scores data validator)"
        self.attempts, self.pause, self.timeout = attempts, pause, timeout

    def get(self, url):
        """(status code or error text, parsed JSON or None)."""
        outcome = "no attempt"
        for attempt in range(self.attempts):
            if attempt:
                time.sleep(self.pause * attempt)
            try:
                response = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as e:
                outcome = type(e).__name__
                continue
            if response.status_code >= 500 or response.status_code == 429:
                outcome = response.status_code
                continue
            try:
                return response.status_code, response.json()
            except ValueError:
                return response.status_code, None
        return outcome, None


def scoreboard_url(league, dates=None, include_params=True):
    parts = [league.scoreboard_params] if league.scoreboard_params and include_params else []
    if dates:
        parts.append(f"dates={dates}")
    return f"{SITE}/{league.path}/scoreboard" + ("?" + "&".join(parts) if parts else "")


def first_problems(problems, limit=3):
    extra = f" and {len(problems) - limit} more" if len(problems) > limit else ""
    return "; ".join(problems[:limit]) + extra


# ---------------------------------------------------------------- payload checks
# Pure: each takes a parsed payload and returns a list of problems. Tested against real
# saved payloads and damaged copies of them in tests/unit/test_validate_espn.py.

def scoreboard_problems(data):
    problems = []
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        return ["no events list"]
    for event in data["events"]:
        label = event.get("id", "an event with no id")
        if not event.get("id"):
            problems.append("an event has no id")
        if not event.get("date"):
            problems.append(f"{label}: no date")
        status_type = (event.get("status") or {}).get("type") or {}
        if not status_type.get("state") or not status_type.get("name"):
            problems.append(f"{label}: no status state or name")
        competitions = event.get("competitions") or []
        if not competitions:
            problems.append(f"{label}: no competitions")
            continue
        competitors = competitions[0].get("competitors") or []
        if len(competitors) != 2:
            problems.append(f"{label}: {len(competitors)} competitors")
            continue
        for competitor in competitors:
            team = competitor.get("team") or {}
            if not team.get("displayName") or not team.get("abbreviation"):
                problems.append(f"{label}: a team with no displayName or abbreviation")
            if competitor.get("homeAway") not in ("home", "away"):
                problems.append(f"{label}: homeAway is {competitor.get('homeAway')!r}")
    return problems


def _athlete_has_name(athlete):
    info = athlete.get("athlete") or {}
    return bool(info.get("displayName") or info.get("shortName"))


def box_score_problems(box, league):
    """What ESPN's box score must look like for box_score.py and BoxScoreView.swift."""
    if not isinstance(box, dict):
        return ["no boxscore"]
    problems = []
    teams = box.get("teams")
    if not isinstance(teams, list) or len(teams) != 2:
        return [f"boxscore.teams has {len(teams) if isinstance(teams, list) else 'no'} teams"]
    for team in teams:
        info = team.get("team") or {}
        if not info.get("displayName") or not info.get("abbreviation"):
            problems.append("a box score team has no displayName or abbreviation")
        for stat in team.get("statistics") or []:
            if not stat.get("name"):
                problems.append("a team statistic has no name")
                break
    if not league.box_score:
        return problems

    if league.family != SOCCER and not any(team.get("statistics") for team in teams):
        problems.append("neither team has statistics")
    for team in teams:
        statistics = team.get("statistics") or []
        if league.family == BASEBALL:
            # Categories wrapping their own stats. ESPN also sends a flat `records` beside them.
            names = {s.get("name") for s in statistics if s.get("stats")}
            if not {"batting", "pitching"} <= names:
                problems.append(f"baseball team stats are no longer nested by category: found {sorted(names)}")
            continue
        for stat in statistics:
            if stat.get("displayValue") is None:
                problems.append(f"team stat {stat.get('name')} has no displayValue")
                break
    if league.family == SOCCER:
        return problems

    players = box.get("players")
    if not isinstance(players, list) or not players:
        return problems + ["boxscore.players is empty"]
    seen_groups, total_athletes = set(), 0
    for team in players:
        for group in team.get("statistics") or []:
            seen_groups.add(group.get("name") or group.get("type") or "")
            athletes = group.get("athletes") or []
            total_athletes += len(athletes)
            headers = group.get("names") or group.get("labels") or []
            if athletes and not headers:
                problems.append(f"group {group.get('name')!r}: athletes but no names or labels")
                continue
            for athlete in athletes:
                if not _athlete_has_name(athlete):
                    problems.append("an athlete has neither displayName nor shortName")
                stats = athlete.get("stats")
                if stats is None:
                    problems.append("an athlete has no stats key")
                elif stats and len(stats) != len(headers):
                    problems.append(f"group {group.get('name')!r}: {len(stats)} stats under {len(headers)} columns")
    if not total_athletes:
        problems.append("no athletes in any group")
    required = {FOOTBALL: {"passing", "rushing", "receiving"}, HOCKEY: {"forwards", "goalies"},
                BASEBALL: {"batting", "pitching"}}.get(league.family, set())
    missing = required - seen_groups
    if missing:
        problems.append(f"expected groups are gone: {', '.join(sorted(missing))} (found {', '.join(sorted(seen_groups))})")
    return problems


def play_problems(summary, league):
    """Plays or drives, including what play audio reads."""
    if not league.plays or league.family == SOCCER:
        return []
    if league.family == FOOTBALL:
        drives = summary.get("drives") or {}
        previous = drives.get("previous")
        if not previous:
            return ["drives.previous is empty"]
        problems = []
        if not any(d.get("plays") for d in previous):
            problems.append("no drive has plays")
        for drive in previous:
            if not (drive.get("team") or {}).get("displayName"):
                problems.append("a drive has no team")
                break
        return problems
    plays = summary.get("plays")
    if not plays:
        return ["plays is empty"]
    problems = []
    for play in plays:
        if not play.get("id"):
            problems.append("a play has no id")
            break
        if not (play.get("type") or {}).get("text"):
            problems.append("a play has no type.text")
            break
        if not (play.get("period") or {}).get("number"):
            problems.append("a play has no period.number")
            break
    if league.family in (BASKETBALL, HOCKEY):
        located = [p for p in plays if isinstance(p.get("coordinate"), dict)]
        if not located:
            problems.append("no play has a coordinate, so play audio has nothing")
        else:
            xs = [p["coordinate"].get("x") for p in located]
            usable = [x for x in xs if isinstance(x, (int, float)) and abs(x) < 1_000_000]
            limit = 50 if league.family == BASKETBALL else 100
            wild = [x for x in usable if abs(x) > limit + 10]
            if wild:
                problems.append(f"{len(wild)} coordinates outside the court or rink, such as x={wild[0]}")
    return problems


def _standing_nodes(node):
    yield node
    for child in node.get("children") or []:
        yield from _standing_nodes(child)


def standings_entries(data):
    entries = []
    for node in _standing_nodes(data or {}):
        entries.extend((node.get("standings") or {}).get("entries") or [])
    return entries


def standings_problems(data, league):
    entries = standings_entries(data)
    if not entries:
        return ["no entries anywhere in the response"]
    problems = []
    for entry in entries:
        name = (entry.get("team") or {}).get("displayName")
        if not name:
            problems.append("an entry has no team.displayName")
        stats = entry.get("stats") or []
        if not stats:
            problems.append(f"{name}: no stats")
            continue
        if league.family != SOCCER and not any(s.get("type") == "total" for s in stats):
            problems.append(f"{name}: no stat with type 'total', the overall record")
    return problems


def summary_header_problems(summary):
    competitions = (summary.get("header") or {}).get("competitions") or []
    if not competitions:
        return ["header.competitions is empty"]
    competitors = competitions[0].get("competitors") or []
    if len(competitors) != 2:
        return [f"header has {len(competitors)} competitors"]
    problems = []
    if not ((competitions[0].get("status") or {}).get("type") or {}).get("state"):
        problems.append("header has no status state")
    return problems


def invented_names(value):
    """Any text that came from the invented fallbacks the app used to have."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            for item in node.values():
                walk(item)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            lowered = node.lower()
            if any(term in lowered for term in INVENTED):
                found.append(node)

    walk(value)
    return found


def played_athletes_missing_from_tables(box, tables):
    """Names of people ESPN lists that box_score.build_box_tables dropped."""
    shown = {str(row[0]).strip() for table in tables for row in table.rows if row}
    missing = []
    for team in box.get("players") or []:
        for group in team.get("statistics") or []:
            if not (group.get("names") or group.get("labels")):
                continue
            for athlete in group.get("athletes") or []:
                info = athlete.get("athlete") or {}
                name = (info.get("displayName") or info.get("shortName") or "").strip()
                if name and name not in shown:
                    missing.append(name)
    return missing


# ------------------------------------------------------------------ live helpers

def is_played_final(event):
    """Finished and actually played. Soccer says STATUS_FULL_TIME, so go by state. A
    postponed game is also state "post"."""
    status_type = (event.get("status") or {}).get("type") or {}
    if status_type.get("state") != "post" or not status_type.get("completed"):
        return False
    if status_type.get("name") in ("STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_CANCELLED", "STATUS_FORFEIT"):
        return False
    return len((event.get("competitions") or [{}])[0].get("competitors") or []) == 2


def espn_date(iso):
    """The day ESPN files a game under, which is its Eastern date. A 9 PM Eastern game is
    tomorrow in UTC, and this runs on a machine in UTC."""
    moment = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return moment.astimezone(pytz.timezone("America/New_York")).date()


def find_recent_final(http, league, today=None):
    """(event, scoreboard url) for the most recent finished game, or (None, url)."""
    today = today or date.today()
    url = ""
    candidates = [(today - timedelta(days=n)).strftime("%Y%m%d") for n in range(0, 4)]
    year, month = today.year, today.month
    for _ in range(MONTHS_TO_SEARCH):
        candidates.append(f"{year}{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    for dates in candidates:
        url = scoreboard_url(league, dates)
        status, data = http.get(url)
        if status != 200 or not isinstance(data, dict):
            continue
        finals = [e for e in data.get("events") or [] if is_played_final(e)]
        if finals:
            finals.sort(key=lambda e: e.get("date", ""), reverse=True)
            return finals[0], url
    return None, url


# ---------------------------------------------------------------- per league

def check_scoreboard(http, report, league):
    url = scoreboard_url(league)
    status, data = http.get(url)
    if status != 200:
        report.fail(league.key, "Scoreboard", f"got {status}", url)
        return None
    problems = scoreboard_problems(data)
    if problems:
        report.fail(league.key, "Scoreboard", first_problems(problems), url)
        return data
    count = len(data["events"])
    report.ok(league.key, "Scoreboard", f"{count} games" if count else "no games now, fine out of season", url)
    return data


def check_app_scores(report, league, event):
    """The app lists exactly the games the feed has on that date."""
    import espn_api
    from models.game import GameData

    day = espn_date(event["date"])
    try:
        if league.family == FOOTBALL:
            week = event.get("week", {}).get("number") if isinstance(event.get("week"), dict) else None
            season = (event.get("season") or {}).get("year")
            season_type = (event.get("season") or {}).get("type")
            if not week:
                report.warn(league.key, "App: game list", "the final's event has no week number, so it wasn't compared")
                return
            games = espn_api.get_scores(league.key, week=week, season=season, seasontype=season_type)
        else:
            games = espn_api.get_scores(league.key, day)
    except Exception as e:
        report.fail(league.key, "App: game list", f"get_scores raised {type(e).__name__}: {e}")
        return
    ids = {str(g.get("id")) for g in games}
    if str(event["id"]) not in ids:
        report.fail(league.key, "App: game list",
                    f"game {event['id']} ({event.get('shortName')}) is in the feed but get_scores didn't list it, of {len(games)}")
        return
    bad = []
    for game in games:
        text = GameData(game, league.key).get_display_text()
        if not text or "Unknown" in text:
            bad.append(text or f"game {game.get('id')} has no text")
    if bad:
        report.fail(league.key, "App: game list", f"unreadable rows: {first_problems(bad)}")
    else:
        report.ok(league.key, "App: game list", f"{len(games)} games read cleanly, including {event.get('shortName')}")


def check_game(http, report, league, event):
    url = f"{SITE}/{league.path}/summary?event={event['id']}"
    status, summary = http.get(url)
    if status != 200 or not isinstance(summary, dict):
        report.fail(league.key, "Game summary", f"got {status} for final {event['id']}", url)
        return
    label = f"final {event['id']} ({event.get('shortName')})"

    problems = summary_header_problems(summary)
    if problems:
        report.fail(league.key, "Game summary", first_problems(problems), url)
    else:
        report.ok(league.key, "Game summary", label, url)

    box = summary.get("boxscore")
    problems = box_score_problems(box, league)
    if problems:
        report.fail(league.key, "Box score shape", first_problems(problems), url)
    elif not league.box_score and any(t.get("statistics") for t in (box or {}).get("teams", [])):
        report.warn(league.key, "Box score shape", "ESPN now sends box scores here. The apps could show them", url)
    else:
        report.ok(league.key, "Box score shape", "as expected" if league.box_score else "ESPN sends none, as expected", url)

    problems = play_problems(summary, league)
    if problems:
        report.fail(league.key, "Plays", first_problems(problems), url)
    elif league.plays:
        report.ok(league.key, "Plays", "plays and locations as expected", url)

    if not summary.get("gameInfo", {}).get("venue"):
        report.warn(league.key, "Venue", "gameInfo.venue is missing on this game", url)
    if league.family != SOCCER and not (summary.get("pickcenter") or summary.get("odds")):
        report.warn(league.key, "Odds", "no pickcenter or odds on this game; older finals often have none", url)

    check_app_game(report, league, event, summary)


def check_app_game(report, league, event, summary):
    """The real parsers, on this game."""
    import espn_api
    from box_score import build_box_tables

    box = summary.get("boxscore")
    try:
        tables = build_box_tables(box)
    except Exception as e:
        report.fail(league.key, "App: box score", f"build_box_tables raised {type(e).__name__}: {e}")
        tables = None
    if tables is not None:
        if league.box_score and league.family != SOCCER and not tables:
            report.fail(league.key, "App: box score", f"build_box_tables gave nothing for final {event['id']}")
        elif league.box_score:
            missing = played_athletes_missing_from_tables(box, tables)
            unknown = [t.title for t in tables if "Unknown" in t.title]
            overlong = [t.title for t in tables if any(len(r) > len(t.headers) for r in t.rows)]
            if missing:
                report.fail(league.key, "App: box score", f"players missing: {first_problems(missing)}")
            elif unknown or overlong:
                report.fail(league.key, "App: box score", f"bad tables: {first_problems(unknown + overlong)}")
            else:
                rows = sum(len(t.rows) for t in tables)
                report.ok(league.key, "App: box score", f"{len(tables)} tables, {rows} rows, every player listed")
        elif tables:
            report.warn(league.key, "App: box score", f"expected none, got {len(tables)} tables")
        else:
            report.ok(league.key, "App: box score", "no box score offered, as expected")

    try:
        details = espn_api.get_game_details(league.key, event["id"])
        info = espn_api.extract_meaningful_game_info(details)
    except Exception as e:
        report.fail(league.key, "App: game details", f"raised {type(e).__name__}: {e}")
        return
    if len(info.get("teams") or []) != 2:
        report.fail(league.key, "App: game details", f"{len(info.get('teams') or [])} teams")
        return
    names = [t.get("name") for t in info["teams"]]
    if not all(names) or "Unknown" in names:
        report.fail(league.key, "App: game details", f"team names are {names}")
    else:
        report.ok(league.key, "App: game details", f"{names[0]} and {names[1]}")


def check_standings(http, report, league):
    import espn_api

    url = f"{STANDINGS}/{league.path}/standings"
    status, data = http.get(url)
    if status != 200 or not isinstance(data, dict):
        report.fail(league.key, "Standings", f"got {status}", url)
        return
    problems = standings_problems(data, league)
    if problems:
        report.fail(league.key, "Standings", first_problems(problems), url)
        return
    entries = standings_entries(data)
    report.ok(league.key, "Standings", f"{len(entries)} teams", url)

    if league.family == SOCCER:
        return
    try:
        rows = espn_api.get_standings(league.key)
    except Exception as e:
        report.fail(league.key, "App: standings", f"get_standings raised {type(e).__name__}: {e}")
        return
    if not rows:
        report.fail(league.key, "App: standings", "get_standings returned nothing, and ESPN has data")
        return
    by_name = {r.get("team_name"): r for r in rows}
    missing, wrong = [], []
    for entry in entries:
        name = (entry.get("team") or {}).get("displayName")
        if name not in by_name:
            missing.append(name)
            continue
        total = next((s for s in entry.get("stats") or [] if s.get("type") == "total"), {})
        summary = str(total.get("summary") or total.get("displayValue") or "")
        pieces = summary.split("-")
        if pieces and pieces[0].isdigit() and str(by_name[name].get("wins")) != pieces[0]:
            wrong.append(f"{name} shows {by_name[name].get('wins')} wins, ESPN's record is {summary}")
    divisions = {r.get("division") for r in rows}
    expected = EXPECTED_DIVISIONS.get(league.key)
    if missing:
        report.fail(league.key, "App: standings", f"{len(missing)} of {len(entries)} teams missing: {first_problems(missing)}")
    elif wrong:
        report.fail(league.key, "App: standings", f"{len(wrong)} wrong records: {first_problems(wrong)}")
    elif expected and len(divisions) != expected:
        report.fail(league.key, "App: standings", f"{len(divisions)} divisions, expected {expected}: {sorted(map(str, divisions))}")
    else:
        report.ok(league.key, "App: standings", f"{len(rows)} teams, every record matches ESPN's")


def check_teams(http, report, league, event):
    import espn_api

    url = f"{SITE}/{league.path}/teams?limit=1000"
    status, data = http.get(url)
    teams = []
    if status == 200 and isinstance(data, dict):
        try:
            teams = data["sports"][0]["leagues"][0]["teams"]
        except (KeyError, IndexError, TypeError):
            report.fail(league.key, "Teams", "sports[0].leagues[0].teams is gone", url)
            return
    if status != 200:
        report.fail(league.key, "Teams", f"got {status}", url)
        return
    if not teams:
        report.fail(league.key, "Teams", "no teams", url)
        return
    report.ok(league.key, "Teams", f"{len(teams)} teams", url)

    if not event:
        return
    competitor = event["competitions"][0]["competitors"][0]
    team_id = str((competitor.get("team") or {}).get("id", ""))
    name = (competitor.get("team") or {}).get("displayName")
    if not team_id:
        report.warn(league.key, "Team hub", "the final's team has no id")
        return

    def checked(label, function, *args):
        try:
            return function(*args)
        except Exception as e:
            report.fail(league.key, label, f"raised {type(e).__name__}: {e}")
            return None

    info = checked("App: team info", espn_api.get_team_info, league.key, team_id)
    if info is not None:
        if not info.get("name"):
            report.fail(league.key, "App: team info", f"no name for team {team_id}")
        elif not info.get("record_overall"):
            report.warn(league.key, "App: team info", f"{name}: no overall record, possibly the off-season")
        else:
            report.ok(league.key, "App: team info", f"{name}, {info['record_overall']}")

    roster = checked("App: roster", espn_api.get_team_roster, league.key, team_id)
    if roster is not None:
        decimals = [p["height"] for p in roster if "." in str(p.get("height", ""))]
        nameless = [p for p in roster if not p.get("name")]
        if decimals or nameless:
            report.fail(league.key, "App: roster", f"{len(decimals)} decimal heights such as {decimals[:1]}, {len(nameless)} with no name")
        elif not roster:
            report.warn(league.key, "App: roster", f"{name}: empty. ESPN has none for many college hockey teams")
        else:
            report.ok(league.key, "App: roster", f"{len(roster)} players")

    schedule = checked("App: schedule", espn_api.get_team_schedule, league.key, team_id)
    if schedule is not None:
        if not schedule:
            if league.key == "WNBA":
                report.warn(league.key, "App: schedule", f"{name}: empty. Known limit of the WNBA path, #71")
            else:
                report.fail(league.key, "App: schedule", f"{name}: empty, though the team just played")
        else:
            report.ok(league.key, "App: schedule", f"{len(schedule)} games")

    news = checked("App: team news", espn_api.get_team_news, league.key, team_id)
    if news is not None:
        if news:
            report.ok(league.key, "App: team news", f"{len(news)} articles")
        else:
            report.warn(league.key, "App: team news", f"{name}: none, which can be a quiet team")


def check_news_and_rankings(http, report, league):
    import espn_api

    try:
        news = espn_api.get_news(league.key)
    except Exception as e:
        report.fail(league.key, "App: news", f"get_news raised {type(e).__name__}: {e}")
        news = None
    if news is not None:
        if news:
            report.ok(league.key, "App: news", f"{len(news)} articles")
        else:
            report.warn(league.key, "App: news", "no articles")

    if league.rankings:
        url = f"{SITE}/{league.path}/rankings"
        status, data = http.get(url)
        if status != 200 or not isinstance(data, dict):
            report.fail(league.key, "Rankings", f"got {status}", url)
        elif not data.get("rankings"):
            report.warn(league.key, "Rankings", "none, which is normal before a season", url)
        else:
            polls = espn_api.get_rankings(league.key).get("polls") or []
            if not polls:
                report.fail(league.key, "App: rankings", "ESPN has rankings, get_rankings has none", url)
            else:
                report.ok(league.key, "App: rankings", f"{len(polls)} polls", url)

    if league.transactions:
        url = f"{SITE}/{league.path}/transactions?limit=5"
        status, data = http.get(url)
        if status != 200 or not isinstance(data, dict):
            report.fail(league.key, "Transactions", f"got {status}", url)
        elif data.get("transactions") is None:
            report.fail(league.key, "Transactions", "no transactions key", url)
        else:
            report.ok(league.key, "Transactions", f"{len(data['transactions'])} returned", url)


def check_statistics(http, report, league):
    import espn_api

    if league.player_stats:
        try:
            stats = espn_api.get_player_statistics(league.key)
        except Exception as e:
            report.fail(league.key, "App: player statistics", f"raised {type(e).__name__}: {e}")
            stats = None
        if stats is not None:
            invented = invented_names(stats)
            categories = stats.get("player_stats") or []
            if invented:
                report.fail(league.key, "App: player statistics", f"invented data: {first_problems(invented)}")
            elif not categories:
                report.fail(league.key, "App: player statistics", "none, though ESPN has this league's leaders")
            else:
                report.ok(league.key, "App: player statistics", f"{len(categories)} categories")
    if league.team_stats:
        # The iPhone's team statistics. Windows asks team by team, which #94 tracks.
        url = f"{WEB}/{league.path}/statistics/byteam?region=us&lang=en&limit=1"
        status, data = http.get(url)
        if status != 200 or not isinstance(data, dict):
            report.fail(league.key, "Team statistics (iPhone)", f"got {status}", url)
        elif not data.get("teams"):
            report.warn(league.key, "Team statistics (iPhone)", "no teams, possibly the off-season", url)
        else:
            report.ok(league.key, "Team statistics (iPhone)", "as expected", url)


def check_league(http, league):
    report = Report()
    try:
        check_scoreboard(http, report, league)
        event, url = find_recent_final(http, league)
        if event is None:
            report.warn(league.key, "Recent final", f"none in {MONTHS_TO_SEARCH} months, so no game was checked", url)
        else:
            report.ok(league.key, "Recent final", f"{event.get('shortName')} on {event.get('date', '')[:10]}", url)
            check_app_scores(report, league, event)
            check_game(http, report, league, event)
        check_standings(http, report, league)
        check_teams(http, report, league, event)
        check_news_and_rankings(http, report, league)
        check_statistics(http, report, league)
    except Exception as e:  # one league's surprise shouldn't lose the others' results
        report.fail(league.key, "Validator", f"stopped early on {type(e).__name__}: {e}")
    return report


# ---------------------------------------------------------------- everything else

def check_football_calendar(http, report):
    from services import football_calendar

    for key in ("NFL", "NCAAF"):
        try:
            season, season_type, week = football_calendar.get_current_season_week_and_type(key)
        except Exception as e:
            report.fail(key, "App: football calendar", f"raised {type(e).__name__}: {e}")
            continue
        if not week:
            report.fail(key, "App: football calendar", f"no current week: season {season}, type {season_type}")
        else:
            report.ok(key, "App: football calendar", f"{season}, type {season_type}, week {week}")

    # How both apps ask for a week. A date range is what ESPN stopped accepting.
    year = date.today().year
    url = f"{SITE}/football/nfl/scoreboard?dates={year}&week=1&seasontype=2"
    status, data = http.get(url)
    if status != 200 or not isinstance(data, dict):
        report.fail("NFL", "Week query", f"got {status}", url)
    elif not data.get("events"):
        report.warn("NFL", "Week query", "week 1 is empty, normal before a season's schedule is out", url)
    else:
        report.ok("NFL", "Week query", f"week 1 has {len(data['events'])} games", url)

    url = f"{CORE}/football/leagues/nfl/seasons/{year}/types/2/weeks?limit=3"
    status, data = http.get(url)
    if status != 200 or not isinstance(data, dict) or not data.get("items"):
        report.fail("NFL", "Core API: weeks (iPhone)", f"got {status}", url)
    else:
        report.ok("NFL", "Core API: weeks (iPhone)", f"{data.get('count')} weeks", url)


def check_core_leaders(http, report):
    """The iPhone's league leaders."""
    year = date.today().year
    url = f"{CORE}/football/leagues/nfl/seasons/{year}/types/2/leaders"
    status, data = http.get(url)
    if status != 200 or not isinstance(data, dict):
        report.warn("NFL", "Core API: leaders (iPhone)", f"got {status}, possibly before a season starts", url)
    elif not data.get("categories"):
        report.fail("NFL", "Core API: leaders (iPhone)", "no categories", url)
    else:
        report.ok("NFL", "Core API: leaders (iPhone)", f"{len(data['categories'])} categories", url)


def check_golf(http, report):
    import espn_api

    for tour in espn_api.GOLF_TOURS:
        try:
            schedule = espn_api.get_golf_schedule(tour)
            board = espn_api.get_golf_leaderboard(tour)
        except Exception as e:
            report.fail(tour, "App: golf", f"raised {type(e).__name__}: {e}")
            continue
        if not schedule:
            report.fail(tour, "App: golf schedule", "empty")
        else:
            report.ok(tour, "App: golf schedule", f"{len(schedule)} tournaments")
        if board is None:
            report.warn(tour, "App: golf leaderboard", "no tournament on the scoreboard, fine between events")
        elif not board.get("name"):
            report.fail(tour, "App: golf leaderboard", "a tournament with no name")
        else:
            report.ok(tour, "App: golf leaderboard", f"{board['name']}, {len(board.get('players') or [])} players")


def check_mlb_extras(http, report):
    import espn_api

    try:
        race = espn_api.get_mlb_wildcard_standings()
    except Exception as e:
        report.fail("MLB", "App: wild card", f"raised {type(e).__name__}: {e}")
        race = None
    if race is not None:
        if not race.get("AL") or not race.get("NL"):
            report.warn("MLB", "App: wild card", "empty, which can be the off-season")
        else:
            report.ok("MLB", "App: wild card", f"AL {len(race['AL'])}, NL {len(race['NL'])}")

    url = ("https://statsapi.mlb.com/api/v1/stats/leaders?leaderCategories=homeRuns&statGroup=hitting"
           f"&season={date.today().year}&limit=3")
    status, data = http.get(url)
    if status != 200 or not isinstance(data, dict):
        report.fail("MLB Stats API", "Leaders", f"got {status}", url)
    elif "leagueLeaders" not in data:
        report.fail("MLB Stats API", "Leaders", "no leagueLeaders key", url)
    else:
        report.ok("MLB Stats API", "Leaders", "as expected", url)


def check_fantasy(report):
    import espn_api

    try:
        board = espn_api.get_fantasy_cheatsheet(max_rank=50)
    except Exception as e:
        report.fail("Fantasy", "App: cheatsheet", f"raised {type(e).__name__}: {e}")
        return
    players = (board or {}).get("players") or []
    if not players:
        report.fail("Fantasy", "App: cheatsheet", "no players")
    elif not all(p.get("name") for p in players):
        report.fail("Fantasy", "App: cheatsheet", "players with no name")
    else:
        report.ok("Fantasy", "App: cheatsheet", f"{board.get('season')}: {len(players)} players")


def check_draft(http, report):
    import espn_api

    year = date.today().year
    try:
        draft = espn_api.get_draft(year)
    except Exception as e:
        report.fail("NFL", "App: draft", f"raised {type(e).__name__}: {e}")
    else:
        if draft:
            report.ok("NFL", "App: draft", str(year))
        else:
            report.warn("NFL", "App: draft", f"nothing for {year}, normal before a draft")
    url = f"{SITE}/football/nfl/draft?season={year}"
    status, _ = http.get(url)
    if status == 200:
        report.ok("NFL", "Draft (iPhone)", "as expected", url)
    else:
        report.warn("NFL", "Draft (iPhone)", f"got {status}, possibly out of season", url)


def check_world_cup(http, report):
    import espn_api

    try:
        groups = espn_api.get_world_cup_standings("WC2026")
    except Exception as e:
        report.fail("World Cup", "App: standings", f"raised {type(e).__name__}: {e}")
        return
    if groups:
        report.ok("World Cup", "App: standings", f"{len(groups)} groups")
    else:
        report.warn("World Cup", "App: standings", "none, which can be between tournaments")


def check_cfl(http, report):
    for name, url in (("Rounds", "https://cflscoreboard.cfl.ca/json/scoreboard/rounds.json"),
                      ("Squads", "https://cflscoreboard.cfl.ca/json/scoreboard/squads.json")):
        status, data = http.get(url)
        if status != 200 or not data:
            report.fail("CFL (iPhone)", name, f"got {status}", url)
        else:
            report.ok("CFL (iPhone)", name, "as expected", url)


def check_hockey_web_page(http, report):
    """The fuller hockey plays come from the espn.com page. It's a bonus, so never a failure."""
    import espn_api

    event, _ = find_recent_final(http, LEAGUE_KEYS["NHL"])
    if not event:
        return
    try:
        plays = espn_api._fetch_web_gamepackage_plays("hockey/nhl", event["id"])
    except Exception as e:
        report.warn("NHL", "espn.com game page", f"raised {type(e).__name__}: {e}")
        return
    if plays:
        report.ok("NHL", "espn.com game page", f"{len(plays)} plays")
    else:
        report.warn("NHL", "espn.com game page", "no plays. It can block automated requests; the app falls back to the summary")


def check_others(http):
    report = Report()
    for check in (check_football_calendar, check_core_leaders, check_golf, check_mlb_extras, check_draft, check_world_cup,
                  check_cfl, check_hockey_web_page):
        try:
            check(http, report)
        except Exception as e:
            report.fail("Validator", check.__name__, f"stopped early on {type(e).__name__}: {e}")
    try:
        check_fantasy(report)
    except Exception as e:
        report.fail("Validator", "check_fantasy", f"stopped early on {type(e).__name__}: {e}")
    return report


# ------------------------------------------------------------------ the report

def render(report, started, seconds):
    fails = [c for c in report.checks if c.status == FAIL]
    warns = [c for c in report.checks if c.status == WARN]
    verdict = "**Something the apps rely on is broken.**" if fails else "**Nothing the apps rely on is broken.**"
    lines = ["# ESPN and data source check", "",
             f"{started:%Y-%m-%d %H:%M} UTC, {seconds:.0f} seconds.", "", verdict, "",
             f"{report.count(PASS)} passed, {len(warns)} worth a look, {len(fails)} failed.", ""]

    def rows(title, checks):
        if not checks:
            return []
        out = [f"## {title}", "", "| Source | Check | Detail |", "|---|---|---|"]
        for c in checks:
            detail = c.detail.replace("|", "\\|").replace("\n", " ")
            link = f" [request]({c.url})" if c.url else ""
            out.append(f"| {c.source} | {c.name} | {detail}{link} |")
        return out + [""]

    lines += rows("Failed", fails)
    lines += rows("Worth a look", warns)
    lines += rows("Passed", [c for c in report.checks if c.status == PASS])
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check ESPN and other data sources against what the apps rely on.")
    parser.add_argument("--league", action="append", choices=sorted(LEAGUE_KEYS),
                        help="only this league; repeat for more. Leaves out the non-league checks")
    parser.add_argument("--report", help="also write the Markdown report here")
    parser.add_argument("--json", help="also write the results as JSON here")
    args = parser.parse_args(argv)

    started = datetime.now(timezone.utc)
    clock = time.monotonic()
    http = Http()
    leagues = [LEAGUE_KEYS[k] for k in args.league] if args.league else LEAGUES

    report = Report()
    # The app's code prints its progress. This swap is process-wide, so it goes around
    # the whole run rather than each call: threads doing it per call could leave stdout
    # pointing at a dead buffer.
    with contextlib.redirect_stdout(io.StringIO()):
        with ThreadPoolExecutor(max_workers=4) as pool:
            for league_report in pool.map(lambda league: check_league(http, league), leagues):
                report.checks.extend(league_report.checks)
        if not args.league:
            report.checks.extend(check_others(http).checks)

    text = render(report, started, time.monotonic() - clock)
    print(text)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(text)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump([c.__dict__ for c in report.checks], f, indent=1)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text)
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
