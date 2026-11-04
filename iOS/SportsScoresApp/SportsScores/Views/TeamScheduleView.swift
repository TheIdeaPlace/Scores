//
//  TeamScheduleView.swift
//  SportsScores
//
//  Created on 2/26/26.
//

import SwiftUI

struct TeamScheduleView: View {
    let team: Game.Team
    let sport: Sport
    @StateObject private var viewModel: TeamScheduleViewModel
    @State private var viewMode: ViewMode = .quickList

    init(team: Game.Team, sport: Sport) {
        self.team = team
        self.sport = sport
        _viewModel = StateObject(wrappedValue: TeamScheduleViewModel(teamId: team.id, sport: sport))
    }

    private static let monthFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "MMMM yyyy"
        return f
    }()

    private static let dayFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "EEE, MMM d"
        return f
    }()

    private static let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .none
        f.timeStyle = .short   // e.g. "3:05 PM"
        return f
    }()

    // Group games by "Month Year" string
    private var groupedGames: [(month: String, games: [ScheduleGame])] {
        var dict: [(String, [ScheduleGame])] = []
        var seen: [String: Int] = [:]
        for game in viewModel.games {
            let key = Self.monthFormatter.string(from: game.date)
            if let idx = seen[key] {
                dict[idx].1.append(game)
            } else {
                seen[key] = dict.count
                dict.append((key, [game]))
            }
        }
        return dict.map { (month: $0.0, games: $0.1) }
    }

    var body: some View {
        Group {
            if viewModel.isLoading {
                ProgressView("Loading schedule…")
            } else if viewModel.games.isEmpty {
                VStack(spacing: 16) {
                    Image(systemName: "calendar.badge.exclamationmark")
                        .font(.system(size: 48))
                        .foregroundColor(.secondary)
                    Text(viewModel.errorMessage ?? "No schedule available")
                        .font(.headline)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding()
            } else {
                VStack(spacing: 0) {
                    switch viewMode {
                    case .table:
                        scheduleTableView
                    case .quickList:
                        scheduleQuickListView
                    case .fullList:
                        scheduleList
                    }
                }
            }
        }
        .navigationTitle("\(team.abbreviation) Schedule")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                yearPicker
            }
            if !viewModel.games.isEmpty {
                ToolbarItem(placement: .navigationBarTrailing) {
                    ViewModeMenuButton(currentMode: $viewMode)
                }
            }
        }
        .task { await viewModel.fetchSchedule() }
    }

    // MARK: - Year Picker

    private var yearPicker: some View {
        Menu {
            ForEach(viewModel.availableYears, id: \.self) { year in
                Button(viewModel.seasonLabel(year)) {
                    Task { await viewModel.changeYear(year) }
                }
            }
        } label: {
            HStack(spacing: 2) {
                Text(viewModel.seasonLabel(viewModel.selectedYear))
                    .font(.subheadline.bold())
                Image(systemName: "chevron.down")
                    .font(.caption)
            }
        }
        .accessibilityLabel("Season, currently \(viewModel.seasonLabel(viewModel.selectedYear))")
    }

    // MARK: - Table view mode

    private var scheduleTableView: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                ForEach(groupedGames, id: \.month) { section in
                    scheduleTableSection(month: section.month, games: section.games)
                }
            }
            .padding(.vertical)
        }
    }

    private func scheduleTableSection(month: String, games: [ScheduleGame]) -> some View {
        let headers = ["Date", "Opp", "Result"]
        let tableRows = games.map { g -> [String] in
            let isHome = g.homeTeam.id == team.id
            let opp = isHome ? g.awayTeam : g.homeTeam
            let vs = isHome || g.isNeutralSite
            return [Self.dayFormatter.string(from: g.date),
                    (vs ? "vs " : "@ ") + opp.abbreviation,
                    scheduleResultAndLabel(g)]
        }
        return VStack(alignment: .leading, spacing: 0) {
            Text(month)
                .font(.subheadline.bold())
                .foregroundColor(.secondary)
                .padding(.horizontal, 16)
                .padding(.bottom, 6)
                .accessibilityAddTraits(.isHeader)
            VStack(spacing: 0) {
                HStack(spacing: 0) {
                    ForEach(headers, id: \.self) { h in
                        Text(h)
                            .font(.caption.bold())
                            .foregroundColor(.secondary)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 6)
                            .background(Color.secondary.opacity(0.12))
                    }
                }
                .accessibilityHidden(true)
                ForEach(Array(games.enumerated()), id: \.element.id) { idx, game in
                    let isHome = game.homeTeam.id == team.id
                    let opp = isHome ? game.awayTeam : game.homeTeam
                    let row = [Self.dayFormatter.string(from: game.date),
                               (isHome || game.isNeutralSite ? "vs " : "@ ") + opp.abbreviation,
                               scheduleResultAndLabel(game)]
                    NavigationLink(destination: GameDetailView(game: game.toGame(), sport: sport)) {
                        HStack(spacing: 0) {
                            ForEach(row.indices, id: \.self) { colIdx in
                                Text(row[colIdx])
                                    .font(.subheadline)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 8)
                            }
                        }
                        .background(idx % 2 == 0 ? Color.clear : Color.secondary.opacity(0.04))
                    }
                    .buttonStyle(.plain)
                    .accessibilityHidden(true)
                    if idx < games.count - 1 { Divider() }
                }
            }
            .background(Color.secondary.opacity(0.04))
            .cornerRadius(8)
            .accessibilityHidden(true)
            .overlay(
                AccessibleDataTable(headers: headers, rows: tableRows)
                    .allowsHitTesting(false)
            )
            .padding(.horizontal)
        }
    }

    private func scheduleResultText(_ game: ScheduleGame) -> String {
        if game.isCompleted {
            let myTeam  = game.homeTeam.id == team.id ? game.homeTeam : game.awayTeam
            let oppTeam = game.homeTeam.id == team.id ? game.awayTeam : game.homeTeam
            if let my = myTeam.score, let opp = oppTeam.score {
                let wl = my > opp ? "W" : (my == opp ? "T" : "L")
                return "\(wl) \(my)-\(opp)"
            }
            return "Final"
        } else if game.isInProgress {
            return game.statusText
        } else {
            return (game.timeIsKnown ? Self.timeFormatter.string(from: game.date) : "Time TBD")
        }
    }

    /// The result, then what sets the game apart. The label can run long ("College Football
    /// Playoff Quarterfinal at the Rose Bowl"), so it comes after the part you came for.
    private func scheduleResultAndLabel(_ game: ScheduleGame) -> String {
        let result = scheduleResultText(game)
        return game.label.map { "\(result), \($0)" } ?? result
    }

    // MARK: - Quick List view mode

    private var scheduleQuickListView: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                ForEach(groupedGames, id: \.month) { section in
                    scheduleQuickSection(month: section.month, games: section.games)
                }
            }
            .padding()
        }
    }

    private func scheduleQuickSection(month: String, games: [ScheduleGame]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(month)
                .font(.subheadline.bold())
                .foregroundColor(.secondary)
                .accessibilityAddTraits(.isHeader)
            ForEach(games) { game in
                NavigationLink(destination: GameDetailView(game: game.toGame(), sport: sport)) {
                    Text(scheduleQuickText(game))
                        .font(.subheadline)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(scheduleQuickText(game))
                .accessibilityHint("Opens game details")
            }
        }
    }

    private func scheduleQuickText(_ game: ScheduleGame) -> String {
        let isHome = game.homeTeam.id == team.id
        let opp = isHome ? game.awayTeam : game.homeTeam
        let matchup = (isHome || game.isNeutralSite ? "vs " : "@ ") + opp.abbreviation
        return "\(Self.dayFormatter.string(from: game.date)) \(matchup) \u{2014} \(scheduleResultAndLabel(game))"
    }

    // MARK: - Schedule List

    private var scheduleList: some View {
        List {
            ForEach(groupedGames, id: \.month) { section in
                Section(header: Text(section.month).font(.headline)) {
                    ForEach(section.games) { game in
                        NavigationLink(destination: GameDetailView(game: game.toGame(), sport: sport)) {
                            scheduleRow(game)
                        }
                        .listRowBackground(game.isToday ? Color.accentColor.opacity(0.12) : Color.clear)
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
        .refreshable { await viewModel.fetchSchedule() }
    }

    // MARK: - Schedule Row

    private func scheduleRow(_ game: ScheduleGame) -> some View {
        HStack(spacing: 12) {
            // Date column
            VStack(alignment: .leading, spacing: 2) {
                Text(Self.dayFormatter.string(from: game.date))
                    .font(.caption.bold())
                    .foregroundColor(game.isToday ? .accentColor : .secondary)
                if game.isToday {
                    Text("TODAY")
                        .font(.caption2.bold())
                        .foregroundColor(.accentColor)
                }
            }
            .frame(width: 80, alignment: .leading)

            Divider()

            // Matchup column
            VStack(alignment: .leading, spacing: 3) {
                // Indicate home/away
                let isHome = game.homeTeam.id == team.id
                let opponent = isHome ? game.awayTeam : game.homeTeam
                HStack(spacing: 4) {
                    Text(isHome || game.isNeutralSite ? "vs" : "@")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text(opponent.abbreviation)
                        .font(.subheadline.bold())
                }
                Text(game.venueName ?? (game.isNeutralSite ? "Neutral site" : (isHome ? "Home" : "Away")))
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .lineLimit(1)
                if let label = game.label {
                    Text(label)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }

            Spacer()

            // Score / Status column
            VStack(alignment: .trailing, spacing: 2) {
                if game.isCompleted {
                    let myTeam  = game.homeTeam.id == team.id ? game.homeTeam : game.awayTeam
                    let oppTeam = game.homeTeam.id == team.id ? game.awayTeam : game.homeTeam
                    if let myScore = myTeam.score, let oppScore = oppTeam.score {
                        let won = myScore > oppScore
                        Text(won ? "W" : (myScore == oppScore ? "T" : "L"))
                            .font(.caption.bold())
                            .foregroundColor(won ? .green : (myScore == oppScore ? .secondary : .red))
                        Text("\(myScore)-\(oppScore)")
                            .font(.caption.monospacedDigit())
                            .foregroundColor(.secondary)
                    } else {
                        Text("Final")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                } else if game.isInProgress {
                    Text(game.statusText)
                        .font(.caption)
                        .foregroundColor(.green)
                        .multilineTextAlignment(.trailing)
                } else {
                    // Scheduled: show local game time derived from the parsed date
                    Text((game.timeIsKnown ? Self.timeFormatter.string(from: game.date) : "Time TBD"))
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(scheduleAccessibilityLabel(game))
    }

    private func scheduleAccessibilityLabel(_ game: ScheduleGame) -> String {
        let isHome = game.homeTeam.id == team.id
        let opponent = isHome ? game.awayTeam : game.homeTeam
        let homeAway = isHome || game.isNeutralSite ? "vs" : "at"
        let dateStr = Self.dayFormatter.string(from: game.date)
        let statusPart: String
        if game.isCompleted {
            let myTeam  = game.homeTeam.id == team.id ? game.homeTeam : game.awayTeam
            let oppTeam = game.homeTeam.id == team.id ? game.awayTeam : game.homeTeam
            if let myScore = myTeam.score, let oppScore = oppTeam.score {
                let result = myScore > oppScore ? "Win" : (myScore == oppScore ? "Tie" : "Loss")
                statusPart = "\(result), \(myScore) to \(oppScore)"
            } else {
                statusPart = "Final"
            }
        } else if game.isInProgress {
            statusPart = game.statusText
        } else {
            statusPart = (game.timeIsKnown ? Self.timeFormatter.string(from: game.date) : "Time TBD")
        }
        let label = game.label.map { ", \($0)" } ?? ""
        return "\(dateStr), \(homeAway) \(opponent.displayName), \(statusPart)\(label)"
    }
}

#Preview {
    NavigationStack {
        TeamScheduleView(
            team: Game.Team(id: "10", name: "Yankees", abbreviation: "NYY",
                            displayName: "New York Yankees", score: nil, record: nil, logo: nil),
            sport: .mlb
        )
    }
}
