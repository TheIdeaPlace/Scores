//
//  BoxScoreView.swift
//  SportsScores
//
//  Renders the box score one table at a time.
//  Every table is its own tab-bar button.  Examples:
//    MLB:        "NYY Batting"  "BOS Batting"  "NYY Pitching"  "BOS Pitching"
//                "Team Batting"  "Team Pitching"
//    NFL/NBA:    "Chiefs Passing"  "Eagles Passing"  …  "Team Stats"
//    NHL:        "EDM Skaters"  "CGY Skaters"  "EDM Goalies"  "CGY Goalies"  "Team Stats"
//

import SwiftUI

// MARK: - Page Model

/// One page = exactly one table.  Hashable so it works as a SwiftUI `.id` and
/// can be stored as `@State`.
private enum BoxScorePage: Hashable {
    /// A single team's player-level stat table for one stat group.
    case playerGroup(teamDisplayName: String, teamAbbr: String, groupTitle: String)
    /// Side-by-side team-stat comparison for one MLB category (Batting / Pitching / …).
    case mlbTeamStats(groupTitle: String)
    /// The single flat team-stats table used by NFL / NBA / NHL / Soccer.
    case flatTeamStats

    var tabLabel: String {
        switch self {
        case let .playerGroup(_, abbr, group): return "\(abbr) \(group)"
        case let .mlbTeamStats(group):         return "Team \(group)"
        case .flatTeamStats:                   return "Team Stats"
        }
    }
}

// MARK: - View

struct BoxScoreView: View {
    let boxscore: GameDetails.Boxscore
    let sport: Sport
    /// True before a game has been played, when the team table holds season
    /// averages rather than anything from this game.
    var isPreGame = false
    @State private var showingAllStats = false
    @State private var selectedPage: BoxScorePage?
    @State private var viewMode: ViewMode = .quickList

    // MARK: - Page List

    /// Ordered list of all navigable pages (one page = one table).
    ///
    /// Order:
    ///   • Player tables — for each stat group, one entry per team in API order
    ///     (e.g. "NYY Batting", "BOS Batting", "NYY Pitching", "BOS Pitching")
    ///   • Team-stat tables — one per MLB category, or a single flat table for others
    private var pages: [BoxScorePage] {
        var result: [BoxScorePage] = []

        // ── Player pages ───────────────────────────────────────────────────────
        if let players = boxscore.players {
            // Collect group titles in the order they first appear across all teams.
            var seenGroups = Set<String>()
            var groupOrder: [String] = []
            for teamPlayers in players {
                for group in teamPlayers.statistics where group.hasContent {
                    if seenGroups.insert(group.groupTitle).inserted {
                        groupOrder.append(group.groupTitle)
                    }
                }
            }
            // For each group, emit one page per team (keeps groups together).
            for groupTitle in groupOrder {
                for teamPlayers in players {
                    if teamPlayers.statistics.contains(where: { $0.hasContent && $0.groupTitle == groupTitle }) {
                        result.append(.playerGroup(
                            teamDisplayName: teamPlayers.team.displayName,
                            teamAbbr: teamPlayers.team.abbreviation,
                            groupTitle: groupTitle
                        ))
                    }
                }
            }
        }

        // ── Team-stat pages ────────────────────────────────────────────────────
        if boxscore.teams.hasNestedStatistics {
            // MLB: one side-by-side comparison table per category.
            for cat in boxscore.teams.comparisonEntries {
                result.append(.mlbTeamStats(groupTitle: cat.groupTitle))
            }
        } else if !boxscore.teams.hasNoStatistics {
            result.append(.flatTeamStats)
        }

        return result
    }

    private var currentPage: BoxScorePage {
        if let sel = selectedPage, pages.contains(sel) { return sel }
        return pages.first ?? .flatTeamStats
    }

    // MARK: - Body

    var body: some View {
        VStack(spacing: 0) {
            if pages.count > 1 {
                pageTabBar
            }

            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    if pages.isEmpty {
                        Text("Box score not available")
                            .foregroundColor(.secondary)
                            .padding()
                    } else {
                        if isPreGame {
                            Text("Season averages. This game hasn't been played.")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        } else {
                            toggleButton
                        }
                        pageContent
                    }
                }
                // Reset scroll offset whenever the page changes.
                .id(currentPage)
                .padding()
            }
        }
        .onAppear {
            if selectedPage == nil { selectedPage = pages.first }
        }
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                ViewModeMenuButton(currentMode: $viewMode)
            }
        }
    }

    // MARK: - Tab Bar

    private var pageTabBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 0) {
                ForEach(pages, id: \.self) { page in
                    let isSelected = currentPage == page
                    Button(action: { selectedPage = page }) {
                        Text(page.tabLabel)
                            .font(.subheadline.bold())
                            .padding(.horizontal, 16)
                            .padding(.vertical, 10)
                            .foregroundColor(isSelected ? .white : .primary)
                    }
                    .background(isSelected ? Color.blue : Color.clear)
                    .accessibilityAddTraits(isSelected ? .isSelected : [])
                }
            }
        }
        .background(Color.secondary.opacity(0.1))
    }

    // MARK: - Essential / All Stats Toggle

    private var toggleButton: some View {
        HStack {
            Spacer()
            Button(action: { showingAllStats.toggle() }) {
                HStack(spacing: 6) {
                    Image(systemName: showingAllStats ? "checkmark.circle.fill" : "circle")
                        .font(.caption)
                    Text(showingAllStats ? "All Stats" : "Essential Stats")
                        .font(.caption)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(Color.blue.opacity(0.1))
                .cornerRadius(6)
            }
            .buttonStyle(.plain)
            .accessibilityHint("Toggle between essential and all statistics")
        }
        .padding(.horizontal, 8)
    }

    // MARK: - Page Content Router

    @ViewBuilder
    private var pageContent: some View {
        switch currentPage {
        case let .playerGroup(teamDisplayName, _, groupTitle):
            singleTeamPlayerView(teamDisplayName: teamDisplayName, groupTitle: groupTitle)
        case let .mlbTeamStats(groupTitle):
            mlbTeamStatsPage(groupTitle: groupTitle)
        case .flatTeamStats:
            flatTeamStats
        }
    }

    // MARK: - Single Team Player Table

    private func singleTeamPlayerView(teamDisplayName: String, groupTitle: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if let players = boxscore.players,
               let teamPlayers = players.first(where: { $0.team.displayName == teamDisplayName }),
               let group = teamPlayers.statistics.first(where: { $0.hasContent && $0.groupTitle == groupTitle }) {
                playerStatGroupView(teamName: teamDisplayName, statGroup: group)
            } else {
                Text("No statistics available.")
                    .foregroundColor(.secondary)
            }
        }
    }

    // MARK: - MLB Team Stats Page (one category, both teams side-by-side)

    private func mlbTeamStatsPage(groupTitle: String) -> some View {
        let teams = boxscore.teams
        let profile = BoxScoreProfiles.profile(for: sport)
        let catEntry = teams.comparisonEntries.first(where: { $0.groupTitle == groupTitle })
        let allItems = catEntry?.stats ?? []
        let essentialItems = allItems.filter { profile.essentialTeamStats.contains($0.name) }
        // A category the profile has nothing for (Fielding) still shows its rows.
        let filteredItems = showingAllStats || essentialItems.isEmpty ? allItems : essentialItems

        let tableHeaders: [String] = filteredItems.isEmpty
            ? [] : (["Stat"] + teams.map { $0.team.abbreviation })
        let tableRows: [[String]] = filteredItems.map { stat in
            [stat.displayName] + teams.map { team in
                team.statistics
                    .first(where: { $0.name == catEntry?.name })?
                    .stats?
                    .first(where: { $0.name == stat.name })?
                    .displayValue ?? "-"
            }
        }

        return VStack(alignment: .leading, spacing: 8) {
            if filteredItems.isEmpty {
                Text("No team statistics available.")
                    .foregroundColor(.secondary)
            } else {
                switch viewMode {
                case .table:
                    VStack(spacing: 0) {
                        // Header row
                        HStack(spacing: 0) {
                            Text("Stat")
                                .font(.caption.bold())
                                .foregroundColor(.secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            ForEach(teams, id: \.team.displayName) { team in
                                Text(team.team.abbreviation)
                                    .font(.caption.bold())
                                    .foregroundColor(.secondary)
                                    .frame(minWidth: 60, alignment: .trailing)
                            }
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Color.secondary.opacity(0.12))
                        .accessibilityHidden(true)

                        // Data rows
                        ForEach(Array(filteredItems.enumerated()), id: \.element.name) { rowIdx, stat in
                            HStack(spacing: 0) {
                                Text(stat.displayName)
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                ForEach(teams, id: \.team.displayName) { team in
                                    let matchedStat = team.statistics
                                        .first(where: { $0.name == catEntry?.name })?
                                        .stats?
                                        .first(where: { $0.name == stat.name })
                                    Text(matchedStat?.displayValue ?? "–")
                                        .font(.caption.monospacedDigit())
                                        .frame(minWidth: 60, alignment: .trailing)
                                }
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 4)
                            .background((rowIdx % 2 == 0) ? Color.clear : Color.secondary.opacity(0.04))
                            .accessibilityHidden(true)
                        }
                    }
                    .background(Color.secondary.opacity(0.04))
                    .cornerRadius(8)
                    .accessibilityHidden(true)
                    .overlay(
                        AccessibleDataTable(headers: tableHeaders, rows: tableRows)
                            .allowsHitTesting(false)
                    )
                case .quickList:
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(Array(filteredItems.enumerated()), id: \.element.name) { idx, stat in
                            HStack {
                                Text(stat.displayName)
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                ForEach(teams, id: \.team.displayName) { team in
                                    let val = team.statistics
                                        .first(where: { $0.name == catEntry?.name })?
                                        .stats?
                                        .first(where: { $0.name == stat.name })?
                                        .displayValue ?? "–"
                                    Text("\(team.team.abbreviation): \(val)")
                                        .font(.caption.monospacedDigit())
                                }
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 5)
                            .background(idx % 2 == 0 ? Color.clear : Color.secondary.opacity(0.04))
                        }
                    }
                    .background(Color.secondary.opacity(0.04))
                    .cornerRadius(8)
                case .fullList:
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(filteredItems, id: \.name) { stat in
                            VStack(alignment: .leading, spacing: 6) {
                                Text(stat.displayName)
                                    .font(.caption.bold())
                                    .foregroundColor(.secondary)
                                ForEach(teams, id: \.team.displayName) { team in
                                    let val = team.statistics
                                        .first(where: { $0.name == catEntry?.name })?
                                        .stats?
                                        .first(where: { $0.name == stat.name })?
                                        .displayValue ?? "–"
                                    HStack {
                                        Text(team.team.abbreviation)
                                            .font(.caption.bold())
                                            .frame(width: 50, alignment: .leading)
                                        Text(val)
                                            .font(.caption.monospacedDigit())
                                    }
                                }
                            }
                            .padding(10)
                            .background(Color.secondary.opacity(0.05))
                            .cornerRadius(8)
                            .accessibilityElement(children: .combine)
                        }
                    }
                }
            }
        }
    }

    // MARK: - Flat Team Stats (NFL / NBA / NHL)

    private var flatTeamStats: some View {
        let teams = boxscore.teams
        let allRows = teams.comparisonEntries
        let profile = BoxScoreProfiles.profile(for: sport)

        // Season averages have no essentials: the toggle isn't offered for them.
        let rows = showingAllStats || isPreGame ? allRows : profile.essentialTeamRows(of: allRows)

        let tableHeaders = ["Stat"] + teams.map { $0.team.abbreviation }
        let tableRows = rows.map { stat in
            let statName = stat.label ?? stat.displayName ?? stat.name
            return [statName] + teams.map { team in
                team.statistics
                    .first(where: { $0.name == stat.name })?
                    .displayValue ?? "-"
            }
        }

        return Group {
            switch viewMode {
            case .table:
                VStack(spacing: 0) {
                    // Header row
                    HStack(spacing: 0) {
                        Text("")
                            .frame(maxWidth: .infinity, alignment: .leading)
                        ForEach(teams, id: \.team.displayName) { team in
                            Text(team.team.abbreviation)
                                .font(.subheadline.bold())
                                .frame(minWidth: 70, alignment: .trailing)
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color.secondary.opacity(0.12))
                    .accessibilityHidden(true)

                    // Data rows
                    ForEach(Array(rows.enumerated()), id: \.element.name) { rowIdx, stat in
                        let statName = stat.label ?? stat.displayName ?? stat.name
                        HStack(spacing: 0) {
                            Text(statName)
                                .font(.caption)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            ForEach(teams, id: \.team.displayName) { team in
                                let matchedStat = team.statistics
                                    .first(where: { $0.name == stat.name })
                                Text(matchedStat?.displayValue ?? "–")
                                    .font(.caption.monospacedDigit())
                                    .frame(minWidth: 70, alignment: .trailing)
                            }
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 4)
                        .background((rowIdx % 2 == 0) ? Color.clear : Color.secondary.opacity(0.04))
                        .accessibilityHidden(true)
                    }
                }
                .background(Color.secondary.opacity(0.04))
                .cornerRadius(8)
                .accessibilityHidden(true)
                .overlay(
                    AccessibleDataTable(headers: tableHeaders, rows: tableRows)
                        .allowsHitTesting(false)
                )
            case .quickList:
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(Array(rows.enumerated()), id: \.element.name) { idx, stat in
                        let statName = stat.label ?? stat.displayName ?? stat.name
                        HStack {
                            Text(statName)
                                .font(.caption)
                                .foregroundColor(.secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            ForEach(teams, id: \.team.displayName) { team in
                                let val = team.statistics.first(where: { $0.name == stat.name })?.displayValue ?? "–"
                                Text("\(team.team.abbreviation): \(val)")
                                    .font(.caption.monospacedDigit())
                            }
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 5)
                        .background(idx % 2 == 0 ? Color.clear : Color.secondary.opacity(0.04))
                    }
                }
                .background(Color.secondary.opacity(0.04))
                .cornerRadius(8)
            case .fullList:
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(rows, id: \.name) { stat in
                        let statName = stat.label ?? stat.displayName ?? stat.name
                        VStack(alignment: .leading, spacing: 6) {
                            Text(statName)
                                .font(.caption.bold())
                                .foregroundColor(.secondary)
                            ForEach(teams, id: \.team.displayName) { team in
                                let val = team.statistics.first(where: { $0.name == stat.name })?.displayValue ?? "–"
                                HStack {
                                    Text(team.team.abbreviation)
                                        .font(.caption.bold())
                                        .frame(width: 50, alignment: .leading)
                                    Text(val)
                                        .font(.caption.monospacedDigit())
                                }
                            }
                        }
                        .padding(10)
                        .background(Color.secondary.opacity(0.05))
                        .cornerRadius(8)
                        .accessibilityElement(children: .combine)
                    }
                }
            }
        }
    }

    // MARK: - Player Stat Group View

    private func playerStatGroupView(teamName: String, statGroup: PlayerStatGroup) -> some View {
        let table = statGroup.table(essentialOnly: !showingAllStats,
                                    profile: BoxScoreProfiles.profile(for: sport))
        let columns = table.columns
        let rows = table.rows
        let grid = table.accessibleGrid()

        switch viewMode {
        case .table:
            return AnyView(
                ScrollView(.horizontal, showsIndicators: true) {
                    VStack(spacing: 0) {
                        // Header row
                        HStack(spacing: 0) {
                            Text("Player")
                                .font(.caption.bold())
                                .foregroundColor(.secondary)
                                .frame(width: 140, alignment: .leading)

                            if table.showsPosition {
                                Text("Pos")
                                    .font(.caption.bold())
                                    .foregroundColor(.secondary)
                                    .frame(width: 45, alignment: .center)
                            }

                            ForEach(columns.indices, id: \.self) { idx in
                                Text(columns[idx])
                                    .font(.caption.bold())
                                    .foregroundColor(.secondary)
                                    .frame(width: 50, alignment: .trailing)
                            }
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Color.secondary.opacity(0.12))
                        .accessibilityHidden(true)

                        // Player rows
                        ForEach(rows.indices, id: \.self) { rowIdx in
                            let row = rows[rowIdx]

                            HStack(spacing: 0) {
                                Text(row.name)
                                    .font(row.kind == .totals ? .caption.bold() : .caption)
                                    .frame(width: 140, alignment: .leading)
                                    .lineLimit(1)

                                if table.showsPosition {
                                    Text(row.position)
                                        .font(.caption2)
                                        .foregroundColor(.secondary)
                                        .frame(width: 45, alignment: .center)
                                }

                                if row.kind == .didNotPlay {
                                    Text(BoxPlayerTable.didNotPlayText)
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                        .frame(width: CGFloat(columns.count) * 50, alignment: .leading)
                                } else {
                                    ForEach(row.stats.indices, id: \.self) { statIdx in
                                        Text(row.stats[statIdx])
                                            .font(.caption.monospacedDigit())
                                            .frame(width: 50, alignment: .trailing)
                                    }
                                }
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 4)
                            .background((rowIdx % 2 == 0) ? Color.clear : Color.secondary.opacity(0.04))
                            .accessibilityHidden(true)
                        }
                    }
                    .accessibilityHidden(true)
                    .overlay(
                        AccessibleDataTable(headers: grid.headers, rows: grid.rows)
                            .allowsHitTesting(false)
                    )
                }
                .background(Color.secondary.opacity(0.04))
                .cornerRadius(8)
            )
        case .quickList:
            return AnyView(
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(rows.indices, id: \.self) { idx in
                        let row = rows[idx]
                        let statsText = row.statsText(columns: columns)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(row.title)
                                .font(.caption.bold())
                                .lineLimit(1)
                            if !statsText.isEmpty {
                                Text(statsText)
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(idx % 2 == 0 ? Color.clear : Color.secondary.opacity(0.04))
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(row.spokenText(columns: columns))
                    }
                }
                .background(Color.secondary.opacity(0.04))
                .cornerRadius(8)
            )
        case .fullList:
            return AnyView(
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(rows.indices, id: \.self) { idx in
                        let row = rows[idx]
                        let pairs = zip(columns, row.stats).filter { !$0.1.isEmpty }
                        VStack(alignment: .leading, spacing: 4) {
                            Text(row.title)
                                .font(.headline)
                            if row.kind == .didNotPlay {
                                Text(BoxPlayerTable.didNotPlayText)
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            ForEach(pairs.indices, id: \.self) { pairIdx in
                                let pair = pairs[pairIdx]
                                HStack(alignment: .top) {
                                    Text("\(pair.0):")
                                        .font(.caption.bold())
                                        .foregroundColor(.secondary)
                                        .frame(width: 60, alignment: .leading)
                                    Text(pair.1)
                                        .font(.caption.monospacedDigit())
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                }
                            }
                        }
                        .padding(10)
                        .background(Color.secondary.opacity(0.05))
                        .cornerRadius(8)
                        .accessibilityElement(children: .combine)
                    }
                }
            )
        }
    }
}
