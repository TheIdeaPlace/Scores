# Statistic categories

`stat-categories.csv` lists every statistic category ESPN offers for the leagues the apps cover,
player leaders and team statistics, and says whether each app shows it. It's for reviewing what
we have and what we could have (issues #155 and #165), and it's the groundwork for letting someone
choose the categories they want, which isn't built yet: the `key` and `source` columns are what such
a feature would store and ask for.

It covers MLB, NFL, NBA, NHL, WNBA, NCAAF, NCAAM, NCAAWB and the eleven soccer leagues in
`soccer.SOCCER_LEAGUES`. College hockey (NCAAH and NCAAWH) has no rows: ESPN answers every one of
these sources with a 404 or nothing for it, so there is no category to list.

## Regenerating it

```powershell
.venv\Scripts\python tools\stat_categories.py                  # every league
.venv\Scripts\python tools\stat_categories.py --league NFL     # just one, repeatable
```

It asks ESPN for the season the apps would show and runs the apps' own rules to decide what's
shown, so some answers depend on the season's numbers: a list where nobody has a number yet is
hidden by both apps, and reads "hidden this season". A run early in a season can differ from one
late in it. It prints a count per league at the end.

The file is UTF-8 with a byte order mark and every field quoted, so Excel opens it as it is.
Rows are in the apps' league order (the US leagues, then soccer alphabetically), then by kind,
group and name.

## Columns

| Column | What it holds |
|---|---|
| `league` | The app's name for the league, as in `espn_api.LEAGUES`. |
| `kind` | `player_leader` (league leader lists) or `team_stat` (team statistics). |
| `group` | ESPN's section: batting, pitching, passing, offensive, defensive, goalKeeping and so on. A team's opponents' numbers are `opponent passing` and the like. |
| `key` | The stable name to ask for. A leader category is ESPN's category name as `/leaders` (or the core API, for soccer) gives it, such as `homeRuns`. Anything else is `section.stat`, such as `batting.doubles`, and a team's opponents' numbers are `opponent.section.stat`. One row per league, kind and key. |
| `display_name`, `abbreviation` | ESPN's. Where Windows shows another name, `notes` says so. |
| `definition` | ESPN's description of the stat. Leader categories come without one, so theirs is the description ESPN gives the same stat in a leading player's own statistics. |
| `definition_source` | `espn`, or `written` where ESPN has none and the definition is ours. |
| `source` | Every source that has it, of these: `leaders` (`/leaders`, player leaders for the eight US leagues), `core_leaders` (the core API's leaders, soccer), `byathlete` (`statistics/byathlete`, every player ranked by a column), `core_athlete_stats` (the core API's statistics for one player), `mlb_statsapi` (the MLB Stats API, Windows' MLB leaders until #166), `byteam` (`statistics/byteam`, team statistics on both apps), `site_team_stats` (the per-team request Windows used until #152) and `core_team_stats` (the core API's statistics for one team, which both apps' Team Hub shows). |
| `available_in_current_source` | Whether the source the apps read for this now has it: `/leaders` or the core API's leaders for players, `byteam` for teams. |
| `shown_windows`, `shown_iphone` | Whether the app shows it. A team stat is `yes` if it's on the league list or the Team Hub, which both apps have by the same rule since #196; `notes` says which. The Team Hub shows one team's core statistics, leaving out a few names, Fielding, zeros and stats with no usable rank, so its `yes` means it would show for one of the two teams the tool asked about. |
| `low_is_good` | Which way the apps' rules rank it: `yes` where the lowest number comes first (ERA, turnovers), `no` where the highest does. Team stats take it from `team_stats.low_is_good`, which covers every `byteam` column whether shown or not. Leaders take it from `LOW_IS_GOOD_LEADERS`, the order ESPN lists them in. Blank where no rule covers it. |
| `notes` | Why something isn't shown, what it was dropped in (`dropped in #152`, `dropped in #166`), and anything else worth knowing. |

## Reading it

- **What we lost:** filter `notes` for `dropped in #`. MLB leaders: the 24 categories Windows had
  from the MLB Stats API and `/leaders` doesn't have (#165). Team statistics: what the old per-team
  request had and `byteam` doesn't (#155).
- **What could come back from one request:** a lost or missing player stat with `byathlete` in
  `source` can be ranked league-wide from ESPN in one request, the way `byteam` ranks teams. Its
  list is qualified players only.
- **What would cost a request per team or player:** `core_team_stats`, `site_team_stats` and
  `core_athlete_stats` describe one team or one player at a time. They suit a team or player page
  better than a league ranking. The tool asks about two teams, and about the leading player in each
  leader category, so a stat that only some players have (a catcher's, say) may be missing here.
- **Only ESPN's text:** a definition such as "Games Played" for Games Played is ESPN's own, kept as
  it is.

The MLB Stats API has some 70 leader types. Only the 39 Windows used are listed: the rest are
mostly the same stats under other names, and ESPN's feeds above carry them.
