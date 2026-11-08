"""Writes a steps file that opens a league and arrows down every row, reading the title first.

    python -I gen_slate.py <steps file> <down presses> [first wait seconds]
"""
import sys

path, downs = sys.argv[1], int(sys.argv[2])
first = sys.argv[3] if len(sys.argv) > 3 else "25"
lines = [f"# Slate walk: {downs} Down presses", "w 0.5", "x", f"w {first}", "n t", "w 3"]
for _ in range(downs):
    lines += ["k {DOWN}", "w 1.4"]
lines += ["w 2"]
open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
