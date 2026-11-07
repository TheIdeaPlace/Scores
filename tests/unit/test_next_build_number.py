"""The iOS release's build number: max(highest App Store Connect build + 1, commit count).

iOS/SportsScoresApp/scripts/next_build_number.py is loaded from its path; it
is a workflow script, not part of the app. The network is never touched: the
App Store Connect client modules are replaced with fakes.
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parents[2]
          / "iOS" / "SportsScoresApp" / "scripts" / "next_build_number.py")


@pytest.fixture(scope="module")
def nbn():
    spec = importlib.util.spec_from_file_location("next_build_number", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- parse_build_number -----------------------------------------------------

@pytest.mark.parametrize("version, expected", [
    ("395", 395),
    ("1", 1),
    (" 42 ", 42),
    ("395.1", 395),
    ("10.2.3", 10),
    (396, 396),
    ("", None),
    (None, None),
    ("abc", None),
    ("1.0b", None),
    ("-5", None),
    ("3.", None),
])
def test_parse_build_number(nbn, version, expected):
    assert nbn.parse_build_number(version) == expected


# --- highest_build ----------------------------------------------------------

def test_highest_build_compares_numbers_not_strings(nbn):
    # As strings "99" > "395"; as numbers it isn't.
    assert nbn.highest_build(["99", "395", "100"]) == 395


def test_highest_build_skips_unparseable(nbn):
    assert nbn.highest_build(["junk", None, "12", "7.4"]) == 12


def test_highest_build_none_when_nothing_parses(nbn):
    assert nbn.highest_build([]) is None
    assert nbn.highest_build([None, "x"]) is None


def test_build_versions_reads_a_builds_page(nbn):
    page = {"data": [{"attributes": {"version": "395"}},
                     {"attributes": {"version": "396"}},
                     {"attributes": {}},
                     {}]}
    assert nbn.build_versions(page) == ["395", "396", None, None]
    assert nbn.build_versions({}) == []


# --- choose_build_number ----------------------------------------------------

def test_issue_112_squash_merge_collision(nbn):
    # Build 395 came from a branch; main then landed on a count of 395 too.
    assert nbn.choose_build_number(395, 395) == 396


def test_commit_count_wins_when_ahead(nbn):
    assert nbn.choose_build_number(420, 395) == 420


def test_hand_override_becomes_the_floor(nbn):
    # A build uploaded by hand far ahead lifts every later build past it.
    assert nbn.choose_build_number(400, 1000) == 1001


def test_no_existing_builds_uses_commit_count(nbn):
    assert nbn.choose_build_number(395, None) == 395


def test_existing_one_behind_commit_count(nbn):
    assert nbn.choose_build_number(396, 395) == 396


# --- fetch_highest_build, with fake API clients -------------------------------

class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    def json(self):
        return self._payload


def install_fakes(monkeypatch, responses):
    """Fake jwt and requests; `responses` maps a URL to its response."""
    calls = []
    fake_jwt = types.ModuleType("jwt")
    fake_jwt.encode = lambda *a, **k: "token"
    fake_requests = types.ModuleType("requests")

    def get(url, params=None, timeout=None, headers=None):
        calls.append((url, params))
        return responses[url]

    fake_requests.get = get
    monkeypatch.setitem(sys.modules, "jwt", fake_jwt)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setenv("ASC_ISSUER_ID", "issuer")
    monkeypatch.setenv("ASC_KEY_ID", "key")
    monkeypatch.setenv("ASC_KEY_P8", "pem")
    return calls


def test_fetch_follows_every_page(nbn, monkeypatch):
    api = nbn.API
    page2 = api + "/builds?cursor=2"
    calls = install_fakes(monkeypatch, {
        api + "/apps": FakeResponse({"data": [
            {"id": "app1", "attributes": {"bundleId": "com.sportsscores.app"}}]}),
        api + "/builds": FakeResponse({
            "data": [{"attributes": {"version": "120"}}, {"attributes": {"version": "395"}}],
            "links": {"next": page2}}),
        page2: FakeResponse({"data": [{"attributes": {"version": "99"}}], "links": {}}),
    })
    assert nbn.fetch_highest_build("com.sportsscores.app") == 395
    assert [url for url, _ in calls] == [api + "/apps", api + "/builds", page2]
    assert calls[1][1]["filter[app]"] == "app1"


def test_fetch_raises_on_http_error(nbn, monkeypatch):
    install_fakes(monkeypatch, {nbn.API + "/apps": FakeResponse({"errors": []}, status=401)})
    with pytest.raises(RuntimeError, match="401"):
        nbn.fetch_highest_build("com.sportsscores.app")


def test_fetch_null_next_link_ends_pagination(nbn, monkeypatch):
    api = nbn.API
    install_fakes(monkeypatch, {
        api + "/apps": FakeResponse({"data": [
            {"id": "app1", "attributes": {"bundleId": "com.sportsscores.app"}}]}),
        api + "/builds": FakeResponse({"data": [{"attributes": {"version": "7"}}],
                                       "links": {"self": "x", "next": None}}),
    })
    assert nbn.fetch_highest_build("com.sportsscores.app") == 7


def test_fetch_endless_pagination_raises(nbn, monkeypatch):
    api = nbn.API
    loop = api + "/builds?cursor=loop"
    page = FakeResponse({"data": [{"attributes": {"version": "1"}}], "links": {"next": loop}})
    install_fakes(monkeypatch, {
        api + "/apps": FakeResponse({"data": [
            {"id": "app1", "attributes": {"bundleId": "com.sportsscores.app"}}]}),
        api + "/builds": page,
        loop: page,
    })
    with pytest.raises(RuntimeError, match="pages"):
        nbn.fetch_highest_build("com.sportsscores.app")


def test_fetch_rejects_a_different_app(nbn, monkeypatch):
    install_fakes(monkeypatch, {nbn.API + "/apps": FakeResponse({"data": [
        {"id": "other", "attributes": {"bundleId": "com.sportsscores.app.widget"}}]})})
    with pytest.raises(RuntimeError, match="no app"):
        nbn.fetch_highest_build("com.sportsscores.app")


def test_warning_is_one_line(nbn, capsys):
    nbn.warn("failed (401): {\n  \"errors\": [\n  ]\n}")
    err = capsys.readouterr().err
    assert err == '::warning::failed (401): { "errors": [ ] }\n'


def test_fetch_raises_when_app_missing(nbn, monkeypatch):
    install_fakes(monkeypatch, {nbn.API + "/apps": FakeResponse({"data": []})})
    with pytest.raises(RuntimeError, match="no app"):
        nbn.fetch_highest_build("com.sportsscores.app")


# --- main ---------------------------------------------------------------------

def test_main_prints_only_the_number(nbn, monkeypatch, capsys):
    monkeypatch.setenv("BUNDLE_ID", "com.sportsscores.app")
    monkeypatch.setattr(nbn, "fetch_highest_build", lambda bundle: 395)
    nbn.main(["next_build_number.py", "395"])
    out, err = capsys.readouterr()
    assert out == "396\n"
    assert "using build 396" in err


def test_main_falls_back_to_commit_count_with_warning(nbn, monkeypatch, capsys):
    monkeypatch.setenv("BUNDLE_ID", "com.sportsscores.app")

    def boom(bundle):
        raise RuntimeError("network down")

    monkeypatch.setattr(nbn, "fetch_highest_build", boom)
    nbn.main(["next_build_number.py", "395"])
    out, err = capsys.readouterr()
    assert out == "395\n"
    assert err.startswith("::warning::")
    assert "network down" in err


def test_main_falls_back_when_bundle_id_unset(nbn, monkeypatch, capsys):
    monkeypatch.delenv("BUNDLE_ID", raising=False)
    nbn.main(["next_build_number.py", "12"])
    out, err = capsys.readouterr()
    assert out == "12\n"
    assert "::warning::" in err


@pytest.mark.parametrize("argv", [
    ["next_build_number.py"],
    ["next_build_number.py", "abc"],
    ["next_build_number.py", "3.1"],
    ["next_build_number.py", "1", "2"],
])
def test_main_rejects_bad_arguments(nbn, argv):
    with pytest.raises(SystemExit) as exc:
        nbn.main(argv)
    assert exc.value.code != 0
