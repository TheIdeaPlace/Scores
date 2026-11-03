## What's New in Version 1.0.1

Fixes from a long bug bash on football, hockey and basketball. Box scores are the big one: they were
empty or half empty in most sports, on both Windows and iPhone, and now they work.

### Windows

**Box scores**
- Every player is there in every sport. Football and hockey showed nothing, and basketball showed only
  the five players on the floor at the end.
- Tabs are named for the team and group, such as "Green Bay Packers Passing". There's a Totals row,
  "Did not play" for anyone who sat out, and a Team Stats tab comparing both teams.
- The dialog opens in the first table, ready to read. A game with no box score, like all of college
  hockey, doesn't offer one.

**Getting around**
- Tables are one Tab away. Tab used to stop on an empty area where the arrow keys did nothing.
- F6 moves between the tabs and what's on them, in every dialog with tabs. Alt+V, Alt+T, Alt+Q and Alt+F
  also work from the tab bar, and Enter works in Quick List and Full List.
- Back returns you to the game, date or week you came from.
- Enter presses the button that has focus, everywhere. Enter on a list row no longer also presses a
  dialog's first button: opening a game from a team's schedule was adding or removing the team as a favorite.
- Back from a game opened from a team's schedule no longer closes the app. On Team Hub, Transactions is now
  Alt+R, so Alt+T means table view there too.

**What you hear**
- The app really speaks now. Announcements used to be just a beep. The date or week is said as it changes,
  and it's in the window title.
- Live Scores no longer re-reads your row at every refresh. It speaks when the row's text changes.
- Rows no longer use internal names or emoji, and "Switched to..." no longer grows each time you change view.

**Right information**
- College standings show the overall record, not a split such as the record against ranked teams. All
  conferences are there, including the Sun Belt, with a conference record and streak. Women's college hockey
  no longer reads 0-0 for everyone.
- NHL standings line up with their headings and rank by points, and Utah is in the Central Division. Streaks
  are filled in across the leagues.
- Made-up statistics are gone. Some leagues were showing invented leaders as if they were real. NFL and NHL
  player statistics load again.
- Schedule dates are right: evening games were reading as the next day.
- Games show betting lines, TV, officials, attendance and the number of injured players. A game's Standings row
  opens real tables.
- Men's college basketball has halves, not quarters. Overtimes read OT, 2OT, 3OT.
- Score rows use full team names in women's college basketball and college hockey, show AP ranks, and say "vs"
  at a neutral site.
- Team Hub rosters read 6'5" and 325 lbs, name first, with venue and news filled in. Game Wrap Up shows player
  names again.
- A live football drive no longer appears twice.

**Late games stay put.** Until 5 AM, Live Scores and league screens stay on last night's games, so a West Coast
game no longer vanishes at midnight in the East. This is on iPhone too.

**College basketball locations.** Substitutions, timeouts, free throws and rebounds no longer read "at the rim"
or play a tone, on Windows or iPhone. ESPN marks them with one fixed spot under the basket.

If something unexpected goes wrong in a dialog, the app now keeps running, says so, and writes the details to
`errors.log` next to your settings.

### iPhone

- **Women's college basketball games open.** About one in five failed outright because of a single player with
  only a short name.
- **Football week arrows work,** for past seasons too, and so does the World Cup bracket.
- **Box scores** show real columns in every sport, including shooting in basketball, and team stats fill in. Tabs
  have names, with none for an empty group. There's a Totals row and "Did not play". College hockey says "Box
  score not available" instead of showing nine blank tabs.
- **Standings load** in college football and men's college hockey, which failed outright, and in women's college
  hockey, which was empty. The NHL has one group per division, ranks by points and shows overtime losses.
- **Before a game,** the team table says it holds season stats. Postponed and delayed games no longer read 0 to 0.
- **Game details and rows** show betting lines, AP ranks and "vs" at a neutral site.
- **Plays and drives:** a live football drive no longer appears twice, overtimes read OT and 2OT, and shootouts
  don't show a false score.
- **Team hub:** NFL overall records appear, NHL records include overtime losses, and "Next" is never a game already
  played.

### Known issue

College basketball fouls read and sound as if they happened at the far end of the court, on Windows and iPhone. A
foul under the basket can read "deep, 66 feet out". The fix is planned for the next release.

---

**Platforms:** Windows 10 or later; iPhone through TestFlight
