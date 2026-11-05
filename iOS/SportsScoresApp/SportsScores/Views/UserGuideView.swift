//
//  UserGuideView.swift
//  SportsScores
//
//  In-app user guide covering all features.
//  Structure mirrors the FastWeather app: GuideSection cards + BulletPoint helpers.
//

import SwiftUI

// MARK: - Main view

struct UserGuideView: View {

    private var appVersion: String {
        let info = Bundle.main.infoDictionary
        let v = info?["CFBundleShortVersionString"] as? String ?? "—"
        let b = info?["CFBundleVersion"] as? String ?? "—"
        return "\(v) (build \(b))"
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {

                // MARK: Header
                VStack(alignment: .leading, spacing: 6) {
                    Text("Sports Scores")
                        .font(.largeTitle)
                        .fontWeight(.bold)
                    Text("Live scores, audio venue tours, and deep team stats.")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                .padding(.bottom, 4)

                // MARK: Getting Around
                GuideSection(icon: "sportscourt", title: "Getting Around", color: .blue) {
                    Text("The app has three tabs along the bottom:")
                    IconRow(symbol: "sportscourt",        color: .blue,   label: "Scores",    detail: "Sports list and live scores — the home page")
                    IconRow(symbol: "waveform.and.mic",   color: .purple, label: "The Bench", detail: "Team Hub, venue tours, NFL Draft, Transaction Hub")
                    IconRow(symbol: "gearshape",          color: .gray,   label: "Settings",  detail: "Display preferences")

                    Text("**Home Screen**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("The Scores tab opens a list of sports. A date navigation bar at the top lets you browse any day. The first item — Live Scores — shows all sports at once.")
                    BulletPoint("Select any sport row to open its scores, standings, news, and stats")
                    BulletPoint("Soccer and Golf open their own hub screens with per-league rows")
                    BulletPoint("The left and right arrows (**Previous Day** and **Next Day** in VoiceOver) move one day at a time; **Today** returns to the current date")

                    Text("**Sport Screen**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Five tabs appear along the bottom of each sport screen:")
                    BulletPoint("**Scores** — games for the selected date, grouped by status")
                    BulletPoint("**Standings** — division or conference table. For MLB, a Divisions / Wild Card control at the top switches to the playoff picture: each league's three division leaders, then the wild card race in MLB's official order, with the teams currently holding a spot marked \"Wild card 1, 2, 3\".")
                    BulletPoint("**News** — recent headlines")
                    BulletPoint("**Stats** — league statistical leaders")
                    BulletPoint("**Polls** — AP, Coaches and USCHO rankings; college sports only, when available")
                    BulletPoint("**Venues** — each stadium and arena with its home teams; select one for its details. Not for soccer or CFL")
                    Text("For NFL and NCAA Football, the date bar shows a week number and moves by week.")

                    Text("**Auto-Refresh**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("The clock icon in the toolbar sets how often scores refresh: 1 min, 2 min, 5 min, or manual")
                    BulletPoint("Pull down on any list to refresh immediately")
                }

                // MARK: Game Detail
                GuideSection(icon: "list.bullet.rectangle", title: "Game Detail", color: .green) {
                    Text("Select any game row to open its detail screen. The header shows both teams, the current score or start time, and the venue. Four tabs are available:")
                    BulletPoint("**Box Score** — one tab per team and stat group, then the team comparison. Tables have a Totals row wherever ESPN sends one. Before a game, the team table holds season stats and says so")
                    BulletPoint("**Plays / Drives** — pitch-by-pitch (baseball), play-by-play (basketball, hockey), or drive chart (football)")
                    BulletPoint("**Info** — leaders, injuries, officials, venue, related news")
                    BulletPoint("**More** — win probability and season series; MLB only")

                    Text("**MLB game header extras:**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    IconRow(symbol: "figure.walk",        color: .green,  label: "Field tour",    detail: "Opens the audio stadium tour for that ballpark — appears next to the venue name")
                    IconRow(symbol: "hand.tap",           color: .green,  label: "Explore Zone",  detail: "Opens the pitch zone explorer — appears in the Plays tab when pitch data is available")
                    IconRow(symbol: "square.and.arrow.up", color: .blue,  label: "Share",         detail: "Share a text summary of the final score — appears for completed games")
                }

                // MARK: Table View Modes
                GuideSection(icon: "tablecells", title: "Table View Modes", color: .orange) {
                    Text("Screens that show statistics, standings, rosters, or box scores have a view-mode button in the toolbar. Three modes are available:")
                    IconRow(symbol: "tablecells",                color: .orange, label: "Table View",  detail: "Grid with columns and rows — VoiceOver can navigate by row and column")
                    IconRow(symbol: "list.bullet",               color: .orange, label: "Quick List",  detail: "Each row as a comma-separated line — compact and fast to scan")
                    IconRow(symbol: "list.bullet.rectangle",     color: .orange, label: "Full List",   detail: "Each field on its own line with its header label — maximum context")
                    Text("The default mode is set in Settings. Changing it per screen does not affect the default.")
                }

                // MARK: Team Hub
                GuideSection(icon: "person.3.fill", title: "Team Hub", color: .indigo) {
                    Text("Team Hub lives in The Bench tab. Browse any team across all sports, bookmark favorites, and see live game updates at a glance.")

                    Text("**Browsing Teams**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("Select a sport from the list — college sports show a conference picker first")
                    BulletPoint("Select any team to open its detail screen")
                    BulletPoint("The star button in the top-right corner adds or removes a team from favorites")

                    Text("**Team Detail Tabs**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("**Info** — record, standing, next game, venue, head coach")
                    BulletPoint("**Roster** — full roster table: name, number, position, age")
                    BulletPoint("**News** — recent headlines for this team")
                    BulletPoint("**Schedule** — full season with results")
                    BulletPoint("**Transactions** — recent player moves, signings, and releases")

                    Text("**Favorites**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Favorited teams appear as cards at the top of the Team Hub screen. Each card shows:")
                    BulletPoint("Live game score — for baseball this includes pitcher, batter, base runners, count, and outs")
                    BulletPoint("Most recent completed game result")
                    BulletPoint("Next scheduled game")
                    BulletPoint("Up to two recent news headlines — select one to open the full article")

                    Text("**Reordering Favorites**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Press and hold any favorites card to bring up the context menu:")
                    IconRow(symbol: "arrow.up",          color: .indigo, label: "Move Up",        detail: "Move one position earlier in the list")
                    IconRow(symbol: "arrow.down",        color: .indigo, label: "Move Down",      detail: "Move one position later in the list")
                    IconRow(symbol: "arrow.up.to.line",  color: .indigo, label: "Move to Top",    detail: "Jump to the first position")
                    IconRow(symbol: "arrow.down.to.line", color: .indigo, label: "Move to Bottom", detail: "Jump to the last position")
                    Text("Options that don't apply — for example, Move Up when the team is already first — are not shown.")
                    Text("With VoiceOver, the same four actions appear in the Actions rotor.")
                }

                // MARK: The Bench
                GuideSection(icon: "waveform.and.mic", title: "The Bench", color: .purple) {

                    Text("**Venue Audio Tours**")
                        .fontWeight(.semibold)
                    Text("Each tour shows a scale drawing of a real sports venue. Drag your finger across the canvas to hear continuous terrain-based audio. Lifting your finger triggers a VoiceOver announcement of the zone name and distance. A haptic pulse fires when you cross a zone boundary.")

                    BulletPoint("**MLB Stadiums** — all 30 parks with real wall distances. Three terrain sounds: grass (soft swish), warning track (crunch), foul territory (rough scrape). Stereo panning follows your finger.")
                    BulletPoint("**NFL Football Field** — 120 yards with yard lines, hash marks, and goal posts")
                    BulletPoint("**NHL Hockey Rink** — 200 ft with zones, blue lines, and creases")
                    BulletPoint("**NBA Basketball Court** — 94 ft with the paint, 3-point arc, and free throw line")
                    BulletPoint("**Soccer Pitch** — 105 m × 68 m with center circle, penalty areas, and goals")

                    Text("VoiceOver and the canvas: configure the activation method in Settings → Stadium Exploration. With Direct Touch on, double-tap the canvas to activate, then drag freely. With it off, use the VoiceOver double-tap-and-hold passthrough.")

                    Text("**Strike Zone Explorer**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Drag the 17-inch-wide strike zone to hear audio tones encoding pitch location. Height maps to a musical note (A-minor pentatonic — higher in the zone = higher note). Horizontal position maps to stereo pan. Lifting announces \"Strike\" or \"Ball\" with a body-part location reference.")
                    Text("When accessed from a game's Plays tab (via Explore Zone), real pitch data is overlaid. Flicking up/down steps pitch-by-pitch; the VoiceOver value field shows the current pitch.")

                    Text("**NFL Draft**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Browse pick-by-pick results by year and round. Each pick shows selection number, team, player name, position, and college.")

                    Text("**Transaction Hub**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Browse player moves, signings, and releases by sport and team.")
                }

                // MARK: Settings
                GuideSection(icon: "gearshape", title: "Settings", color: .gray) {
                    Text("**VoiceOver Team Names**")
                        .fontWeight(.semibold)
                    Text("Controls how team names are read everywhere in the app:")
                    BulletPoint("**Abbreviation** — \"BOS\", \"NYY\"")
                    BulletPoint("**City** — \"Boston\", \"New York\"")
                    BulletPoint("**Nickname** — \"Red Sox\", \"Yankees\"")
                    BulletPoint("**Full Name** — \"Boston Red Sox\", \"New York Yankees\"")
                    Text("An example for the Milwaukee Brewers is shown below the picker.")

                    Text("**Table Default**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Sets the default view mode for all tables (standings, rosters, box scores, stats). You can always override it per screen.")

                    Text("**College Football**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    Text("Chooses how much of the college football slate the scoreboard shows:")
                    BulletPoint("**All Division I** (the default) — FBS and FCS together, around 200 games a week. Opening weekend is mostly FCS, so this is the only setting that shows it in full.")
                    BulletPoint("You can also change this without leaving the scores screen: on College Football, a control in the top bar switches coverage and reloads straight away. It changes this same setting.")
                    BulletPoint("**FBS only** — the roughly 100 games a week that most college football coverage means.")

                    Text("**Home Page Sports**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("Toggle any sport on or off to show or hide it on the home screen")
                    BulletPoint("Drag (or use the Move Up/Down/Top/Bottom VoiceOver actions) to reorder the list")
                    BulletPoint("Soccer and Golf are hub sports — toggle only, not reorderable")

                    Text("**Stadium Exploration**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    BulletPoint("**Direct Touch on** — double-tap the canvas to activate, then drag freely; VoiceOver is silenced during the drag")
                    BulletPoint("**Direct Touch off** — swipe to focus the canvas, then use the VoiceOver double-tap-and-hold passthrough gesture")
                }

                // MARK: Icons & Graphics
                GuideSection(icon: "photo", title: "Icons & Graphics", color: .pink) {
                    Text("Every icon in the app has a VoiceOver label. This section lists the icons you will encounter and what they represent.")

                    Text("**Tab Bar**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    IconRow(symbol: "sportscourt",       color: .blue,   label: "Scores",     detail: "VoiceOver: \"Scores\"")
                    IconRow(symbol: "waveform.and.mic",  color: .purple, label: "The Bench",  detail: "VoiceOver: \"The Bench\"")
                    IconRow(symbol: "gearshape",         color: .gray,   label: "Settings",   detail: "VoiceOver: \"Settings\"")

                    Text("**Home Screen & Date Navigation**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    IconRow(symbol: "circle.fill",       color: .red,    label: "Live indicator",   detail: "Red dot on game rows and the Live Scores entry — game is in progress")
                    IconRow(symbol: "chevron.left",      color: .primary, label: "Previous",        detail: "Move back one day (or week for football)")
                    IconRow(symbol: "chevron.right",     color: .primary, label: "Next",            detail: "Move forward one day (or week for football)")
                    IconRow(symbol: "clock",             color: .primary, label: "Auto-refresh",    detail: "VoiceOver: \"Auto-refresh: [current interval]\"")

                    Text("**Sports**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    IconRow(symbol: "figure.baseball",          color: .accentColor, label: "MLB Baseball",         detail: "")
                    IconRow(symbol: "figure.american.football", color: .accentColor, label: "NFL / NCAA Football",  detail: "")
                    IconRow(symbol: "figure.basketball",        color: .accentColor, label: "NBA / NCAAB / WNBA",   detail: "")
                    IconRow(symbol: "figure.hockey",            color: .accentColor, label: "NHL / NCAA Hockey",    detail: "")
                    IconRow(symbol: "figure.golf",              color: .accentColor, label: "PGA / LPGA Golf",      detail: "")
                    IconRow(symbol: "figure.soccer",            color: .accentColor, label: "Soccer",               detail: "")

                    Text("**Game Detail**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    IconRow(symbol: "mappin.circle",      color: .secondary, label: "Venue",        detail: "Location pin — shown next to the stadium name in the game header")
                    IconRow(symbol: "figure.walk",        color: .green,     label: "Field tour",   detail: "VoiceOver: \"Field tour for [stadium name]\" — MLB only")
                    IconRow(symbol: "hand.tap",           color: .green,     label: "Explore Zone", detail: "VoiceOver: \"Explore Zone\" — MLB Plays tab, when pitch data is available")
                    IconRow(symbol: "tv",                 color: .secondary, label: "Broadcast",    detail: "TV network(s) carrying the game — decorative, hidden from VoiceOver")
                    IconRow(symbol: "square.and.arrow.up", color: .blue,     label: "Share",        detail: "VoiceOver: \"Share game summary\" — completed games only")

                    Text("**Team Hub & Favorites**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    IconRow(symbol: "star",               color: .accentColor, label: "Add to Favorites",      detail: "VoiceOver: \"Add to Favorites\"")
                    IconRow(symbol: "star.fill",          color: .accentColor, label: "Remove from Favorites", detail: "VoiceOver: \"Remove from Favorites\"")
                    IconRow(symbol: "arrow.up",           color: .indigo,      label: "Move Up",               detail: "Context menu and VoiceOver action for favorites reordering")
                    IconRow(symbol: "arrow.down",         color: .indigo,      label: "Move Down",             detail: "Context menu and VoiceOver action for favorites reordering")
                    IconRow(symbol: "arrow.up.to.line",   color: .indigo,      label: "Move to Top",           detail: "Context menu and VoiceOver action for favorites reordering")
                    IconRow(symbol: "arrow.down.to.line", color: .indigo,      label: "Move to Bottom",        detail: "Context menu and VoiceOver action for favorites reordering")

                    Text("**The Bench**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    IconRow(symbol: "person.3.fill",           color: .indigo,  label: "Team Hub",         detail: "")
                    IconRow(symbol: "person.3.sequence.fill",  color: .blue,    label: "NFL Draft",        detail: "")
                    IconRow(symbol: "arrow.left.arrow.right",  color: .blue,    label: "Transaction Hub",  detail: "")
                    IconRow(symbol: "square.grid.3x3",         color: .purple,  label: "Strike Zone",      detail: "")

                    Text("**Table View Modes**")
                        .fontWeight(.semibold)
                        .padding(.top, 8)
                    IconRow(symbol: "tablecells",              color: .orange,  label: "Table View",   detail: "VoiceOver: \"View mode: Table View\"")
                    IconRow(symbol: "list.bullet",             color: .orange,  label: "Quick List",   detail: "VoiceOver: \"View mode: Quick List\"")
                    IconRow(symbol: "list.bullet.rectangle",   color: .orange,  label: "Full List",    detail: "VoiceOver: \"View mode: Full List\"")
                    IconRow(symbol: "line.3.horizontal",       color: .secondary, label: "Drag handle", detail: "Settings sports list — drag to reorder. Decorative, hidden from VoiceOver. Use the Actions rotor instead.")

                    Text("All icons are decorative. VoiceOver users receive complete information through labels and announcements — you never need to see an icon to use any feature in the app.")
                        .font(.callout)
                        .foregroundColor(.orange)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 12)
                        .background(Color.orange.opacity(0.1))
                        .cornerRadius(8)
                        .padding(.top, 8)
                }

                // MARK: VoiceOver
                GuideSection(icon: "accessibility", title: "VoiceOver", color: .teal) {
                    Text("The app is built for VoiceOver. Specific behaviors:")
                    BulletPoint("**Game rows** are single elements. Reading order: away team, score, home team, score, status")
                    BulletPoint("**Section headers** (In Progress, Upcoming, Completed) have the heading trait — navigate between them with the Headings rotor")
                    BulletPoint("**Play-by-play rows** read as: what happened, clock, score")
                    BulletPoint("**Date controls** support swipe up/down to increment or decrement the date without opening the picker")
                    BulletPoint("**Tables in Table View mode** use the data-table accessibility protocol — navigate by row or column using the rotor")
                    BulletPoint("**Favorites reordering** — open the Actions rotor on a favorites card for Move Up, Move Down, Move to Top, and Move to Bottom")
                    BulletPoint("**Sports reordering in Settings** — same four Actions rotor actions on each sport row")
                    BulletPoint("**Live baseball in Favorites** — the card label includes pitcher name, batter name, base runners, count, and outs")
                    BulletPoint("**Venue tour canvas** — configure activation method in Settings → Stadium Exploration")
                }

                // MARK: Data Notes
                GuideSection(icon: "antenna.radiowaves.left.and.right", title: "Data", color: .cyan) {
                    Text("All data comes from ESPN's public API.")
                    BulletPoint("**MLB Spring Training** runs February–March. The app defaults to spring training games during that window")
                    BulletPoint("**NBA, NHL and college basketball/hockey** seasons are shown as the two years they span, e.g. 2026–27. The WNBA plays inside one calendar year, so it shows a single year")
                    BulletPoint("**NCAA Hockey** data is sometimes incomplete — ESPN sends no box score at all for college hockey, so the Box Score tab says so")
                    BulletPoint("Game times are shown in your device's local time zone. A game with no set time reads **Time TBD**")
                    BulletPoint("**\"Today\" lasts until 5 AM.** Until then, Live Scores and the league screens stay on last night's games")
                    BulletPoint("**College basketball plays** with no real location, such as substitutions and free throws, have no location or tone")
                }

                // Footer
                VStack(spacing: 12) {
                    Divider()
                    Text("Version \(appVersion)")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding(.top, 16)
                .padding(.bottom, 40)
            }
            .padding()
        }
        .navigationTitle("User Guide")
        .navigationBarTitleDisplayMode(.inline)
    }
}

// MARK: - GuideSection

struct GuideSection<Content: View>: View {
    let icon: String
    let title: String
    let color: Color
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                Image(systemName: icon)
                    .font(.title2)
                    .foregroundColor(color)
                    .accessibilityHidden(true)
                Text(title)
                    .font(.title3)
                    .fontWeight(.semibold)
            }
            .accessibilityElement(children: .combine)
            .accessibilityAddTraits(.isHeader)

            VStack(alignment: .leading, spacing: 8) {
                content
            }
            .font(.body)
        }
        .padding()
        .background(Color(uiColor: .secondarySystemGroupedBackground))
        .cornerRadius(12)
    }
}

// MARK: - BulletPoint

struct BulletPoint: View {
    let text: LocalizedStringKey

    init(_ text: LocalizedStringKey) {
        self.text = text
    }

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Text("•")
                .foregroundColor(.accentColor)
                .accessibilityHidden(true)
            Text(text)
        }
    }
}

// MARK: - IconRow

/// A rendered SF Symbol beside a label and optional detail — used in the icons section.
private struct IconRow: View {
    let symbol: String
    let color: Color
    let label: String
    let detail: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: symbol)
                .font(.title2)
                .foregroundColor(color)
                .frame(width: 32)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                    .fontWeight(.semibold)
                if !detail.isEmpty {
                    Text(detail)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
    }
}

#Preview {
    NavigationStack {
        UserGuideView()
    }
}
