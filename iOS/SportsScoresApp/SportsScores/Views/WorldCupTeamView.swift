//
//  WorldCupTeamView.swift
//  SportsScores
//
//  Shows a single World Cup team's full tournament path:
//    • Group standing card (current position + stats)
//    • All confirmed matches, grouped by phase in chronological order
//
//  Supports Table · Quick List · Full List view modes for the match list.
//  Each match row navigates to GameDetailView.
//

import SwiftUI

struct WorldCupTeamView: View {

    @StateObject private var viewModel: WorldCupTeamViewModel
    @State private var viewMode: ViewMode = .savedDefault()
    @EnvironmentObject private var appSettings: AppSettings

    let sport: Sport

    init(entry: WorldCupGroupEntry, group: WorldCupGroup, sport: Sport, phases: [WorldCupPhase]) {
        self.sport = sport
        _viewModel = StateObject(wrappedValue:
            WorldCupTeamViewModel(entry: entry, group: group, sport: sport, phases: phases))
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0, pinnedViews: []) {
                groupStandingCard
                    .padding()

                Divider()

                if viewModel.isLoading {
                    ProgressView("Loading matches…")
                        .frame(maxWidth: .infinity, minHeight: 120)
                        .accessibilityLabel("Loading \(viewModel.entry.teamDisplayName) matches")
                } else if let err = viewModel.error {
                    ErrorStateView(message: err) { Task { await viewModel.refresh() } }
                        .padding()
                } else if viewModel.phaseGames.isEmpty {
                    Text("No matches found yet. Check back once the tournament begins.")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .padding()
                        .frame(maxWidth: .infinity)
                } else {
                    matchPath
                }
            }
        }
        .navigationTitle(viewModel.entry.teamDisplayName)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                ViewModeMenuButton(currentMode: $viewMode)
            }
        }
        .task { await viewModel.load() }
        .refreshable { await viewModel.refresh() }
    }

    // MARK: - Group standing card

    private var groupStandingCard: some View {
        let e = viewModel.entry
        return VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("\(viewModel.group.name) — \(ordinal(e.rank))")
                    .font(.headline)
                Spacer()
                if let note = e.advancementNote {
                    HStack(spacing: 4) {
                        Circle()
                            .fill(Color.green)
                            .frame(width: 8, height: 8)
                            .accessibilityHidden(true)
                        Text(note)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            }

            HStack(spacing: 0) {
                statCell(label: "GP", value: "\(e.gamesPlayed)")
                statCell(label: "W",  value: "\(e.wins)")
                statCell(label: "D",  value: "\(e.draws)")
                statCell(label: "L",  value: "\(e.losses)")
                statCell(label: "GF", value: "\(e.goalsFor)")
                statCell(label: "GA", value: "\(e.goalsAgainst)")
                statCell(label: "GD", value: e.goalDifferenceFormatted)
                statCell(label: "Pts", value: "\(e.points)")
            }
            .background(Color.secondary.opacity(0.06))
            .cornerRadius(8)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(e.accessibilityLabel())
    }

    private func statCell(label: String, value: String) -> some View {
        VStack(spacing: 2) {
            Text(label)
                .font(.system(.caption2, design: .rounded))
                .foregroundColor(.secondary)
            Text(value)
                .font(.system(.subheadline, design: .rounded).monospacedDigit().bold())
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
    }

    private func ordinal(_ n: Int) -> String {
        switch n % 10 {
        case 1 where n % 100 != 11: return "\(n)st"
        case 2 where n % 100 != 12: return "\(n)nd"
        case 3 where n % 100 != 13: return "\(n)rd"
        default:                     return "\(n)th"
        }
    }

    // MARK: - Match path

    private var matchPath: some View {
        LazyVStack(alignment: .leading, spacing: 0) {
            ForEach(viewModel.phaseGames, id: \.phase.id) { item in
                phaseSection(phase: item.phase, games: item.games)
            }
        }
    }

    @ViewBuilder
    private func phaseSection(phase: WorldCupPhase, games: [Game]) -> some View {
        // Section header
        Text(phase.label)
            .font(.headline)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal)
            .padding(.vertical, 8)
            .background(Color(uiColor: .systemBackground))
            .accessibilityAddTraits(.isHeader)

        switch viewMode {
        case .table:    tableSection(games: games, phase: phase)
        case .quickList: quickSection(games: games, phase: phase)
        case .fullList:  fullSection(games: games, phase: phase)
        }

        Divider()
    }

    // MARK: - Table mode

    private func tableSection(games: [Game], phase: WorldCupPhase) -> some View {
        let headers = ["Away", "Home", "Status"]
        let rows = games.map { tableRow($0) }
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
                        ForEach(Array(tableRow(game).enumerated()), id: \.offset) { _, val in
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
        .accessibilityHidden(true)
        .overlay(
            AccessibleDataTable(headers: headers, rows: rows)
                .allowsHitTesting(false)
        )
        .padding(.horizontal)
        .padding(.bottom, 8)
    }

    // MARK: - Quick List mode

    private func quickSection(games: [Game], phase: WorldCupPhase) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(games) { game in
                NavigationLink(destination: GameDetailView(game: game, sport: sport)) {
                    Text(quickText(game))
                        .font(.subheadline)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(quickAccessibilityText(game))
                .accessibilityHint("Opens match details")
            }
        }
        .padding(.bottom, 8)
    }

    // MARK: - Full List mode

    private func fullSection(games: [Game], phase: WorldCupPhase) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(games) { game in
                NavigationLink(destination: GameDetailView(game: game, sport: sport)) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("\(game.awayTeam.displayName) vs \(game.homeTeam.displayName)")
                            .font(.headline)
                        Text(fullDetailText(game))
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
                .accessibilityLabel(quickAccessibilityText(game))
                .accessibilityHint("Opens match details")
            }
        }
        .padding(.bottom, 8)
    }

    // MARK: - Row formatters

    private func tableRow(_ game: Game) -> [String] {
        let away = game.awayTeam.abbreviation + scoreStr(game.awayTeam.score)
        let home = game.homeTeam.abbreviation + scoreStr(game.homeTeam.score)
        return [away, home, statusText(game, short: true)]
    }

    private func quickText(_ game: Game) -> String {
        let away = game.awayTeam.abbreviation + scoreStr(game.awayTeam.score)
        let home = game.homeTeam.abbreviation + scoreStr(game.homeTeam.score)
        return "\(away) @ \(home) — \(statusText(game, short: true))"
    }

    private func quickAccessibilityText(_ game: Game) -> String {
        let pref = appSettings.teamNamePreference
        let away = game.awayTeam.voiceOverName(for: pref) + scoreStr(game.awayTeam.score)
        let home = game.homeTeam.voiceOverName(for: pref) + scoreStr(game.homeTeam.score)
        return "\(away) at \(home), \(statusText(game, short: false))"
    }

    private func fullDetailText(_ game: Game) -> String {
        var parts = [statusText(game, short: false)]
        if let venue = game.venue?.fullName, !venue.isEmpty { parts.append(venue) }
        if game.shouldShowBroadcastInfo, let b = game.broadcasts.first, !b.isEmpty {
            parts.append("TV: \(b)")
        }
        return parts.joined(separator: " · ")
    }

    private func statusText(_ game: Game, short: Bool) -> String {
        if game.status.isLive       { return game.status.displayText }
        if game.status.isPostponed  { return short ? "PPD" : "Postponed" }
        if game.status.isCancelled  { return short ? "Cxl" : "Cancelled" }
        if game.status.isSuspended  { return short ? "Susp" : "Suspended" }
        if game.status.isCompleted  { return "Final" }
        return game.displayTime
    }

    private func scoreStr(_ score: Int?) -> String {
        score.map { " \($0)" } ?? ""
    }
}
