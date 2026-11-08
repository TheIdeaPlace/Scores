"""macOS only, on the mac-build branch (#246): Return and Enter open a list or table row,
as they do on Windows.

On macOS, Qt's item views treat Return as "edit this item" and open a row with Command+O
instead, so every list in the app (games, teams, sections) ignored Enter. This filter gives
an item view the activation Windows gives it: when Return or Enter reaches a list, tree or
table that isn't editing, it emits `activated` for the current row and lets the key carry on,
which is what Qt does on Windows. Held-down Enter is skipped, as the app's tables skip it.
"""

import sys

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QAbstractItemView, QApplication


class ReturnActivates(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            mods = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
            view = obj if isinstance(obj, QAbstractItemView) else None
            if (view is not None and not event.isAutoRepeat() and mods == Qt.KeyboardModifier.NoModifier
                    and view.state() != QAbstractItemView.State.EditingState):
                index = view.currentIndex()
                if index.isValid():
                    view.activated.emit(index)
        return False


def install(app: QApplication):
    """Install the filter on macOS; elsewhere, do nothing."""
    if sys.platform != "darwin":
        return None
    keys = ReturnActivates(app)
    app.installEventFilter(keys)
    return keys
