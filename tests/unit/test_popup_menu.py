"""Context menus open with their first item selected, so a screen reader speaks at once
instead of waiting for an arrow key.

Real menus are shown offscreen, which runs Qt's event loop. Earlier tests in the suite
leave loaders and timers behind for widgets they've deleted, and an event loop here would
deliver them and abort the run, so the menus run in a process of their own: this file,
run as a script."""
import os
import subprocess
import sys

import pytest

pytest.importorskip("PyQt6")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _selected_on_open(menu, exec_, wait_ms=2000):
    """The item selected after the menu opens, with no key pressed: the first one that
    turns up within `wait_ms`, or None if nothing is selected by then.

    Watched rather than read once at a fixed moment: the first menu in a fresh process can
    take a while to show on a cold CI runner, and a single early look then sees nothing."""
    from PyQt6.QtCore import QElapsedTimer, QPoint, QTimer

    seen = []
    clock = QElapsedTimer()
    clock.start()
    poll = QTimer(menu)

    def look():
        if menu.isVisible() and (menu.activeAction() is not None or clock.elapsed() >= wait_ms):
            poll.stop()
            seen.append(menu.activeAction())
            menu.close()

    poll.timeout.connect(look)
    poll.start(20)
    exec_(menu, QPoint(20, 20))
    return seen


def run_checks():
    """Each check, by name, and whether it held. Run in its own process."""
    from PyQt6.QtCore import QPoint, Qt, QTimer
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QMenu

    from popup_menu import exec_menu

    app = QApplication.instance() or QApplication([])  # noqa: F841 (kept alive)
    results = {}

    menu = QMenu()
    first = menu.addAction("Game Details")
    menu.addAction("Listen to the Game")
    results["first item is selected as the menu opens"] = _selected_on_open(menu, exec_menu) == [first]

    menu = QMenu()
    menu.addSeparator()
    first = menu.addAction("Open Pitch Explorer")
    results["a leading separator is passed over"] = _selected_on_open(menu, exec_menu) == [first]

    # The silence this fixes: without the helper, nothing is selected until a key.
    menu = QMenu()
    menu.addAction("Game Details")
    results["a plain menu opens with nothing selected"] = (
        _selected_on_open(menu, lambda m, p: m.exec(p), wait_ms=500) == [None])

    # A submenu first is selected, not opened.
    menu = QMenu()
    submenu = menu.addMenu("More")
    submenu.addAction("Inside")
    seen = _selected_on_open(menu, exec_menu)
    results["a submenu first is selected, not opened"] = (
        seen == [submenu.menuAction()] and not submenu.isVisible())

    # The first item is already selected, so one Down reaches the second.
    menu = QMenu()
    first = menu.addAction("Game Details")
    second = menu.addAction("Listen to the Game")
    poll = QTimer(menu)

    def choose():
        # Once the helper has selected the first item, as someone would hear it.
        if menu.activeAction() is first:
            poll.stop()
            QTest.keyClick(menu, Qt.Key.Key_Down)
            QTest.keyClick(menu, Qt.Key.Key_Return)

    poll.timeout.connect(choose)
    poll.start(20)
    QTimer.singleShot(3000, menu.close)  # never hang the run if nothing gets selected
    results["Down then Enter chooses the second item"] = exec_menu(menu, QPoint(20, 20)) is second
    return results


def test_menus_open_on_their_first_item():
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONPATH=ROOT)
    run = subprocess.run([sys.executable, os.path.abspath(__file__)], cwd=ROOT, env=env,
                         capture_output=True, text=True, timeout=60)
    lines = [line for line in run.stdout.splitlines() if line.startswith(("PASS ", "FAIL "))]
    assert run.returncode == 0 and len(lines) == 5, run.stdout + run.stderr
    assert all(line.startswith("PASS ") for line in lines), "\n".join(lines)


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    outcome = run_checks()
    for name, held in outcome.items():
        print(("PASS " if held else "FAIL ") + name)
    sys.exit(0)
