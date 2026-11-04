//
//  TeamScheduleTabView.swift
//  SportsScores
//
//  Schedule tab for Team Hub — simplified two-section list (Recent + Upcoming).
//  Tapping a completed game navigates to GameDetailView.
//

import SwiftUI

struct TeamScheduleTabView: View {
    @ObservedObject var viewModel: TeamHubViewModel
    let team: TransactionTeam
    let sport: Sport

    private var fullScheduleTeam: Game.Team {
        Game.Team(id: team.id, name: team.name ?? team.displayName, abbreviation: team.abbreviation,
                  displayName: team.displayName, score: nil, record: nil, logo: nil)
    }

    private static let dateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .medium
        f.timeStyle = .short
        return f
    }()

    var body: some View {
        Group {
            if viewModel.isLoadingSchedule && viewModel.schedule.isEmpty {
                ProgressView("Loading schedule…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = viewModel.errorSchedule, viewModel.schedule.isEmpty {
                errorState(message: error)
            } else if viewModel.schedule.isEmpty {
                emptyState
            } else {
                scheduleList
            }
        }
        .task { await viewModel.loadSchedule() }
    }

    // MARK: - Schedule list

    private var scheduleList: some View {
        List {
            let recent = viewModel.recentGames
            let upcoming = viewModel.upcomingGames

            if !recent.isEmpty {
                Section("Recent") {
                    ForEach(recent) { game in
                        NavigationLink(destination: GameDetailView(game: game.toGame(), sport: sport)) {
                            gameRow(game: game)
                        }
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(gameAccessibilityLabel(game))
                        .accessibilityHint("Opens game detail")
                    }
                }
            }

            if !upcoming.isEmpty {
                Section("Upcoming") {
                    ForEach(upcoming) { game in
                        gameRow(game: game)
                            .accessibilityElement(children: .ignore)
                            .accessibilityLabel(gameAccessibilityLabel(game))
                    }
                }
            }

            if recent.isEmpty && upcoming.isEmpty {
                Text("No recent or upcoming games")
                    .foregroundColor(.secondary)
                    .font(.subheadline)
            }

            Section {
                NavigationLink(destination: TeamScheduleView(team: fullScheduleTeam, sport: sport)) {
                    Label("View Full Schedule", systemImage: "calendar")
                }
            }
        }
        .listStyle(.insetGrouped)
    }

    // MARK: - Game row

    private func gameRow(game: ScheduleGame) -> some View {
        let teamIsHome = game.homeTeam.id == viewModel.teamId
        let opponent = teamIsHome ? game.awayTeam : game.homeTeam
        let locationText = teamIsHome || game.isNeutralSite ? "vs" : "@"

        return HStack(spacing: 12) {
            resultBadge(game: game, teamIsHome: teamIsHome)
                .frame(width: 32)

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 4) {
                    Text(locationText)
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text(opponent.displayName)
                        .font(.subheadline)
                        .fontWeight(.medium)
                }
                Text((game.timeIsKnown ? Self.dateFormatter.string(from: game.date) : DateFormatter.localizedString(from: game.date, dateStyle: .medium, timeStyle: .none)))
                    .font(.caption)
                    .foregroundColor(.secondary)
                if let label = game.label {
                    Text(label)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }

            Spacer()

            if game.isCompleted {
                scoreText(game: game, teamIsHome: teamIsHome)
            } else {
                Text(game.statusText)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .padding(.vertical, 2)
    }

    @ViewBuilder
    private func resultBadge(game: ScheduleGame, teamIsHome: Bool) -> some View {
        if game.isCompleted {
            let outcome = game.outcome(forTeamId: viewModel.teamId)
            let color: Color = outcome == .win ? .green : (outcome == .loss ? .red : .secondary)
            Text(outcome == .win ? "W" : (outcome == .loss ? "L" : (outcome == .tie ? "T" : "–")))
                .font(.caption2).bold()
                .frame(width: 22, height: 22)
                .background(color.opacity(0.15))
                .foregroundColor(color)
                .cornerRadius(4)
        } else if game.isInProgress {
            Image(systemName: "circle.fill")
                .foregroundColor(.orange)
                .font(.caption2)
        } else {
            Image(systemName: "circle")
                .foregroundColor(.secondary)
                .font(.caption2)
        }
    }

    private func scoreText(game: ScheduleGame, teamIsHome: Bool) -> some View {
        let homeScore = game.homeTeam.score ?? 0
        let awayScore = game.awayTeam.score ?? 0
        let teamScore = teamIsHome ? homeScore : awayScore
        let oppScore  = teamIsHome ? awayScore : homeScore
        return Text("\(teamScore)–\(oppScore)")
            .font(.subheadline).monospacedDigit()
            .fontWeight(game.outcome(forTeamId: viewModel.teamId) == .win ? .bold : .regular)
    }

    private func gameAccessibilityLabel(_ game: ScheduleGame) -> String {
        let teamIsHome = game.homeTeam.id == viewModel.teamId
        let opponent = teamIsHome ? game.awayTeam : game.homeTeam
        let location = teamIsHome || game.isNeutralSite ? "vs" : "at"
        let date = (game.timeIsKnown ? Self.dateFormatter.string(from: game.date) : DateFormatter.localizedString(from: game.date, dateStyle: .medium, timeStyle: .none))
        let label = game.label.map { ", \($0)" } ?? ""
        if game.isCompleted {
            let ts = teamIsHome ? (game.homeTeam.score ?? 0) : (game.awayTeam.score ?? 0)
            let os = teamIsHome ? (game.awayTeam.score ?? 0) : (game.homeTeam.score ?? 0)
            switch game.outcome(forTeamId: viewModel.teamId) {
            case .win:  return "Win \(location) \(opponent.displayName), \(ts) to \(os), on \(date)\(label)"
            case .loss: return "Loss \(location) \(opponent.displayName), \(ts) to \(os), on \(date)\(label)"
            case .tie:  return "Tie \(location) \(opponent.displayName), \(ts) to \(os), on \(date)\(label)"
            case nil:   return "Final \(location) \(opponent.displayName), on \(date)\(label)"
            }
        }
        return "\(location) \(opponent.displayName), \(date)\(label)"
    }

    // MARK: - States

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "calendar.badge.exclamationmark")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
            Text("No schedule available")
                .font(.headline)
                .foregroundColor(.secondary)
        }
    }

    private func errorState(message: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 40))
                .foregroundColor(.secondary)
            Text(message)
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
            Button("Retry") { Task { await viewModel.loadSchedule() } }
                .buttonStyle(.borderedProminent)
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
