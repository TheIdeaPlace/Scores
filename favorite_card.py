"""Pure: what a favorite team's card on Home says about its games.

The card reads the team's schedule (espn_api.get_favorite_card_schedule, the current season,
or the last one before the next is published) and, while the team is playing, that game's
/summary. It shows the game being played or else the last one finished, then the next one
to play. No Qt and no network, so it is tested on any platform.

**The iPhone's twin is `Models/FavoriteCardGames.swift`, which `FavoriteTeamCardView` and
`FavoritesHubViewModel` use. Both are held to `tests/fixtures/favorite_card_grid.json`:
which game is live, last and next, and the line the last game reads as. Change both in the
same commit.** The live line and the next game's date aren't in the grid: the iPhone writes
the date in the phone's own short style, and a live line needs a whole /summary.
"""
from datetime import datetime, timezone
from typing import Any, NamedTuple, Optional

from game_labels import schedule_game_label

# A finished game's status where ESPN gives no `completed`. Soccer says STATUS_FULL_TIME, or
# STATUS_FINAL_PEN after a shootout. ScheduleGame.finishedStatuses on the iPhone.
FINISHED_STATUSES = frozenset({"STATUS_FINAL", "STATUS_FULL_TIME", "STATUS_FINAL_PEN", "STATUS_FINAL_AET"})


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _dicts(value: Any) -> list:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _score(value: Any) -> Optional[int]:
    """A schedule's score is {"value": 3.0, "displayValue": "3"}, or missing before the game.
    The iPhone reads `value`."""
    if isinstance(value, dict):
        value = value.get("value", value.get("displayValue"))
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def _team(competitor: dict) -> dict:
    team = _as_dict(competitor.get("team"))
    return {
        "id": str(team.get("id") or ""),
        "abbreviation": team.get("abbreviation") or "",
        "display_name": team.get("displayName") or "",
        "score": _score(competitor.get("score")),
    }


def _utc(date_text: Any) -> Optional[datetime]:
    if not isinstance(date_text, str) or not date_text:
        return None
    try:
        parsed = datetime.fromisoformat(date_text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def card_game(event: Any) -> Optional[dict]:
    """One ESPN schedule event as the card needs it, or None without a date and both teams.
    `completed` and `state` stay None where ESPN leaves them out, as the iPhone's do."""
    if not isinstance(event, dict):
        return None
    competitions = _dicts(event.get("competitions"))
    if not competitions:
        return None
    comp = competitions[0]
    sides = {}
    for competitor in _dicts(comp.get("competitors")):
        side = competitor.get("homeAway")
        if side in ("home", "away") and side not in sides:
            sides[side] = _team(competitor)
    start = _utc(event.get("date"))
    if "home" not in sides or "away" not in sides or start is None:
        return None
    time_valid = event.get("timeValid")
    if time_valid is None:
        time_valid = comp.get("timeValid")
    status_type = _as_dict(_as_dict(comp.get("status")).get("type"))
    completed = status_type.get("completed")
    state = status_type.get("state")
    return {
        "id": str(event.get("id") or ""),
        "start": start,
        "time_valid": time_valid is not False,
        "status_name": status_type.get("name") or "",
        "completed": completed if isinstance(completed, bool) else None,
        "state": state if isinstance(state, str) else None,
        "home": sides["home"],
        "away": sides["away"],
        "neutral_site": comp.get("neutralSite") is True,
        "label": schedule_game_label(event),
    }


def _when(game: dict) -> datetime:
    """When a game is, as an aware time. A game with no time set is at noon local on its UTC
    date, which is the true one, as ScheduleGame does on the iPhone."""
    start = game["start"]
    if game["time_valid"]:
        return start
    return datetime(start.year, start.month, start.day, 12).astimezone()


def card_games(events: Any) -> list:
    """A schedule's events as card games, in time order, each game once (the first kept).
    A doubleheader's two games stay in order within their day."""
    seen, games = set(), []
    for event in _dicts(events):
        game = card_game(event)
        if game is None:
            continue
        if game["id"]:
            if game["id"] in seen:
                continue
            seen.add(game["id"])
        games.append(game)
    return sorted(games, key=_when)


def is_completed(game: dict) -> bool:
    if game["completed"] is not None:
        return game["completed"]
    return game["status_name"] in FINISHED_STATUSES


def is_in_progress(game: dict) -> bool:
    """Includes halftime and a delay, which ESPN counts as under way and names differently."""
    if game["state"] is not None:
        return game["state"] == "in"
    return game["status_name"] == "STATUS_IN_PROGRESS"


def is_called_off(game: dict) -> bool:
    """Postponed or canceled: over, as far as this date goes, with nothing played."""
    return game["completed"] is False and game["state"] == "post"


def is_ahead(game: dict, now: datetime) -> bool:
    """The start is still to come. With no time set, a game later today still counts."""
    if game["time_valid"]:
        return game["start"] > now
    return game["start"].date() >= now.astimezone().date()


class CardGames(NamedTuple):
    live: Optional[dict]
    last: Optional[dict]
    next: Optional[dict]


def pick(games: list, now: datetime) -> CardGames:
    """The game being played, the last one finished and the next one to play. A game called
    off is none of them, whatever its date says. `now` is an aware time."""
    live = next((g for g in games if is_in_progress(g)), None)
    finished = [g for g in games if is_completed(g)]
    upcoming = next((g for g in games
                     if not is_completed(g) and not is_in_progress(g) and not is_called_off(g)
                     and is_ahead(g, now)), None)
    return CardGames(live, finished[-1] if finished else None, upcoming)


def _sides(game: dict, team_id: str):
    """(this team, the other team, "vs" or "@"). A neutral site reads as "vs"."""
    is_home = game["home"]["id"] == str(team_id)
    mine, theirs = (game["home"], game["away"]) if is_home else (game["away"], game["home"])
    return mine, theirs, "vs" if is_home or game["neutral_site"] else "@"


def _label(game: dict) -> str:
    return f", {game['label']}" if game["label"] else ""


def result_line(game: dict, team_id: str, prefix: str = "Last") -> str:
    """"Last: W vs LAD 2-1, Doubleheader - Game 2". This team's score comes first."""
    mine, theirs, where = _sides(game, team_id)
    my_score, their_score = mine["score"] or 0, theirs["score"] or 0
    result = "W" if my_score > their_score else ("L" if my_score < their_score else "T")
    return f"{prefix}: {result} {where} {theirs['abbreviation']} {my_score}-{their_score}{_label(game)}"


def _short_date(day) -> str:
    return f"{day.month}/{day.day}/{day:%y}"


def next_line(game: dict, team_id: str, prefix: str = "Next", zone=None) -> str:
    """"Next: @ VAN, 11/14/26, 11:45 AM", in local time (or `zone`), as the iPhone's short
    date and time read in the US. A game with no time set has its date alone."""
    _, theirs, where = _sides(game, team_id)
    if game["time_valid"]:
        local = game["start"].astimezone(zone)
        hour = local.hour % 12 or 12
        when = f"{_short_date(local)}, {hour}:{local:%M} {'AM' if local.hour < 12 else 'PM'}"
    else:
        when = _short_date(game["start"].date())
    return f"{prefix}: {where} {theirs['abbreviation']}, {when}{_label(game)}"


def player_names(summary: Any) -> dict:
    """Player id to short name, across both teams' rosters in a /summary."""
    names = {}
    for team in _dicts(_as_dict(summary).get("rosters")):
        for entry in _dicts(team.get("roster")):
            athlete = _as_dict(entry.get("athlete"))
            name = athlete.get("shortName") or athlete.get("displayName")
            if athlete.get("id") is not None and name:
                names[str(athlete["id"])] = name
    return names


def _player(situation: dict, key: str, names: dict) -> Optional[str]:
    player_id = _as_dict(situation.get(key)).get("playerId")
    return names.get(str(player_id)) if player_id is not None else None


def situation_text(summary: Any) -> Optional[str]:
    """Baseball's situation from a /summary: "P: G. Cole, AB: R. Devers, 1st & 3rd, 1-2,
    2 outs". None for a sport without one. The iPhone's words, in
    GameDetails.SummarySituation.situationText; it joins them with a middle dot, which a
    Windows screen reader can read out as "dot", so here it's a comma."""
    situation = _as_dict(_as_dict(summary).get("situation"))
    balls, strikes, outs = situation.get("balls"), situation.get("strikes"), situation.get("outs")
    if balls is None and outs is None:
        return None
    names = player_names(summary)
    parts = []
    pitcher = _player(situation, "pitcher", names)
    if pitcher:
        parts.append(f"P: {pitcher}")
    batter = _player(situation, "batter", names)
    if batter:
        parts.append(f"AB: {batter}")
    bases = [label for key, label in (("onFirst", "1st"), ("onSecond", "2nd"), ("onThird", "3rd"))
             if situation.get(key)]
    parts.append(" & ".join(bases) if bases else "Bases empty")
    if balls is not None and strikes is not None:
        parts.append(f"{balls}-{strikes}")
    if outs is not None:
        parts.append(f"{outs} {'out' if outs == 1 else 'outs'}")
    return ", ".join(parts)


def _header_competition(summary: Any) -> dict:
    competitions = _dicts(_as_dict(_as_dict(summary).get("header")).get("competitions"))
    return competitions[0] if competitions else {}


def live_line(game: dict, team_id: str, summary: Any = None, prefix: str = "Live") -> str:
    """"Live: Alabama Crimson Tide 10 @ LSU Tigers 12, 2:44 - 3rd Quarter", with baseball's
    situation after it. The schedule has no score for a game being played, so the score and
    the inning or clock come from the game's /summary. Without one, the opponent alone."""
    comp = _header_competition(summary)
    if comp:
        scores = {}
        for competitor in _dicts(comp.get("competitors")):
            side = competitor.get("homeAway")
            score = competitor.get("score")
            if side in ("home", "away") and side not in scores:
                scores[side] = "" if score is None or score == "" else f" {score}"
        line = (f"{prefix}: {game['away']['display_name']}{scores.get('away', '')}"
                f" @ {game['home']['display_name']}{scores.get('home', '')}")
        detail = _as_dict(_as_dict(comp.get("status")).get("type")).get("detail")
        if isinstance(detail, str) and detail.strip():
            line += f", {detail}"
        situation = situation_text(summary)
        if situation:
            line += f", {situation}"
        return line
    mine, theirs, where = _sides(game, team_id)
    if mine["score"] is not None and theirs["score"] is not None:
        return f"{prefix}: {where} {theirs['abbreviation']} {mine['score']}-{theirs['score']}"
    return f"{prefix}: {where} {theirs['abbreviation']}"
