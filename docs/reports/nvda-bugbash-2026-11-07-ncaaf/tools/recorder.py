"""Saves what ESPN said about today's college football every few minutes, so every clip can be
compared with the feed at that moment. Run with -I. Read-only requests; nothing else.

    python -I recorder.py <out dir> [minutes between snapshots] [hours to run]
"""
import gzip
import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

SITE = "https://site.api.espn.com/apis/site/v2/sports/football/college-football"
DAY = "20261107"


def get(url):
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.load(resp)


def save(folder, name, data):
    with gzip.open(folder / f"{name}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(data, f)


def snapshot(out):
    stamp = datetime.now().strftime("%H%M%S")
    folder = out / stamp
    folder.mkdir(parents=True, exist_ok=True)
    live = []
    for group, label in (("80", "fbs"), ("81", "fcs")):
        try:
            board = get(f"{SITE}/scoreboard?dates={DAY}&groups={group}&limit=400")
            save(folder, f"scoreboard-{label}", board)
            live += [e["id"] for e in board.get("events", [])
                     if e.get("status", {}).get("type", {}).get("state") == "in"]
        except Exception as e:
            print(stamp, label, "failed:", e, flush=True)
    try:
        save(folder, "rankings", get(f"{SITE}/rankings"))
    except Exception as e:
        print(stamp, "rankings failed:", e, flush=True)
    for game in live[:25]:
        try:
            save(folder, f"summary-{game}", get(f"{SITE}/summary?event={game}"))
        except Exception as e:
            print(stamp, game, "failed:", e, flush=True)
    print(stamp, "saved,", len(live), "live", flush=True)


def main():
    out = Path(sys.argv[1])
    minutes = float(sys.argv[2]) if len(sys.argv) > 2 else 3
    hours = float(sys.argv[3]) if len(sys.argv) > 3 else 12
    end = time.time() + hours * 3600
    while time.time() < end:
        snapshot(out)
        time.sleep(minutes * 60)


if __name__ == "__main__":
    main()
