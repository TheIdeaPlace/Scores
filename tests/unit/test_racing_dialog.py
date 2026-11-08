"""The Racing screens, shown offscreen on ESPN's real racing answers: which tabs each series has,
what each table holds, where each starts, and what a failed request shows.

The dialogs load on threads, which needs Qt's event loop, and earlier tests in the suite leave
loaders and timers behind that an event loop here would deliver, so the checks run in a process
of their own: this file, run as a script (the pattern in test_popup_menu.py)."""
import os
import subprocess
import sys

import pytest

pytest.importorskip("PyQt6")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHECKS = 28


def run_checks():
    import json

    from PyQt6.QtCore import QElapsedTimer, Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QListWidget

    app = QApplication.instance() or QApplication([])  # noqa: F841 (kept alive)

    import racing
    import scores
    from exceptions import ApiError
    from services.api_service import ApiService

    def load(name):
        with open(os.path.join(ROOT, "tests", "fixtures", "espn", name), encoding="utf-8") as f:
            return json.load(f)

    slug = {key: path.split("/")[1] for key, (path, *_) in racing.RACING_SERIES.items()}
    calls = {"event": 0}
    failing = {"event": False, "standings": False}
    announced = []

    def race_event(series):
        calls["event"] += 1
        if failing["event"]:
            raise ApiError("ESPN isn't providing this race right now. Try again in a minute.")
        answer = load(f"racing_scoreboard_{slug[series]}.json")
        return {"event": racing.parse_race_event(answer), "season": racing.season_year(answer)}

    def standings(series):
        if failing["standings"]:
            raise ApiError("ESPN isn't providing standings right now. Try again in a minute.")
        return racing.parse_standings(load(f"racing_standings_{slug[series]}.json"))

    def news(series, limit=25):
        if series == "NASCAR":
            return []
        return [{"headline": a["headline"], "web_url": "https://www.espn.com/f1/story"}
                for a in load("racing_news_f1.json")["articles"]]

    ApiService.get_race_event = staticmethod(race_event)
    ApiService.get_racing_schedule = staticmethod(
        lambda series, year: racing.parse_schedule(load(f"racing_season_{slug[series]}_2026.json")))
    ApiService.get_racing_standings = staticmethod(standings)
    ApiService.get_news = staticmethod(news)
    scores.announce = announced.append

    def wait_for(condition, ms=5000):
        clock = QElapsedTimer()
        clock.start()
        while not condition() and clock.elapsed() < ms:
            app.processEvents()
        return condition()

    def tab_labels(dialog):
        return [dialog.tab_widget.tabText(i) for i in range(dialog.tab_widget.count())]

    def is_table(page):
        return isinstance(page.content, scores.RacingTable)

    def headers(table):
        return [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]

    def message(page):
        return page.content.item(0).text() if isinstance(page.content, QListWidget) else None

    results = {}

    hub = scores.RacingHubDialog()
    results["the hub's title"] = hub.windowTitle() == "Racing - Sports Scores"
    results["the hub lists the three series"] = [
        hub.series_list.item(i).text() for i in range(hub.series_list.count())] == [
        "Formula 1", "IndyCar Series", "NASCAR Cup Series"]
    # Enter on a series opens it, and closing that leaves the hub open for the next one.
    opened = []
    real_series = scores.RacingSeriesDialog
    scores.RacingSeriesDialog = lambda key, parent: type("Stub", (), {"exec": lambda self: opened.append(key)})()
    hub.show()
    wait_for(lambda: hub.isVisible())
    hub.series_list.setFocus()
    QTest.keyClick(hub.series_list, Qt.Key.Key_Return)
    wait_for(lambda: False, ms=200)
    results["Enter on a series opens it and leaves the hub open"] = opened == ["F1"] and hub.isVisible()
    scores.RacingSeriesDialog = real_series
    hub.close()
    hub.deleteLater()

    f1 = scores.RacingSeriesDialog("F1")
    f1.show()
    loaded = wait_for(lambda: all(is_table(p) for p in (f1.race_page, f1.sessions_page, f1.schedule_page,
                                                         f1.drivers_page, f1.constructors_page))
                      and isinstance(f1.news_page.content, QListWidget) and f1.news_page.has_data)
    results["Formula 1 loads every tab"] = loaded
    results["Formula 1's title"] = f1.windowTitle() == "Formula 1 - Racing - Sports Scores"
    results["Formula 1's six tabs"] = tab_labels(f1) == [
        "Race", "Sessions", "Schedule", "Drivers", "Constructors", "News"]
    race = f1.race_page.content
    results["an entry list has no position column"] = (
        headers(race) == ["Driver", "Nationality"] and race.rowCount() == 22)
    results["the entry list says what it is, and when"] = race.accessible_name.startswith(
        "Entry List: MSC Cruises São Paulo Grand Prix. Autodromo Jose Carlos Pace. Sunday, November 8, ")
    results["all three views are filled"] = race.quick_list.count() == 22 and race.full_list.count() == 22
    results["sessions start on the race"] = f1.sessions_page.content.table_widget.currentRow() == 4
    schedule = f1.schedule_page.content
    results["the schedule has a circuit column"] = headers(schedule) == ["Race", "Circuit", "Date", "Result"]
    results["the schedule starts on the next race"] = (
        schedule.table_widget.item(schedule.table_widget.currentRow(), 0).text() == "MSC Cruises São Paulo Grand Prix")
    results["constructors have no nationality"] = headers(f1.constructors_page.content) == [
        "Pos", "Constructor", "Points"]
    results["the race label says it"] = f1.race_label.text().startswith("MSC Cruises São Paulo Grand Prix.")
    results["news headlines"] = f1.news_page.content.count() == 3

    # Enter in a table mustn't press Refresh: a reload would make a new table.
    f1.tab_widget.setCurrentWidget(f1.drivers_page)
    drivers = f1.drivers_page.content
    QTest.keyClick(drivers.table_widget, Qt.Key.Key_Return)
    wait_for(lambda: False, ms=200)
    results["Enter in a table doesn't refresh"] = f1.drivers_page.content is drivers

    # Tab from the tabs reaches the table before the buttons.
    # (Other pages' content sits between them too, but it's hidden, which Tab skips.)
    chain, widget = [], f1.tab_widget.tabBar().nextInFocusChain()
    while widget is not f1.tab_widget.tabBar() and len(chain) < 500:
        chain.append(widget)
        widget = widget.nextInFocusChain()
    buttons = [i for i, w in enumerate(chain) if isinstance(w, scores.QPushButton)]
    results["the loaded table comes after the tabs, before the buttons"] = (
        drivers.table_widget in chain and buttons and chain.index(drivers.table_widget) < min(buttons))

    # A refresh keeps the row and column someone was on.
    drivers.table_widget.setCurrentCell(5, 2)
    drivers.table_widget.setFocus()
    f1._load_all()
    wait_for(lambda: f1.drivers_page.content is not drivers)
    wait_for(lambda: False, ms=200)
    again = f1.drivers_page.content
    results["a refresh keeps the place in the table"] = (
        again is not drivers and again.table_widget.currentRow() == 5 and again.table_widget.currentColumn() == 2)

    # A refresh that fails keeps what's on show and says so once.
    failing["event"] = failing["standings"] = True
    f1._load_all()
    wait_for(lambda: len(announced) >= 1, ms=3000)
    wait_for(lambda: False, ms=300)
    results["a failed refresh keeps the tables"] = is_table(f1.race_page) and is_table(f1.drivers_page)
    # The race and the standings both fail; whichever answers first is said, and only that.
    results["and is said once"] = len(announced) == 1 and announced[0].startswith("ESPN isn't providing")
    failing["event"] = failing["standings"] = False
    f1.close()
    f1.deleteLater()

    indy = scores.RacingSeriesDialog("IndyCar")
    indy.show()
    wait_for(lambda: is_table(indy.race_page) and is_table(indy.schedule_page) and is_table(indy.drivers_page))
    results["IndyCar's four tabs"] = tab_labels(indy) == ["Race", "Schedule", "Standings", "News"]
    results["results have positions and whose row it is"] = (
        headers(indy.race_page.content) == ["Pos", "Driver", "Nationality"]
        and indy.race_page.content.ROW_CONTEXT_COLUMN == 1)
    results["IndyCar's schedule has no circuit column"] = headers(indy.schedule_page.content) == ["Race", "Date", "Result"]
    indy.close()
    indy.deleteLater()

    nascar = scores.RacingSeriesDialog("NASCAR")
    nascar.show()
    wait_for(lambda: (message(nascar.race_page) or "").endswith("isn't out yet.")
             and message(nascar.news_page) is not None and not message(nascar.news_page).startswith("Loading"))
    results["no entry list yet says so"] = (message(nascar.race_page) or "").endswith("The entry list isn't out yet.")
    results["no news says so"] = message(nascar.news_page) == "No NASCAR Cup Series news right now."
    nascar.close()
    nascar.deleteLater()

    # A first load that fails says so, and Enter on that row tries again.
    failing["event"] = True
    broken = scores.RacingSeriesDialog("IndyCar")
    broken.show()
    wait_for(lambda: (message(broken.race_page) or "").startswith("ESPN isn't"))
    row = broken.race_page.content.item(0)
    results["a failed race says so with a row to try again"] = (
        row.text().startswith("ESPN isn't providing this race")
        and row.data(Qt.ItemDataRole.UserRole) == scores.RETRY_ROW
        and (message(broken.schedule_page) or "").startswith("ESPN isn't"))
    failing["event"] = False
    before = calls["event"]
    broken.race_page.content.itemActivated.emit(row)
    results["Enter on it loads the race"] = wait_for(lambda: is_table(broken.race_page)) and calls["event"] == before + 1
    results["and the schedule with it"] = wait_for(lambda: is_table(broken.schedule_page))
    broken.close()
    broken.deleteLater()
    app.processEvents()
    return results


def test_the_racing_screens(tmp_path):
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
