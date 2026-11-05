## What's New in Version 1.1.0

Long lists work the way a keyboard user expects, a lot of missing data is back, and both apps now read
the same data almost everywhere, so they agree with each other.

### Windows

**Lists and tabs**
- More than eight tabs is now a list: college conferences in Standings and Teams, and the tables in a
  football box score. Arrow to the one you want and press Enter, and its table opens in the list's place.
  Escape or the Back button returns you to the same row, and Ctrl+Tab goes on to the next table. The window
  title names what's open.
- Player and Team Statistics work the same way, with a list of the statistics. Their results are now real
  tables, so Alt+V, Alt+T, Alt+Q and Alt+F work on them, and each cell says whose row it is. Players level on
  a number share a rank.
- Tab bars have Home and End, Left and Right go round past the ends, and typing goes to a tab by name. S, U, N
  reaches Sun Belt. Eight tabs or fewer stay as tabs.
- Ctrl+Tab goes straight to the next tab's table, without stopping on Close along the way.
- Switching a table's view stays on your row, and the view you choose carries to the next table.

**Data that was missing**
- The WNBA has Standings, Statistics, Teams, Transactions and Venues.
- The NBA and WNBA have player leaders, and a game's Leaders opens. It only showed an error.
- FCS teams are in college football standings and Teams, following the "College football games shown" setting.
- Team statistics rank the whole league, best first, where college basketball stopped at 50 of about 360 teams.
- Team schedules have the whole football season, including the Super Bowl and bowl games. The WNBA and soccer
  show the season you pick.
- Venues work for college basketball and college hockey, and each one says who plays there.

**Data that was wrong**
- NFL and NHL player statistics are the regular season. They were preseason numbers, and the dialog says which
  season you're looking at.
- Team Hub shows a team's real record and standing during the playoffs. The Lynx, 33-11 and first in the West,
  read 0-2 and 8th.
- Team Info shows where a team plays now. The Nets read Prudential Center.
- Utah is in the Central Division in the NHL. The 1.0.1 notes said it was, but it wasn't until now.
- Times are right in summer for Eastern, Pacific and Mountain users.
- A blank field from ESPN no longer reads out as "None".

**Faster**
- MLB leaders open in about 2 seconds rather than 30, in the same order every time.
- The NFL Draft opens much faster, and focus stays where you are as you arrow through rounds and years.
- Team statistics and hockey games each take fewer downloads.

**When something goes wrong**
- If ESPN doesn't answer, Statistics, Standings, Teams, Venues and team schedules say so and suggest trying
  again, rather than looking empty.

**Less than before.** Both apps now share one source, and it doesn't have everything:
- MLB leaders have 19 categories rather than 39. New ones include WAR and quality starts. Doubles, triples,
  walks, innings pitched, complete games, shutouts, blown saves and fielding are gone.
- About half of MLB's team statistics and a third of the NFL's are gone, with some from other leagues.
- Player lists go to 20 rather than 50.

### iPhone

- **League leaders** now come from the same place as on Windows, so both apps agree. The list says which season it is, and players level on a number share a rank.
- **A team's Stats** lists its own players, ranked within the team, with qualified players first. A team with nobody high in the league used to have nothing to show.
- **Team statistics** are the whole regular season, out of season too, and say which season. Team ranks match the league list, and college teams have ranks at all: "118th of 302".
- **FCS teams** are in college football standings and Team Hub, following the "College football games shown" setting.
- **Team schedules** work for soccer, and every league has its preseason and postseason, labelled.
- **Team Hub** shows the real record and standing during the playoffs, and where a team plays now.
- **NFL Draft:** colleges read in full, such as Georgia State, and older drafts name their centers and kickers.
- **Numbers read properly:** 38.3 points rather than 38.29, half sacks keep their half, and on-base percentage reads .360.
- **Fixed:** a tied game read as a loss, one blank game could lose a whole football week, and a failed schedule now says so, with a Retry button.

### iPhone known issues

- College basketball fouls still read and sound as if they happened at the far end of the court. The 1.0.1 notes said this would be fixed in this release, and it wasn't.
- VoiceOver reads the View All link on Stats twice.

### Windows known issues

- College basketball fouls still read and sound as if they happened at the far end of the court. The 1.0.1 notes
  said this would be fixed in this release, and it wasn't.
- On long lists, screen readers can give the wrong item count, because the list only reports the rows on screen.
  Table view gives the true row and total. We believe this is a bug in Qt 6, the toolkit the Windows app is built
  on: [QTBUG-149577](https://qt-project.atlassian.net/browse/QTBUG-149577).
- JAWS reads each tab twice as you arrow along tabs.

---

**Platforms:** Windows 10 or later; iPhone through TestFlight
