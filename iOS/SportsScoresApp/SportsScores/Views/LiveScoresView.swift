//
//  LiveScoresView.swift
//  SportsScores
//
//  Created on 1/4/26.
//

import SwiftUI
import UIKit

// MARK: - Golf live state (lightweight, separate from team-sport viewmodel)

@MainActor
private class GolfLiveViewModel: ObservableObject {
    @Published var activeTournaments: [(sport: Sport, tournament: GolfTournament)] = []
    private let api = ESPNAPIService.shared

    func fetch() async {
        var found: [(sport: Sport, tournament: GolfTournament)] = []
        await withTaskGroup(of: (Sport, GolfTournament?).self) { group in
            for tour in Sport.golfTours {
                group.addTask {
                    let result = try? await self.api.fetchGolfTournament(for: tour)
                    return (tour, result?.tournament)
                }
            }
            for await (tour, tournament) in group {
                if let t = tournament, t.isInProgress {
                    found.append((sport: tour, tournament: t))
                }
            }
        }
        activeTournaments = found.sorted { $0.sport.rawValue < $1.sport.rawValue }
    }
}

struct LiveScoresView: View {
    @StateObject private var viewModel = LiveScoresViewModel()
    @StateObject private var golfVM   = GolfLiveViewModel()
    @State private var viewMode: ViewMode = .quickList
    @EnvironmentObject private var appSettings: AppSettings

    var body: some View {
        Group {
            if viewModel.isLoading {
                ProgressView("Loading all games...")
            } else if let error = viewModel.errorMessage {
                VStack(spacing: 16) {
                    Image(systemName: "calendar.badge.clock")
                        .font(.system(size: 48))
                        .foregroundColor(.secondary)
                    Text(error)
                        .multilineTextAlignment(.center)
                        .foregroundColor(.secondary)
                    Button("Retry") {
                        Task {
                            await viewModel.fetchAllGames()
                        }
                    }
                    .buttonStyle(.bordered)
                }
                .padding()
            } else {
                scrollContent
            }
        }
        .navigationTitle("Live Scores")
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
            if appSettings.golfHubEnabled { await golfVM.fetch() }
        }
        // Switching college football coverage changes the NCAAF slate ESPN returns.
        .onChange(of: appSettings.ncaafCoverage) {
            Task { await viewModel.refresh() }
        }
        .task(id: appSettings.autoRefreshInterval) {
            while !Task.isCancelled {
                let secs = appSettings.autoRefreshInterval.rawValue
                if secs > 0 {
                    try? await Task.sleep(for: .seconds(secs))
                    guard !Task.isCancelled else { break }
                    await viewModel.refresh()
                    if appSettings.golfHubEnabled { await golfVM.fetch() }
                } else {
                    try? await Task.sleep(for: .seconds(86400))
                }
            }
        }
        .refreshable {
            await viewModel.refresh()
            // Someone asked for this one. The timer's stay quiet.
            if let note = viewModel.failureNote {
                UIAccessibility.post(notification: .announcement, argument: note)
            }
            if appSettings.golfHubEnabled { await golfVM.fetch() }
        }
    }
    
    private var scrollContent: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                // Golf Live Now section (shown first when a tournament is in progress)
                if appSettings.golfHubEnabled && !golfVM.activeTournaments.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        sectionHeader(title: "⛳ GOLF LIVE", count: golfVM.activeTournaments.count)
                        ForEach(golfVM.activeTournaments, id: \.sport.rawValue) { item in
                            NavigationLink(destination: GolfLeagueView(sport: item.sport)) {
                                golfTournamentRow(item.tournament, sport: item.sport)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal)
                }

                // Live Games Section
                if !viewModel.liveGames.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        sectionHeader(title: "LIVE NOW", count: totalCount(viewModel.liveGames))
                        
                        ForEach(viewModel.liveGames) { sportGames in
                            sportSection(sportGames: sportGames, isLive: true)
                        }
                    }
                    .padding(.horizontal)
                }
                
                // Upcoming Games Section
                if !viewModel.upcomingGames.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        sectionHeader(title: "UPCOMING", count: totalCount(viewModel.upcomingGames))
                        
                        ForEach(viewModel.upcomingGames) { sportGames in
                            sportSection(sportGames: sportGames, isLive: false)
                        }
                    }
                    .padding(.horizontal)
                }
                
                // Completed Games Section
                if !viewModel.completedGames.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        sectionHeader(title: "COMPLETED", count: totalCount(viewModel.completedGames))
                        
                        ForEach(viewModel.completedGames) { sportGames in
                            sportSection(sportGames: sportGames, isLive: false)
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

                if viewModel.liveGames.isEmpty && viewModel.completedGames.isEmpty && viewModel.upcomingGames.isEmpty && (!appSettings.golfHubEnabled || golfVM.activeTournaments.isEmpty) {
                    VStack(spacing: 16) {
                        Image(systemName: "calendar.badge.exclamationmark")
                            .font(.system(size: 48))
                            .foregroundColor(.secondary)
                        Text("No games today")
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
    
    private func sportSection(sportGames: LiveScoresViewModel.SportGames, isLive: Bool) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            // Sport Header
            HStack {
                Text(sportGames.sport.icon)
                    .font(.title3)
                Text(sportGames.sport.displayName)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                Text("\(sportGames.games.count)")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color.secondary.opacity(0.1))
            .cornerRadius(8)
            .accessibilityElement(children: .combine)
            .accessibilityAddTraits(.isHeader)
            
            // Games List
            switch viewMode {
            case .table:
                liveTableSection(games: sportGames.games, sport: sportGames.sport)
            case .quickList:
                liveQuickSection(games: sportGames.games, sport: sportGames.sport, isLive: isLive)
            case .fullList:
                ForEach(sportGames.games) { game in
                    NavigationLink(destination: GameDetailView(game: game, sport: sportGames.sport)) {
                        CompactGameRow(game: game, isLive: isLive, sport: sportGames.sport)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.vertical, 4)
    }
    
    private func liveGameRow(_ game: Game) -> [String] {
        let away = game.awayTeam.rankedAbbreviation + (game.awayTeam.score.map { " \($0)" } ?? "")
        let home = game.homeTeam.rankedAbbreviation + (game.homeTeam.score.map { " \($0)" } ?? "")
        let status = game.status.isLive ? game.status.displayText
            : (game.status.isSuspended ? "Susp" : (game.status.isCompleted ? "Final" : game.displayTime))
        return [away, home, status]
    }

    private func liveAccessibleGameRow(_ game: Game) -> [String] {
        let pref = appSettings.teamNamePreference
        let away = game.awayTeam.voiceOverName(for: pref) + (game.awayTeam.score.map { " \($0)" } ?? "")
        let home = game.homeTeam.voiceOverName(for: pref) + (game.homeTeam.score.map { " \($0)" } ?? "")
        var statusParts: [String] = []
        if game.status.isLive {
            statusParts.append(game.status.displayText)
            if let sit = game.situation, let t = sit.displayText, !t.isEmpty {
                statusParts.append(t)
            }
        } else if game.status.isSuspended { statusParts.append("Suspended") }
        else if game.status.isCompleted { statusParts.append("Final") }
        else { statusParts.append(game.displayTime) }
        return [away, home, statusParts.joined(separator: ", ")]
    }

    private func liveTableSection(games: [Game], sport: Sport) -> some View {
        let headers = ["Away", "Home", "Status"]
        let rows = games.map { liveAccessibleGameRow($0) }
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
                        ForEach(Array(liveGameRow(game).enumerated()), id: \.offset) { _, val in
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

    private func liveQuickSection(games: [Game], sport: Sport, isLive: Bool) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(games) { game in
                NavigationLink(destination: GameDetailView(game: game, sport: sport)) {
                    Text(liveQuickText(game))
                        .font(.subheadline)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(liveQuickAccessibilityText(game))
                .accessibilityHint("Opens game details")
            }
        }
    }

    private func liveQuickText(_ game: Game) -> String {
        let away = game.awayTeam.rankedAbbreviation + (game.awayTeam.score.map { " \($0)" } ?? "")
        let home = game.homeTeam.rankedAbbreviation + (game.homeTeam.score.map { " \($0)" } ?? "")
        let status = game.status.isLive ? game.status.displayText
            : (game.status.isSuspended ? "Suspended" : (game.status.isCompleted ? "Final" : game.displayTime))
        return "\(away) \(game.matchupSymbol) \(home) \u{2014} \(status)"
    }

    private func liveQuickAccessibilityText(_ game: Game) -> String {
        let pref = appSettings.teamNamePreference
        let away = game.awayTeam.voiceOverName(for: pref) + (game.awayTeam.score.map { " \($0)" } ?? "")
        let home = game.homeTeam.voiceOverName(for: pref) + (game.homeTeam.score.map { " \($0)" } ?? "")
        var statusParts: [String] = []
        if game.status.isLive {
            statusParts.append(game.status.displayText)
            if let sit = game.situation, let t = sit.displayText, !t.isEmpty {
                statusParts.append(t)
            }
        } else if game.status.isSuspended { statusParts.append("Suspended") }
        else if game.status.isCompleted { statusParts.append("Final") }
        else { statusParts.append(game.displayTime) }
        var label = "\(away) \(game.matchupWord) \(home), \(statusParts.joined(separator: ", "))"
        if game.shouldShowBroadcastInfo, let broadcast = game.broadcasts.first, !broadcast.isEmpty {
            label += ", on \(broadcast)"
        }
        return label
    }

    private func totalCount(_ sportGames: [LiveScoresViewModel.SportGames]) -> Int {
        sportGames.reduce(0) { $0 + $1.games.count }
    }

    private func golfTournamentRow(_ tournament: GolfTournament, sport: Sport) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: sport.systemImage)
                    .font(.title3)
                Text(sport.displayName)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                Label(tournament.roundStatusText, systemImage: "circle.fill")
                    .font(.caption)
                    .foregroundColor(.red)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color.secondary.opacity(0.1))
            .cornerRadius(8)

            HStack {
                Text(tournament.name)
                    .font(.subheadline)
                Spacer()
                // Top 3 leaders
                if !tournament.competitors.isEmpty {
                    VStack(alignment: .trailing, spacing: 2) {
                        ForEach(tournament.competitors.prefix(3)) { comp in
                            Text("\(comp.positionDisplay). \(comp.shortName)  \(comp.overallScore)")
                                .font(.caption.monospacedDigit())
                                .foregroundColor(.secondary)
                        }
                    }
                }
            }
            .padding(.horizontal, 12)
            .padding(.bottom, 4)
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
        .accessibilityLabel({
            let leaders = tournament.competitors.prefix(3).map { "\($0.positionDisplay). \($0.playerName), \($0.overallScore)" }.joined(separator: "; ")
            return "\(sport.displayName), \(tournament.name), \(tournament.roundStatusText). Leaders: \(leaders)"
        }())
        .accessibilityHint("Opens \(sport.displayName) leaderboard")
    }
}

struct CompactGameRow: View {
    let game: Game
    let isLive: Bool
    let sport: Sport

    @EnvironmentObject private var appSettings: AppSettings
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Teams and Scores FIRST
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(game.awayTeam.abbreviation)
                        .font(.body)
                        .fontWeight(.medium)
                    
                    Text(game.homeTeam.abbreviation)
                        .font(.body)
                        .fontWeight(.medium)
                }
                
                Spacer()
                
                VStack(alignment: .trailing, spacing: 4) {
                    if let score = game.awayTeam.score {
                        Text("\(score)")
                            .font(.title3)
                            .fontWeight(.bold)
                            .monospacedDigit()
                    } else {
                        Text("-")
                            .font(.title3)
                            .foregroundColor(.secondary)
                    }
                    
                    if let score = game.homeTeam.score {
                        Text("\(score)")
                            .font(.title3)
                            .fontWeight(.bold)
                            .monospacedDigit()
                    } else {
                        Text("-")
                            .font(.title3)
                            .foregroundColor(.secondary)
                    }
                }
            }
            
            // Status Bar SECOND (below teams)
            HStack {
                if isLive {
                    Label(game.status.displayText, systemImage: "circle.fill")
                        .foregroundColor(.red)
                        .font(.caption)
                        .fontWeight(.semibold)
                } else if game.status.isSuspended {
                    Text(game.status.detail.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Suspended" : game.status.detail)
                        .font(.caption)
                        .foregroundColor(.orange)
                } else if game.status.isCompleted {
                    Text("Final")
                        .font(.caption)
                        .foregroundColor(.secondary)
                } else {
                    Text(game.displayTime)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                Spacer()
                
                if game.shouldShowBroadcastInfo, !game.broadcasts.isEmpty {
                    Text(game.broadcasts.first ?? "")
                        .font(.caption2)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.blue.opacity(0.2))
                        .cornerRadius(4)
                }
            }
            
            // Last play / situation info (no truncation for accessibility)
            if isLive, let situation = game.situation, let displayText = situation.displayText {
                Text(displayText)
                    .font(.caption)
                    .foregroundColor(.primary)
                    .fixedSize(horizontal: false, vertical: true)
                    .lineLimit(nil)
            }
            
            // Team records (less important, shown last)
            if let awayRecord = game.awayTeam.record, let homeRecord = game.homeTeam.record {
                HStack(spacing: 12) {
                    Text("(\(awayRecord))")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                    Spacer()
                    Text("(\(homeRecord))")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }

            // Venue / location
            if let venue = game.venue, !venue.name.isEmpty {
                Label(venue.fullName, systemImage: "mappin.and.ellipse")
                    .labelStyle(.titleAndIcon)
                    .font(.caption2)
                    .foregroundColor(.secondary)
                    .lineLimit(1)
            }
        }
        .padding(12)
        .background(Color.secondary.opacity(0.05))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(isLive ? Color.red.opacity(0.3) : Color.clear, lineWidth: 2)
        )
        // Combine all sub-elements so VoiceOver reads a single coherent label (design debt #2)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(compactAccessibilityLabel)
        .onAppear {
            debugLogAccessibilityLabelIfNeeded()
        }
    }

    private var compactAccessibilityLabel: String {
        let pref = appSettings.teamNamePreference

        // Away / Home with scores
        let awayScore = game.awayTeam.score.map { " \($0)" } ?? ""
        let awayPart = "\(game.awayPrefix)\(game.awayTeam.voiceOverName(for: pref))\(awayScore)"
        let homeScore = game.homeTeam.score.map { " \($0)" } ?? ""
        let homePart = "\(game.homePrefix)\(game.homeTeam.voiceOverName(for: pref))\(homeScore)"

        // Status field — section headings communicate live/final, omit to avoid redundancy
        var statusParts: [String] = []
        if !game.status.isLive && !game.status.isCompleted && !game.status.isSuspended {
            statusParts.append(game.displayTime)
        }
        // Suspended rows sit under the Live heading, which does not convey that play
        // is halted, so this one is always spoken.
        if game.status.isSuspended {
            let detail = game.status.detail.trimmingCharacters(in: .whitespacesAndNewlines)
            statusParts.append(detail.isEmpty ? "Suspended" : detail)
        }
        if isLive {
            // For live games: inning first for baseball, then situation.
            // For all other sports, situation leads and period/clock follows.
            if sport == .mlb {
                statusParts.append(game.status.detail)
                if let sit = game.situation, let t = sit.displayText, !t.isEmpty {
                    statusParts.append(t)
                }
            } else {
                if let sit = game.situation, let t = sit.displayText, !t.isEmpty {
                    statusParts.append(t)
                }
                statusParts.append(game.status.displayText)
            }
        }

        var parts = [awayPart, homePart]
        if !statusParts.isEmpty {
            parts.append("Status: \(statusParts.joined(separator: ", "))")
        }

        // Venue / location
        if let venue = game.venue, !venue.name.isEmpty {
            parts.append("at \(venue.fullName)")
        }

        // Broadcast last
        if game.shouldShowBroadcastInfo,
           let broadcast = game.broadcasts.first,
           !broadcast.isEmpty {
            parts.append("on \(broadcast)")
        }

        return parts.joined(separator: ", ")
    }

    private func debugLogAccessibilityLabelIfNeeded() {
        #if DEBUG
        guard isLive else { return }
        guard ProcessInfo.processInfo.arguments.contains("-A11YDebugLiveLabels") else { return }
        print("[A11Y][LiveScoresView][\(game.id)] \(compactAccessibilityLabel)")
        #endif
    }
}

#Preview {
    NavigationStack {
        LiveScoresView()
    }
    .environmentObject(AppSettings())
}
