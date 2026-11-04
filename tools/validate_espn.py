#!/usr/bin/env python3
"""Check ESPN and the app's other data sources against what both apps rely on.

Nothing documents these feeds, and they change without notice: ESPN began rejecting
`dates=A-B` scoreboard ranges in September 2026, which broke the iPhone's football week
arrows for weeks before anyone noticed. This calls the endpoints the apps use, checks the
shape each one relies on, and runs the real Windows parsers on the live data.

    python tools/validate_espn.py                     everything
    python tools/validate_espn.py --league NCAAM      just one (repeat for more)
    python tools/validate_espn.py --report out.md     also write the report to a file

It opens no windows, so it is safe to run anywhere. It only reads. It exits 1 if anything
FAILed. `.github/workflows/validate-espn.yml` runs it on demand and every night.

What the results mean:
    PASS  it did what the apps need
    WARN  worth a look, but not proof of a break
    FAIL  something the apps rely on is gone or wrong, or our parser got it wrong

What's covered: full depth for the leagues in LEAGUES, a scoreboard check for every other
league either app names (espn_api.LEAGUES and the iPhone's Sport.swift), and the other
sources below. It doesn't test whether the iPhone can decode what it gets. That's
iOS/SportsScoresApp/SportsScoresTests, which can read payloads saved with --save-payloads.

How it tells broken from quiet:
- A league is in season if it has played in the last IN_SEASON_DAYS. In season, an empty
  answer is a FAIL. Out of season, it's a WARN. An error status is a FAIL either way.
- Every league plays within MONTHS_TO_SEARCH, so finding no final means something broke.
- One odd game isn't a feed break: if a game's shape is wrong, two more are checked first.
- A blip isn't news: requests are retried, and a league that fails is run again before
  it counts.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
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

from exceptions import ApiError  # noqa: E402

SITE = "https://site.api.espn.com/apis/site/v2/sports"
STANDINGS = "https://site.api.espn.com/apis/v2/sports"
CORE = "https://sports.core.api.espn.com/v2/sports"
WEB = "https://site.web.api.espn.com/apis/common/v3/sports"

FOOTBALL, BASKETBALL, HOCKEY, BASEBALL, SOCCER = "football", "basketball", "hockey", "baseball", "soccer"
PASS, WARN, FAIL = "PASS", "WARN", "FAIL"

INVENTED = ("sample player", "sample stat", "team1")  # the app's old made-up fallbacks
MONTHS_TO_SEARCH = 14
IN_SEASON_DAYS = 14
SCHEDULE_WINDOW_DAYS = 30
FINALS_TO_TRY = 3
# A dead host costs minutes per request. Past this, requests stop waiting and fail, so the
# run still ends with a report. The workflow's own limit is higher.
DEADLINE_SECONDS = 15 * 60
NOT_PLAYED = ("STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_CANCELLED", "STATUS_FORFEIT")
# A World Cup match from the core API, which is where the iPhone gets match numbers.
WORLD_CUP_MATCH = "760512"
# What the iPhone asks the core API for. ESPN has no statistics for some season types, such
# as the NBA's preseason and play-in, so one season type on its own proves nothing.
CORE_SEASON_TYPES = (2, 3, 1)
# ESPN's /statistics fails often, mostly for college basketball, with this message on a 404.
# The failure can stay cached for up to 30 seconds, so the pause has to outlast that.
STATISTICS_TRIES = 3
STATISTICS_PAUSE = 35
STATISTICS_BLIP = "Failed to retrieve league stats"


@dataclass(frozen=True)
class League:
    key: str
    path: str
    family: str
    scoreboard_params: str = ""
    # What ESPN is known to offer here, so that its absence isn't reported as a break.
    box_score: bool = True
    plays: bool = True
    rankings: bool = False
    transactions: bool = True
    player_stats: bool = True
    player_stats_gap: str = ""  # the app can't read these today, and this says why
    team_stats: bool = True
    core_leaders: bool = True
    # espn_api's team schedule only looks this far either side of today for these leagues.
    schedule_window: bool = False
    # ESPN has none of these here, so an empty answer is the normal one.
    team_records: bool = True
    rosters: bool = True
    # What the app asks standings for, and what the answer has to hold to be the whole league.
    standings_params: str = ""
    standings_min_teams: int = 0
    standings_groupings: tuple = ()  # the levels above the conferences, each with teams under it

    @property
    def is_college(self) -> bool:
        return self.key.startswith("NCAA")

    @property
    def core_path(self) -> str:
        sport, name = self.path.split("/", 1)
        return f"{sport}/leagues/{name}"


_COLLEGE_HOCKEY = dict(box_score=False, plays=False, rankings=True, transactions=False, player_stats=False,
                       team_stats=False, core_leaders=False, team_records=False, rosters=False)
_SOCCER = dict(plays=False, transactions=False, player_stats=False, team_stats=False, core_leaders=False,
               schedule_window=True)

LEAGUES = [
    League("NFL", "football/nfl", FOOTBALL),
    League("NCAAF", "football/college-football", FOOTBALL, "groups=90&limit=400", rankings=True, transactions=False,
           standings_params="group=90", standings_min_teams=200, standings_groupings=("FBS", "FCS")),
    League("NBA", "basketball/nba", BASKETBALL,
           player_stats_gap="ESPN's /statistics has no leaders for the NBA, so Windows shows none (#95)"),
    League("WNBA", "basketball/wnba", BASKETBALL, schedule_window=True),
    League("NCAAM", "basketball/mens-college-basketball", BASKETBALL, "groups=50&limit=400",
           rankings=True, transactions=False),
    League("NCAAWB", "basketball/womens-college-basketball", BASKETBALL, "groups=50&limit=400",
           rankings=True, transactions=False),
    League("NHL", "hockey/nhl", HOCKEY),
    League("NCAAH", "hockey/mens-college-hockey", HOCKEY, **_COLLEGE_HOCKEY),
    League("NCAAWH", "hockey/womens-college-hockey", HOCKEY, **_COLLEGE_HOCKEY),
    League("MLB", "baseball/mlb", BASEBALL),
    League("EPL", "soccer/eng.1", SOCCER, **_SOCCER),
    League("MLS", "soccer/usa.1", SOCCER, **_SOCCER),
]
LEAGUE_KEYS = {league.key: league for league in LEAGUES}

# The app maps teams to divisions itself. A team it doesn't know lands outside them, as Utah did.
EXPECTED_DIVISIONS = {"NFL": 8, "NBA": 6, "NHL": 4, "MLB": 6, "WNBA": 2}
# In Sport.swift, but the iPhone gets this league from the CFL's own feed rather than ESPN.
NOT_FROM_ESPN = {"football/cfl"}


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

    def seasonal(self, in_season, source, name, detail, url=""):
        """Nothing where there should be something. Only a break if the season is on."""
        if in_season:
            self.fail(source, name, f"{detail}, in season", url)
        else:
            self.warn(source, name, f"{detail}, out of season", url)

    def count(self, status):
        return sum(1 for c in self.checks if c.status == status)

    @property
    def failed(self):
        return self.count(FAIL) > 0


class Http:
    """GET with retries, because a single 503 from ESPN isn't news."""

    def __init__(self, attempts=3, pause=4.0, timeout=30, save_dir=None, deadline=None):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "Mozilla/5.0 (Scores data validator)"
        self.attempts, self.pause, self.timeout = attempts, pause, timeout
        self.save_dir = save_dir
        self.deadline = deadline

    def get(self, url, attempts=None, timeout=None):
        """(status code or error text, parsed JSON or None)."""
        outcome = "no attempt"
        for attempt in range(attempts or self.attempts):
            if self.deadline is not None and time.monotonic() > self.deadline:
                return "out of time", None
            if attempt:
                time.sleep(self.pause * attempt)
            try:
                response = self.session.get(url, timeout=timeout or self.timeout)
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

    def save(self, kind, league_key, data):
        """Keep a payload for the iPhone's decode tests to read."""
        if not self.save_dir or not isinstance(data, dict):
            return
        os.makedirs(self.save_dir, exist_ok=True)
        with open(os.path.join(self.save_dir, f"{kind}-{league_key}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f)


def install_retrying_get(deadline=None):
    """Give the app's own requests the same patience as ours. They go through requests.get,
    and turn a non-200 into an empty result, so one 503 would read as "the feed has nothing"."""
    original = requests.get

    def retrying_get(url, **kwargs):
        response = None
        for attempt in range(3):
            if deadline is not None and time.monotonic() > deadline:
                raise requests.Timeout("the validator ran out of time")
            if attempt:
                time.sleep(4.0 * attempt)
            try:
                response = original(url, **kwargs)
            except requests.RequestException:
                if attempt == 2:
                    raise
                continue
            if response.status_code < 500 and response.status_code != 429:
                return response
        return response

    requests.get = retrying_get
    return original


def scoreboard_url(league, dates=None):
    parts = [league.scoreboard_params] if league.scoreboard_params else []
    if dates:
        parts.append(f"dates={dates}")
    return f"{SITE}/{league.path}/scoreboard" + ("?" + "&".join(parts) if parts else "")


def first_problems(problems, limit=3):
    extra = f" and {len(problems) - limit} more" if len(problems) > limit else ""
    return "; ".join(str(p) for p in problems[:limit]) + extra


# ---------------------------------------------------------------- payload checks
# Pure: each takes a parsed payload and returns a list of problems.

def scoreboard_problems(data):
    problems = []
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        return ["no events list"]
    for event in data["events"]:
        if not event:
            continue  # ESPN leaves a literal {} in some lists. check_scoreboard mentions it.
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
        competition = competitions[0]
        if not ((competition.get("status") or {}).get("type") or {}).get("name"):
            problems.append(f"{label}: no competition status, which get_scores reads")
        competitors = competition.get("competitors") or []
        if len(competitors) != 2:
            problems.append(f"{label}: {len(competitors)} competitors")
            continue
        for competitor in competitors:
            team = competitor.get("team") or {}
            if not team.get("displayName") or not team.get("abbreviation"):
                problems.append(f"{label}: a team with no displayName or abbreviation")
            if competitor.get("homeAway") not in ("home", "away"):
                problems.append(f"{label}: homeAway is {competitor.get('homeAway')!r}")
            if status_type.get("state") == "post" and status_type.get("name") not in NOT_PLAYED and "score" not in competitor:
                problems.append(f"{label}: a finished game's team has no score")
    return problems


def calendar_problems(data):
    """Football's week arrows, on both apps, come from the undated scoreboard's calendar."""
    leagues = (data or {}).get("leagues") or []
    if not leagues:
        return ["no leagues block"]
    calendar = leagues[0].get("calendar")
    if not calendar:
        return ["leagues[0].calendar is empty"]
    if not any(isinstance(entry, dict) and entry.get("entries") for entry in calendar):
        return ["no season type in the calendar has week entries"]
    return []


def _athlete_has_name(athlete):
    info = athlete.get("athlete") or {}
    return bool(info.get("displayName") or info.get("shortName"))


def box_score_problems(box, league):
    """What ESPN's box score must look like for box_score.py and BoxScoreTables.swift."""
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
                problems.append(f"baseball team stats are no longer nested by category: found {sorted(map(str, names))}")
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
        problems.append(f"expected groups are gone: {', '.join(sorted(missing))} "
                        f"(found {', '.join(sorted(map(str, seen_groups)))})")
    return problems


def _usable(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value) < 1_000_000


def play_problems(summary, league):
    """Plays or drives, including what play audio reads."""
    if not league.plays:
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
        coordinates = [p["coordinate"] for p in plays if isinstance(p.get("coordinate"), dict)]
        located = [c for c in coordinates if _usable(c.get("x")) and _usable(c.get("y"))]
        if not located:
            problems.append("no play has a usable coordinate, so play audio has nothing")
        x_limit, y_limit = (60, 110) if league.family == BASKETBALL else (110, 60)
        wild = [c for c in located if abs(c["x"]) > x_limit or abs(c["y"]) > y_limit]
        if wild:
            problems.append(f"{len(wild)} coordinates outside the court or rink, such as {wild[0]}")
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


def standings_coverage_problems(data, league):
    """What's missing for this to be the whole league. Without group=, ESPN sends FBS alone."""
    problems = []
    count = len(standings_entries(data))
    if count < league.standings_min_teams:
        problems.append(f"{count} teams, expected at least {league.standings_min_teams}")
    for grouping in league.standings_groupings:
        node = next((n for n in _standing_nodes(data or {}) if n.get("name") == grouping), {})
        conferences = [c for c in node.get("children") or [] if standings_entries(c)]
        if not conferences:
            problems.append(f"no {grouping} conference has teams")
    return problems


def _total_stat(entry):
    return next((s for s in entry.get("stats") or [] if s.get("type") == "total"), None)


def standings_problems(data, league):
    problems = []
    for entry in standings_entries(data):
        name = (entry.get("team") or {}).get("displayName")
        if not name:
            problems.append("an entry has no team.displayName")
        stats = entry.get("stats") or []
        if not stats:
            problems.append(f"{name}: no stats")
            continue
        if league.family == SOCCER:
            continue
        total = _total_stat(entry)
        if total is None:
            problems.append(f"{name}: no stat with type 'total', the overall record")
        elif not parse_record(total.get("summary") or total.get("displayValue")):
            problems.append(f"{name}: can't read the overall record {total.get('summary')!r}")
    return problems


def parse_record(text):
    """(wins, losses) from "7-1" or "10-4-1", or None if it isn't a record."""
    pieces = str(text or "").split("-")
    if len(pieces) < 2 or not all(p.strip().isdigit() for p in pieces):
        return None
    return int(pieces[0]), int(pieces[1])


def standings_row_problems(entries, rows):
    """The app's standings against ESPN's overall records: every team, wins and losses."""
    by_name = {r.get("team_name"): r for r in rows}
    missing, wrong = [], []
    for entry in entries:
        name = (entry.get("team") or {}).get("displayName")
        if name not in by_name:
            missing.append(name)
            continue
        total = _total_stat(entry) or {}
        record = parse_record(total.get("summary") or total.get("displayValue"))
        if record and (by_name[name].get("wins"), by_name[name].get("losses")) != record:
            wrong.append(f"{name} shows {by_name[name].get('wins')}-{by_name[name].get('losses')}, "
                         f"ESPN's record is {total.get('summary')}")
    return missing, wrong


def rankings_problems(polls):
    if not polls:
        return ["no polls"]
    problems = []
    for poll in polls:
        ranks = poll.get("ranks") or []
        if not ranks:
            problems.append(f"{poll.get('name')}: no ranks")
            continue
        for rank in ranks:
            team = rank.get("team") or {}
            if not (team.get("location") or team.get("name") or team.get("nickname")) or not team.get("abbreviation"):
                problems.append(f"{poll.get('name')}: a rank has no team name or abbreviation")
                break
            if rank.get("current") is None:
                problems.append(f"{poll.get('name')}: a rank has no current position")
                break
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


def game_problems(summary, league):
    """Everything wrong with one game's summary, by the check it belongs to."""
    return {"Game summary": summary_header_problems(summary),
            "Box score shape": box_score_problems(summary.get("boxscore"), league),
            "Plays": play_problems(summary, league)}


def invented_names(value):
    """Any text that came from the made-up fallbacks the app used to have."""
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


def is_played_final(event, team_ids=None):
    """Finished and actually played. Soccer says STATUS_FULL_TIME, so go by state. A postponed
    game is also state "post". `team_ids` rules out games between sides that aren't in the
    league, such as the NFL's Pro Bowl, which has no box score or drives."""
    status_type = (event.get("status") or {}).get("type") or {}
    if status_type.get("state") != "post" or not status_type.get("completed"):
        return False
    if status_type.get("name") in NOT_PLAYED:
        return False
    competitors = (event.get("competitions") or [{}])[0].get("competitors") or []
    if len(competitors) != 2:
        return False
    if team_ids:
        return all(str((c.get("team") or {}).get("id")) in team_ids for c in competitors)
    return True


def espn_date(iso):
    """The day ESPN files a game under, which is its Eastern date. A 9 PM Eastern game is
    tomorrow in UTC, and this runs on a machine in UTC."""
    moment = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return moment.astimezone(pytz.timezone("America/New_York")).date()


def days_since(event, today=None):
    return ((today or date.today()) - espn_date(event["date"])).days


def apps_league_paths():
    """Every league path either app names."""
    import espn_api
    paths = set(espn_api.LEAGUES.values())
    swift = os.path.join(ROOT, "iOS", "SportsScoresApp", "SportsScores", "Models", "Sport.swift")
    if os.path.exists(swift):
        with open(swift, encoding="utf-8") as f:
            paths |= set(re.findall(r'"((?:baseball|basketball|football|golf|hockey|racing|soccer)/[\w.-]+)"', f.read()))
    return paths - NOT_FROM_ESPN


# ------------------------------------------------------------------ finding games

@dataclass
class Finals:
    events: list
    url: str
    bad_statuses: dict


def find_recent_finals(http, league, team_ids=None, today=None):
    """The most recent finished games, however far back, from one scoreboard."""
    today = today or date.today()
    candidates = [(today - timedelta(days=n)).strftime("%Y%m%d") for n in range(0, 4)]
    year, month = today.year, today.month
    for _ in range(MONTHS_TO_SEARCH):
        candidates.append(f"{year}{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    url, bad = "", {}
    for dates in candidates:
        url = scoreboard_url(league, dates)
        # Quick: this is up to 18 requests, and a hang here shouldn't eat the whole run.
        status, data = http.get(url, attempts=2, timeout=20)
        if status != 200 or not isinstance(data, dict):
            bad[str(status)] = bad.get(str(status), 0) + 1
            continue
        finals = [e for e in data.get("events") or [] if is_played_final(e, team_ids)]
        if finals:
            finals.sort(key=lambda e: e.get("date", ""), reverse=True)
            http.save("scoreboard", league.key, data)
            return Finals(finals[:FINALS_TO_TRY], url, bad)
    return Finals([], url, bad)


# ---------------------------------------------------------------- per league

def check_team_list(http, report, league):
    url = f"{SITE}/{league.path}/teams?limit=1000"
    status, data = http.get(url)
    if status != 200 or not isinstance(data, dict):
        report.fail(league.key, "Teams", f"got {status}", url)
        return set()
    try:
        teams = data["sports"][0]["leagues"][0]["teams"]
    except (KeyError, IndexError, TypeError):
        report.fail(league.key, "Teams", "sports[0].leagues[0].teams is gone", url)
        return set()
    if not teams:
        report.fail(league.key, "Teams", "no teams", url)
        return set()
    report.ok(league.key, "Teams", f"{len(teams)} teams", url)
    return {str((t.get("team") or {}).get("id")) for t in teams}


def check_scoreboard(http, report, league):
    url = scoreboard_url(league)
    status, data = http.get(url)
    if status != 200:
        report.fail(league.key, "Scoreboard", f"got {status}", url)
        return
    # What the apps open on, with its scheduled and live games and football's calendar. The
    # one find_recent_finals saves is all finals.
    http.save("scoreboard", f"{league.key}-now", data)
    problems = scoreboard_problems(data)
    if problems:
        report.fail(league.key, "Scoreboard", first_problems(problems), url)
    else:
        count = len(data["events"])
        report.ok(league.key, "Scoreboard", f"{count} games now" if count else "no games right now", url)
        if not all(data["events"]):
            report.warn(league.key, "Scoreboard", "a blank event in the list, which both apps should skip", url)
    if league.family == FOOTBALL:
        problems = calendar_problems(data)
        if problems:
            report.fail(league.key, "Season calendar", first_problems(problems), url)
        else:
            report.ok(league.key, "Season calendar", "as expected", url)


def check_app_scores(report, league, event):
    """The app lists the game the feed has on that date, and can read every row."""
    import espn_api
    from models.game import GameData

    day = espn_date(event["date"])
    try:
        if league.family == FOOTBALL:
            week = (event.get("week") or {}).get("number")
            season = (event.get("season") or {}).get("year")
            season_type = (event.get("season") or {}).get("type")
            if not week:
                report.fail(league.key, "App: game list", f"final {event['id']} has no week number")
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


def check_games(http, report, league, finals, in_season):
    """The shape of a game's summary. One odd game isn't a broken feed, so if the first has
    a problem the others get a say. Returns (event, summary) for a game that read well."""
    results, chosen = [], None
    for event in finals.events:
        url = f"{SITE}/{league.path}/summary?event={event['id']}"
        status, summary = http.get(url)
        if status != 200 or not isinstance(summary, dict):
            problems = {"Game summary": [f"got {status}"]}
            summary = None
        else:
            problems = game_problems(summary, league)
        results.append((event, url, summary, problems))
        if not any(problems.values()):
            chosen = (event, url, summary)
            break

    failing = [r for r in results if any(r[3].values())]
    broken = len(failing) > len(results) / 2
    for name in ("Game summary", "Box score shape", "Plays"):
        bad = [(event, url, problems[name]) for event, url, _, problems in results if problems.get(name)]
        if bad and broken:
            event, url, problems = bad[0]
            report.fail(league.key, name,
                        f"{len(bad)} of {len(results)} recent finals: {event['id']} ({event.get('shortName')}): "
                        f"{first_problems(problems)}", url)
        elif bad:
            event, url, problems = bad[0]
            report.warn(league.key, name, f"odd game {event['id']} ({event.get('shortName')}), but not "
                                          f"others: {first_problems(problems)}", url)
        elif name == "Plays" and not league.plays:
            continue
        else:
            event, url = results[0][:2]
            detail = f"final {event['id']} ({event.get('shortName')})"
            if name == "Box score shape" and not league.box_score:
                detail = "ESPN sends none, as expected"
            report.ok(league.key, name, detail, url)

    if not chosen:
        return None
    event, url, summary = chosen
    if not league.box_score and any(t.get("statistics") for t in (summary.get("boxscore") or {}).get("teams", [])):
        report.warn(league.key, "Box score shape", "ESPN now sends box scores here. The apps could show them", url)
    if not (summary.get("gameInfo") or {}).get("venue"):
        report.warn(league.key, "Venue", f"gameInfo.venue is missing on final {event['id']}", url)
    # Lines come and go, and college finals often have none, so only a recent pro game says anything.
    if in_season and not league.is_college and league.family != SOCCER and not (summary.get("pickcenter") or summary.get("odds")):
        report.warn(league.key, "Odds", f"no pickcenter or odds on final {event['id']}", url)
    http.save("summary", league.key, summary)
    return event, summary


def check_app_game(report, league, event, summary):
    """The real parsers, on this game."""
    import espn_api
    from box_score import build_box_tables
    from play_geometry import audio_params, has_coordinate, league_family

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
                report.ok(league.key, "App: box score",
                          f"{len(tables)} tables, {sum(len(t.rows) for t in tables)} rows, every player listed")
        elif tables:
            report.warn(league.key, "App: box score", f"expected none, got {len(tables)} tables")
        else:
            report.ok(league.key, "App: box score", "no box score offered, as expected")

    if league.plays and league_family(league.key):
        plays = summary.get("plays") or []
        try:
            located = [p for p in plays if has_coordinate(p, league.key)]
            sounds = [audio_params(league.key, p["coordinate"]["x"], p["coordinate"]["y"]) for p in located]
        except Exception as e:
            report.fail(league.key, "App: play audio", f"raised {type(e).__name__}: {e}")
        else:
            if not located:
                report.fail(league.key, "App: play audio", f"no play has a location, of {len(plays)}")
            elif not all(sounds):
                report.fail(league.key, "App: play audio", "a located play has no sound")
            else:
                report.ok(league.key, "App: play audio", f"{len(located)} of {len(plays)} plays have a location")

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


def check_standings(http, report, league, in_season):
    import espn_api

    url = f"{STANDINGS}/{league.path}/standings"
    if league.standings_params:
        url += f"?{league.standings_params}"
    status, data = http.get(url)
    if status != 200 or not isinstance(data, dict):
        report.fail(league.key, "Standings", f"got {status}", url)
        return
    entries = standings_entries(data)
    if not entries:
        report.seasonal(in_season, league.key, "Standings", "no entries anywhere in the response", url)
        return
    problems = standings_problems(data, league) + standings_coverage_problems(data, league)
    if problems:
        report.fail(league.key, "Standings", first_problems(problems), url)
        return
    report.ok(league.key, "Standings", f"{len(entries)} teams", url)
    http.save("standings", league.key, data)

    if league.family == SOCCER:
        report.ok(league.key, "App: standings", "not checked: Windows has no soccer standings")
        return
    try:
        rows = espn_api.get_standings(league.key)
    except Exception as e:
        report.fail(league.key, "App: standings", f"get_standings raised {type(e).__name__}: {e}")
        return
    if not rows:
        report.fail(league.key, "App: standings", "get_standings returned nothing, and ESPN has data")
        return
    missing, wrong = standings_row_problems(entries, rows)
    divisions = {r.get("division") for r in rows}
    expected = EXPECTED_DIVISIONS.get(league.key)
    if missing:
        report.fail(league.key, "App: standings", f"{len(missing)} of {len(entries)} teams missing: {first_problems(missing)}")
    elif wrong:
        report.fail(league.key, "App: standings", f"{len(wrong)} wrong records: {first_problems(wrong)}")
    elif expected and len(divisions) != expected:
        report.fail(league.key, "App: standings", f"{len(divisions)} divisions, expected {expected}: {sorted(map(str, divisions))}")
    elif divisions & set(league.standings_groupings):
        report.fail(league.key, "App: standings", f"a conference is named {sorted(divisions & set(league.standings_groupings))}")
    else:
        report.ok(league.key, "App: standings", f"{len(rows)} teams, every record matches ESPN's")


def check_team_hub(http, report, league, event, in_season):
    import espn_api

    competitor = event["competitions"][0]["competitors"][0]
    team_id = str((competitor.get("team") or {}).get("id", ""))
    name = (competitor.get("team") or {}).get("displayName")
    if not team_id:
        report.fail(league.key, "Team hub", f"final {event['id']}'s team has no id")
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
        elif info.get("record_overall"):
            report.ok(league.key, "App: team info", f"{name}, {info['record_overall']}")
        elif league.team_records:
            report.seasonal(in_season, league.key, "App: team info", f"{name} has no overall record")
        else:
            report.ok(league.key, "App: team info", f"{name}. ESPN has no team records in this league")

    # The app turns an error into an empty list, so ask ESPN directly first.
    url = f"{SITE}/{league.path}/teams/{team_id}/roster"
    status, raw = http.get(url)
    if status != 200:
        report.fail(league.key, "Roster", f"got {status}", url)
    else:
        roster = checked("App: roster", espn_api.get_team_roster, league.key, team_id)
        if roster is not None:
            decimals = [p["height"] for p in roster if "." in str(p.get("height", ""))]
            nameless = [p for p in roster if not p.get("name")]
            if decimals or nameless:
                report.fail(league.key, "App: roster",
                            f"{len(decimals)} decimal heights such as {decimals[:1]}, {len(nameless)} with no name", url)
            elif roster:
                report.ok(league.key, "App: roster", f"{len(roster)} players", url)
            elif isinstance(raw, dict) and raw.get("athletes"):
                report.fail(league.key, "App: roster", f"ESPN has {name}'s roster, and the app read nothing", url)
            elif league.rosters:
                report.seasonal(in_season, league.key, "App: roster", f"{name} has an empty roster", url)
            else:
                report.ok(league.key, "App: roster", f"{name} has none. ESPN has few rosters in this league", url)

    schedule = checked("App: schedule", espn_api.get_team_schedule, league.key, team_id)
    if schedule is not None:
        reachable = not league.schedule_window or days_since(event) <= SCHEDULE_WINDOW_DAYS
        if schedule:
            report.ok(league.key, "App: schedule", f"{len(schedule)} games")
        elif reachable:
            report.fail(league.key, "App: schedule", f"{name} has no games, though it played recently")
        else:
            report.warn(league.key, "App: schedule",
                        f"{name} has none within {SCHEDULE_WINDOW_DAYS} days, the most this path looks (#71)")

    url = f"{SITE}/{league.path}/news?team={team_id}"
    status, raw = http.get(url)
    if status != 200:
        report.fail(league.key, "Team news", f"got {status}", url)
    else:
        news = checked("App: team news", espn_api.get_team_news, league.key, team_id)
        if news:
            report.ok(league.key, "App: team news", f"{len(news)} articles", url)
        elif news is not None and isinstance(raw, dict) and raw.get("articles"):
            report.fail(league.key, "App: team news", f"ESPN has news for {name}, and the app read nothing", url)
        elif news is not None:
            report.warn(league.key, "App: team news", f"{name} has none, which can be a quiet team", url)


def check_news(http, report, league):
    import espn_api

    url = f"{SITE}/{league.path}/news"
    status, data = http.get(url)
    if status != 200 or not isinstance(data, dict):
        report.fail(league.key, "News", f"got {status}", url)
        return
    if not data.get("articles"):
        report.fail(league.key, "News", "no articles, and every league has some in any month", url)
        return
    try:
        news = espn_api.get_news(league.key)
    except Exception as e:
        report.fail(league.key, "App: news", f"get_news raised {type(e).__name__}: {e}")
        return
    if news:
        report.ok(league.key, "App: news", f"{len(news)} articles", url)
    else:
        report.fail(league.key, "App: news", "get_news has none, and ESPN does", url)


def check_rankings(http, report, league, in_season):
    import espn_api

    url = f"{SITE}/{league.path}/rankings"
    status, data = http.get(url)
    if status != 200 or not isinstance(data, dict):
        report.fail(league.key, "Rankings", f"got {status}", url)
        return
    if not data.get("rankings"):
        report.seasonal(in_season, league.key, "Rankings", "no polls", url)
        return
    try:
        polls = espn_api.get_rankings(league.key).get("polls") or []
    except Exception as e:
        report.fail(league.key, "App: rankings", f"get_rankings raised {type(e).__name__}: {e}")
        return
    problems = rankings_problems(polls)
    if problems:
        report.fail(league.key, "App: rankings", first_problems(problems), url)
    else:
        report.ok(league.key, "App: rankings", f"{len(polls)} polls, every rank has a team", url)


def check_transactions(http, report, league):
    import espn_api

    url = f"{SITE}/{league.path}/transactions?limit=5"
    status, data = http.get(url)
    if status != 200 or not isinstance(data, dict):
        report.fail(league.key, "Transactions", f"got {status}", url)
    elif data.get("transactions"):
        try:
            rows, _ = espn_api.get_transactions(league.key, limit=5)
        except Exception as e:
            report.fail(league.key, "App: transactions", f"raised {type(e).__name__}: {e}", url)
        else:
            if rows and all(r.get("description") for r in rows):
                report.ok(league.key, "App: transactions", f"{len(rows)} read", url)
            else:
                report.fail(league.key, "App: transactions", f"{len(rows)} rows, some with no description, and ESPN has data", url)
    elif "transactions" in data:
        report.warn(league.key, "Transactions", "an empty list right now", url)
    elif data.get("count") == 0:
        report.warn(league.key, "Transactions", "none right now", url)
    else:
        report.fail(league.key, "Transactions", "no transactions key", url)
    if league.key == "NFL":
        # The iPhone filters these by date. Unlike the scoreboard, this still takes a range.
        today = date.today()
        url = (f"{SITE}/{league.path}/transactions?limit=1&dates="
               f"{(today - timedelta(days=30)).strftime('%Y%m%d')}-{today.strftime('%Y%m%d')}")
        status, _ = http.get(url)
        if status == 200:
            report.ok(league.key, "Transactions by date (iPhone)", "takes a date range", url)
        else:
            report.fail(league.key, "Transactions by date (iPhone)", f"got {status}, so the date filter is broken", url)


def check_statistics(http, report, league, event, in_season):
    import espn_api

    if league.player_stats_gap:
        report.warn(league.key, "App: player statistics", league.player_stats_gap)
    elif league.player_stats:
        # ESPN's blip comes in spells that can outlast the app's own retries, so nothing is only
        # nothing if it lasts. Only the last try says why: an earlier blip mustn't excuse a parser
        # that then reads nothing from a good answer, or a broken app could close its own alarm.
        stats, tries, app_said_blip, ever_blipped = None, 0, False, False
        try:
            for tries in range(1, STATISTICS_TRIES + 1):
                app_said_blip = False
                try:
                    stats = espn_api.get_player_statistics(league.key)
                except ApiError:
                    stats, app_said_blip, ever_blipped = {"player_stats": []}, True, True
                if stats.get("player_stats"):
                    break
                if tries < STATISTICS_TRIES:
                    time.sleep(STATISTICS_PAUSE)
        except Exception as e:
            report.fail(league.key, "App: player statistics", f"raised {type(e).__name__}: {e}")
            stats = None
        if stats is not None:
            invented = invented_names(stats)
            categories = stats.get("player_stats") or []
            if invented:
                report.fail(league.key, "App: player statistics", f"invented data: {first_problems(invented)}")
            elif categories and tries > 1:
                report.warn(league.key, "App: player statistics",
                            f"{len(categories)} categories on try {tries}. " +
                            ("ESPN's /statistics failed before that, and a user would have been told to try again"
                             if ever_blipped else "It came back empty before that, and a user would have seen none"))
            elif categories:
                report.ok(league.key, "App: player statistics", f"{len(categories)} categories")
            else:
                url = f"{SITE}/{league.path}/statistics"
                _, raw = http.get(url)
                if app_said_blip or (isinstance(raw, dict) and raw.get("message") == STATISTICS_BLIP):
                    report.warn(league.key, "App: player statistics",
                                f"ESPN kept saying \"{STATISTICS_BLIP}\" over {STATISTICS_TRIES} tries, "
                                "and a user would have been told to try again", url)
                elif isinstance(raw, dict) and (raw.get("stats") or {}).get("categories"):
                    report.fail(league.key, "App: player statistics", "ESPN has them, and the app read nothing", url)
                else:
                    report.seasonal(in_season, league.key, "App: player statistics",
                                    f"no categories in {STATISTICS_TRIES} tries", url)

    if league.team_stats:
        # The iPhone's team statistics. Windows asks team by team, which #94 tracks.
        url = f"{WEB}/{league.path}/statistics/byteam?region=us&lang=en&limit=1"
        status, data = http.get(url)
        if status != 200 or not isinstance(data, dict):
            report.fail(league.key, "Team statistics (iPhone)", f"got {status}", url)
        elif data.get("teams"):
            report.ok(league.key, "Team statistics (iPhone)", "as expected", url)
        else:
            report.seasonal(in_season, league.key, "Team statistics (iPhone)", "no teams", url)

    if league.core_leaders:
        check_core_statistics(http, report, league, event, in_season)


def check_core_stats(http, report, league, year, name, tail, read):
    """Ask as the iPhone does: this season and last, a season type at a time. Last season
    is what a team with no games on record yet shows. `read` finds the categories."""
    answers = []
    for season in (year, year - 1):
        for season_type in CORE_SEASON_TYPES:
            url = f"{CORE}/{league.core_path}/seasons/{season}/types/{season_type}/{tail}"
            status, data = http.get(url)
            categories = read(data) if status == 200 and isinstance(data, dict) else None
            if categories:
                report.ok(league.key, name, f"{season}, season type {season_type}: {len(categories)} categories", url)
                return True
            answers.append(status)
    return answers


def check_core_statistics(http, report, league, event, in_season):
    year = (event.get("season") or {}).get("year")
    team_id = (event["competitions"][0]["competitors"][0].get("team") or {}).get("id")
    if not (year and team_id):
        report.fail(league.key, "Core API (iPhone)", f"final {event['id']} has no season or team id")
        return
    for name, tail, read in (
            ("Core API: leaders (iPhone)", "leaders", lambda d: d.get("categories")),
            ("Core API: team statistics (iPhone)", f"teams/{team_id}/statistics",
             lambda d: (d.get("splits") or {}).get("categories"))):
        answers = check_core_stats(http, report, league, year, name, tail, read)
        if answers is not True:
            report.seasonal(in_season, league.key, name,
                            f"no categories in {year} or {year - 1}, with answers {sorted(set(map(str, answers)))}",
                            f"{CORE}/{league.core_path}/seasons/{year}/types/2/{tail}")


def check_league(http, league):
    """(report, whether it's in season)."""
    report, in_season = Report(), False
    try:
        # Pro leagues only: college games routinely include sides outside the team list.
        team_ids = check_team_list(http, report, league)
        check_scoreboard(http, report, league)
        finals = find_recent_finals(http, league, None if league.is_college else team_ids)
        event = None
        if not finals.events:
            bad = f" Errors along the way: {finals.bad_statuses}." if finals.bad_statuses else ""
            report.fail(league.key, "Recent final",
                        f"none in {MONTHS_TO_SEARCH} months, and every league plays in that time.{bad}", finals.url)
        else:
            event = finals.events[0]
            in_season = days_since(event) <= IN_SEASON_DAYS
            problems = scoreboard_problems({"events": finals.events})
            if problems:
                report.fail(league.key, "Recent final", first_problems(problems), finals.url)
            else:
                report.ok(league.key, "Recent final", f"{event.get('shortName')} on {event.get('date', '')[:10]}", finals.url)
            # A refused date is a break even if an earlier one still worked. It's how the
            # September change looked.
            refused = {k: n for k, n in finals.bad_statuses.items() if k.isdigit() and int(k) < 500 and k != "429"}
            if refused:
                report.fail(league.key, "Dated scoreboard", f"ESPN refused dated queries: {refused}", finals.url)
            elif finals.bad_statuses:
                report.warn(league.key, "Dated scoreboard", f"some dated queries failed: {finals.bad_statuses}", finals.url)
            check_app_scores(report, league, event)
            chosen = check_games(http, report, league, finals, in_season)
            if chosen:
                check_app_game(report, league, *chosen)
        check_standings(http, report, league, in_season)
        if event:
            check_team_hub(http, report, league, event, in_season)
        check_news(http, report, league)
        if league.rankings:
            check_rankings(http, report, league, in_season)
        if league.transactions:
            check_transactions(http, report, league)
        if event:
            check_statistics(http, report, league, event, in_season)
    except Exception as e:  # one league's surprise shouldn't lose the others' results
        report.fail(league.key, "Validator", f"stopped early on {type(e).__name__}: {e}")
    return report, in_season


def check_league_twice(http, league):
    """A failure gets one more try before it counts, since the feeds do blip."""
    report, in_season = check_league(http, league)
    if not report.failed:
        return report, in_season
    first = report
    report, in_season = check_league(http, league)
    note_what_cleared(first, report)
    return report, in_season


def note_what_cleared(first, second):
    if not second.failed:
        for check in first.checks:
            if check.status == FAIL:
                second.warn(check.source, check.name, f"failed once, then passed: {check.detail}", check.url)


# ---------------------------------------------------------------- everything else

def check_every_league_path(http, report):
    """A cheap check of every league either app names, not just the ones checked in depth."""
    deep = {league.path for league in LEAGUES}
    for path in sorted(apps_league_paths() - deep):
        url = f"{SITE}/{path}/scoreboard"
        status, data = http.get(url)
        if status != 200 or not isinstance(data, dict):
            report.fail(path, "Scoreboard", f"got {status}", url)
        elif not isinstance(data.get("events"), list):
            report.fail(path, "Scoreboard", "no events list", url)
        else:
            report.ok(path, "Scoreboard", f"{len(data['events'])} events", url)


def check_football_calendar(http, report):
    from services import football_calendar

    for key in ("NFL", "NCAAF"):
        # Directly, because the app's resolver falls back to "week 1" rather than saying.
        try:
            season, weeks = football_calendar._fetch_calendar(key)
        except Exception as e:
            report.fail(key, "App: football calendar", f"raised {type(e).__name__}: {e}")
            continue
        if not season or not weeks:
            report.fail(key, "App: football calendar", f"season {season}, {len(weeks or [])} weeks")
            continue
        report.ok(key, "App: football calendar", f"{season}: {len(weeks)} weeks")

        # How both apps ask for a week. A date range is what ESPN stopped accepting.
        league = LEAGUE_KEYS[key]
        first = weeks[0]
        url = scoreboard_url(league, f"{season}&week={first['week']}&seasontype={first['season_type']}")
        status, data = http.get(url)
        if status != 200 or not isinstance(data, dict):
            report.fail(key, "Week query", f"got {status}, so the week arrows would fail", url)
        elif not isinstance(data.get("events"), list):
            report.fail(key, "Week query", "no events list", url)
        else:
            report.ok(key, "Week query", f"{first['label']} of {season}: {len(data['events'])} games", url)

        url = f"{CORE}/{league.core_path}/seasons/{season}/types/2/weeks?limit=3"
        status, data = http.get(url)
        if status != 200 or not isinstance(data, dict):
            report.fail(key, "Core API: weeks (iPhone)", f"got {status}", url)
        elif not data.get("items"):
            report.fail(key, "Core API: weeks (iPhone)", f"{season} has count {data.get('count')} and no items", url)
        else:
            report.ok(key, "Core API: weeks (iPhone)", f"{data.get('count')} weeks", url)


def check_golf(http, report):
    import espn_api

    for tour in espn_api.GOLF_TOURS:
        try:
            schedule = espn_api.get_golf_schedule(tour)
            board = espn_api.get_golf_leaderboard(tour)
        except Exception as e:
            report.fail(tour, "App: golf", f"raised {type(e).__name__}: {e}")
            continue
        if schedule:
            report.ok(tour, "App: golf schedule", f"{len(schedule)} tournaments")
        else:
            report.fail(tour, "App: golf schedule", "empty, and a tour's schedule always has events")
        if board is None:
            report.warn(tour, "App: golf leaderboard", "no tournament on the scoreboard, fine between events")
        elif not board.get("name"):
            report.fail(tour, "App: golf leaderboard", "a tournament with no name")
        else:
            report.ok(tour, "App: golf leaderboard", f"{board['name']}, {len(board.get('players') or [])} players")


def check_mlb_extras(http, report, seasons):
    import espn_api

    in_season = seasons.get("MLB", False)
    try:
        race = espn_api.get_mlb_wildcard_standings()
    except Exception as e:
        report.fail("MLB", "App: wild card", f"raised {type(e).__name__}: {e}")
        race = None
    if race is not None:
        if race.get("AL") and race.get("NL"):
            report.ok("MLB", "App: wild card", f"AL {len(race['AL'])}, NL {len(race['NL'])}")
        else:
            report.seasonal(in_season, "MLB", "App: wild card", "empty")

    today = date.today()
    season = today.year if today.month >= 4 else today.year - 1
    url = ("https://statsapi.mlb.com/api/v1/stats/leaders?leaderCategories=homeRuns&statGroup=hitting"
           f"&season={season}&limit=3")
    status, data = http.get(url)
    if status != 200 or not isinstance(data, dict):
        report.fail("MLB Stats API", "Leaders", f"got {status}", url)
    elif "leagueLeaders" not in data:
        report.fail("MLB Stats API", "Leaders", "no leagueLeaders key", url)
    else:
        report.ok("MLB Stats API", "Leaders", "as expected", url)


def check_draft(http, report):
    import espn_api

    # A year's draft exists from April. Before that the last one has to.
    year = date.today().year
    drafted = None
    for season in (year, year - 1):
        url = f"{SITE}/football/nfl/draft?season={season}"
        status, data = http.get(url)
        # A draft yet to happen answers 200 with its rounds, and no picks.
        if status == 200 and isinstance(data, dict) and data.get("picks"):
            drafted = season
            report.ok("NFL", "Draft (iPhone)", f"{season} has picks", url)
            break
    if drafted is None:
        report.fail("NFL", "Draft (iPhone)", f"no picks for {year} or {year - 1}; last answer {status}", url)
        return

    try:
        draft = espn_api.get_draft(drafted)
        picks = espn_api.get_draft_round(drafted, 1)
    except Exception as e:
        report.fail("NFL", "App: draft", f"raised {type(e).__name__}: {e}")
        return
    if not draft:
        report.fail("NFL", "App: draft", f"nothing for {drafted}, and ESPN has it")
    elif not picks or not all(p.get("player_name") for p in picks):
        report.fail("NFL", "App: draft", f"round 1 of {drafted}: {len(picks)} picks, or some with no player")
    else:
        report.ok("NFL", "App: draft", f"round 1 of {drafted}: {len(picks)} picks")


def check_world_cup(http, report):
    import espn_api

    url = f"{CORE}/soccer/leagues/fifa.world/events/{WORLD_CUP_MATCH}?lang=en"
    status, data = http.get(url)
    number = ((data or {}).get("competitions") or [{}])[0].get("matchNumber") if isinstance(data, dict) else None
    if number:
        report.ok("World Cup", "Core API: match number (iPhone)", f"match {number}", url)
    else:
        report.fail("World Cup", "Core API: match number (iPhone)", f"got {status} and no matchNumber, "
                                                                    "which orders the knockout rounds", url)

    url = f"{STANDINGS}/soccer/fifa.world/standings"
    status, data = http.get(url)
    if status != 200 or not isinstance(data, dict):
        report.fail("World Cup", "Standings", f"got {status}", url)
        return
    try:
        groups = espn_api.get_world_cup_standings("WC2026")
    except Exception as e:
        report.fail("World Cup", "App: standings", f"raised {type(e).__name__}: {e}")
        return
    if groups:
        report.ok("World Cup", "App: standings", f"{len(groups)} groups", url)
    elif standings_entries(data):
        report.fail("World Cup", "App: standings", "ESPN has entries, and the app has no groups", url)
    else:
        report.warn("World Cup", "App: standings", "none, which can be between tournaments", url)


def check_cfl(http, report):
    for name, url in (("Rounds", "https://cflscoreboard.cfl.ca/json/scoreboard/rounds.json"),
                      ("Squads", "https://cflscoreboard.cfl.ca/json/scoreboard/squads.json")):
        status, data = http.get(url)
        if status != 200:
            report.fail("CFL (iPhone)", name, f"got {status}", url)
        elif not data:
            report.warn("CFL (iPhone)", name, "empty, possibly the off-season", url)
        else:
            report.ok("CFL (iPhone)", name, "as expected", url)


def check_hockey_web_page(http, report):
    """Fuller hockey plays come from the espn.com page. It's a bonus, and it blocks automated
    requests some of the time, so an empty answer is no news. Raising is."""
    import espn_api

    finals = find_recent_finals(http, LEAGUE_KEYS["NHL"])
    if not finals.events:
        return
    try:
        plays = espn_api._fetch_web_gamepackage_plays("hockey/nhl", finals.events[0]["id"])
    except Exception as e:
        report.warn("NHL", "espn.com game page", f"raised {type(e).__name__}: {e}")
        return
    report.ok("NHL", "espn.com game page", f"{len(plays)} plays" if plays else "none, as usual from a server")


# How many home teams the Venues list should find: a little under what one month of each
# league had in November 2026. College football's is for the narrower coverage setting.
VENUE_HOME_TEAMS = {"MLB": 28, "NFL": 28, "NBA": 28, "NHL": 28, "WNBA": 12, "NCAAF": 120,
                    "NCAAM": 300, "NCAAWB": 300, "NCAAH": 50, "NCAAWH": 35}

# Team Info's venue comes from the team's home games. ESPN has no other venue for these.
TEAM_INFO_VENUES = (("WNBA", "8"), ("NCAAM", "275"))


def check_venues(http, report, seasons):
    """Windows' venue list, with its home teams, from one month of each league's scoreboard.
    It reaches back to last season when out of season, so no venues is always a failure."""
    import espn_api
    from services.venue_service import VenueService

    for key, expected_teams in VENUE_HOME_TEAMS.items():
        try:
            venues = VenueService().get_venues_for_league(key.lower())
        except Exception as e:
            report.fail(key, "App: venues", f"raised {type(e).__name__}: {e}")
            continue
        teams = {team["id"] for venue in venues.values() for team in venue["home_teams"]}
        if not venues:
            report.fail(key, "App: venues", "no venues")
        elif not all(v.get("name") for v in venues.values()):
            report.fail(key, "App: venues", "a venue has no name")
        elif not all(v["home_teams"] for v in venues.values()):
            report.fail(key, "App: venues", "a venue has no home team")
        elif len(teams) < expected_teams:
            report.warn(key, "App: venues", f"only {len(teams)} home teams at {len(venues)} venues, expected {expected_teams}")
        else:
            report.ok(key, "App: venues", f"{len(venues)} venues, {len(teams)} home teams")

    for key, team_id in TEAM_INFO_VENUES:
        try:
            venue = espn_api.get_team_info(key, team_id).get("venue_name")
        except Exception as e:
            report.fail(key, "App: team info venue", f"raised {type(e).__name__}: {e}")
            continue
        if venue:
            report.ok(key, "App: team info venue", venue)
        else:
            report.seasonal(seasons.get(key, False), key, "App: team info venue", f"no venue for team {team_id}")


def check_fantasy(http, report):
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


def check_others_twice(http, seasons):
    report = check_others(http, seasons)
    if not report.failed:
        return report
    first = report
    report = check_others(http, seasons)
    note_what_cleared(first, report)
    return report


def check_others(http, seasons):
    report = Report()
    for check in (check_every_league_path, check_football_calendar, check_golf, check_draft, check_world_cup,
                  check_cfl, check_hockey_web_page, check_fantasy):
        try:
            check(http, report)
        except Exception as e:
            report.fail("Validator", check.__name__, f"stopped early on {type(e).__name__}: {e}")
    for check in (check_mlb_extras, check_venues):
        try:
            check(http, report, seasons)
        except Exception as e:
            report.fail("Validator", check.__name__, f"stopped early on {type(e).__name__}: {e}")
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
    parser.add_argument("--save-payloads", help="keep each league's payloads here, for the iPhone's decode tests")
    parser.add_argument("--fake-failure", action="store_true",
                        help="report one made-up failure, to test what happens on a failure")
    args = parser.parse_args(argv)

    started = datetime.now(timezone.utc)
    clock = time.monotonic()
    deadline = clock + DEADLINE_SECONDS
    http = Http(save_dir=args.save_payloads, deadline=deadline)
    leagues = [LEAGUE_KEYS[k] for k in args.league] if args.league else LEAGUES

    # This run is about all of Division I, whatever this machine's own setting says.
    import settings
    settings._cache = {"ncaaf_coverage": "all_d1"}
    original_get = install_retrying_get(deadline)

    report, seasons = Report(), {}
    # The app's code prints its progress. This swap is process-wide, so it goes around the
    # whole run rather than each call: threads doing it per call could leave stdout
    # pointing at a dead buffer. What it printed is kept with the JSON.
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            with ThreadPoolExecutor(max_workers=4) as pool:
                for league, (league_report, in_season) in zip(
                        leagues, pool.map(lambda lg: check_league_twice(http, lg), leagues)):
                    report.checks.extend(league_report.checks)
                    seasons[league.key] = in_season
            if not args.league:
                report.checks.extend(check_others_twice(http, seasons).checks)
    finally:
        requests.get = original_get
    if args.fake_failure:
        report.fail("Validator", "Fake failure", "asked for with --fake-failure, to test what a failure does")

    text = render(report, started, time.monotonic() - clock)
    # Files first: a name printing badly on an old console mustn't lose the report.
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(text)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"in_season": seasons, "checks": [c.__dict__ for c in report.checks],
                       "app_output": captured.getvalue()}, f, indent=1)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    print(text)
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
