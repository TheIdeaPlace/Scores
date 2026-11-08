"""Nothing a screen reader speaks may be decoration.

NVDA read "--- News Headlines ---" as "dash dash dash News Headlines dash dash dash", and
emoji by their names ("star", "baseball", "direct hit"). Rows, labels and buttons say words;
a heading is set apart by bold and its background, never by characters. This reads the
string literals in the files that build the app's text, without importing them, so it runs
anywhere, and fails if a marker or an emoji comes back.
"""
import ast
import os
import re

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")

# The files whose strings become rows, labels, buttons and announcements.
SOURCES = ["scores.py", "espn_api.py", "game_labels.py", "accessible_table.py", "live_play_format.py"]

MARKERS = re.compile(r"-{3,}|={3,}")
# Emoji, pictographs, arrows, stars, check marks, triangles and bullets: all read by name.
SYMBOLS = re.compile(
    "[\U0001F000-\U0001FFFF"   # emoji and pictographs
    "←-⇿"            # arrows
    "•"                   # bullet
    "☀-➿"            # misc symbols, dingbats: stars, check marks, the baseball
    "■-◿"            # geometric shapes: the play triangles
    "⬀-⯿"            # more arrows and stars
    "️]"                  # emoji presentation selector
)

# A disabled separator row on Home: drawn as a line, never focused or spoken by arrowing.
BOX_RULE = "─"


def _is_html(text):
    """The wrap-up and exported game log are web pages, read in the browser, not the app."""
    return bool(re.search(r"<\s*/?\s*(div|h[1-6]|p|ul|li|span|br|html|body|style|table|tr|td)\b", text))


def _docstring_nodes(tree):
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                found.add(id(body[0].value))
    return found


def _strings(path):
    """Every string literal in the file, f-string parts included, with its line; no docstrings."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    skip = _docstring_nodes(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            # Read whole, so a web page's f-string is known by its tags; not part by part.
            skip.update(id(v) for v in node.values)
            whole = "".join(v.value for v in node.values if isinstance(v, ast.Constant))
            yield node.lineno, whole
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            yield node.lineno, node.value


def _problems(path):
    out = []
    for line, text in _strings(path):
        if _is_html(text):
            continue
        if MARKERS.search(text):
            out.append((line, text))
        elif SYMBOLS.search(text.replace(BOX_RULE, "")):
            out.append((line, text))
    return out


@pytest.mark.parametrize("name", SOURCES)
def test_no_markers_or_emoji_in_spoken_strings(name):
    path = os.path.join(ROOT, name)
    if not os.path.exists(path):
        pytest.skip(f"{name} is gone")
    problems = _problems(path)
    assert not problems, "\n".join(
        f"{name}:{line}: {text[:80]!a}" for line, text in problems)


def test_the_check_finds_what_it_is_for(tmp_path):
    """The guard itself: each of the old offenders is caught, and a web page isn't."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        'a = "--- News Headlines ---"\n'
        'b = f"=== {x}, 5 ==="\n'
        'c = "★ Favorited"\n'
        'd = f"⚾ {header}"\n'
        'e = "Next Day ▶"\n'
        'f = "• fact"\n'
        'g = "<h2 class=\\"t\\">\U0001f3af Scoring Summary</h2>"\n'
        'h = "─" * 30\n'
        'i = "Standings"\n',
        encoding="utf-8")
    lines = sorted({line for line, _ in _problems(str(sample))})
    assert lines == [1, 2, 3, 4, 5, 6]
