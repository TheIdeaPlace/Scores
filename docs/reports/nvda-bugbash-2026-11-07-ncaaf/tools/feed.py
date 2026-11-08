"""Look up games in the snapshot nearest a time.

    python -I feed.py <HHMMSS> <text to match in shortName or name>...   (or 'neutral' / 'all')
"""
import gzip
import json
import sys
from pathlib import Path

SNAP = Path(__file__).resolve().parent.parent / "snapshots"


def nearest(stamp):
    folders = sorted(p.name for p in SNAP.iterdir() if p.is_dir())
    before = [f for f in folders if f <= stamp]
    return SNAP / (before[-1] if before else folders[0])


def events(folder):
    out = []
    for name in ("scoreboard-fbs", "scoreboard-fcs"):
        f = folder / f"{name}.json.gz"
        if f.exists():
            out += json.load(gzip.open(f, "rt", encoding="utf-8")).get("events", [])
    return out


def describe(e):
    comp = e["competitions"][0]
    st = e["status"]
    sit = comp.get("situation") or {}
    teams = " / ".join(f"{c['homeAway']} {c['team'].get('abbreviation')} {c.get('score')}" for c in comp["competitors"])
    last = (sit.get("lastPlay") or {}).get("text")
    return (f"{e['id']} {e['shortName']} | {st['type']['state']} {st['type'].get('detail')} | "
            f"clock {st.get('displayClock')} period {st.get('period')} | neutral {comp.get('neutralSite')} | {teams}\n"
            f"   lastPlay: {last}\n   downDistance: {sit.get('downDistanceText')} possession: {sit.get('possession')}")


def main():
    folder = nearest(sys.argv[1])
    print("snapshot", folder.name)
    evs = events(folder)
    for want in sys.argv[2:]:
        for e in evs:
            comp = e["competitions"][0]
            if (want == "all" or (want == "neutral" and comp.get("neutralSite"))
                    or want.lower() in (e["shortName"] + " " + e["name"]).lower()):
                print(describe(e))


main()
