"""The golf dialog on Windows: Enter on a schedule row opens that tournament's leaderboard
(scoreboard?dates=YYYYMMDD, picked by id), as the iPhone opens a past tournament (#189)."""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

FAILED = "ESPN isn't providing the leaderboard right now. Try again in a minute."

SCHEDULE = [
    {"id": "401811927", "name": "The Sentry", "start_date": "2026-01-08", "end_date": "2026-01-11",
     "status": "Canceled", "state": "post", "winner": ""},
    {"id": "401811928", "name": "Sony Open in Hawaii", "start_date": "2026-01-15", "end_date": "2026-01-18",
     "status": "Final", "state": "post", "winner": "Chris Gotterup (-16)"},
    {"id": "401850979", "name": "World Wide Technology Championship", "start_date": "2026-11-05",
     "end_date": "2026-11-08", "status": "In Progress", "state": "in", "winner": ""},
]

SONY = {"id": "401811928", "name": "Sony Open in Hawaii", "date": "2026-01-15", "end_date": "2026-01-18",
        "state": "post", "status_detail": "Final", "round_num": 4,
        "players": [{"position": 1, "name": "Chris Gotterup", "country": "USA", "total_score": "-16",
                     "rounds": ["-7", "-1", "-2", "-6"]}]}


class FakeSignal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def emit(self, *args):
        for slot in self.slots:
            slot(*args)


class FakeLoader:
    made = []

    def __init__(self, tour, date=None, event_id=None):
        self.tour, self.date, self.event_id = tour, date, event_id
        self.data_loaded = FakeSignal()
        self.error_occurred = FakeSignal()
        FakeLoader.made.append(self)

    def start(self):
        pass


class TestGolfDialog:
    @pytest.fixture(autouse=True)
    def qt(self):
        pytest.importorskip("PyQt6")
        from PyQt6.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication([])
        import scores
        self.scores = scores
        FakeLoader.made = []
        with patch.object(scores, "GolfLeaderboardLoader", FakeLoader), \
                patch.object(scores.GolfTournamentDialog, "_load_schedule"):
            yield

    @staticmethod
    def rows(lst):
        return [lst.item(i).text() for i in range(lst.count())]

    def dialog(self):
        dialog = self.scores.GolfTournamentDialog("PGA")
        dialog._on_schedule_loaded(SCHEDULE)
        return dialog

    def test_it_opens_on_the_current_tournament(self):
        self.dialog()
        assert [(l.tour, l.date, l.event_id) for l in FakeLoader.made] == [("PGA", None, None)]

    def test_schedule_rows_say_winners_and_carry_their_event(self):
        dialog = self.dialog()
        rows = self.rows(dialog.schedule_list)
        assert rows[0].startswith("[Canceled]") and "The Sentry" in rows[0]
        assert rows[1].startswith("[Final]") and rows[1].endswith("Chris Gotterup (-16)")
        assert rows[2].startswith("[Live]")
        from PyQt6.QtCore import Qt
        assert dialog.schedule_list.item(1).data(Qt.ItemDataRole.UserRole)["id"] == "401811928"

    def test_enter_on_a_row_opens_its_leaderboard(self):
        dialog = self.dialog()
        dialog.tab_widget.setCurrentIndex(1)
        dialog.schedule_list.itemActivated.emit(dialog.schedule_list.item(1))
        loader = FakeLoader.made[-1]
        assert (loader.date, loader.event_id) == ("2026-01-15", "401811928")
        assert dialog.tab_widget.currentIndex() == 0
        assert self.rows(dialog.leaderboard_list) == ["Loading Sony Open in Hawaii…"]
        assert dialog.tournament_label.text() == "Loading Sony Open in Hawaii…"

        loader.data_loaded.emit(SONY)
        assert "Chris Gotterup" in self.rows(dialog.leaderboard_list)[0]
        assert dialog.tournament_label.text().startswith("Sony Open in Hawaii  |  Final")
        assert dialog.windowTitle() == "Sony Open in Hawaii — PGA Tour — Sports Scores"

    def test_only_the_newest_answer_is_shown(self):
        dialog = self.dialog()
        current = FakeLoader.made[0]
        dialog._open_tournament(dialog.schedule_list.item(1))
        current.data_loaded.emit({"id": "401850979", "name": "World Wide Technology Championship",
                                  "players": [{"position": 1, "name": "Ben James", "total_score": "-20"}]})
        current.error_occurred.emit(FAILED)
        assert self.rows(dialog.leaderboard_list) == ["Loading Sony Open in Hawaii…"]
        assert dialog.leaderboard_list not in dialog._failed_lists
        FakeLoader.made[-1].data_loaded.emit(SONY)
        assert "Chris Gotterup" in self.rows(dialog.leaderboard_list)[0]

    def test_a_chosen_tournament_with_nothing_says_which(self):
        dialog = self.dialog()
        dialog._open_tournament(dialog.schedule_list.item(0))
        FakeLoader.made[-1].data_loaded.emit({})
        assert self.rows(dialog.leaderboard_list) == ["No leaderboard available for The Sentry."]
        assert dialog.tournament_label.text() == "The Sentry"

    def test_f5_after_a_chosen_tournament_fails_asks_for_it_again(self):
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent
        dialog = self.dialog()
        dialog._open_tournament(dialog.schedule_list.item(1))
        FakeLoader.made[-1].error_occurred.emit(FAILED)
        assert self.rows(dialog.leaderboard_list) == [FAILED]
        dialog.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F5, Qt.KeyboardModifier.NoModifier))
        assert (FakeLoader.made[-1].date, FakeLoader.made[-1].event_id) == ("2026-01-15", "401811928")

    def test_rows_that_are_not_tournaments_open_nothing(self):
        dialog = self.scores.GolfTournamentDialog("PGA")  # still "Loading schedule…"
        dialog._open_tournament(dialog.schedule_list.item(0))
        dialog._on_schedule_loaded([])
        dialog._open_tournament(dialog.schedule_list.item(0))
        assert len(FakeLoader.made) == 1
        assert dialog._chosen is None

    def test_enter_in_a_list_does_not_press_close(self):
        from PyQt6.QtWidgets import QPushButton
        dialog = self.dialog()
        assert not any(b.autoDefault() or b.isDefault() for b in dialog.findChildren(QPushButton))
