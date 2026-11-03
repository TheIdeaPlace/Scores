"""The last line of defence: nothing raises, the log is written, the speech is rate-limited."""
import sys

import error_log


def boom():
    try:
        raise ValueError("bad row")
    except ValueError:
        return sys.exc_info()


def test_logs_and_announces(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(error_log, "_last_announced", 0.0)
    said = []
    error_log.report_uncaught(*boom(), announce=said.append, now=lambda: 100.0)
    assert len(said) == 1
    assert "ValueError: bad row" in (tmp_path / "Scores" / "errors.log").read_text(encoding="utf-8")


def test_repeats_are_rate_limited(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(error_log, "_last_announced", 0.0)
    said = []
    for moment in (100.0, 110.0, 131.0):
        error_log.report_uncaught(*boom(), announce=said.append, now=lambda m=moment: m)
    assert len(said) == 2


def test_a_broken_announce_or_log_never_raises(monkeypatch):
    monkeypatch.setattr(error_log, "log_path", lambda: 1 / 0)
    monkeypatch.setattr(error_log, "_last_announced", 0.0)

    def broken(_):
        raise RuntimeError("no")
    error_log.report_uncaught(*boom(), announce=broken, now=lambda: 100.0)
