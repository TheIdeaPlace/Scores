"""Keep JAWS from saying a closed dialog's text again.

As a dialog opens, JAWS reads its text: the static text that comes before the dialog's first
control that takes focus, in the accessibility tree's order. It keeps that text with the
window that owns the dialog, here the main window, and after the dialog has closed it says it
again each time it announces the main window: on Alt+Tab back, and on every title change, such
as Escape to the home screen. So, after a league's News, Kelly heard "Press Enter or
double-click a headline to open in your browser:" on screens that have no news at all. Only
the next dialog to open replaces it. Measured with JAWS 2027 (exact speech from its speech
history); NVDA keeps nothing, which is why NVDA runs never showed it.

Neither deleting the dialog, nor a label's buddy, nor an event on the main window stops it.
What does is for no static text to come before a dialog's first focusable control. Qt orders a
widget's accessible children as its children list, and raise_() moves a widget to the end of
that list, so putting every part of a dialog that holds nothing focusable after the parts that
do changes what JAWS reads as the dialog's text and leaves the screen as it was: a layout
places widgets, and these don't overlap. A message box's message is still read as it opens
(JAWS reads a message box as an alert), and nothing is kept.

DialogTextOrder does it for every dialog in the app, as it shows and each time it's activated
again (its content may have been rebuilt since).
"""

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QDialog, QWidget

_DIRECT = Qt.FindChildOption.FindDirectChildrenOnly


def _takes_focus(widget: QWidget) -> bool:
    """Whether the widget, or anything in it that isn't hidden, can take keyboard focus."""
    if widget.isHidden():
        return False
    for w in [widget] + widget.findChildren(QWidget):
        if w.isWindow() and w is not widget:
            continue  # another dialog parented here: not part of this one
        if w.focusPolicy() != Qt.FocusPolicy.NoFocus and (w is widget or w.isVisibleTo(widget)):
            return True
    return False


def put_text_after_controls(widget: QWidget) -> None:
    """Move each child of `widget` that holds nothing focusable after its siblings, in Qt's
    accessibility order, and do the same inside each child that isn't focusable itself but
    holds something that is. Their order among themselves, and every widget's place on screen
    and in the tab order, stay as they were."""
    for child in widget.findChildren(QWidget, options=_DIRECT):
        if child.isWindow():
            continue
        if not _takes_focus(child):
            child.raise_()
        elif child.focusPolicy() == Qt.FocusPolicy.NoFocus:
            put_text_after_controls(child)


class DialogTextOrder(QObject):
    """Application-wide (install on the QApplication): every dialog's text after its
    controls, as it shows and each time it's activated."""

    def eventFilter(self, obj, event):
        if (event.type() in (QEvent.Type.Show, QEvent.Type.WindowActivate)
                and isinstance(obj, QDialog) and obj.isWindow()):
            put_text_after_controls(obj)
        return super().eventFilter(obj, event)
