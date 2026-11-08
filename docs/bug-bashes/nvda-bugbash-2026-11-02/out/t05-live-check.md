# Screen reader check: t05-live

Speech from NVDA's speech log (exact text). A logged utterance is what NVDA sent to its voice; the next key can cut it off, so the log shows what was sent, not that all of it was heard.

**5 of 6 expectations met.**

## line 3: `x`

-   4.86 s: Sports Scores window
-   4.87 s: League Selection List list List of available sports leagues and live scores
-   4.88 s: Live Scores - All Sports

## line 5: `k {ENTER}`

-  16.93 s: Live Scores List list List of currently live games from all sports. Press Alt+M to monitor a game for notifications.
-  16.96 s: Loading live scores...
-  18.51 s: === LIVE GAMES ===
- **PASS** (line 7) says `Live Scores List`

## line 8: `k {TAB}`

-  28.80 s: Refresh (F5) button
- **PASS** (line 10) matches `Refresh`

## line 13: `k +{TAB}`

-  31.35 s: Live Scores List list List of currently live games from all sports. Press Alt+M to monitor a game for notifications.
-  31.36 s: === LIVE GAMES ===

## line 15: `k +{TAB}`

-  32.43 s: Refresh Frequency combo box 1 minute collapsed Select how often live scores should update automatically Down
- **PASS** (line 17) says `Refresh Frequency`

## line 18: `k {END}`

-  35.13 s: Manual (F5 only)
- **PASS** (line 20) says `Manual (F5 only)`
- **FAIL** (line 21) says `Automatic refresh disabled` — not said

## line 22: `k {ESC}`

-  39.08 s: League Selection List list List of available sports leagues and live scores
-  39.09 s: Live Scores - All Sports
- **PASS** (line 24) says `League Selection List`

