"""A dialog's text goes after its controls in the accessibility order, so JAWS doesn't keep it
and say it again after the dialog has closed (dialog_text.py). Builds Qt widgets (offscreen),
so run this in the test VM or CI, not on a PC someone is using."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QListWidget, QMainWindow,
                             QMessageBox, QPushButton, QVBoxLayout, QWidget)

from dialog_text import DialogTextOrder, _takes_focus, put_text_after_controls

DIRECT = Qt.FindChildOption.FindDirectChildrenOnly


@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication([])
    order = DialogTextOrder()
    app.installEventFilter(order)
    yield app
    app.removeEventFilter(order)


def children(widget):
    return widget.findChildren(QWidget, options=DIRECT)


def news_dialog(parent=None):
    """The league News dialog's shape: an instruction, the list, a row of buttons."""
    dialog = QDialog(parent)
    layout = QVBoxLayout(dialog)
    label = QLabel("Press Enter or double-click a headline to open in your browser:")
    news = QListWidget()
    news.addItems(["One", "Two"])
    layout.addWidget(label)
    layout.addWidget(news)
    row = QWidget()
    buttons = QHBoxLayout(row)
    buttons.addWidget(QPushButton("Open Selected"))
    buttons.addWidget(QPushButton("Close"))
    layout.addWidget(row)
    return dialog, label, news, row


def test_the_label_goes_after_the_controls_when_the_dialog_shows(app):
    main = QMainWindow()
    dialog, label, news, row = news_dialog(main)
    assert children(dialog) == [label, news, row]  # as built
    dialog.show()
    try:
        assert children(dialog) == [news, row, label]
    finally:
        dialog.close()


def test_nothing_moves_on_screen_or_in_the_tab_order(app):
    dialog, label, news, row = news_dialog()
    dialog.show()
    app.processEvents()
    before = {w: w.geometry() for w in (label, news, row)}
    tab_chain_before = news.nextInFocusChain()
    put_text_after_controls(dialog)
    app.processEvents()
    try:
        assert {w: w.geometry() for w in (label, news, row)} == before
        assert label.y() < news.y()  # still shown above the list
        assert news.nextInFocusChain() is tab_chain_before
    finally:
        dialog.close()


def test_text_inside_a_container_goes_after_too(app):
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    header = QWidget()
    QVBoxLayout(header).addWidget(QLabel("Canadian Football League"))
    body = QWidget()
    body_layout = QVBoxLayout(body)
    status = QLabel("Loading the week...")
    games = QListWidget()
    body_layout.addWidget(status)
    body_layout.addWidget(games)
    layout.addWidget(header)
    layout.addWidget(body)
    put_text_after_controls(dialog)
    assert children(dialog) == [body, header]
    assert children(body) == [games, status]


def test_static_text_keeps_its_own_order(app):
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    first, second = QLabel("First"), QLabel("Second")
    lst = QListWidget()
    for w in (first, lst, second):
        layout.addWidget(w)
    put_text_after_controls(dialog)
    assert children(dialog) == [lst, first, second]


def test_a_hidden_control_doesnt_count(app):
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    box = QWidget()
    box_layout = QVBoxLayout(box)
    note = QLabel("No news headlines available.")
    hidden_list = QListWidget()
    box_layout.addWidget(note)
    box_layout.addWidget(hidden_list)
    hidden_list.hide()
    shown_list = QListWidget()
    layout.addWidget(box)
    layout.addWidget(shown_list)
    put_text_after_controls(dialog)
    assert children(dialog) == [shown_list, box]


def test_a_child_dialog_is_left_alone(app):
    parent, label, news, row = news_dialog()
    child = QDialog(parent)
    QVBoxLayout(child).addWidget(QLabel("Inner"))
    put_text_after_controls(parent)
    assert [w for w in children(parent) if not w.isWindow()] == [news, row, label]
    assert child.parent() is parent
    assert [type(w) for w in children(child)] == [QLabel]  # not reordered as part of the parent


def test_a_message_box_shows_as_before(app):
    # Its message takes click focus (it's selectable), so it counts as a control and stays
    # first; JAWS reads a message box as an alert anyway, and keeps nothing from it.
    box = QMessageBox(QMessageBox.Icon.Information, "No Link", "No web link available for this story.")
    box.show()
    try:
        message = next(w for w in children(box) if isinstance(w, QLabel) and w.text().startswith("No web"))
        assert _takes_focus(message)
        assert box.findChildren(QPushButton)[0].text() == "OK"
    finally:
        box.close()


def test_it_runs_again_when_the_dialog_is_activated(app):
    dialog, label, news, row = news_dialog()
    dialog.show()
    try:
        late = QLabel("Rebuilt after it opened")
        dialog.layout().insertWidget(0, late)  # a new child goes to the end of the list
        late.show()
        late.stackUnder(news)  # and here before the list, as a rebuilt page could be
        assert children(dialog).index(late) < children(dialog).index(news)
        app.sendEvent(dialog, QEvent(QEvent.Type.WindowActivate))
        assert children(dialog).index(late) > children(dialog).index(news)
    finally:
        dialog.close()
