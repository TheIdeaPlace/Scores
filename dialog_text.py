"""Keep JAWS from saying a closed dialog's text again.

As a dialog opens, JAWS reads its text: the static text that comes before the dialog's first
control that takes focus, in the accessibility tree's order. It keeps that text with the
window that owns the dialog, here the main window, and after the dialog has closed it says it
again each time it announces the main window: on Alt+Tab back, and on every title change, such
as Escape to the home screen. So, after a league's News, Kelly heard "Press Enter or
double-click a headline to open in your browser:" on screens that have no news at all. Only
the next dialog to open replaces it. Measured with JAWS 2027 (exact speech from its speech
history); NVDA keeps nothing, which is why NVDA runs never showed it.

Neither deleting the dialog, nor a label's buddy, nor an event on the main window stops it,
and a dialog with no owner (or another owner) can't be left with Alt+Tab while it's open. What
does work is for no static text to come before a dialog's first focusable control. Qt orders a
widget's accessible children as its children list, and raise_() moves a widget to the end of
that list, so putting every part of a dialog that holds nothing focusable after the parts that
do changes what JAWS reads as the dialog's text and leaves the screen as it was: a layout
places widgets, and these don't overlap. The tab order is a list of its own and doesn't change.
A message box's message is still read as it opens (JAWS reads a message box as an alert), and
nothing is kept. What JAWS no longer reads by itself as a dialog opens is a heading or an
instruction above its first control; the window title and the control's own name still are.

DialogTextOrder does it for every dialog in the app, as it shows and each time it's activated
again (its content may have been rebuilt since).
"""

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QDialog, QScrollArea, QTabWidget, QWidget

_DIRECT = Qt.FindChildOption.FindDirectChildrenOnly


def _children(widget: QWidget):
    """The widget's child widgets that belong to its window (not another dialog parented to it)."""
    return [c for c in widget.findChildren(QWidget, options=_DIRECT) if not c.isWindow()]


def _tab_focus(widget: QWidget) -> bool:
    return bool(widget.focusPolicy() & Qt.FocusPolicy.TabFocus)


def _takes_focus(widget: QWidget) -> bool:
    """Whether the widget, or anything in it that isn't hidden, can be reached with Tab.
    A widget that only takes focus from a click is static text to a screen reader."""
    if widget.isHidden():
        return False
    if _tab_focus(widget):
        return True
    return any(_takes_focus(c) for c in _children(widget))


def _inner_pages(widget: QWidget):
    """What's inside a focusable container that has a layout of its own: a tab widget's pages,
    a scroll area's contents. Item views and the like are left alone."""
    if isinstance(widget, QTabWidget):
        return [widget.widget(i) for i in range(widget.count())]
    if isinstance(widget, QScrollArea):
        return [widget.widget()] if widget.widget() is not None else []
    return []


def put_text_after_controls(widget: QWidget) -> None:
    """Move each child of `widget` that holds nothing focusable after its siblings, in Qt's
    accessibility order, and do the same inside each child that holds something that is.
    Their order among themselves, and every widget's place on screen and in the tab order,
    stay as they were."""
    for child in _children(widget):
        if not _takes_focus(child):
            child.raise_()
        elif not _tab_focus(child):
            put_text_after_controls(child)
        for page in _inner_pages(child):
            put_text_after_controls(page)


class DialogTextOrder(QObject):
    """Application-wide (install on the QApplication): every dialog's text after its
    controls, as it shows and each time it's activated."""

    def eventFilter(self, obj, event):
        if (event.type() in (QEvent.Type.Show, QEvent.Type.WindowActivate)
                and isinstance(obj, QDialog) and obj.isWindow()):
            # An exception escaping an event filter ends the app under PyQt6; a dialog read in
            # the old order is the lesser loss.
            try:
                put_text_after_controls(obj)
            except Exception:
                import error_log
                error_log.log_handled()
        return False
