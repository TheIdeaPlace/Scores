# JAWS: a closed dialog's text heard again (November 8, 2026)

**What Kelly heard (JAWS):** after a dialog closed, its first line of text came back after the main
window's title every time he returned to Scores or the screen changed. From a game's News, on Escape
back to Live Scores and on Alt+Tab back: "Live Scores - Sports Scores", then "News Headlines (🎯 =
Game-specific, Enter or double-click to open in browser):". From a league's News, even on screens with
no news: "Press Enter or double-click a headline to open in your browser:".

**Short answer:** reproduced with JAWS, explained, and fixed in **#250** (merged to main as b41dd9c).
**1.1.1 does it too**, so it isn't a regression, and there was nothing to bisect. NVDA never says it.

Run: JAWS 2027.2610.428 (40-minute mode) and NVDA 2026.2 in ClaudeTesting on SURFACEPRO7 (an ARM64
VM; the JAWS offline x64 installer refuses it, but the web installer works). JAWS's speech is
**exact**: it comes from JAWS's own speech history, read through its COM API after every key (see "How
JAWS speech was captured").

## Why it happens

As a dialog opens, JAWS reads the dialog's **static text that comes before its first focusable
control**, and keeps it with the window that **owns** the dialog: the main window. After the dialog
closes, JAWS says that text again after the main window's title whenever it announces that window: on
Alt+Tab back, and on every title change (Escape to home, Back to Live Scores). It does so until another
dialog replaces it. A dialog with no such text replaces it with nothing.

By then the dialog, and the view that owned it, are gone: JAWS still says it on the home screen. No
window, UIA element or MSAA object of the app holds the text (`probe2.ps1`), so no event could have
told JAWS to drop it. This is how JAWS handles owned dialogs in a UIA app, and it isn't specific to
Scores' code: a 60-line PyQt6 app does the same. Every dialog in Scores with a label above its first
control was affected: News (league and game), Statistics, Standings, Team Hub, Golf, CFL, World Cup,
Venues and more.

What the minimal PyQt6 app (`harness.py`) showed, all with exact JAWS speech:

| Variant | Repeated after close? |
|---|---|
| `QDialog(self)`, a label above a list | **yes** (h0) |
| `WA_DeleteOnClose` (delete the dialog on close) | yes (h1) |
| the label is the list's buddy | yes (h2) |
| `NotifyWinEvent(EVENT_OBJECT_REORDER)` on the main window | yes (h4) |
| the main window has a static text of its own | yes, JAWS says both (h13) |
| a blank or zero-width-space label on the main window | yes (h14, h15) |
| the dialog has no owner (app-wide event filter) | no (h6), **but Alt+Tab while it's open stays in the app** (h9) |
| the dialog is owned by a hidden window | no (h7), **same Alt+Tab problem** (h10) |
| label after the list | no, and not read on open (h16) |
| label after the list in children order only (`raise_()`) | no, and not read on open (h19) |
| the instruction as a QGroupBox title | no, **and still read on open** as the group's name (h17) |
| label text set 1.5 s after opening | no (h18) |
| a dialog with no text opened afterwards | clears it (h12) |
| a plain QMessageBox | **not** repeated: JAWS reads it as an alert (h22) |

## The fix (#250)

`dialog_text.py`: `DialogTextOrder`, installed app-wide in `SportsScoresApp.__init__` (scores.py,
next to `ButtonKeys`), puts every part of each dialog that holds nothing Tab can reach after the parts
that do, in Qt's accessibility order (Qt orders accessible children as the children list, and
`raise_()` moves a widget to its end). It also looks inside tab pages and scroll areas. It runs as each
dialog shows and when it's activated again. Nothing moves on screen or in the tab order.

**The trade-off you'll hear:** as a dialog opens, JAWS says its title and the control you land on, but
no longer reads the heading or instruction above that control by itself. Insert+B and the JAWS cursor
still find it, now after the controls. Message boxes are read as before. NVDA is unchanged: it works out
a dialog's text by itself and still reads it as the dialog opens.

A per-dialog alternative that keeps JAWS reading the instruction on open is to make it a QGroupBox
title around the list (h17). That's dozens of screens and a visible change, so it wasn't done here; it
could be done later for the dialogs where the instruction matters.

## JAWS before and after (exact speech)

Before is the 1.2.0 candidate (`testing\Scores\1.2.0-candidate`). After is main with #250, built the
same way (`build.py --onefile`, PyQt 6.12). Since #249, main's rows have no "---" and the game News label
has no emoji, so the steps type "News" and "Stat" there.

| Path, key | Before (c3, c4, c5) | After (f4, f5, f6) |
|---|---|---|
| Live Scores > Lazio at Napoli > News > Enter | "News Details dialog" / "News Headlines (🎯 = Game-specific, ...)" / list | "News Details dialog" / list |
| ... Esc, **Esc back to Live Scores** | "Live Scores - Sports Scores" / **"News Headlines (🎯 = Game-specific, Enter or double-click to open in browser):"** / "Live Scores - All Sports: ..." | "Live Scores - Sports Scores" / "Live Scores - All Sports: ..." |
| ... **Alt+Tab back** | "Live Scores - Sports Scores" / **"News Headlines (🎯 ...)"** | "Live Scores - Sports Scores" / ... |
| ... **Esc to home**, then Alt+Tab back | **"News Headlines (🎯 ...)"** both times | "Sports Scores" / "Select a League:" ... |
| Home > NBA > News Headlines > Enter, Esc, **Alt+Tab back** | "NBA, Sunday, November 08, 2026 - Sports Scores" / **"Press Enter or double-click a headline to open in your browser:"** / "Date: ..." | "NBA, Sunday, November 08, 2026 - Sports Scores" / "Date: ..." |
| ... **Esc to home**, then Alt+Tab back | "Sports Scores" / **"Press Enter or double-click a headline ..."** / "Select a League:" (both times) | "Sports Scores" / "Select a League:" |
| Home > NBA > Statistics > Enter, Esc, Alt+Tab back, Esc to home, Alt+Tab back | **"NBA Statistics Selection"** after the title each time | not said |
| 1.1.1, the same Statistics path (b1) | **"NBA Statistics Selection"** after the title on Alt+Tab back and on Esc to home | n/a |

Across f4, f5 and f6, none of the three labels is spoken anywhere.

The title said twice on Alt+Tab back ("Live Scores - Sports Scores", "Live Scores - Sports Scores") is
JAWS speaking the foreground window and then the focused window's client, both named with the title
(the Nov 7 NVDA report saw the same two events). It's the same in 1.1.1, and not part of this.

**NVDA 2026.2 on the fix (n1, n2, its own log):** as each dialog opens, "News Headlines - NBA, dialog,
Press Enter or double-click a headline to open in your browser:" and "News Details, dialog, News
Headlines (Enter or double-click opens in the browser):", as before. After close, Alt+Tab back and Escape
to home give only the title and the list.

## What only Kelly can check

1. **Your own JAWS, with your settings**, on the next build from main: Live Scores > a game > News >
   Escape, Escape, Alt+Tab away and back, Escape to home. You should hear only the title and where you
   are, never the News label.
2. **A dialog opening:** league News, Statistics, Team Hub. You'll hear the title and the list, but not
   the line above the list. Say if any dialog loses something you need; that one can get a group box.
3. **A Yes/No message box** (Check for Updates when there is one): you should still hear the question.
   The harness showed JAWS reads message boxes as alerts after the change too (h23), but the update
   prompt itself wasn't run.
4. **NVDA+B / Insert+B in a dialog:** the heading or instruction now comes after the controls.

## Not verified

- The update prompt and the progress dialogs, with either screen reader (above).
- Dialogs other than News, game News and Statistics weren't walked with JAWS on the fix. The change is
  app-wide and covered by unit tests (`tests/unit/test_dialog_text.py`).
- JAWS's own script source isn't shipped, so "keeps it with the owner" is inferred from the takes, not
  read from JAWS.

## How JAWS speech was captured

JAWS keeps no log, and an injected Insert key doesn't reach it, but its COM API (`FreedomSci.JawsApi`)
runs JAWS scripts. `jdrive.ps1` (runs in the VM, `-STA`) plays a steps file with SendKeys and around
every key calls `RunScript('ClearSpeechHistory')`, then after the wait
`RunScript('CopySpeechHistoryToClipboard')`, and writes `said:` lines per key. `jrun.ps1` (host)
resets the app's settings, opens Notepad behind it, launches a build and runs a steps file; `hrun.ps1`
does the same for the harness. JAWS's 40-minute mode needs a Windows restart, not a JAWS restart:
`reboot-jaws.ps1`. Install: `install-jaws.ps1` with the web installer `J2027.2610.428.400.exe`
(`/Type silent`); then `restart-jaws.ps1` closes the activation and sign-in windows.

## Files

- `steps/`: `league-news`, `league-stats`, `live-news` (1.2.0 candidate and 1.1.1 row names),
  `league-news-main`, `league-stats-main` (main since #249), `harness*` (for the harness), `diag-stats`.
  `e!` lines are the text that must not be said. Live data: pick a game that's on that day (`live-news`
  types "Lazio").
- `tools/`: `jdrive.ps1` (VM side), `jrun.ps1`, `hrun.ps1`, the JAWS setup scripts, `reset.ps1` (the
  app's settings), `probe2.ps1` (looks for text in the main window's windows, MSAA and UIA trees), and
  `harness.py` (build with `python -m PyInstaller --noconfirm --windowed --name Harness harness.py`).
  The host scripts expect to sit in `C:\Users\kelly\scratch\jaws-stray\` and write takes to the OneDrive
  folder below; change the paths at their tops to run them from elsewhere.
- The speech logs (`*.jaws.txt` per take) and the NVDA log were kept in
  `OneDrive\testing\Scores\jaws-stray-dialog-text-2026-11-08\out\` and `moreaudio\...\clips\`, which
  may be cleared; the tables above quote them.

**To run it again:** `vmtest begin`, `setup-rig.ps1 -ScreenReader NVDA` (the audio cable and NVDA),
stop NVDA, `install-jaws.ps1` (elevated, web installer in `C:\vmtest\files`), `restart-jaws.ps1`,
deploy builds as `C:\vmtest\apps\<Name>\Scores.exe`, then
`jrun.ps1 -Steps league-news-main -Name x1 -Build <Name>`. Reboot with `reboot-jaws.ps1` every half hour
or so.
