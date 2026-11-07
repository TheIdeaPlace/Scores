"""Popup menus that a screen reader announces as they open."""

from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

# Long enough for the popup to be the foreground window, too short to notice.
SELECT_DELAY_MS = 50


def exec_menu(menu, position):
    """Show a popup menu with its first item selected, and return what was chosen.

    A menu opened with nothing selected gives a screen reader no focus to speak, so JAWS
    and NVDA stay silent until an arrow key is pressed. Once it is showing, it gets the
    Down arrow someone would press, which selects the first item and is announced just as
    it would be then. Every context menu in the app opens through here."""
    def select_first():
        if menu.isVisible() and menu.activeAction() is None:
            for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                QApplication.postEvent(menu, QKeyEvent(kind, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier))

    # The menu's own timer, so it goes when the menu does. A free-standing one would
    # still fire after a menu that never opened was deleted, and reach a dead object.
    # A moment's wait, not none: Windows has to bring the popup's window forward first,
    # or a screen reader can drop the focus change from a window not yet in front.
    timer = QTimer(menu)
    timer.setSingleShot(True)
    timer.timeout.connect(select_first)
    timer.start(SELECT_DELAY_MS)
    return menu.exec(position)
