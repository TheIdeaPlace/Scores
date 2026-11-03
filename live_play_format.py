"""List text for a live game's current play.

Shared by the All Scores view and a single league's scores list, so a live
game reads the same in both. The play text itself comes from
espn_api.scoreboard_live_detail(); this only lays it out. Kept free of Qt so it can
be tested directly.
"""

import re

# Plays in leagues without an enhanced display are cut to this many characters.
# Long enough for an assist or a second name. Cutting mid-name loses the point of the play.
PLAY_LIMIT = 140

# The clock at the start of a status like "12:57 - 4th".
_STATUS_CLOCK = re.compile(r"^(\d{1,2}:\d{2})\b")


def short_play(text, limit=PLAY_LIMIT):
    """`text` cut to `limit` characters at a word boundary, marked with "..."."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0] or text[:limit]
    return cut.rstrip(" ,;:|-") + "..."


def away_then_home(teams):
    """The first two teams, away first whenever home and away are known."""
    away = next((t for t in teams if t.get("home_away") == "away"), None)
    home = next((t for t in teams if t.get("home_away") == "home"), None)
    return [away, home] if away and home else list(teams[:2])


def score_line(teams):
    """'Away 3 at Home 7', in that order whenever home and away are known."""
    return " at ".join(f"{t.get('name', '')} {t.get('score', '')}".strip()
                       for t in away_then_home(teams))


def _repeats_clock(status, line):
    """True when `status` only restates the clock `line` already gives.

    The football play line carries "12:57 Q4"; the status "12:57 - 4th" says
    the same thing again, which a screen reader would speak twice. A status
    with no clock ("Halftime", "End of 3rd") still adds something.
    """
    match = _STATUS_CLOCK.match(status or "")
    # Whole clock only: "1:11" must not match inside "11:11".
    return bool(match) and re.search(rf"(?<![\d:]){re.escape(match.group(1))}\b", line) is not None


def format_football(teams, status, recent_play):
    """Two lines: teams, score and last play; then clock, down and drive."""
    lines = recent_play.split("\n")
    if len(lines) >= 2:
        team_line, stats_line = lines[0], lines[1]
        if status and status not in stats_line and not _repeats_clock(status, stats_line):
            stats_line += f" ({status})"
        return f"{team_line}\n{stats_line}"
    if " at " in recent_play:
        # The scoreboard's line 1 alone (teams, score, play): with no clock
        # line to carry the status, the status gets a line of its own.
        return f"{recent_play}\n{status}" if status else recent_play
    return _single_line(teams, status, recent_play)


def format_baseball(teams, status, recent_play):
    """Three lines: teams and score; runners, count and batter; last play."""
    lines = recent_play.split("\n")
    if len(lines) >= 2:
        team_line = lines[0]
        if status and (len(lines) < 3 or status not in lines[1]):
            team_line += f" ({status})"
        return "\n".join([team_line] + lines[1:3])
    return _single_line(teams, status, recent_play)


def _single_line(teams, status, recent_play):
    text = score_line(teams)
    if status:
        text += f" ({status})"
    return f"{text} | {recent_play}"


def format_other(game_text, recent_play):
    """The game's usual list text with the latest play after it."""
    return f"{game_text} | {short_play(recent_play)}"


def format_live_game(league, teams, status, recent_play, game_text):
    """The list text for a live game in `league`.

    `game_text` is the game's ordinary one-line text, used for leagues without
    an enhanced display.
    """
    try:
        if league in ("NFL", "NCAAF"):
            return format_football(teams, status, recent_play)
        if league == "MLB":
            return format_baseball(teams, status, recent_play)
    except Exception as e:
        print(f"Error formatting live {league} game: {e}")
        return _single_line(teams, status, short_play(recent_play))
    return format_other(game_text, recent_play)


def use_list_team_names(text, name_map):
    """Rename teams in the score at the start of a live game's text.

    The play text names teams by ESPN's full display name ("Kansas City
    Chiefs"); a league's list uses the short name for NFL and MLB ("Chiefs").
    Without this a live game reads differently from the games around it and
    type-ahead on the short name skips it. `name_map` maps display name to
    list name.
    """
    first, sep, rest = text.partition("\n")
    # Only the teams and score: line 1 can go on to the play, which names
    # teams in ESPN's words and is left as ESPN wrote it.
    score, bar, play = first.partition(" | ")
    # Longest first, so "New York Yankees" is replaced before a shorter name
    # it contains could be.
    for full in sorted(name_map, key=len, reverse=True):
        short = name_map[full]
        if full and short and full != short:
            # A list name can contain the full one ("#5 Arizona Wildcats"), and the
            # text may already use it: undo that first so it isn't added twice.
            if full in short:
                score = score.replace(short, full)
            score = score.replace(full, short)
    return score + bar + play + sep + rest


def list_team_names(game_raw, teams):
    """{ESPN display name: the name `teams` uses} for a get_scores() game.

    `teams` is that game's "teams" list, which get_scores() builds in the
    same order as the raw competitors.
    """
    competitors = ((game_raw.get("competitions") or [{}])[0] or {}).get("competitors", [])
    names = {}
    for competitor, team in zip(competitors, teams):
        full = competitor.get("team", {}).get("displayName", "")
        if full and team.get("name"):
            names[full] = team["name"]
    return names
