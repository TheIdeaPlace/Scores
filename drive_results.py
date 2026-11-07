"""Who scored on a football drive, and how many points. Pure: no PyQt.

ESPN's drive ``result`` names how the drive ended, not who scored. A missed field
goal run back for a touchdown, a kickoff returned for one, a pick six and a safety are
all marked on the drive of the team that gave the points up ("TD" on NC State's
drive when Duke ran its missed field goal back 100 yards). And ESPN gives no points
for the drive, so a touchdown with no extra point (a missed kick, or a walk-off in
overtime, where no try is run) or with a two-point conversion can't be told apart
by its result.

Every play carries the score after it (``awayScore``, ``homeScore``), so the rule
here reads the score instead: in a drive with a scoring play, the side whose score
went up first scored, with every point that side added in the drive. The kind of score follows
from the points (6 to 8 a touchdown, 3 a field goal, 2 given up a safety).

The iPhone's twin is ``Services/DriveResults.swift``. The two must agree:
``tests/fixtures/drive_results_grid.json`` holds both to the same answers, with
``tests/unit/test_drive_results.py`` and ``DriveResultsGridTests.swift``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# How a drive's scoring reads. A drive with no score has kind None.
TD = "TD"                # the team with the ball scored a touchdown
FG = "FG"                # the team with the ball kicked a field goal
SCORE = "SCORE"          # any other points by the team with the ball
RETURN_TD = "RETURN TD"  # the other team scored a touchdown: a return or a turnover
SAFETY = "SAFETY"        # the other team scored two: a safety
OPPONENT_SCORE = "OPPONENT SCORE"  # any other points by the other team


@dataclass(frozen=True)
class DriveResult:
    kind: Optional[str] = None
    points: int = 0
    # "away" or "home": the side that scored. None when nobody did.
    scorer: Optional[str] = None
    # True when the side that scored isn't the side with the ball.
    by_opponent: bool = False
    # Points the other side scored later in the same drive, such as a blocked
    # extra point run back for two.
    other_points: int = 0


def _score(value) -> Optional[int]:
    """A score as ESPN may send it: an int, a float or text such as "7" or "1,000".

    The same values the iPhone's lenientNumber reads.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.replace(",", "").strip()
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if math.isfinite(number) else None


def _side(team_id, away_id, home_id) -> Optional[str]:
    team_id = "" if team_id is None else str(team_id)
    if not team_id:
        return None
    if team_id == str(away_id or ""):
        return "away"
    if team_id == str(home_id or ""):
        return "home"
    return None


def _kind(points: int, by_opponent: bool) -> str:
    if by_opponent:
        if 6 <= points <= 8:
            return RETURN_TD
        if points == 2:
            return SAFETY
        return OPPONENT_SCORE
    if 6 <= points <= 8:
        return TD
    if points == 3:
        return FG
    return SCORE


def drive_results(drives, away_id, home_id) -> list[DriveResult]:
    """One result per drive, for ESPN drives in the order they were played.

    The score before a play is the last score seen, in this drive or the ones before
    it, as ESPN's ``previous`` list gives them. Points count only in a drive with a
    play ESPN marks ``scoringPlay``, so a rise in the score with no scoring play behind
    it isn't anybody's points: a drive missing from the list, or a score that dips and
    comes back. The whole drive counts, not just from the scoring play on: ESPN's
    score can move a play early (on the timeout before Duke's return in 401858286),
    and the try after a touchdown can be a play of its own. A play without a score
    is skipped.
    """
    results = []
    running = (0, 0)
    for drive in drives or []:
        if not isinstance(drive, dict):
            results.append(DriveResult())
            continue
        added = {"away": 0, "home": 0}
        first = None
        plays = [p for p in drive.get("plays") or [] if isinstance(p, dict)]
        scoring = any(p.get("scoringPlay") is True for p in plays)
        for play in plays:
            away, home = _score(play.get("awayScore")), _score(play.get("homeScore"))
            if away is None or home is None:
                continue
            if scoring:
                for side, now, before in (("away", away, running[0]), ("home", home, running[1])):
                    if now > before:
                        added[side] += now - before
                        first = first or side
            running = (away, home)
        if first is None:
            results.append(DriveResult())
            continue
        team = drive.get("team")
        offense = _side(team.get("id") if isinstance(team, dict) else None, away_id, home_id)
        by_opponent = offense is not None and offense != first
        other = "home" if first == "away" else "away"
        results.append(DriveResult(
            kind=_kind(added[first], by_opponent),
            points=added[first],
            scorer=first,
            by_opponent=by_opponent,
            other_points=added[other],
        ))
    return results


def _pts(points: int) -> str:
    return f"{points}pt" if points == 1 else f"{points}pts"


def drive_badge(result: DriveResult, scorer_name: str = "", other_name: str = "") -> Optional[str]:
    """The badge for a drive that scored, such as "TD 6pts" or "Duke Blue Devils return TD 7pts".

    None for a drive with no score: each app names those its own way. A score by the
    team without the ball is named for the team that scored, since the drive itself is
    shown under the team that had the ball.
    """
    if result.kind is None:
        return None
    points = _pts(result.points)
    scorer = scorer_name or "Other team"
    badge = {
        TD: f"TD {points}",
        FG: f"FG {points}",
        SCORE: points,
        RETURN_TD: f"{scorer} return TD {points}",
        SAFETY: f"{scorer} safety {points}",
        OPPONENT_SCORE: f"{scorer} {points}",
    }[result.kind]
    if result.other_points:
        badge += f", {other_name or 'other team'} {_pts(result.other_points)}"
    return badge


def summary_teams(summary) -> dict:
    """{"away": {"id", "name", "abbreviation"}, "home": {...}} from a summary's header."""
    teams = {}
    header = summary.get("header") if isinstance(summary, dict) else None
    competitions = header.get("competitions") if isinstance(header, dict) else None
    if not competitions or not isinstance(competitions[0], dict):
        return teams
    for competitor in competitions[0].get("competitors") or []:
        if not isinstance(competitor, dict):
            continue
        side = str(competitor.get("homeAway") or "").lower()
        team = competitor.get("team") if isinstance(competitor.get("team"), dict) else {}
        if side in ("away", "home"):
            teams[side] = {
                "id": str(team.get("id") or competitor.get("id") or ""),
                "name": team.get("displayName") or team.get("shortDisplayName") or "",
                "abbreviation": team.get("abbreviation") or "",
            }
    return teams


def chronological_drives(drives_data) -> list:
    """ESPN's drives in the order they were played, each once.

    During a live game ``previous`` already holds the drive in progress, so
    ``current`` is added only when it isn't there.
    """
    if not isinstance(drives_data, dict):
        return []
    previous = [d for d in drives_data.get("previous") or [] if isinstance(d, dict)]
    current = drives_data.get("current")
    if isinstance(current, dict) and current and not any(
            d.get("id") == current.get("id") for d in previous):
        previous.append(current)
    return previous
