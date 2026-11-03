"""Stubbed ESPN for the replay tests: real payloads in, a record of every request out.

Nothing here touches Qt or the network. An unstubbed URL raises UnstubbedRequest,
which is a BaseException so the data layer's `except Exception` can't swallow it,
and the `espn` fixture fails the test at teardown even if a bare `except:` did.
"""
import copy
import json
import os
import re
from urllib.parse import urlencode

import requests

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "espn")

# ESPN answers a dates=START-END scoreboard range with a 400 (September 2026).
# Every replay test checks every URL against this at teardown.
DATE_RANGE = re.compile(r"dates=\d{4,8}-\d{4,8}")


def load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return json.load(f)


class UnstubbedRequest(BaseException):
    """A request no route answers. A test can't pass by reaching the real ESPN."""


class FakeResponse:
    def __init__(self, data=None, status=200, text=None, bad_json=False):
        self.status_code = status
        self._data = data
        self._bad_json = bad_json
        self.text = text if text is not None else ("" if data is None else json.dumps(data))
        self.headers = {}

    def json(self):
        if self._bad_json:
            raise requests.exceptions.JSONDecodeError("Expecting value", "<html>", 0)
        return copy.deepcopy(self._data)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


# The ways a request goes wrong. Each is what a route replies with.
TIMEOUT = requests.exceptions.Timeout("read timed out")
HTTP_404 = FakeResponse({"code": 404, "message": "not found"}, status=404)
HTTP_500 = FakeResponse({"code": 500, "message": "server error"}, status=500)
EMPTY_JSON = FakeResponse({})
NOT_JSON = FakeResponse(text="<html>Service Unavailable</html>", bad_json=True)


class FakeEspn:
    """Answers requests from routes, last one added winning, and records them."""

    def __init__(self):
        self.routes = []
        self.calls = []
        self.kwargs = []
        self.unstubbed = []

    def on(self, pattern, reply):
        """Reply to URLs matching a regex. A reply is JSON data, a FakeResponse,
        an exception to raise, or a function of the URL returning any of those."""
        self.routes.append((re.compile(pattern), reply))
        return self

    def __call__(self, url, **kwargs):
        full = url
        params = kwargs.get("params")
        if params:
            full += ("&" if "?" in url else "?") + urlencode(params)
        self.calls.append(full)
        self.kwargs.append(kwargs)
        for pattern, reply in reversed(self.routes):
            if pattern.search(full):
                return self._answer(reply, full)
        self.unstubbed.append(full)
        raise UnstubbedRequest(full)

    def _answer(self, reply, url):
        if callable(reply):
            reply = reply(url)
        if isinstance(reply, BaseException):
            raise reply
        if isinstance(reply, FakeResponse):
            return reply
        return FakeResponse(reply)

    def urls(self, pattern=""):
        return [u for u in self.calls if re.search(pattern, u)]


def mutations(payload, max_depth=8):
    """Every copy of a payload with one field missing, null, or an empty list.

    Walks dicts and the first element of each list, since ESPN's lists repeat a
    shape, and cuts lists to two items first so a big payload stays quick. Each
    result is (description, mutated copy).
    """

    def shrink(node):
        if isinstance(node, dict):
            return {key: shrink(value) for key, value in node.items()}
        if isinstance(node, list):
            return [shrink(item) for item in node[:2]]
        return node

    payload = shrink(payload)
    paths = []

    def walk(node, path):
        if len(path) >= max_depth:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                paths.append(path + (key,))
                walk(value, path + (key,))
        elif isinstance(node, list) and node:
            walk(node[0], path + (0,))

    walk(payload, ())
    for path in paths:
        for kind in ("missing", "null", "empty"):
            changed = copy.deepcopy(payload)
            node = changed
            for step in path[:-1]:
                node = node[step]
            if kind == "missing":
                del node[path[-1]]
            elif kind == "null":
                node[path[-1]] = None
            else:
                node[path[-1]] = []
            yield f"{'.'.join(map(str, path))} {kind}", changed
