//
//  SoccerLiveView.swift
//  SportsScores
//
//  All-leagues soccer live scores view. Mirrors LiveScoresView but scoped
//  to Sport.soccerLeagues only. Accessible from the Soccer hub.
//

import SwiftUI

struct SoccerLiveView: View {
    @StateObject private var viewModel = SoccerLiveViewModel()
    @State private var viewMode: ViewMode = .quickList
    @EnvironmentObject private var appSettings: AppSettings

    var body: some View {
        Group {
            if viewModel.isLoading {
                ProgressView("Loading soccer games...")
            } else if let error = viewModel.errorMessage {
                VStack(spacing: 16) {
                    Image(systemName: "calendar.badge.clock")
                        .font(.system(size: 48))
                        .foregroundColor(.secondary)
                    Text(error)
                        .multilineTextAlignment(.center)
                        .foregroundColor(.secondary)
                    Button("Retry") {
                        Task { await viewModel.fetchAllGames() }
                    }
                    .buttonStyle(.bordered)
                }
                .padding()
            } else {
                scrollContent
            }
        }
        .navigationTitle("Live Soccer")
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Menu {
                    ForEach(AutoRefreshInterval.allCases) { interval in
                        Button {
                            appSettings.autoRefreshInterval = interval
                        } label: {
                            HStack {
                                Text(interval == .manual ? "Manual" : "Every \(interval.label)")
                                if appSettings.autoRefreshInterval == interval {
                                    Image(systemName: "checkmark")
                                }
                            }
                        }
                    }
                } label: {
                    Label(appSettings.autoRefreshInterval == .manual
                          ? "Manual" : "Auto \(appSettings.autoRefreshInterval.label)",
                          systemImage: "arrow.clockwise")
                    .font(.subheadline)
                }
            }
            ToolbarItem(placement: .navigationBarTrailing) {
                ViewModeMenuButton(currentMode: $viewMode)
            }
        }
        .task {
            await viewModel.fetchAllGames()
        }
        .task(id: appSettings.autoRefreshInterval) {
            while !Task.isCancelled {
                let secs = appSettings.autoRefreshInterval.rawValue
                if secs > 0 {
                    try? await Task.sleep(for: .seconds(secs))
                    guard !Task.isCancelled else { break }
                    await viewModel.refresh()
                } else {
                    try? await Task.sleep(for: .seconds(86400))
                }
            }
        }
        .refreshable {
            await viewModel.refresh()
        }
    }

    private var scrollContent: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                if !viewModel.liveGames.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        sectionHeader(title: "LIVE NOW", count: totalCount(viewModel.liveGames))
                        ForEach(viewModel.liveGames) { lg in
                            leagueSection(leagueGames: lg, isLive: true)
                        }
                    }
                    .padding(.horizontal)
                }

                if !viewModel.upcomingGames.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        sectionHeader(title: "UPCOMING", count: totalCount(viewModel.upcomingGames))
                        ForEach(viewModel.upcomingGames) { lg in
                            leagueSection(leagueGames: lg, isLive: false)
                        }
                    }
                    .padding(.horizontal)
                }

                if !viewModel.completedGames.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        sectionHeader(title: "COMPLETED", count: totalCount(viewModel.completedGames))
                        ForEach(viewModel.completedGames) { lg in
                            leagueSection(leagueGames: lg, isLive: false)
                        }
                    }
                    .padding(.horizontal)
                }

                if let note = viewModel.failureNote {
                    Text(note)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .padding(.horizontal)
                }

                if viewModel.liveGames.isEmpty && viewModel.upcomingGames.isEmpty && viewModel.completedGames.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "calendar.badge.exclamationmark")
                            .font(.system(size: 48))
                            .foregroundColor(.secondary)
                        Text("No soccer games today")
                            .font(.headline)
                            .foregroundColor(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.top, 40)
                }
            }
            .padding(.vertical)
            }
        }
    }

    private func sectionHeader(title: String, count: Int) -> some View {
        HStack {
            Text(title)
                .font(.headline)
                .fontWeight(.bold)
            Text("\(count)")
                .font(.caption)
                .foregroundColor(.white)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.blue)
                .cornerRadius(12)
        }
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isHeader)
    }

    private func leagueSection(leagueGames: SoccerLiveViewModel.LeagueGames, isLive: Bool) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: leagueGames.sport.systemImage)
                    .font(.title3)
                Text(leagueGames.sport.displayName)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                Text("\(leagueGames.games.count)")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color.secondary.opacity(0.1))
            .cornerRadius(8)
            .accessibilityElement(children: .combine)
            .accessibilityAddTraits(.isHeader)

            switch viewMode {
            case .table:
                soccerTableSection(games: leagueGames.games, sport: leagueGames.sport)
            case .quickList:
                soccerQuickSection(games: leagueGames.games, sport: leagueGames.sport)
            case .fullList:
                ForEach(leagueGames.games) { game in
                    NavigationLink(destination: GameDetailView(game: game, sport: leagueGames.sport)) {
                        CompactGameRow(game: game, isLive: isLive, sport: leagueGames.sport)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.vertical, 4)
    }

    private func soccerGameRow(_ game: Game) -> [String] {
        let away = game.awayTeam.rankedAbbreviation + (game.awayTeam.score.map { " \($0)" } ?? "")
        let home = game.homeTeam.rankedAbbreviation + (game.homeTeam.score.map { " \($0)" } ?? "")
        let status = game.status.isLive ? game.status.displayText
            : (game.status.isSuspended ? "Susp" : (game.status.isCompleted ? "Final" : game.displayTime))
        return [away, home, status]
    }

    private func soccerTableSection(games: [Game], sport: Sport) -> some View {
        let headers = ["Away", "Home", "Status"]
        let rows = games.map { soccerGameRow($0) }
        return VStack(spacing: 0) {
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
                        ForEach(Array(soccerGameRow(game).enumerated()), id: \.offset) { _, val in
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
    }

    private func soccerQuickSection(games: [Game], sport: Sport) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(games) { game in
                NavigationLink(destination: GameDetailView(game: game, sport: sport)) {
                    Text(soccerQuickText(game))
                        .font(.subheadline)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(soccerQuickText(game))
                .accessibilityHint("Opens game details")
            }
        }
    }

    private func soccerQuickText(_ game: Game) -> String {
        let away = game.awayTeam.rankedAbbreviation + (game.awayTeam.score.map { " \($0)" } ?? "")
        let home = game.homeTeam.rankedAbbreviation + (game.homeTeam.score.map { " \($0)" } ?? "")
        let status = game.status.isLive ? game.status.displayText
            : (game.status.isSuspended ? "Suspended" : (game.status.isCompleted ? "Final" : game.displayTime))
        return "\(away) \(game.matchupSymbol) \(home) \u{2014} \(status)"
    }

    private func totalCount(_ groups: [SoccerLiveViewModel.LeagueGames]) -> Int {
        groups.reduce(0) { $0 + $1.games.count }
    }
}
