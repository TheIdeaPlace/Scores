"""The CFL screens, shown offscreen on the CFL's real feed: the tabs, what each table holds, the week
keys, the game and team pages, and what a failed request shows.

The dialogs load on threads, which needs Qt's event loop, and earlier tests in the suite leave
loaders and timers behind that an event loop here would deliver, so the checks run in a process
of their own: this file, run as a script (the pattern in test_popup_menu.py)."""
import os
import subprocess
import sys

import pytest

pytest.importorskip("PyQt6")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHECKS = 33


def run_checks():
    import json
    from datetime import datetime, timezone

    from PyQt6.QtCore import QElapsedTimer, Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QListWidget

    app = QApplication.instance() or QApplication([])  # noqa: F841 (kept alive)

    import cfl
    import scores
    from exceptions import ApiError
    from services.api_service import ApiService

    def load(name):
        with open(os.path.join(ROOT, "tests", "fixtures", "espn", name), encoding="utf-8") as f:
            return json.load(f)

    # The capture's moment, so the week it shows is the one with the game at halftime.
    captured = datetime(2026, 11, 8, 0, 53, tzinfo=timezone.utc)
    real_parse_round = cfl.parse_round
    cfl.parse_round = lambda rounds, squads, index=None, now=None: real_parse_round(
        rounds, squads, index, now or captured)

    calls = {"feed": 0}
    failing = {"feed": False}
    announced = []
    unavailable = cfl.unavailable("scores")

    def feed():
        calls["feed"] += 1
        if failing["feed"]:
            raise ApiError(unavailable)
        return {"rounds": load("cfl_rounds_2026_halftime.json"), "squads": load("cfl_squads_2026.json")}

    ApiService.get_cfl_feed = staticmethod(feed)
    scores.announce = announced.append

    def wait_for(condition, ms=5000):
        clock = QElapsedTimer()
        clock.start()
        while not condition() and clock.elapsed() < ms:
            app.processEvents()
        return condition()

    def is_table(page):
        return isinstance(page.content, scores.RacingTable)

    def headers(table):
        return [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]

    def cell(table, row, column):
        return table.table_widget.item(row, column).text()

    def message(page):
        return page.content.item(0).text() if isinstance(page.content, QListWidget) else None

    def tab_chain(dialog):
        chain, widget = [], dialog.tab_widget.tabBar().nextInFocusChain()
        while widget is not dialog.tab_widget.tabBar() and len(chain) < 500:
            chain.append(widget)
            widget = widget.nextInFocusChain()
        return chain

    results = {}

    dialog = scores.CFLDialog()
    dialog.show()
    loaded = wait_for(lambda: all(is_table(p) for p in dialog._pages()))
    results["every tab loads"] = loaded
    results["the title"] = dialog.windowTitle() == "CFL - Sports Scores"
    results["three tabs"] = [dialog.tab_widget.tabText(i) for i in range(dialog.tab_widget.count())] == [
        "Scores", "Standings", "Teams"]
    games = dialog.scores_page.content
    results["the current week, named in the table"] = (
        games.accessible_name == "CFL Conference Finals, this week, 2 games"
        and dialog.week_label.text() == "Conference Finals, this week, 2 games.")
    results["score headers"] = headers(games) == ["Game", "Score", "Status", "Kickoff"]
    results["the game at halftime"] = (cell(games, 1, 0) == "BC Lions at Edmonton Elks"
                                       and cell(games, 1, 1) == "BC 9, EDM 6" and cell(games, 1, 2) == "Halftime")
    results["all three views are filled"] = games.quick_list.count() == 2 and games.full_list.count() == 2
    results["the game is whose row it is"] = games.ROW_CONTEXT_COLUMN == 0

    # Enter on a game opens it, and doesn't press a button: no button is a default.
    opened = []
    real_game = scores.CFLGameDialog
    scores.CFLGameDialog = lambda game, parent: type("Stub", (), {"exec": lambda self: opened.append(game["id"])})()
    games.table_widget.setFocus()
    games.table_widget.setCurrentCell(1, 0)
    before = calls["feed"]
    QTest.keyClick(games.table_widget, Qt.Key.Key_Return)
    wait_for(lambda: False, ms=200)
    results["Enter on a game opens it"] = opened == ["13463065"]
    results["and doesn't refresh"] = calls["feed"] == before and dialog.scores_page.content is games
    scores.CFLGameDialog = real_game
    results["no button is a default"] = not any(
        b.autoDefault() or b.isDefault() for b in dialog.findChildren(scores.QPushButton))

    # Tab from the tabs reaches the table before the buttons.
    chain = tab_chain(dialog)
    buttons = [i for i, w in enumerate(chain) if isinstance(w, scores.QPushButton)]
    results["the loaded table comes after the tabs, before the buttons"] = (
        games.table_widget in chain and buttons and chain.index(games.table_widget) < min(buttons))

    # The week keys.
    games.table_widget.setFocus()
    QTest.keyClick(games.table_widget, Qt.Key.Key_N, Qt.KeyboardModifier.AltModifier)
    wait_for(lambda: dialog.scores_page.content is not games)
    grey_cup = dialog.scores_page.content
    results["Alt+N shows next week"] = grey_cup.accessible_name == "CFL 113th Grey Cup, 1 game"
    results["a game to come has no score"] = cell(grey_cup, 0, 1) == "Not started"
    results["the new week has the focus"] = grey_cup.table_widget.hasFocus() or not dialog.isActiveWindow()
    announced.clear()
    dialog._step_week(1)
    results["past the last week says so"] = announced == ["This is the last week of the season."]
    dialog._step_week(-1)
    dialog._step_week(-1)
    results["Alt+P steps back"] = dialog.scores_page.content.accessible_name == "CFL Semi-Finals, 2 games"
    results["another week starts at the top"] = dialog.scores_page.content.table_widget.currentRow() == 0
    # From another tab, a week key goes to the scores.
    dialog.tab_widget.setCurrentWidget(dialog.standings_page)
    dialog._step_week(1)
    results["a week key from Standings goes to Scores"] = (
        dialog.tab_widget.currentWidget() is dialog.scores_page
        and dialog.scores_page.content.accessible_name.startswith("CFL Conference Finals"))

    standings = dialog.standings_page.content
    results["standings headers"] = headers(standings) == ["Rank", "Team", "Division", "W", "L", "Pct"]
    results["standings, East then West"] = (cell(standings, 0, 1) == "Montreal Alouettes"
                                            and cell(standings, 4, 1) == "Edmonton Elks"
                                            and cell(standings, 4, 2) == "West Division")
    teams = dialog.teams_page.content
    results["the teams"] = teams.rowCount() == 9 and cell(teams, 0, 0) == "BC Lions"

    # Enter on a team opens its season.
    opened_teams = []
    real_team = scores.CFLTeamDialog
    scores.CFLTeamDialog = lambda team_id, feed, parent: type(
        "Stub", (), {"exec": lambda self: opened_teams.append(team_id)})()
    standings.table_widget.itemActivated.emit(standings.table_widget.item(4, 0))
    teams.table_widget.itemActivated.emit(teams.table_widget.item(0, 0))
    results["Enter on a team in the standings or the teams opens it"] = opened_teams == ["114347", "93775"]
    scores.CFLTeamDialog = real_team

    # A refresh keeps the week and the place in it.
    dialog.scores_page.content.table_widget.setCurrentCell(1, 2)
    before_week = dialog._week_index
    current = dialog.scores_page.content
    dialog._load()
    wait_for(lambda: dialog.scores_page.content is not current)
    again = dialog.scores_page.content
    results["a refresh keeps the week and the place"] = (
        dialog._week_index == before_week and again.table_widget.currentRow() == 1
        and again.table_widget.currentColumn() == 2)

    # A refresh that fails keeps what's on show and says so once.
    failing["feed"] = True
    announced.clear()
    dialog._load()
    wait_for(lambda: len(announced) >= 1, ms=3000)
    wait_for(lambda: False, ms=300)
    results["a failed refresh keeps the tables and says so once"] = (
        all(is_table(p) for p in dialog._pages()) and announced == [unavailable])
    failing["feed"] = False
    feed_now = dialog._feed
    dialog.close()
    dialog.deleteLater()

    # The game page.
    game = cfl.parse_round(feed_now["rounds"], feed_now["squads"])["games"][1]
    page = scores.CFLGameDialog(game)
    results["the game's title"] = page.windowTitle() == "BC Lions at Edmonton Elks - CFL - Sports Scores"
    table = page.page.content
    results["the game's table says the status first"] = (
        table.accessible_name.startswith("BC Lions at Edmonton Elks: Halftime. Conference Finals. ")
        and headers(table) == ["Team", "Score", "Record", "Side"]
        and [cell(table, 0, i) for i in range(4)] == ["BC Lions", "9", "10-8", "Away"])
    page.close()
    page.deleteLater()

    # The team page.
    team = scores.CFLTeamDialog("114347", feed_now)
    results["the team's title"] = team.windowTitle() == "Edmonton Elks - CFL - Sports Scores"
    schedule = team.page.content
    results["the team's schedule is named with its record"] = schedule.accessible_name == (
        "Edmonton Elks schedule: 13-5, 1st in West Division.")
    results["the schedule starts on the game under way"] = (
        schedule.table_widget.currentRow() == schedule.rowCount() - 1
        and cell(schedule, schedule.rowCount() - 1, 1) == "Halftime, 6-9")
    team.close()
    team.deleteLater()

    # A first load that fails says so, in each page's words, and Enter on that row tries again.
    failing["feed"] = True
    broken = scores.CFLDialog()
    broken.show()
    wait_for(lambda: (message(broken.standings_page) or "").startswith("The CFL"))
    row = broken.standings_page.content.item(0)
    results["a failed load says so with a row to try again"] = (
        row.text() == cfl.unavailable("standings")
        and row.data(Qt.ItemDataRole.UserRole) == scores.RETRY_ROW
        and message(broken.scores_page) == unavailable
        and message(broken.teams_page) == cfl.unavailable("teams"))
    announced.clear()
    broken._step_week(1)
    results["a week key with nothing loaded says so"] = announced == ["The CFL's weeks haven't loaded yet."]
    failing["feed"] = False
    broken.standings_page.content.itemActivated.emit(row)
    results["Enter on it loads them all"] = wait_for(lambda: all(is_table(p) for p in broken._pages()))
    broken.close()
    broken.deleteLater()
    app.processEvents()
    return results


def test_the_cfl_screens(tmp_path):
    # Its own settings file, so someone's saved view doesn't change what the tables start in.
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=ROOT, APPDATA=str(tmp_path))
    run = subprocess.run([sys.executable, os.path.abspath(__file__)], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=120, encoding="utf-8")
    lines = [line for line in run.stdout.splitlines() if line.startswith(("PASS ", "FAIL "))]
    assert run.returncode == 0 and len(lines) == CHECKS, run.stdout + run.stderr
    assert all(line.startswith("PASS ") for line in lines), "\n".join(lines)


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    outcome = run_checks()
    for name, held in outcome.items():
        print(("PASS " if held else "FAIL ") + name)
    sys.exit(0)
