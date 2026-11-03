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


def test_no_message_is_quiet():
    assert wn._raise_uia_notification("") is False
