"""The Windows Transactions dialog's running list and Go to Month (#188).

The dialog is built offscreen with its loaders stubbed out, and each load's answer is handed
to it as the loader would, so nothing here touches the network or runs Qt's event loop.
"""
import os
import sys
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

TODAY = (2026, 11)


def row(date, team, description):
    return {"date": date, "team": team, "description": description, "type": "", "player": "", "position": ""}


ROWS = [row("2026-11-07", "ATL", "Signed a kicker."), row("2026-11-06", "CLE", "Waived a back.")]


@pytest.fixture
def qt():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import scores
    with patch.object(scores, "announce") as said:
        yield scores, said
    del app


class Harness:
    """A dialog whose loads are recorded instead of started."""

    def __init__(self, scores):
        self.scores = scores
        self.started = []
        harness = self

        def load_next(dialog):
            if dialog._cursor is None or dialog._loading:
                return
            dialog._loading = True
            dialog.load_more_btn.setEnabled(False)
            item = scores.QListWidgetItem("Loading transactions..." if dialog._first_load
                                          else "Loading older transactions...")
            dialog.trans_list.addItem(item)
            harness.started.append((dict(dialog._cursor), dialog.current_team_id, item, dialog._generation))

        with patch.object(scores.TransactionsDialog, "_load_teams"), \
                patch.object(scores.TransactionsDialog, "_load_next", load_next):
            self.dialog = scores.TransactionsDialog("NFL", today=TODAY)
        # Keep stubbing after construction.
        self.dialog._load_next = lambda: load_next(self.dialog)

    def answer(self, rows, following, oldest_year=2026, which=-1, skipped=()):
        cursor, _team, item, generation = self.started[which]
        self.dialog._on_loaded({"rows": rows, "next": following, "oldest_year": oldest_year,
                                "skipped": list(skipped)}, item, generation)

    def texts(self):
        lst = self.dialog.trans_list
        return [lst.item(i).text() for i in range(lst.count())]


@pytest.fixture
def harness(qt):
    scores, _ = qt
    return Harness(scores)


class TestNewestFirst:
    def test_opens_on_the_newest(self, harness):
        dialog = harness.dialog
        assert harness.started[0][0] == {"year": 2026, "month": None, "page": 1}
        assert dialog.windowTitle() == "Transactions — NFL — Sports Scores"
        assert dialog.trans_list.accessibleName() == "NFL Transactions, newest first"
        assert dialog.position_label.text() == "Newest first"
        assert harness.texts() == ["Loading transactions..."]

    def test_the_first_load_shows_rows_and_offers_more(self, harness):
        harness.answer(ROWS, {"year": 2026, "month": None, "page": 2})
        assert harness.texts() == ["2026-11-07 — ATL — Signed a kicker.", "2026-11-06 — CLE — Waived a back."]
        assert harness.dialog.trans_list.currentRow() == 0
        assert harness.dialog.load_more_btn.isEnabled()

    def test_load_more_appends_older_and_moves_to_the_first_new_row(self, qt, harness):
        _, said = qt
        harness.answer(ROWS, {"year": 2026, "month": None, "page": 2})
        harness.dialog._load_more()
        assert harness.started[-1][0] == {"year": 2026, "month": None, "page": 2}
        assert harness.texts()[-1] == "Loading older transactions..."
        assert not harness.dialog.load_more_btn.isEnabled(), "not twice at once"
        harness.answer([row("2026-11-05", "KC", "Released a corner.")], {"year": 2026, "month": None, "page": 3})
        assert harness.texts()[-1] == "2026-11-05 — KC — Released a corner."
        assert harness.dialog.trans_list.currentRow() == 2
        said.assert_called_once_with("1 more transactions loaded.")

    def test_nothing_older_ends_the_list_and_says_so(self, harness):
        harness.answer(ROWS, None, oldest_year=2001)
        assert harness.texts()[-1] == "No older transactions. The list goes back to January 2001."
        assert not harness.dialog.load_more_btn.isEnabled()

    def test_a_load_more_that_finds_nothing_says_how_far_back_it_looked(self, qt, harness):
        _, said = qt
        harness.answer(ROWS, {"year": 2026, "month": None, "page": 2})
        harness.dialog._load_more()
        harness.answer([], {"year": 2020, "month": None, "page": 1}, oldest_year=2021)
        said.assert_called_once_with("No older transactions found back to January 2021.")
        assert harness.dialog.load_more_btn.isEnabled()

    def test_a_league_with_nothing_says_so_plainly(self, harness):
        harness.answer([], {"year": 2021, "month": None, "page": 1}, oldest_year=2022)
        assert harness.texts() == ["No transactions since January 2022."]
        assert harness.dialog.load_more_btn.isEnabled()


class TestReachingTheEnd:
    def test_down_on_the_last_row_loads_older(self, qt, harness):
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent
        _, said = qt
        dialog = harness.dialog
        harness.answer(ROWS, {"year": 2026, "month": None, "page": 2})
        dialog.trans_list.setCurrentRow(1)
        down = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
        assert dialog.eventFilter(dialog.trans_list, down) is True
        assert harness.started[-1][0]["page"] == 2
        said.assert_called_once_with("Loading older transactions.")
        # Again while it loads: nothing more is asked for.
        dialog.eventFilter(dialog.trans_list, down)
        assert len(harness.started) == 2

    def test_down_elsewhere_or_with_nothing_older_is_just_down(self, harness):
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent
        dialog = harness.dialog
        harness.answer(ROWS, {"year": 2026, "month": None, "page": 2})
        down = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
        dialog.trans_list.setCurrentRow(0)
        assert dialog.eventFilter(dialog.trans_list, down) is False
        dialog._cursor = None
        dialog.trans_list.setCurrentRow(dialog.trans_list.count() - 1)
        assert dialog.eventFilter(dialog.trans_list, down) is False
        assert len(harness.started) == 1


class TestGoToMonth:
    def jump(self, harness, month):
        class Picker:
            def __init__(self, subject, months, shown, parent=None):
                Picker.seen = (subject, months[0], months[-1], shown)

            def exec(self):
                return harness.scores.QDialog.DialogCode.Accepted

            def selected_month(self):
                return month

        with patch.object(harness.scores, "MonthPickerDialog", Picker):
            harness.dialog._go_to_month()
        return Picker.seen

    def test_a_month_starts_the_list_at_its_end(self, harness):
        seen = self.jump(harness, (2003, 3))
        assert seen == ("NFL Transactions", (2026, 11), (2001, 1), (2026, 11))
        dialog = harness.dialog
        assert harness.started[-1][0] == {"year": 2003, "month": 3, "page": 1}
        assert dialog.windowTitle() == "Transactions from March 2003 — NFL — Sports Scores"
        assert dialog.trans_list.accessibleName() == "NFL Transactions from March 2003, newest first"
        assert dialog.position_label.text() == "From March 2003, newest first"
        assert self.jump(harness, (2003, 3))[3] == (2003, 3), "opens on the month shown"

    def test_an_empty_month_says_so_above_the_older_ones(self, harness):
        self.jump(harness, (2003, 3))
        harness.answer([row("2003-02-27", "CHI", "Signed a guard.")], {"year": 2003, "month": 3, "page": 2})
        assert harness.texts() == ["No transactions in March 2003. Older ones follow.",
                                   "2003-02-27 — CHI — Signed a guard."]
        assert harness.dialog.trans_list.currentRow() == 0

    def test_a_month_with_some_has_no_notice(self, harness):
        self.jump(harness, (2026, 3))
        harness.answer([row("2026-03-31", "CHI", "Signed a guard.")], None)
        assert harness.texts()[0] == "2026-03-31 — CHI — Signed a guard."

    def test_nothing_at_all_from_a_jump(self, harness):
        self.jump(harness, (2003, 3))
        harness.answer([], {"year": 1998, "month": None, "page": 1}, oldest_year=2001)
        assert harness.texts() == ["No transactions from January 2001 to March 2003."]

    def test_a_month_espn_cant_give_says_so_not_that_it_had_none(self, harness):
        self.jump(harness, (2003, 3))
        harness.answer([row("2002-12-30", "CHI", "Signed a guard.")], {"year": 2002, "month": None, "page": 2},
                       oldest_year=2002, skipped=[{"year": 2003, "below": False}])
        assert harness.texts() == [
            "ESPN couldn't provide some of 2003's transactions, so the list goes on with 2002.",
            "2002-12-30 — CHI — Signed a guard."]

    def test_a_skip_below_what_was_found(self, harness):
        harness.answer([row("2026-01-02", "", "January.")], {"year": 2025, "month": None, "page": 1},
                       skipped=[{"year": 2026, "below": True}])
        assert harness.texts() == ["2026-01-02 — January.",
                                   "ESPN couldn't provide some of 2026's transactions, so the list goes on with 2025."]

    def test_a_load_more_that_only_skips_says_so(self, qt, harness):
        _, said = qt
        harness.answer(ROWS, {"year": 2026, "month": None, "page": 2})
        harness.dialog._load_more()
        harness.answer([], {"year": 2025, "month": None, "page": 1}, skipped=[{"year": 2026, "below": False}])
        said.assert_called_once_with("ESPN couldn't provide some of 2026's transactions, so the list goes on with 2025.")

    def test_the_current_month_goes_back_to_the_newest(self, harness):
        self.jump(harness, (2003, 3))
        self.jump(harness, (2026, 11))
        assert harness.started[-1][0] == {"year": 2026, "month": None, "page": 1}
        assert harness.dialog.windowTitle() == "Transactions — NFL — Sports Scores"

    def test_cancel_changes_nothing(self, harness):
        class Cancelled:
            def __init__(self, *args, **kwargs):
                pass

            def exec(self):
                return harness.scores.QDialog.DialogCode.Rejected

        with patch.object(harness.scores, "MonthPickerDialog", Cancelled):
            harness.dialog._go_to_month()
        assert len(harness.started) == 1

    def test_a_load_from_before_the_jump_is_dropped(self, harness):
        self.jump(harness, (2003, 3))
        harness.answer(ROWS, {"year": 2026, "month": None, "page": 2}, which=0)
        assert harness.texts() == ["Loading transactions..."]
        harness.answer([row("2003-03-03", "CHI", "Signed a guard.")], None)
        assert harness.texts()[0] == "2003-03-03 — CHI — Signed a guard."


class TestTeamFilter:
    def test_a_team_keeps_the_month_and_is_named(self, harness):
        dialog = harness.dialog
        dialog._on_teams_loaded([{"team_name": "Chicago Bears", "team_id": "3"}])
        TestGoToMonth().jump(harness, (2003, 3))
        dialog.team_combo.setCurrentIndex(1)
        cursor, team, _item, _gen = harness.started[-1]
        assert (cursor, team) == ({"year": 2003, "month": 3, "page": 1}, "3")
        assert dialog.windowTitle() == "Transactions from March 2003 — Chicago Bears — NFL — Sports Scores"
        harness.answer([], None, oldest_year=2001)
        assert harness.texts() == ["No Chicago Bears transactions from January 2001 to March 2003."]


class TestMonthPicker:
    def test_lists_every_month_newest_first_and_opens_on_the_one_shown(self, qt):
        scores, _ = qt
        import transactions_paging
        months = transactions_paging.months_back(2026, 11)
        dialog = scores.MonthPickerDialog("NFL Transactions", months, (2003, 3))
        lst = dialog.month_list
        assert dialog.windowTitle() == "Go to Month - NFL Transactions"
        assert lst.count() == 311
        assert lst.item(0).text() == "November 2026, current month"
        assert lst.item(1).text() == "October 2026"
        assert lst.item(lst.count() - 1).text() == "January 2001"
        assert lst.currentItem().text() == "March 2003"
        assert dialog.selected_month() == (2003, 3)
        assert lst.accessibleName() == "Month"

    def test_a_month_not_listed_opens_on_the_current(self, qt):
        scores, _ = qt
        import transactions_paging
        dialog = scores.MonthPickerDialog("NFL Transactions", transactions_paging.months_back(2026, 11), (1990, 1))
        assert dialog.selected_month() == (2026, 11)
