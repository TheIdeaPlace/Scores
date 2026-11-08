#!/bin/bash
# Reset, record and check steps files in the test VM with NVDA.  run.sh [-a "<app args>"] name...
#
#   PROJECT  the clip folder (steps\, clips\, out\, tools\), as a Windows path. It holds the
#            recordings, so keep it outside the repo: by default OneDrive\testing\scores\moreaudio\<name>.
#   REPO     a checkout of Scores whose branch holds the VM (vmtest finds the VM by repo and branch).
#   MODE     0 table, 1 quick list, 2 full list: the saved default_view_mode for the clip.
#   EXE      the Scores.exe in the VM; by default the one the installer puts there.
P="${PROJECT:-C:\\Users\\kelly\\OneDrive\\testing\\scores\\moreaudio\\nvda-bugbash-2026-11-07-ncaaf}"
T='C:\Users\kelly\GitHub\TheWorkBench\audio-demo\tools'
PY="$LOCALAPPDATA/audio-demo/venv/Scripts/python.exe"
V='C:\Users\kelly\GitHub\TheWorkBench\vmtest\vmtest.ps1'
ARGS=""
if [ "$1" = "-a" ]; then ARGS="$2"; shift 2; fi
cd "${REPO:-/c/Users/kelly/GitHub/Scores}" || exit 1
HERE=$(cygpath -u "$P")
mkdir -p "$HERE/out" "$HERE/clips"
for name in "$@"; do
  echo "=== $name $(date +%H:%M:%S)"
  sed "s/\"default_view_mode\": 0/\"default_view_mode\": ${MODE:-0}/" "$HERE/tools/reset.ps1" > "$HERE/tools/reset-now.ps1"
  powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$V" run -ScriptFile "$P\tools\reset-now.ps1" >/dev/null 2>&1
  # A fresh VM's ShellExperienceHost can hold the foreground, invisibly, so nothing launched comes to the front.
  timeout 90 powershell -NoProfile -ExecutionPolicy Bypass -File "$P\tools\vm-shell-reset.ps1" >/dev/null 2>&1
  EXTRA=(); [ -n "$ARGS" ] && EXTRA=(-LaunchArgs "$ARGS")
  powershell -NoProfile -ExecutionPolicy Bypass -File "$T\clip.ps1" -Project "$P" -Name "$name" -Launch "${EXE:-C:\\Users\\vmuser\\AppData\\Local\\Programs\\Scores\\Scores.exe}" "${EXTRA[@]}" -NoTranscribe > "$HERE/out/$name-run.txt" 2>&1
  tail -${TAILN:-3} "$HERE/out/$name-run.txt"
  "$PY" -I "$T\srcheck.py" "$P" "$name" 2>&1 | tail -3
done
