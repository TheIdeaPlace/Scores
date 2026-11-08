//
//  LiveScoresView.swift
//  SportsScores
//
//  Created on 1/4/26.
//

import SwiftUI
import UIKit

// MARK: - Nothing came back

/// What Live Scores and Live Soccer show with nothing to list. Retry stays where it is while it
/// runs, so VoiceOver stays on it and can say what came of it: the same words coming back would
/// otherwise be silent. `retry` returns the error still showing, or nil if the games came back.
struct LiveFailureView: View {
    let message: String
    let isRetrying: Bool
    let retry: () async -> String?

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "calendar.badge.clock")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
                .accessibilityHidden(true)
            Text(message)
                .multilineTextAlignment(.center)
                .foregroundColor(.secondary)
            Button("Retry") {
                guard !isRetrying else { return }
                UIAccessibility.post(notification: .announcement, argument: "Retrying")
                Task {
                    if let stillFailing = await retry() {
                        // Queued, or it can cut off "Retrying" when the failure is immediate.
                        let said = NSAttributedString(
                            string: stillFailing,
                            attributes: [.accessibilitySpeechQueueAnnouncement: true])
                        UIAccessibility.post(notification: .announcement, argument: said)
                    } else {
                        // Retry is gone from under VoiceOver. Let the list settle first.
                        try? await Task.sleep(for: .milliseconds(300))
                        UIAccessibility.post(notification: .screenChanged, argument: nil)
                    }
                }
            }
            .buttonStyle(.bordered)
            if isRetrying {
                ProgressView()
                    .accessibilityHidden(true)
            }
        }
        .padding()
    }
}

struct LiveScoresView: View {
    @StateObject private var viewModel = LiveScoresViewModel()
    @State private var viewMode: ViewMode = .savedDefault()
    @EnvironmentObject private var appSettings: AppSettings
    @EnvironmentObject private var monitoring: MonitoringStore

    /// Where VoiceOver goes after Stop Monitoring on a Monitoring row: the next one there,
    /// or the section's header when there's none after it.
    private enum MonitoringFocus: Hashable {
        case header
        case row(String)
    }
    @AccessibilityFocusState private var monitoringFocus: MonitoringFocus?

    /// Shown under Monitoring with nothing monitored. Table rows have no actions yet (#208).
    private var monitoringEmptyText: String {
        viewMode == .table
            ? "No games monitored. To add one, switch to Quick List or Full List and choose Monitor in a game's actions."
            : "No games monitored. To add one, choose Monitor in a game's actions, or press and hold the game."
    }

    var body: some View {
        Group {
            if viewModel.isLoading {
                ProgressView("Loading all games...")
            } else if let error = viewModel.errorMessage {
                LiveFailureView(message: error, isRetrying: viewModel.isRetrying) {
                    await viewModel.retry(golf: appSettings.golfHubEnabled)
                }
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
            await viewModel.fetchAllGames(golf: appSettings.golfHubEnabled)
        }
        // Switching college football coverage changes the NCAAF slate ESPN returns.
        .onChange(of: appSettings.ncaafCoverage) {
            Task { await viewModel.refresh(golf: appSettings.golfHubEnabled) }
        }
        // Golf's rows, and any tour named in the failure note, come and go with the setting.
        .onChange(of: appSettings.golfHubEnabled) {
            Task { await viewModel.refresh(golf: appSettings.golfHubEnabled) }
        }
        .task(id: appSettings.autoRefreshInterval) {
            while !Task.isCancelled {
                let secs = appSettings.autoRefreshInterval.rawValue
                if secs > 0 {
                    try? await Task.sleep(for: .seconds(secs))
                    guard !Task.isCancelled else { break }
                    await viewModel.refresh(golf: appSettings.golfHubEnabled)
                } else {
                    try? await Task.sleep(for: .seconds(86400))
                }
            }
        }
        .refreshable {
            await viewModel.refresh(golf: appSettings.golfHubEnabled)
            // Someone asked for this one. The timer's stay quiet.
            if let note = viewModel.failureNote {
                UIAccessibility.post(notification: .announcement, argument: note)
            }
        }
    }
    
    private var scrollContent: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                // Monitoring, always first: the games someone chose to keep up with.
                monitoringSection

                // Golf Live Now section (shown first when a tournament is in progress)
                if appSettings.golfHubEnabled && !viewModel.activeTournaments.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        sectionHeader(title: "⛳ GOLF LIVE", count: viewModel.activeTournaments.count)
                        ForEach(viewModel.activeTournaments, id: \.sport.rawValue) { item in
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

                if viewModel.liveGames.isEmpty && viewModel.completedGames.isEmpty && viewModel.upcomingGames.isEmpty && (!appSettings.golfHubEnabled || viewModel.activeTournaments.isEmpty) {
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
                liveTableSection(sportGames.games.map { GameInSport(game: $0, sport: sportGames.sport) }, showsSport: false)
            case .quickList:
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(sportGames.games) { game in
                        liveQuickRow(game, sport: sportGames.sport, monitoringRow: false)
                    }
                }
            case .fullList:
                ForEach(sportGames.games) { game in
                    liveFullRow(game, sport: sportGames.sport, isLive: isLive, monitoringRow: false)
                }
            }
        }
        .padding(.vertical, 4)
    }

    // MARK: - Monitoring (#185)

    /// The monitored games on today's list, in the order added, each with its sport.
    private var monitoredRows: [GameInSport] {
        let sections = (viewModel.liveGames + viewModel.upcomingGames + viewModel.completedGames)
            .map { (sport: $0.sport, games: $0.games) }
        return monitoring.shown(in: sections)
    }

    /// Always there, at the top. Each row reads as the game's own row does below, with its
    /// sport after it; the game stays in its own section too.
    private var monitoringSection: some View {
        let rows = monitoredRows
        let shownIDs = rows.map(\.id)
        return VStack(alignment: .leading, spacing: 12) {
            sectionHeader(title: "MONITORING", count: rows.count)
                .accessibilityFocused($monitoringFocus, equals: .header)
            if rows.isEmpty {
                Text(monitoringEmptyText)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                switch viewMode {
                case .table:
                    // Table rows have no actions yet, so no Stop Monitoring here (#208).
                    liveTableSection(rows, showsSport: true)
                case .quickList:
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(rows) { row in
                            liveQuickRow(row.game, sport: row.sport, monitoringRow: true, shownIDs: shownIDs)
                        }
                    }
                case .fullList:
                    ForEach(rows) { row in
                        liveFullRow(row.game, sport: row.sport, isLive: Self.isLiveRow(row.game),
                                    monitoringRow: true, shownIDs: shownIDs)
                    }
                }
            }
        }
        .padding(.horizontal)
    }

    /// Whether a game's row is drawn as a live one: the Live section has suspended games too.
    private static func isLiveRow(_ game: Game) -> Bool {
        game.status.isLive || game.status.isSuspended
    }

    /// What follows a row's own text: the sport on a Monitoring row, as on Windows
    /// (" | NFL Football"), and " - monitoring" on a monitored game's own row.
    private func rowSuffix(_ game: Game, sport: Sport, monitoringRow: Bool) -> String {
        if monitoringRow { return " | \(sport.displayName)" }
        return monitoring.isMonitored(game.id) ? " - monitoring" : ""
    }

    /// On a game's own row, Monitor, or Stop Monitoring once it is; focus stays there. On a
    /// Monitoring row, Stop Monitoring, which moves focus to the next one.
    private func monitorAction(_ game: Game, monitoringRow: Bool, shownIDs: [String]) -> MonitorAction {
        if monitoringRow {
            return MonitorAction(name: MonitoringStore.ActionName.stop) {
                stopMonitoring(game, shownIDs: shownIDs)
            }
        }
        return MonitorAction(name: monitoring.actionName(for: game.id)) {
            announceMonitoring(monitoring.toggleFromLiveScores(game))
        }
    }

    /// The row VoiceOver was on goes, so it lands on the next Monitoring row, or the
    /// section's header, once the list has redrawn. Then it says which game went, after
    /// the row it landed on, since moving focus would cut off anything said before.
    private func stopMonitoring(_ game: Game, shownIDs: [String]) {
        let result = monitoring.stopFromMonitoringRow(game, shown: shownIDs)
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(150))
            monitoringFocus = result.next.map { .row($0) } ?? .header
            try? await Task.sleep(for: .milliseconds(350))
            announceMonitoring(result.said, queued: true)
        }
    }

    /// A Monitoring row is where focus goes after Stop Monitoring on the one above it.
    @ViewBuilder
    private func focusTarget<Row: View>(_ row: Row, monitoringRow: Bool, gameID: String) -> some View {
        if monitoringRow {
            row.accessibilityFocused($monitoringFocus, equals: .row(gameID))
        } else {
            row
        }
    }

    private func liveFullRow(_ game: Game, sport: Sport, isLive: Bool, monitoringRow: Bool,
                             shownIDs: [String] = []) -> some View {
        focusTarget(
            NavigationLink(destination: GameDetailView(game: game, sport: sport)) {
                CompactGameRow(game: game, isLive: isLive, sport: sport,
                               suffix: rowSuffix(game, sport: sport, monitoringRow: monitoringRow),
                               saysFinal: monitoringRow)
            }
            .buttonStyle(.plain)
            .listenToGame(game, sport: sport,
                          monitor: monitorAction(game, monitoringRow: monitoringRow, shownIDs: shownIDs)),
            monitoringRow: monitoringRow, gameID: game.id)
    }

    private func liveQuickRow(_ game: Game, sport: Sport, monitoringRow: Bool,
                              shownIDs: [String] = []) -> some View {
        let suffix = rowSuffix(game, sport: sport, monitoringRow: monitoringRow)
        return focusTarget(
            NavigationLink(destination: GameDetailView(game: game, sport: sport)) {
                Text(liveQuickText(game) + suffix)
                    .font(.subheadline)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(liveQuickAccessibilityText(game) + suffix)
            .accessibilityHint("Opens game details")
            .listenToGame(game, sport: sport,
                          monitor: monitorAction(game, monitoringRow: monitoringRow, shownIDs: shownIDs)),
            monitoringRow: monitoringRow, gameID: game.id)
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

    /// A section's games as a table. In Monitoring (`showsSport`) a Sport column follows; in a
    /// sport's own section a monitored game's status says so.
    private func liveTableSection(_ items: [GameInSport], showsSport: Bool) -> some View {
        let headers = ["Away", "Home", "Status"] + (showsSport ? ["Sport"] : [])
        func cells(_ row: [String], _ item: GameInSport) -> [String] {
            if showsSport { return row + [item.sport.displayName] }
            guard monitoring.isMonitored(item.game.id), let status = row.last else { return row }
            return Array(row.dropLast()) + [status + " - monitoring"]
        }
        let rows = items.map { cells(liveAccessibleGameRow($0.game), $0) }
        let shownRows = items.map { cells(liveGameRow($0.game), $0) }
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
            ForEach(Array(items.enumerated()), id: \.element.id) { idx, item in
                NavigationLink(destination: GameDetailView(game: item.game, sport: item.sport)) {
                    HStack(spacing: 0) {
                        ForEach(Array(shownRows[idx].enumerated()), id: \.offset) { _, val in
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
                if idx < items.count - 1 { Divider() }
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
    /// Said and shown after the rest: the sport on a Monitoring row, " - monitoring" on a
    /// monitored game's own row.
    var suffix: String = ""
    /// Says Final on a finished game. A row in Live Scores' Completed section leaves it to
    /// the heading; a Monitoring row has no such heading.
    var saysFinal: Bool = false

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

            // The sport on a Monitoring row, or that the game is monitored.
            if !suffix.isEmpty {
                Text(suffix.trimmingCharacters(in: CharacterSet(charactersIn: " |-")))
                    .font(.caption.weight(.semibold))
                    .foregroundColor(.blue)
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
        if saysFinal && game.status.isCompleted && !game.status.isSuspended {
            statusParts.append("Final")
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

        return parts.joined(separator: ", ") + suffix
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
    .environmentObject(MonitoringStore())
}
