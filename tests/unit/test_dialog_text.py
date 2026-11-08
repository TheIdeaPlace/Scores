"""A dialog's text goes after its controls in the accessibility order, so JAWS doesn't keep it
and say it again after the dialog has closed (dialog_text.py). Builds Qt widgets (offscreen),
so run this in the test VM or CI, not on a PC someone is using."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                             QListWidget, QMainWindow, QMessageBox, QPushButton, QScrollArea,
                             QStackedWidget, QTabWidget, QVBoxLayout, QWidget)

import dialog_text
from dialog_text import DialogTextOrder, put_text_after_controls

DIRECT = Qt.FindChildOption.FindDirectChildrenOnly


@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication([])
    order = DialogTextOrder()
    app.installEventFilter(order)
    yield app
    app.removeEventFilter(order)


def children(widget):
    return [w for w in widget.findChildren(QWidget, options=DIRECT) if not w.isWindow()]


def focus_chain(dialog):
    chain, w = [], dialog.nextInFocusChain()
    while w is not dialog and len(chain) < 100:
        chain.append(w)
        w = w.nextInFocusChain()
    return chain


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
    dialog.layout().removeWidget(label)  # build the old order again, on screen as it was
    dialog.layout().insertWidget(0, label)
    label.stackUnder(news)
    app.processEvents()
    assert children(dialog)[0] is label
    before = {w: w.geometry() for w in (label, news, row)}
    chain = focus_chain(dialog)
    put_text_after_controls(dialog)
    app.processEvents()
    try:
        assert children(dialog) == [news, row, label]
        assert {w: w.geometry() for w in (label, news, row)} == before
        assert label.y() < news.y()  # still shown above the list
        assert focus_chain(dialog) == chain
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


def test_click_focus_alone_isnt_a_control(app):
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    selectable = QLabel("Selectable text")
    selectable.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    assert selectable.focusPolicy() != Qt.FocusPolicy.NoFocus  # Qt gives it click focus
    lst = QListWidget()
    layout.addWidget(selectable)
    layout.addWidget(lst)
    put_text_after_controls(dialog)
    assert children(dialog) == [lst, selectable]


def test_a_child_dialog_is_neither_counted_nor_reordered(app):
    parent = QDialog()
    layout = QVBoxLayout(parent)
    holder = QWidget()  # its only control is in a dialog parented to it
    QVBoxLayout(holder).addWidget(QLabel("Holder text"))
    child = QDialog(holder)
    inner_label, inner_button = QLabel("Inner"), QPushButton("Inner button")
    child_layout = QVBoxLayout(child)
    child_layout.addWidget(inner_label)
    child_layout.addWidget(inner_button)
    lst = QListWidget()
    layout.addWidget(holder)
    layout.addWidget(lst)
    child.show()  # orders itself as it shows
    assert children(child) == [inner_button, inner_label]
    inner_label.stackUnder(inner_button)  # so a pass over the parent would show if it went in
    try:
        put_text_after_controls(parent)
        assert children(parent) == [lst, holder]  # the child's button doesn't make holder a control
        assert children(child) == [inner_label, inner_button]
        assert child.parent() is holder
    finally:
        child.close()


def test_a_tab_page_and_a_scroll_area_are_looked_inside(app):
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    tabs = QTabWidget()
    page = QWidget()
    note = QLabel("No statistical leaders available for the Bears.")
    page_list = QListWidget()
    page_layout = QVBoxLayout(page)
    page_layout.addWidget(note)
    page_layout.addWidget(page_list)
    tabs.addTab(page, "Leaders")
    scroll = QScrollArea()
    inner = QWidget()
    loading = QLabel("Loading group standings...")
    groups = QListWidget()
    inner_layout = QVBoxLayout(inner)
    inner_layout.addWidget(loading)
    inner_layout.addWidget(groups)
    scroll.setWidget(inner)
    tabs.addTab(scroll, "Groups")
    layout.addWidget(tabs)
    put_text_after_controls(dialog)
    assert children(page) == [page_list, note]
    assert children(inner) == [groups, loading]


def test_a_stacked_widget_keeps_its_pages(app):
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    stack = QStackedWidget()
    text_page, list_page = QLabel("Loading..."), QListWidget()
    stack.addWidget(text_page)
    stack.addWidget(list_page)
    stack.setCurrentIndex(1)
    layout.addWidget(stack)
    dialog.show()
    try:
        assert stack.widget(0) is text_page and stack.currentWidget() is list_page
        assert list_page.isVisible() and not text_page.isVisible()
    finally:
        dialog.close()


def test_a_button_box(app):
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    note = QLabel("Choose a season")
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    layout.addWidget(note)
    layout.addWidget(box)
    put_text_after_controls(dialog)
    assert children(dialog) == [box, note]
    assert [b.text().replace("&", "") for b in box.buttons()] == ["OK", "Cancel"]


def test_a_dialog_with_nothing_focusable(app):
    dialog = QDialog()  # the "Checking for updates" progress has no button
    layout = QVBoxLayout(dialog)
    first, second = QLabel("Checking for updates..."), QLabel("Please wait")
    layout.addWidget(first)
    layout.addWidget(second)
    put_text_after_controls(dialog)
    assert children(dialog) == [first, second]


def test_a_message_box_message_follows_its_buttons(app):
    box = QMessageBox(QMessageBox.Icon.Information, "No Link", "No web link available for this story.")
    box.show()
    try:
        kids = [w for w in children(box) if not w.isHidden()]
        message = next(w for w in kids if isinstance(w, QLabel) and w.text().startswith("No web"))
        buttons = next(w for w in kids if isinstance(w, QDialogButtonBox))
        assert kids.index(buttons) < kids.index(message)
        assert box.text() == "No web link available for this story."
    finally:
        box.close()


def test_it_runs_again_when_the_dialog_is_activated(app):
    dialog, label, news, row = news_dialog()
    dialog.show()
    try:
        late = QLabel("Rebuilt after it opened")
        dialog.layout().insertWidget(0, late)
        late.show()
        late.stackUnder(news)  # before the list, as a rebuilt page could be
        assert children(dialog).index(late) < children(dialog).index(news)
        app.sendEvent(dialog, QEvent(QEvent.Type.WindowActivate))
        assert children(dialog).index(late) > children(dialog).index(news)
    finally:
        dialog.close()


def test_an_error_is_logged_not_raised(app, monkeypatch):
    def boom(widget):
        raise RuntimeError("wrapped C/C++ object has been deleted")
    logged = []
    monkeypatch.setattr(dialog_text, "put_text_after_controls", boom)
    monkeypatch.setattr("error_log.log_handled", lambda: logged.append(True))
    dialog = QDialog()
    assert DialogTextOrder().eventFilter(dialog, QEvent(QEvent.Type.Show)) is False
    assert logged == [True]


def test_only_dialogs(app):
    widget = QWidget()
    layout = QVBoxLayout(widget)
    label, lst = QLabel("Select a League:"), QListWidget()
    layout.addWidget(label)
    layout.addWidget(lst)
    widget.show()  # the main window's views keep their order
    try:
        assert children(widget) == [label, lst]
    finally:
        widget.close()
