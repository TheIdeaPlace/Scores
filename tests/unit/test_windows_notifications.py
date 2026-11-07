"""announce() reaches the UIA call exactly once. The real call is replaced, so nothing
is sent to a screen reader on the machine running the tests."""
import windows_notifications as wn


def test_announce_raises_one_notification(monkeypatch):
    said = []
    monkeypatch.setattr(wn, "_raise_uia_notification", said.append)
    wn.announce("Monday, November 2")
    assert said == ["Monday, November 2"]


def test_helper_method_raises_one_notification(monkeypatch):
    said = []
    monkeypatch.setattr(wn, "_raise_uia_notification", said.append)
    wn.WindowsNotificationHelper().announce("Refreshing")
    assert said == ["Refreshing"]


def test_no_message_or_no_window_is_quiet(monkeypatch):
    monkeypatch.setattr(wn, "_notifier", None)
    assert wn._raise_uia_notification("") is False
    assert wn._raise_uia_notification("Hello") is False


def test_nothing_is_printed_in_place_of_speech(monkeypatch, capsys):
    """print is invisible in the windowed build, so it must never stand in for a notification."""
    monkeypatch.setattr(wn, "_notifier", None)
    wn.WindowsNotificationHelper().announce("Hello")
    wn.announce("Hello")
    assert capsys.readouterr() == ("", "")
