//
//  DataTableView.swift
//  SportsScores
//
//  Created on 1/4/26.
//
//  Revolutionary three-view-mode table component
//  Supports: Table View, Quick List, Full List

import SwiftUI

struct DataTableView: View {
    let headers: [String]
    let rows: [[String]]
    @State private var viewMode: ViewMode = .savedDefault()

    var body: some View {
        VStack(spacing: 0) {
            // Content based on view mode
            ScrollView {
                switch viewMode {
                case .table:
                    tableView
                case .quickList:
                    quickListView
                case .fullList:
                    fullListView
                }
            }
        }
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                ViewModeMenuButton(currentMode: $viewMode)
            }
        }
    }
    
    // MARK: - Table View
    private var tableView: some View {
        tableGrid
            .accessibilityHidden(true)
            .overlay(
                AccessibleDataTable(headers: headers, rows: rows)
                    .allowsHitTesting(false)
            )
    }

    private var tableGrid: some View {
        VStack(spacing: 0) {
            // Header Row
            HStack(spacing: 0) {
                ForEach(headers, id: \.self) { header in
                    Text(header)
                        .font(.caption)
                        .fontWeight(.bold)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                        .background(Color.secondary.opacity(0.2))
                }
            }
            
            Divider()
            
            // Data Rows
            ForEach(Array(rows.enumerated()), id: \.offset) { index, row in
                HStack(spacing: 0) {
                    ForEach(Array(row.enumerated()), id: \.offset) { colIndex, value in
                        Text(value)
                            .font(.caption)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 8)
                            .background(index % 2 == 0 ? Color.clear : Color.secondary.opacity(0.05))
                    }
                }
                if index < rows.count - 1 {
                    Divider()
                }
            }
        }
    }
    
    // MARK: - Quick List View
    private var quickListView: some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(Array(rows.enumerated()), id: \.offset) { index, row in
                VStack(alignment: .leading, spacing: 4) {
                    Text(row.joined(separator: ", "))
                        .font(.body)
                        .padding(.vertical, 8)
                        .padding(.horizontal, 12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(index % 2 == 0 ? Color.clear : Color.secondary.opacity(0.05))
                        .cornerRadius(6)
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel(row.joined(separator: ", "))
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
    }
    
    // MARK: - Full List View
    private var fullListView: some View {
        VStack(alignment: .leading, spacing: 16) {
            ForEach(Array(rows.enumerated()), id: \.offset) { index, row in
                VStack(alignment: .leading, spacing: 6) {
                    Text(row.first ?? "")
                        .font(.headline)
                        .foregroundColor(.primary)
                    
                    ForEach(Array(row.enumerated()), id: \.offset) { colIndex, value in
                        HStack(alignment: .top) {
                            Text("\(headers[colIndex]):")
                                .font(.caption)
                                .fontWeight(.semibold)
                                .foregroundColor(.secondary)
                                .frame(width: 100, alignment: .leading)
                            
                            Text(value)
                                .font(.caption)
                                .foregroundColor(.primary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
                .padding(12)
                .background(Color.secondary.opacity(0.05))
                .cornerRadius(8)
                .accessibilityElement(children: .combine)
                .accessibilityLabel(createFullAccessibilityLabel(for: row))
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
    }
    
    // MARK: - Accessibility Helpers
    private func createFullAccessibilityLabel(for row: [String]) -> String {
        zip(headers, row).map { "\($0): \($1)" }.joined(separator: "; ")
    }
}

// MARK: - Standings-Specific Table View
struct StandingsTableView: View {
    let standingsGroups: [StandingsGroup]
    let sport: Sport
    /// Wild card groups swap GB for wild-card GB and add the Status column that
    /// carries the playoff cut line.
    var isWildCard: Bool = false
    @State private var viewMode: ViewMode = .savedDefault()
    @State private var showExpanded = false
    @EnvironmentObject private var appSettings: AppSettings
    /// A soccer table's fixed widths grow with the text size, so nothing is cut off.
    @ScaledMetric(relativeTo: .caption) private var soccerWidthScale: CGFloat = 1

    // MARK: Column definitions

    private var basicHeaders: [String] {
        if sport.isSoccer { return SoccerTableRow.headers }
        return isWildCard
            ? ["Pos", "Team", "W", "L", "PCT", "WCGB", "Streak", "Status"]
            : (sport == .nhl ? ["Team", "W", "L", "OTL", "PTS", "Streak"]
                             : ["Team", "W", "L", "PCT", "GB", "Streak"])
    }

    private var expandedHeaders: [String] {
        // The wild card columns are the whole story; there is no wider variant. A soccer table
        // has one set too, the same as on Windows.
        if isWildCard || sport.isSoccer { return basicHeaders }
        switch sport {
        case .mlb:  return ["Team", "W", "L", "PCT", "GB", "R", "RA", "Diff", "Home", "Road", "L10"]
        case .nfl:  return ["Team", "W", "L", "T", "PCT", "PF", "PA", "Diff", "Div", "Seed"]
        case .nba:  return ["Team", "W", "L", "PCT", "GB", "PPG", "Opp", "Diff", "Seed"]
        case .nhl:  return ["Team", "W", "L", "OTL", "PTS", "GF", "GA", "Diff", "Seed"]
        default:    return basicHeaders
        }
    }

    private var activeHeaders: [String] { showExpanded ? expandedHeaders : basicHeaders }

    /// Column holding the team name. Wild card and soccer rows lead with a position,
    /// so the team sits at 1 there; everywhere else it is column 0. Drives both the
    /// flexible-width column and the accessibility row header.
    private var teamColumn: Int { isWildCard || sport.isSoccer ? 1 : 0 }

    /// A soccer table scrolls sideways, where a flexible column has no width to fill, so
    /// each column has its own and the rows line up under the headings.
    private func soccerColumnWidth(_ column: Int) -> CGFloat {
        switch SoccerTableRow.headers[column] {
        case "Team":   return 64 * soccerWidthScale
        case "Status": return 340 * soccerWidthScale
        default:       return 40 * soccerWidthScale
        }
    }

    private func rowData(for entry: StandingsEntry) -> [String] {
        if let soccer = entry.soccer {
            return soccer.cells(team: entry.team.abbreviation)
        }
        let s = entry.stats
        if let wc = entry.wildCard, isWildCard {
            return [wc.position, entry.team.abbreviation,
                    "\(s.wins)", "\(s.losses)",
                    s.displayWinPercent, wc.gamesBack, s.streak,
                    wc.spokenStatus]
        }
        if !showExpanded {
            if sport == .nhl {
                return [entry.team.abbreviation,
                        "\(s.wins)", "\(s.losses)", "\(s.otLosses ?? 0)",
                        "\(s.nhlPoints ?? 0)", s.streak]
            }
            return [entry.team.abbreviation,
                    "\(s.wins)", "\(s.losses)",
                    s.displayWinPercent, s.gamesBack, s.streak]
        }
        switch sport {
        case .mlb:
            return [entry.team.abbreviation,
                    "\(s.wins)", "\(s.losses)", s.displayWinPercent, s.gamesBack,
                    "\(s.pointsFor ?? 0)", "\(s.pointsAgainst ?? 0)",
                    s.differential ?? "-",
                    s.homeRecord ?? "-", s.roadRecord ?? "-", s.lastTenRecord ?? "-"]
        case .nfl:
            return [entry.team.abbreviation,
                    "\(s.wins)", "\(s.losses)", "\(s.ties ?? 0)", s.displayWinPercent,
                    "\(s.pointsFor ?? 0)", "\(s.pointsAgainst ?? 0)",
                    s.differential ?? "-",
                    s.divisionRecord ?? "-",
                    s.playoffSeed.map { "\($0)" } ?? "-"]
        case .nba:
            return [entry.team.abbreviation,
                    "\(s.wins)", "\(s.losses)", s.displayWinPercent, s.gamesBack,
                    String(format: "%.1f", s.avgPointsFor ?? 0),
                    String(format: "%.1f", s.avgPointsAgainst ?? 0),
                    s.differential ?? "-",
                    s.playoffSeed.map { "\($0)" } ?? "-"]
        case .nhl:
            return [entry.team.abbreviation,
                    "\(s.wins)", "\(s.losses)", "\(s.otLosses ?? 0)",
                    "\(s.nhlPoints ?? 0)",
                    "\(s.pointsFor ?? 0)", "\(s.pointsAgainst ?? 0)",
                    s.differential ?? "-",
                    s.playoffSeed.map { "\($0)" } ?? "-"]
        default:
            return [entry.team.abbreviation,
                    "\(s.wins)", "\(s.losses)",
                    s.displayWinPercent, s.gamesBack, s.streak]
        }
    }

    /// Same as `rowData(for:)` but uses the preference-aware team name in column 0
    /// — used by the UIKit accessibility table overlay so VoiceOver speaks the name
    /// according to the user's team name setting.
    private func accessibleRowData(for entry: StandingsEntry) -> [String] {
        var cols = rowData(for: entry)
        // Wild card and soccer rows lead with the position, so the team name is column 1.
        let nameColumn = (isWildCard && entry.wildCard != nil) || entry.soccer != nil ? 1 : 0
        if cols.count > nameColumn {
            cols[nameColumn] = entry.team.voiceOverName(for: appSettings.teamNamePreference)
        }
        return cols
    }

    /// Accessibility label for quick list mode: no field names, canonical order, preference-aware team name.
    private func quickListAccessibilityLabel(for entry: StandingsEntry) -> String {
        let teamName = entry.team.voiceOverName(for: appSettings.teamNamePreference)
        if let soccer = entry.soccer {
            return soccer.quickText(team: teamName)
        }
        let s = entry.stats
        if let wc = entry.wildCard, isWildCard {
            let lead = wc.position == "-" ? "" : "\(wc.position). "
            return "\(lead)\(teamName), \(s.wins)-\(s.losses), "
                + "\(s.displayWinPercent), wild card games back: \(wc.gamesBack), "
                + "\(s.streak), \(wc.spokenStatus)"
        }
        if sport == .nhl {
            return "\(teamName), \(s.wins)-\(s.losses)-\(s.otLosses ?? 0), \(s.nhlPoints ?? 0) points, streak \(s.streak)"
        }
        var label = "\(teamName), \(s.wins)-\(s.losses), \(s.displayWinPercent), GB: \(s.gamesBack)"
        if let l10 = s.lastTenRecord { label += ", last 10: \(l10)" }
        return label
    }

    /// Accessibility label for full list mode: the row's own text, so VoiceOver hears every
    /// field it shows, with the preference-aware team name.
    private func fullListAccessibilityLabel(for entry: StandingsEntry) -> String {
        let teamName = entry.team.voiceOverName(for: appSettings.teamNamePreference)
        if let soccer = entry.soccer {
            return soccer.fullText(team: teamName)
        }
        return sport == .nhl ? entry.nhlFullListText(team: teamName) : entry.fullListText(team: teamName)
    }

    /// Convert a standings TeamInfo into the Game.Team type that TeamScheduleView expects.
    private func scheduleTeam(from info: StandingsEntry.TeamInfo) -> Game.Team {
        Game.Team(id: info.id, name: info.name, abbreviation: info.abbreviation,
                  displayName: info.displayName, score: nil, record: nil, logo: nil)
    }

    var body: some View {
        VStack(spacing: 0) {
            // Single vertical ScrollView — NO nested vertical scroll views
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0, pinnedViews: [.sectionHeaders]) {
                    ForEach(standingsGroups) { group in
                        Section {
                            switch viewMode {
                            case .table:
                                // Wild card is 8 columns including a wordy Status,
                                // so it needs the horizontal scroll that expanded
                                // mode gets — it does not fit a phone otherwise. Nor
                                // does a soccer table's 11.
                                if showExpanded || isWildCard || sport.isSoccer {
                                    ScrollView(.horizontal, showsIndicators: true) {
                                        standingsTableSection(for: group)
                                    }
                                } else {
                                    standingsTableSection(for: group)
                                }
                            case .quickList:
                                quickListSection(for: group)
                            case .fullList:
                                fullListSection(for: group)
                            }
                        } header: {
                            Text(group.name)
                                .font(.headline)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.horizontal)
                                .padding(.vertical, 8)
                                .background(Color(uiColor: .systemBackground))
                                .accessibilityAddTraits(.isHeader)
                        }
                    }
                }
            }
        }
        .toolbar {
            ToolbarItemGroup(placement: .navigationBarTrailing) {
                // Wild card and soccer have one column set, so Expand would
                // announce a state change and do nothing.
                if viewMode == .table && !isWildCard && !sport.isSoccer {
                    Button {
                        withAnimation { showExpanded.toggle() }
                    } label: {
                        Label(showExpanded ? "Basic" : "Expand",
                              systemImage: showExpanded ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right")
                        .labelStyle(.iconOnly)
                    }
                    .accessibilityLabel(showExpanded ? "Show basic columns" : "Show expanded columns")
                }
                ViewModeMenuButton(currentMode: $viewMode)
            }
        }
    }

    // MARK: - Table mode

    private func standingsTableSection(for group: StandingsGroup) -> some View {
        VStack(spacing: 0) {
            // Header row — derived from activeHeaders
            HStack(spacing: 0) {
                ForEach(Array(activeHeaders.enumerated()), id: \.offset) { idx, col in
                    if sport.isSoccer {
                        Text(col)
                            .font(.caption.bold())
                            .frame(width: soccerColumnWidth(idx))
                    } else if idx == teamColumn {
                        Text(col)
                            .font(.caption.bold())
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 8)
                    } else {
                        Text(col)
                            .font(.caption.bold())
                            .frame(width: isWildCard ? 60 : 44)
                    }
                }
            }
            .padding(.vertical, 6)
            .background(Color.secondary.opacity(0.15))

            Divider()

            ForEach(Array(group.entries.enumerated()), id: \.element.id) { idx, entry in
                let cols = rowData(for: entry)
                NavigationLink(destination: TeamScheduleView(team: scheduleTeam(from: entry.team), sport: sport)) {
                    HStack(spacing: 0) {
                        if sport.isSoccer {
                            ForEach(Array(cols.enumerated()), id: \.offset) { column, value in
                                Text(value)
                                    .font(.caption.monospacedDigit())
                                    .lineLimit(1)
                                    .frame(width: soccerColumnWidth(column))
                            }
                        } else {
                            Text(cols[0])   // Team abbreviation — flexible
                                .font(.subheadline.bold())
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.horizontal, 8)
                            ForEach(Array(cols.dropFirst().enumerated()), id: \.offset) { _, value in
                                Text(value)
                                    .font(.caption.monospacedDigit())
                                    .frame(width: 44)
                            }
                        }
                    }
                    .padding(.vertical, 7)
                    .background(idx % 2 == 0 ? Color.clear : Color.secondary.opacity(0.05))
                }
                .buttonStyle(.plain)
                // Row is hidden from VoiceOver; AccessibleDataTable overlay
                // handles all accessibility navigation for the table view.
                .accessibilityHidden(true)

                if idx < group.entries.count - 1 {
                    Divider().padding(.leading, 8)
                }
            }
        }
        .accessibilityHidden(true) // UIKit overlay handles VoiceOver for table mode
        .overlay(
            AccessibleDataTable(
                headers: activeHeaders,
                rows: group.entries.map { accessibleRowData(for: $0) },
                rowHeaderColumn: teamColumn,
                columnWidths: sport.isSoccer ? activeHeaders.indices.map { soccerColumnWidth($0) } : nil
            )
            .allowsHitTesting(false)
        )
        .padding(.bottom, 16)
    }

    // MARK: - Quick List mode

    private func quickListSection(for group: StandingsGroup) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(group.entries) { entry in
                NavigationLink(destination: TeamScheduleView(team: scheduleTeam(from: entry.team), sport: sport)) {
                    Text(entry.soccer?.quickText(team: entry.team.abbreviation)
                         ?? (sport == .nhl ? entry.nhlQuickListText : entry.quickListText))
                        .font(.subheadline)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(quickListAccessibilityLabel(for: entry))
                .accessibilityHint("Opens \(entry.team.displayName) schedule")
            }
        }
        .padding(.bottom, 16)
    }

    // MARK: - Full List mode

    private func fullListSection(for group: StandingsGroup) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(group.entries) { entry in
                NavigationLink(destination: TeamScheduleView(team: scheduleTeam(from: entry.team), sport: sport)) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(entry.team.displayName)
                            .font(.headline)
                        Text(entry.soccer?.fullText(team: entry.team.displayName)
                             ?? (sport == .nhl ? entry.nhlFullListText : entry.fullListText))
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.secondary.opacity(0.05))
                    .cornerRadius(8)
                    .padding(.horizontal, 12)
                }
                .buttonStyle(.plain)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(fullListAccessibilityLabel(for: entry))
                .accessibilityHint("Opens \(entry.team.displayName) schedule")
            }
        }
        .padding(.bottom, 16)
    }
}

// MARK: - Preview
#Preview {
    NavigationView {
        DataTableView(
            headers: ["Rank", "Team", "W", "L"],
            rows: [
                ["1", "LAD", "95", "67"],
                ["2", "ARI", "84", "78"],
                ["3", "SD", "82", "80"]
            ]
        )
        .navigationTitle("Example Table")
    }
}
