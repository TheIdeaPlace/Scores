"""College football's bowls and playoff as one list, under round headings. Pure: no PyQt.

The rule is the iPhone's (``Models/Postseason.swift``): the round comes from ESPN's
note headline, and the competition type only when there is no headline. The type
alone files games wrong: the playoff's first-round games come as type 1, a plain
game, and were filed among the bowls (#202). A round is the playoff's only when the
headline says "College Football Playoff" (or CFP), so another division's playoff
stays with the bowls under its own name.
"""

from __future__ import annotations

from typing import Optional

FIRST_ROUND = "Playoff First Round"
QUARTERFINALS = "Playoff Quarterfinals"
SEMIFINALS = "Playoff Semifinals"
CHAMPIONSHIP = "National Championship"
BOWLS = "Bowl Games"

# The order the list shows them: the playoff in the order it's played, then the bowls.
ROUNDS = (FIRST_ROUND, QUARTERFINALS, SEMIFINALS, CHAMPIONSHIP, BOWLS)
PLAYOFF_ROUNDS = frozenset(ROUNDS[:-1])


def _type_id(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def postseason_round(headline: Optional[str], type_id=None) -> str:
    """The heading a game goes under, from its note headline and competition type."""
    text = (headline or "").strip().lower()
    if not text:
        return {33: CHAMPIONSHIP, 35: SEMIFINALS}.get(_type_id(type_id), BOWLS)
    is_playoff = ("college football playoff" in text or text.startswith("cfp ")
                  or " cfp " in text)
    if not is_playoff:
        return BOWLS
    if "first round" in text:
        return FIRST_ROUND
    if "quarterfinal" in text:
        return QUARTERFINALS
    if "semifinal" in text:
        return SEMIFINALS
    if "championship" in text:
        return CHAMPIONSHIP
    return BOWLS


def game_headline(game) -> str:
    """ESPN's name for the game, such as "Cricket Celebration Bowl"; "" when it gives none."""
    competitions = game.get("competitions") if isinstance(game, dict) else None
    competition = competitions[0] if competitions and isinstance(competitions[0], dict) else {}
    for note in competition.get("notes") or []:
        if isinstance(note, dict):
            headline = str(note.get("headline") or "").strip()
            if headline:
                return headline
    return ""


def game_round(game) -> str:
    competitions = game.get("competitions") if isinstance(game, dict) else None
    competition = competitions[0] if competitions and isinstance(competitions[0], dict) else {}
    kind = competition.get("type") if isinstance(competition.get("type"), dict) else {}
    return postseason_round(game_headline(game), kind.get("id"))


def heading_text(round_name: str, count: int) -> str:
    """"Bowl Games, 36 games": a heading row says whether the section is worth entering."""
    return f"{round_name}, {count} {'game' if count == 1 else 'games'}"


def postseason_sections(games) -> list[tuple[str, list]]:
    """[(round, games)] in list order, each round's games by kickoff, empty rounds left out."""
    by_round: dict[str, list] = {name: [] for name in ROUNDS}
    for game in games or []:
        if isinstance(game, dict):
            by_round[game_round(game)].append(game)
    sections = []
    for name in ROUNDS:
        ordered = sorted(by_round[name], key=lambda g: (
            str(g.get("date") or ""), game_headline(g) or str(g.get("name") or "")))
        if ordered:
            sections.append((name, ordered))
    return sections
