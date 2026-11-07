//
//  WorldCupHubView.swift
//  SportsScores
//
//  Root hub for the FIFA World Cup (men's and women's).
//  Four tabs: Scores · Groups · Bracket · News
//
//  • Scores tab — date-navigable list of that day's matches (3 view modes)
//  • Groups tab — all 12 group standings (3 view modes, AccessibleDataTable overlay)
//  • Bracket tab — phase picker + match list for each knockout round
//  • News tab    — World Cup news feed (reuses NewsView)
//

import SwiftUI
import UIKit

private enum WCTab: Int {
    case scores = 0, groups, bracket, news
}

struct WorldCupHubView: View {

    let sport: Sport    // .worldCup or .worldCupWomens

    @StateObject private var viewModel: WorldCupViewModel
    @State private var selectedTab: WCTab = .scores
    @State private var viewMode: ViewMode = .savedDefault()
    @EnvironmentObject private var appSettings: AppSettings

    init(sport: Sport) {
        self.sport = sport
        _viewModel = StateObject(wrappedValue: WorldCupViewModel(sport: sport))
    }

    var body: some View {
        VStack(spacing: 0) {
            if selectedTab == .scores {
                dateNavigationBar
                    .padding(.horizontal)
                    .padding(.top, 8)
                    .padding(.bottom, 6)
            }

            tabContent
                .frame(maxWidth: .infinity, maxHeight: .infinity)

            Divider()
            Picker("Section", selection: $selectedTab) {
                Text("Scores").tag(WCTab.scores)
                Text("Groups").tag(WCTab.groups)
                Text("Bracket").tag(WCTab.bracket)
                Text("News").tag(WCTab.news)
            }
            .pickerStyle(.segmented)
            .padding(.horizontal)
            .padding(.top, 4)
            .padding(.bottom, 8)
        }
        .navigationTitle(sport.displayName)
        .toolbar {
            if selectedTab == .scores && !viewModel.games.isEmpty {
                ToolbarItem(placement: .navigationBarTrailing) {
                    ViewModeMenuButton(currentMode: $viewMode)
                }
            }
        }
        .task { await viewModel.loadAll() }
        .refreshable {
            switch selectedTab {
            case .scores:  await viewModel.loadGamesForDate()
            case .groups:  await viewModel.loadGroups()
            case .bracket:
                if let phase = viewModel.selectedPhase, phase.id != "1" {
                    await viewModel.loadBracket(for: phase)
                } else {
                    await viewModel.loadGroups()
                }
            case .news: break
            }
        }
    }

    // MARK: - Tab content

    @ViewBuilder
    private var tabContent: some View {
        switch selectedTab {
        case .scores:
            scoresTab
        case .groups:
            WorldCupGroupsView(
                groups: viewModel.groups,
                sport: sport,
                phases: viewModel.phases,
                isLoading: viewModel.isLoadingGroups,
                error: viewModel.groupsError,
                onRetry: { Task { await viewModel.loadGroups() } }
            )
        case .bracket:
            WorldCupBracketView(viewModel: viewModel, sport: sport)
        case .news:
            NewsView(sport: sport)
        }
    }

    // MARK: - Scores tab

    @ViewBuilder
    private var scoresTab: some View {
        if viewModel.isLoadingGames {
            ProgressView("Loading matches…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .accessibilityLabel("Loading World Cup matches")
        } else if let err = viewModel.gamesError {
            ErrorStateView(message: err) { Task { await viewModel.loadGamesForDate() } }
        } else if viewModel.games.isEmpty {
            noGamesState
        } else {
            switch viewMode {
            case .table:    gamesTableView
            case .quickList: gamesQuickListView
            case .fullList:  gamesFullListView
            }
        }
    }

    // MARK: - Date navigation bar

    private var dateNavigationBar: some View {
        HStack(spacing: 8) {
            Button {
                Task { await viewModel.goBack(); announceNavigation() }
            } label: {
                Image(systemName: "chevron.left")
                    .font(.body.bold())
                    .frame(width: 44, height: 36)
                    .contentShape(Rectangle())
            }
            .disabled(viewModel.isLoadingGames || !viewModel.canNavigateBackward)
            .accessibilityLabel("Previous Day")

            Spacer()

            VStack(spacing: 2) {
                Text(viewModel.selectedDate.formatted(date: .abbreviated, time: .omitted))
                    .font(.subheadline.bold())
                Text(dayOfWeek(viewModel.selectedDate))
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel(viewModel.dateAccessibilityText)

            Spacer()

            Button {
                Task { await viewModel.goForward(); announceNavigation() }
            } label: {
                Image(systemName: "chevron.right")
                    .font(.body.bold())
                    .frame(width: 44, height: 36)
                    .contentShape(Rectangle())
            }
            .disabled(viewModel.isLoadingGames || !viewModel.canNavigateForward)
            .accessibilityLabel("Next Day")

            if !viewModel.isOnToday {
                Button("Today") {
                    Task { await viewModel.goToToday(); announceNavigation() }
                }
                .font(.caption)
                .buttonStyle(.bordered)
                .controlSize(.small)
                .transition(.opacity)
            }
        }
    }

    private func announceNavigation() {
        UIAccessibility.post(notification: .announcement, argument: viewModel.dateAccessibilityText)
    }

    private func dayOfWeek(_ date: Date) -> String {
        let fmt = DateFormatter()
        fmt.dateFormat = "EEEE"
        return fmt.string(from: date)
    }

    // MARK: - Table view mode

    private var gamesTableView: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                gamesTableSection(title: "In Progress", games: viewModel.inProgressGames)
                gamesTableSection(title: "Upcoming",    games: viewModel.upcomingGames)
                gamesTableSection(title: "Completed",   games: viewModel.completedGames)
                gamesTableSection(title: "Postponed",   games: viewModel.postponedGames)
            }
            .padding(.vertical)
        }
    }

    @ViewBuilder
    private func gamesTableSection(title: String, games: [Game]) -> some View {
        if !games.isEmpty {
            let headers = ["Away", "Home", "Status"]
            let rows = games.map { gameTableRow($0) }
            VStack(alignment: .leading, spacing: 0) {
                Text(title)
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
                        NavigationLink(destination: GameDetailView(game: game, sport: sport)) {
                            HStack(spacing: 0) {
                                ForEach(Array(gameTableRow(game).enumerated()), id: \.offset) { _, val in
                                    Text(val)
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
                    AccessibleDataTable(headers: headers, rows: rows)
                        .allowsHitTesting(false)
                )
                .padding(.horizontal)
            }
        }
    }

    // MARK: - Quick List view mode

    private var gamesQuickListView: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                gamesQuickSection(title: "In Progress", games: viewModel.inProgressGames)
                gamesQuickSection(title: "Upcoming",    games: viewModel.upcomingGames)
                gamesQuickSection(title: "Completed",   games: viewModel.completedGames)
                gamesQuickSection(title: "Postponed",   games: viewModel.postponedGames)
            }
            .padding()
        }
    }

    @ViewBuilder
    private func gamesQuickSection(title: String, games: [Game]) -> some View {
        if !games.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.subheadline.bold())
                    .foregroundColor(.secondary)
                    .accessibilityAddTraits(.isHeader)
                ForEach(games) { game in
                    NavigationLink(destination: GameDetailView(game: game, sport: sport)) {
                        Text(gameQuickText(game))
                            .font(.subheadline)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(gameQuickAccessibilityText(game))
                    .accessibilityHint("Opens match details")
                }
            }
        }
    }

    // MARK: - Full List view mode

    private var gamesFullListView: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                gamesFullSection(title: "In Progress", games: viewModel.inProgressGames)
                gamesFullSection(title: "Upcoming",    games: viewModel.upcomingGames)
                gamesFullSection(title: "Completed",   games: viewModel.completedGames)
                gamesFullSection(title: "Postponed",   games: viewModel.postponedGames)
            }
            .padding()
        }
    }

    @ViewBuilder
    private func gamesFullSection(title: String, games: [Game]) -> some View {
        if !games.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text(title)
                    .font(.subheadline.bold())
                    .foregroundColor(.secondary)
                    .accessibilityAddTraits(.isHeader)
                ForEach(games) { game in
                    NavigationLink(destination: GameDetailView(game: game, sport: sport)) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("\(game.awayTeam.displayName) vs \(game.homeTeam.displayName)")
                                .font(.headline)
                            Text(gameFullDetailText(game))
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.secondary.opacity(0.05))
                        .cornerRadius(8)
                    }
                    .buttonStyle(.plain)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(gameQuickAccessibilityText(game))
                    .accessibilityHint("Opens match details")
                }
            }
        }
    }

    // MARK: - Row formatters

    private func gameTableRow(_ game: Game) -> [String] {
        let away = game.awayTeam.abbreviation + (game.awayTeam.score.map { " \($0)" } ?? "")
        let home = game.homeTeam.abbreviation + (game.homeTeam.score.map { " \($0)" } ?? "")
        return [away, home, gameStatusText(game, abbreviated: true)]
    }

    private func gameQuickText(_ game: Game) -> String {
        let away = game.awayTeam.abbreviation + (game.awayTeam.score.map { " \($0)" } ?? "")
        let home = game.homeTeam.abbreviation + (game.homeTeam.score.map { " \($0)" } ?? "")
        var line = "\(away) @ \(home) — \(gameStatusText(game, abbreviated: true))"
        if let venue = game.venue, !venue.name.isEmpty { line += " · \(venue.fullName)" }
        return line
    }

    private func gameQuickAccessibilityText(_ game: Game) -> String {
        let pref = appSettings.teamNamePreference
        let away = game.awayTeam.voiceOverName(for: pref) + (game.awayTeam.score.map { " \($0)" } ?? "")
        let home = game.homeTeam.voiceOverName(for: pref) + (game.homeTeam.score.map { " \($0)" } ?? "")
        var label = "\(away) at \(home), \(gameStatusText(game, abbreviated: false))"
        // Venue: unlabeled (terse) but still spoken.
        if let venue = game.venue, !venue.name.isEmpty { label += ", \(venue.fullName)" }
        return label
    }

    private func gameFullDetailText(_ game: Game) -> String {
        var parts = [gameStatusText(game, abbreviated: false)]
        if let venue = game.venue?.fullName, !venue.isEmpty { parts.append(venue) }
        if game.shouldShowBroadcastInfo, let b = game.broadcasts.first, !b.isEmpty {
            parts.append("TV: \(b)")
        }
        return parts.joined(separator: " · ")
    }

    private func gameStatusText(_ game: Game, abbreviated: Bool) -> String {
        if game.status.isLive           { return game.status.displayText }
        if game.status.isPostponed      { return abbreviated ? "PPD" : "Postponed" }
        if game.status.isCancelled      { return abbreviated ? "Cxl" : "Cancelled" }
        if game.status.isSuspended      { return abbreviated ? "Susp" : "Suspended" }
        if game.status.isCompleted      { return "Final" }
        return game.displayTime
    }

    // MARK: - No games state

    private var noGamesState: some View {
        VStack(spacing: 16) {
            Image(systemName: "calendar.badge.exclamationmark")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
                .accessibilityHidden(true)
            Text("No matches scheduled")
                .font(.headline)
                .foregroundColor(.secondary)
            if !viewModel.isOnToday {
                Button("Go to Today") {
                    Task { await viewModel.goToToday() }
                }
                .buttonStyle(.bordered)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

#Preview {
    NavigationStack {
        WorldCupHubView(sport: .worldCup)
            .environmentObject(AppSettings())
    }
}
