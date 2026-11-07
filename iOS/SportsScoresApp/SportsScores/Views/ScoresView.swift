//
//  ScoresView.swift
//  SportsScores
//
//  Created on 1/4/26.
//

import SwiftUI
import UIKit

private enum ScoresTab: Int {
    case scores = 0, standings, news, stats, polls, venues
}

struct ScoresView: View {
    let sport: Sport
    let initialDate: Date?
    @StateObject private var viewModel = ScoresViewModel()
    @State private var selectedTab = ScoresTab.scores
    @State private var showDatePicker = false
    @State private var hasLoadedInitialData = false
    @State private var viewMode: ViewMode = .quickList
    @EnvironmentObject private var appSettings: AppSettings

    init(sport: Sport, initialDate: Date? = nil) {
        self.sport = sport
        self.initialDate = initialDate
        _viewModel = StateObject(wrappedValue: ScoresViewModel())
        _selectedTab = State(initialValue: .scores)
        _showDatePicker = State(initialValue: false)
    }

    var body: some View {
        VStack(spacing: 0) {

            // ── Date / Week navigation bar (only on Scores tab) ──────────
            if selectedTab == .scores {
                dateNavigationBar
                    .padding(.horizontal)
                    .padding(.top, 8)
                    .padding(.bottom, 6)
            }

            // ── Content ───────────────────────────────────────────────────
            tabContent
                .frame(maxWidth: .infinity, maxHeight: .infinity)

            // ── Tab selector (Scores / Standings / News / Stats [/ Polls] [/ Venues]) ─
            Divider()
            Picker("View", selection: $selectedTab) {
                Text("Scores").tag(ScoresTab.scores)
                Text("Standings").tag(ScoresTab.standings)
                // CFL has no ESPN-backed News or Stats feeds.
                if !sport.usesCFLSource {
                    Text("News").tag(ScoresTab.news)
                    Text("Stats").tag(ScoresTab.stats)
                }
                if sport.hasPolls {
                    Text("Polls").tag(ScoresTab.polls)
                }
                if sport.hasVenues {
                    Text("Venues").tag(ScoresTab.venues)
                }
            }
            .pickerStyle(.segmented)
            .padding(.horizontal)
            .padding(.top, 4)
            .padding(.bottom, 8)
        }
        .navigationTitle(sport.displayName)
        .toolbar {
            // Only show auto-refresh on the Scores tab and only when viewing current data.
            // Historical dates/weeks can't meaningfully auto-refresh, and other tabs
            // (Standings, News, Stats, Polls) are not wired to this refresh loop.
            let isViewingCurrent = sport.usesWeekNavigation ? viewModel.isOnCurrentWeek : viewModel.isOnToday
            if selectedTab == .scores && isViewingCurrent {
                ToolbarItem(placement: .navigationBarTrailing) {
                    autoRefreshMenu
                }
            }
            if selectedTab == .scores && sport == .ncaaf {
                ToolbarItem(placement: .navigationBarTrailing) {
                    coverageMenu
                }
            }
            if selectedTab == .scores && !viewModel.games.isEmpty {
                ToolbarItem(placement: .navigationBarTrailing) {
                    ViewModeMenuButton(currentMode: $viewMode)
                }
            }
        }
        .task {
            guard !hasLoadedInitialData else { return }
            hasLoadedInitialData = true
            if let initialDate = initialDate {
                await viewModel.goToDate(initialDate, for: sport)
            } else {
                await viewModel.fetchGames(for: sport)
            }
        }
        // The college football coverage setting changes which games ESPN returns,
        // so anything already on screen is stale the moment it is switched.
        .onChange(of: appSettings.ncaafCoverage) {
            guard sport == .ncaaf else { return }
            Task { await viewModel.refresh(for: sport) }
        }
        // Auto-refresh loop — cancels and restarts whenever the interval changes.
        // Only actually refreshes when on the Scores tab viewing current data.
        .task(id: appSettings.autoRefreshInterval) {
            while !Task.isCancelled {
                let secs = appSettings.autoRefreshInterval.rawValue
                if secs > 0 {
                    try? await Task.sleep(for: .seconds(secs))
                    guard !Task.isCancelled else { break }
                    let isViewingCurrent = sport.usesWeekNavigation ? viewModel.isOnCurrentWeek : viewModel.isOnToday
                    if selectedTab == .scores && isViewingCurrent {
                        await viewModel.refresh(for: sport)
                    }
                } else {
                    // Manual — park until cancelled
                    try? await Task.sleep(for: .seconds(86400))
                }
            }
        }
        .refreshable {
            // Refresh the active tab
            switch selectedTab {
            case .scores: await viewModel.refresh(for: sport)
            default: break  // Standings and News have their own refresh
            }
        }
        .sheet(isPresented: $showDatePicker) {
            DatePickerView(selectedDate: viewModel.currentDate) { pickedDate in
                Task { await viewModel.goToDate(pickedDate, for: sport) }
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .appReturnedToNewDay)) { _ in
            Task { await viewModel.goToToday(for: sport) }
        }
    }

    // MARK: - College football coverage menu

    /// Changes how much of the college football slate is shown, without a trip to
    /// Settings. It edits the same stored preference the Settings picker does, so
    /// there is one value in play rather than a screen-local override competing
    /// with a saved one — the `.onChange` below refetches either way.
    private var coverageMenu: some View {
        Menu {
            Picker("College football coverage", selection: $appSettings.ncaafCoverage) {
                ForEach(NCAAFCoverage.allCases) { coverage in
                    Text(coverage.settingsLabel).tag(coverage)
                }
            }
            .pickerStyle(.inline)
        } label: {
            Label(appSettings.ncaafCoverage.shortLabel, systemImage: "line.3.horizontal.decrease.circle")
                .labelStyle(.iconOnly)
        }
        .accessibilityLabel("College football coverage, currently \(appSettings.ncaafCoverage.settingsLabel)")
        .accessibilityHint("All Division I shows FBS and FCS together, around 200 games a week. "
                           + "FBS only shows about 100. Changing this also updates the Settings screen.")
    }

    // MARK: - Auto-refresh menu

    private var autoRefreshMenu: some View {
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
                  ? "Manual"
                  : "Auto \(appSettings.autoRefreshInterval.label)",
                  systemImage: "arrow.clockwise")
            .font(.subheadline)
        }
        .accessibilityLabel("Auto-refresh interval, currently \(appSettings.autoRefreshInterval == .manual ? "manual" : "every \(appSettings.autoRefreshInterval.label)")")
    }

    // MARK: - Date / Week Navigation Bar

    @ViewBuilder
    private var dateNavigationBar: some View {
        HStack(spacing: 8) {

            // ── Previous button ──────────────────────────────────────────
            Button {
                Task { await viewModel.goBack(for: sport); announceNavigation() }
            } label: {
                Image(systemName: "chevron.left")
                    .font(.body.bold())
                    .frame(width: 44, height: 36)
                    .contentShape(Rectangle())
            }
            .disabled(viewModel.isLoading || (sport.usesWeekNavigation && viewModel.isAtWeekStart))
            .accessibilityLabel(sport.usesWeekNavigation ? "Previous Week" : "Previous Day")

            Spacer()

            // ── Centre label ─────────────────────────────────────────────
            if sport.usesWeekNavigation {
                let weekText = viewModel.weekLabel.isEmpty
                    ? (viewModel.currentWeek.map { "Week \($0)" } ?? "Current Week")
                    : viewModel.weekLabel
                VStack(spacing: 2) {
                    Text(weekText)
                        .font(.subheadline.bold())
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                        // Static text — VoiceOver reads it as part of the row; no interactive trait.
                        .accessibilityLabel(weekText)

                    // ESPN season / season-type pickers — real football only.
                    // CFL has a single live season, so it shows just the week label.
                    if sport.isFootball {
                    HStack(spacing: 6) {
                        // Season year picker
                        Menu {
                            ForEach(sport.availableSeasonYears, id: \.self) { year in
                                Button(String(year)) {
                                    Task { await viewModel.goToSeason(year, for: sport); announceNavigation() }
                                }
                            }
                        } label: {
                            HStack(spacing: 3) {
                                Text(String(viewModel.resolvedSeason))
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                Image(systemName: "chevron.up.chevron.down")
                                    .font(.system(size: 9))
                                    .foregroundColor(.secondary)
                            }
                        }
                        .accessibilityLabel("\(viewModel.resolvedSeason) season")
                        .accessibilityHint("Select to change season")

                        // Season type picker (only when calendar is loaded with >1 type)
                        if viewModel.availableSeasonTypes.count > 1 {
                            let currentTypeName = viewModel.availableSeasonTypes
                                .first { $0.type == viewModel.currentSeasonType }?.label ?? "Regular"
                            Menu {
                                ForEach(viewModel.availableSeasonTypes) { typeInfo in
                                    Button(typeInfo.label) {
                                        Task { await viewModel.goToSeasonType(typeInfo.type, for: sport); announceNavigation() }
                                    }
                                }
                            } label: {
                                let shortLabel = viewModel.availableSeasonTypes
                                    .first { $0.type == viewModel.currentSeasonType }?.shortLabel ?? "Reg"
                                HStack(spacing: 2) {
                                    Text(shortLabel)
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                    Image(systemName: "chevron.up.chevron.down")
                                        .font(.system(size: 9))
                                        .foregroundColor(.secondary)
                                }
                            }
                            .accessibilityLabel("\(currentTypeName)")
                            .accessibilityHint("Select to change between preseason, regular, and postseason")
                        }
                    }
                    }
                }
                .accessibilityElement(children: .contain)
                .accessibilityLabel("\(weekText), \(viewModel.resolvedSeason)")
                .accessibilityHint("Swipe up for next week, swipe down for previous week")
                .accessibilityAdjustableAction { direction in
                    Task {
                        switch direction {
                        case .increment: await viewModel.goForward(for: sport)
                        case .decrement: await viewModel.goBack(for: sport)
                        @unknown default: break
                        }
                        announceNavigation()
                    }
                }
            } else {
                VStack(spacing: 2) {
                    Button { showDatePicker = true } label: {
                        HStack(spacing: 4) {
                            Text(viewModel.dateLabelText)
                                .font(.subheadline.bold())
                            Image(systemName: "calendar")
                                .font(.caption)
                        }
                        .foregroundColor(.primary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 6)
                        .background(Color.secondary.opacity(0.12))
                        .cornerRadius(8)
                    }
                    .accessibilityLabel(viewModel.dateAccessibilityString)
                    .accessibilityHint("Opens date picker. Swipe up for next day, swipe down for previous day")
                    .accessibilityAdjustableAction { direction in
                        Task {
                            switch direction {
                            case .increment: await viewModel.goForward(for: sport)
                            case .decrement: await viewModel.goBack(for: sport)
                            @unknown default: break
                            }
                            announceNavigation()
                        }
                    }

                    // Season picker for non-football, non-soccer sports.
                    // CFL is excluded — the feed only carries the current season.
                    if !sport.isSoccer && !sport.usesCFLSource {
                        let displayYear = viewModel.displaySeasonYear(for: sport)
                        let seasonName  = sport.seasonDisplayName(year: displayYear)
                        Menu {
                            ForEach(sport.availableSeasonYears, id: \.self) { year in
                                Button(sport.seasonDisplayName(year: year)) {
                                    Task { await viewModel.goToSeason(year, for: sport); announceNavigation() }
                                }
                            }
                        } label: {
                            HStack(spacing: 3) {
                                Text(seasonName)
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                Image(systemName: "chevron.up.chevron.down")
                                    .font(.system(size: 9))
                                    .foregroundColor(.secondary)
                            }
                        }
                        .accessibilityLabel("\(seasonName) season")
                        .accessibilityHint("Select to change season")
                    }
                }
            }

            Spacer()

            // ── Next button ───────────────────────────────────────────────
            Button {
                Task { await viewModel.goForward(for: sport); announceNavigation() }
            } label: {
                Image(systemName: "chevron.right")
                    .font(.body.bold())
                    .frame(width: 44, height: 36)
                    .contentShape(Rectangle())
            }
            .disabled(viewModel.isLoading || (sport.usesWeekNavigation && viewModel.isAtWeekEnd))
            .accessibilityLabel(sport.usesWeekNavigation ? "Next Week" : "Next Day")

            // ── Today button (only when not on today / current week) ──────
            let showToday = sport.usesWeekNavigation ? !viewModel.isOnCurrentWeek : !viewModel.isOnToday
            if showToday {
                Button("Today") {
                    Task { await viewModel.goToToday(for: sport); announceNavigation() }
                }
                .font(.subheadline)
                .buttonStyle(.bordered)
                .controlSize(.small)
                .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.15), value: viewModel.isOnToday)
        .animation(.easeInOut(duration: 0.15), value: viewModel.isOnCurrentWeek)
        .animation(.none, value: viewModel.weekLabel)
        // Belt-and-suspenders named actions for VoiceOver custom actions rotor
        .accessibilityAction(named: sport.usesWeekNavigation ? "Previous Week" : "Previous Day") {
            Task { await viewModel.goBack(for: sport); announceNavigation() }
        }
        .accessibilityAction(named: sport.usesWeekNavigation ? "Next Week" : "Next Day") {
            Task { await viewModel.goForward(for: sport); announceNavigation() }
        }
    }

    /// Posts a haptic and VoiceOver announcement after any date/week navigation.
    private func announceNavigation() {
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        let description: String
        if sport.usesWeekNavigation {
            let weekText = viewModel.weekLabel.isEmpty
                ? (viewModel.currentWeek.map { "Week \($0)" } ?? "Current Week")
                : viewModel.weekLabel
            description = "\(weekText), \(viewModel.resolvedSeason)"
        } else {
            description = viewModel.dateAccessibilityString
        }
        UIAccessibility.post(notification: .announcement, argument: description)
    }

    // MARK: - Tab content (conditional — no TabView to avoid height/task issues)

    @ViewBuilder
    private var tabContent: some View {
        switch selectedTab {
        case .standings:
            StandingsView(sport: sport)
        case .news:
            NewsView(sport: sport)
        case .stats:
            StatisticsView(sport: sport)
        case .polls where sport.hasPolls:
            PollsView(sport: sport)
        case .venues where sport.hasVenues:
            VenuesView(sport: sport)
        default:
            scoresTab
        }
    }

    private var scoresTab: some View {
        Group {
            if viewModel.isLoading {
                ProgressView("Loading games...")
            } else if let error = viewModel.errorMessage, viewModel.games.isEmpty {
                // Only surface the error when there's no cached data to fall back on.
                // A failed background refresh while games are already displayed is silently
                // ignored — the existing data stays visible.
                ErrorStateView(message: error) {
                    Task { await viewModel.fetchGames(for: sport) }
                }
            } else if viewModel.games.isEmpty {
                VStack(spacing: 16) {
                    Image(systemName: "calendar.badge.exclamationmark")
                        .font(.system(size: 48))
                        .foregroundColor(.secondary)
                    Text("No games scheduled")
                        .font(.headline)
                        .foregroundColor(.secondary)
                    if !sport.usesWeekNavigation {
                        Button("Go to Today") {
                            Task { await viewModel.goToToday(for: sport) }
                        }
                        .buttonStyle(.bordered)
                    }
                }
            } else {
                VStack(spacing: 0) {
                    switch viewMode {
                    case .table:
                        gamesTableView
                    case .quickList:
                        gamesQuickListView
                    case .fullList:
                        gamesList
                    }
                }
            }
        }
    }

    // MARK: - Section ordering

    /// One section list, used by all three view modes so they cannot drift apart.
    private struct GameSection: Identifiable {
        let id: String
        let title: String
        let games: [Game]
        let context: GameSectionContext
    }

    /// One order for every sport: what is on now, what is on next, then what
    /// finished. Football weeks span played and unplayed days at once, so a
    /// Saturday's finals do sit below games that have not kicked off — the game
    /// count in each section header is what makes them findable.
    private var orderedSections: [GameSection] {
        let inProgress = GameSection(id: "inProgress", title: "In Progress",
                                     games: viewModel.inProgressGames, context: .inProgress)
        let upcoming = GameSection(id: "upcoming", title: "Upcoming",
                                   games: viewModel.upcomingGames, context: .upcoming)
        let completed = GameSection(id: "completed", title: "Completed",
                                    games: viewModel.completedGames, context: .completed)
        let postponed = GameSection(id: "postponed", title: "Postponed / Cancelled",
                                    games: viewModel.postponedGames, context: .postponed)
        return [inProgress, upcoming, completed, postponed].filter { !$0.games.isEmpty }
    }

    // MARK: - Table view mode

    private var gamesTableView: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                ForEach(orderedSections) { section in
                    gamesTableSection(title: section.title, games: section.games)
                }
            }
            .padding(.vertical)
        }
    }

    /// "Completed" -> "Completed, 57 games". On a 200-game college football week
    /// this is what lets a user tell in one flick whether a section is worth
    /// entering — and confirms the games are there, which is the confusion that
    /// prompted the section reorder in the first place.
    private func sectionHeaderText(_ title: String, count: Int) -> String {
        "\(title), \(count) \(count == 1 ? "game" : "games")"
    }

    private func gamesTableSection(title: String, games: [Game]) -> some View {
        let headers = ["Away", "Home", "Status"]
        let tableRows = games.map { gameAccessibleTableRow($0) }
        return VStack(alignment: .leading, spacing: 0) {
            Text(sectionHeaderText(title, count: games.count))
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
                AccessibleDataTable(headers: headers, rows: tableRows)
                    .allowsHitTesting(false)
            )
            .padding(.horizontal)
        }
    }

    private func gameTableRow(_ game: Game) -> [String] {
        let away = game.awayTeam.rankedAbbreviation + (game.awayTeam.score.map { " \($0)" } ?? "")
        let home = game.homeTeam.rankedAbbreviation + (game.homeTeam.score.map { " \($0)" } ?? "")
        let status: String
        if game.status.isLive { status = game.status.displayText }
        else if game.status.isPostponed { status = "PPD" }
        else if game.status.isCancelled { status = "Cxl" }
        else if game.status.isSuspended { status = "Susp" }
        else if game.status.isCompleted { status = "Final" }
        else { status = game.displayTime }
        return [away, home, status]
    }

    private func gameAccessibleTableRow(_ game: Game) -> [String] {
        let pref = appSettings.teamNamePreference
        let away = game.awayTeam.voiceOverName(for: pref) + (game.awayTeam.score.map { " \($0)" } ?? "")
        let home = game.homeTeam.voiceOverName(for: pref) + (game.homeTeam.score.map { " \($0)" } ?? "")
        var statusParts: [String] = []
        if game.status.isLive {
            statusParts.append(game.status.displayText)
            if let sit = game.situation, let t = sit.displayText, !t.isEmpty {
                statusParts.append(t)
            }
        } else if game.status.isPostponed { statusParts.append("Postponed") }
        else if game.status.isCancelled { statusParts.append("Cancelled") }
        else if game.status.isSuspended { statusParts.append("Suspended") }
        else if game.status.isCompleted { statusParts.append("Final") }
        else { statusParts.append(game.displayTime) }
        return [away, home, statusParts.joined(separator: ", ")]
    }

    // MARK: - Quick List view mode

    private var gamesQuickListView: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                ForEach(orderedSections) { section in
                    gamesQuickSection(title: section.title, games: section.games)
                }
            }
            .padding()
        }
    }

    @ViewBuilder
    private func gamesQuickSection(title: String, games: [Game]) -> some View {
        if !games.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text(sectionHeaderText(title, count: games.count))
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
                    .accessibilityHint("Opens game details")
                }
            }
        }
    }

    private func gameQuickText(_ game: Game) -> String {
        let away = game.awayTeam.rankedAbbreviation + (game.awayTeam.score.map { " \($0)" } ?? "")
        let home = game.homeTeam.rankedAbbreviation + (game.homeTeam.score.map { " \($0)" } ?? "")
        let status: String
        if game.status.isLive {
            var parts = [game.status.displayText]
            if let sit = game.situation, let sitText = sit.displayText, !sitText.isEmpty {
                parts.append(sitText)
            }
            status = parts.joined(separator: " · ")
        } else if game.status.isPostponed { status = "PPD" }
        else if game.status.isCancelled { status = "Cancelled" }
        else if game.status.isSuspended { status = "Suspended" }
        else if game.status.isCompleted { status = "Final" }
        else { status = game.displayTime }
        var line = "\(away) \(game.matchupSymbol) \(home) — \(status)"
        if let venue = game.venue, !venue.name.isEmpty { line += " · \(venue.fullName)" }
        return line
    }

    private func gameQuickAccessibilityText(_ game: Game) -> String {
        let pref = appSettings.teamNamePreference
        let away = game.awayTeam.voiceOverName(for: pref) + (game.awayTeam.score.map { " \($0)" } ?? "")
        let home = game.homeTeam.voiceOverName(for: pref) + (game.homeTeam.score.map { " \($0)" } ?? "")
        let status: String
        if game.status.isLive {
            var parts = [game.status.displayText]
            if let sit = game.situation, let t = sit.displayText, !t.isEmpty { parts.append(t) }
            status = parts.joined(separator: ", ")
        } else if game.status.isPostponed { status = "Postponed" }
        else if game.status.isCancelled { status = "Cancelled" }
        else if game.status.isSuspended { status = "Suspended" }
        else if game.status.isCompleted { status = "Final" }
        else { status = game.displayTime }
        var label = "\(away) \(game.matchupWord) \(home), \(status)"
        // Venue: unlabeled (terse) but the data is still spoken.
        if let venue = game.venue, !venue.name.isEmpty { label += ", \(venue.fullName)" }
        if game.shouldShowBroadcastInfo, let broadcast = game.broadcasts.first, !broadcast.isEmpty {
            label += ", on \(broadcast)"
        }
        return label
    }

    private var gamesList: some View {
        List {
            ForEach(orderedSections) { section in
                Section {
                    ForEach(section.games) { game in
                        gameRow(game, context: section.context)
                    }
                } header: {
                    Text(sectionHeaderText(section.title, count: section.games.count))
                        .accessibilityAddTraits(.isHeader)
                }
            }
        }
        .listStyle(.plain)
    }

    @ViewBuilder
    private func gameRow(_ game: Game, context: GameSectionContext) -> some View {
        NavigationLink(destination: GameDetailView(game: game, sport: sport)) {
            GameRow(game: game, sport: sport, sectionContext: context)
        }
        .listenToGame(game, sport: sport)
    }
}

// MARK: - Section Context

/// Indicates which status section a game row is displayed in.
/// Used to suppress redundant VoiceOver status words (design debt #5).
enum GameSectionContext {
    case inProgress, upcoming, completed, postponed
}

// MARK: - Game Row

struct GameRow: View {
    let game: Game
    let sport: Sport
    /// The list section this row is in. `nil` = unknown / no sectioning.
    var sectionContext: GameSectionContext? = nil

    @EnvironmentObject private var appSettings: AppSettings

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {

            // Status / time + broadcast chip
            HStack {
                statusChip
                Spacer()
                if game.shouldShowBroadcastInfo,
                   let broadcast = game.broadcasts.first,
                   !broadcast.isEmpty {
                    Text(broadcast)
                        .font(.caption2)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.blue.opacity(0.2))
                        .cornerRadius(4)
                }
            }

            // Away / Home score rows
            VStack(alignment: .leading, spacing: 4) {
                TeamScoreRow(team: game.awayTeam, isHome: false, isNeutralSite: game.isNeutralSite == true)
                TeamScoreRow(team: game.homeTeam, isHome: true, isNeutralSite: game.isNeutralSite == true)
            }

            // Live situation line
            if game.status.isLive, let sit = game.situation, let text = sit.displayText, !text.isEmpty {
                HStack(spacing: 6) {
                    Text(text)
                        .font(.caption)
                        .foregroundColor(.orange)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                    if sit.isRedZone == true {
                        Text("🔴 Red Zone")
                            .font(.caption2)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(Color.red.opacity(0.18))
                            .foregroundColor(.red)
                            .cornerRadius(4)
                    }
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
        .padding(.vertical, 4)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityLabel)
        .onAppear {
            debugLogAccessibilityLabelIfNeeded()
        }
    }

    @ViewBuilder
    private var statusChip: some View {
        if game.status.isLive {
            Label(game.status.displayText, systemImage: "circle.fill")
                .foregroundColor(.red)
                .font(.caption)
                .fontWeight(.semibold)
        } else if game.status.isPostponed {
            Text("Postponed")
                .font(.caption)
                .foregroundColor(.orange)
        } else if game.status.isCancelled {
            Text(game.status.detail.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Cancelled" : game.status.detail)
                .font(.caption)
                .foregroundColor(.orange)
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
    }

    private var accessibilityLabel: String {
        let pref = appSettings.teamNamePreference

        // Away / Home with scores
        let awayScore = game.awayTeam.score.map { " \($0)" } ?? ""
        let awayPart = "\(game.awayPrefix)\(game.awayTeam.voiceOverName(for: pref))\(awayScore)"
        let homeScore = game.homeTeam.score.map { " \($0)" } ?? ""
        let homePart = "\(game.homePrefix)\(game.homeTeam.voiceOverName(for: pref))\(homeScore)"

        // Status field — same data as quick list, field name added here (full list mode)
        // Suppress status word when section heading already communicates it (design debt #5)
        let suppressFinal = sectionContext == .completed
        var statusParts: [String] = []

        if game.status.isPostponed {
            if sectionContext != .postponed { statusParts.append("Postponed") }
        } else if game.status.isCancelled {
            // The "Postponed / Cancelled" heading already says it; don't repeat.
            if sectionContext != .postponed {
                let statusDetail = game.status.detail.trimmingCharacters(in: .whitespacesAndNewlines)
                statusParts.append(statusDetail.isEmpty ? "Cancelled" : statusDetail)
            }
        } else if game.status.isSuspended {
            // Always spoken: suspended rows sit under "In Progress", which does not
            // convey that play is halted.
            let statusDetail = game.status.detail.trimmingCharacters(in: .whitespacesAndNewlines)
            statusParts.append(statusDetail.isEmpty ? "Suspended" : statusDetail)
        } else if game.status.isCompleted {
            if !suppressFinal { statusParts.append("Final") }
        } else if game.status.isLive {
            // For live games: inning first for baseball, then situation.
            // For all other sports, situation leads and period/clock follows.
            if sport == .mlb {
                statusParts.append(game.status.detail)
                if let sit = game.situation, let t = sit.displayText, !t.isEmpty {
                    statusParts.append(t)
                }
            } else {
                if let sit = game.situation {
                    if let t = sit.displayText, !t.isEmpty { statusParts.append(t) }
                    if sit.isRedZone == true { statusParts.append("Red Zone") }
                }
                statusParts.append(game.status.displayText)
            }
        } else {
            statusParts.append(game.displayTime)
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
        guard game.status.isLive else { return }
        guard ProcessInfo.processInfo.arguments.contains("-A11YDebugLiveLabels") else { return }
        print("[A11Y][ScoresView][\(sport.rawValue)][\(game.id)] \(accessibilityLabel)")
        #endif
    }
}

// MARK: - Team Score Row

struct TeamScoreRow: View {
    let team: Game.Team
    let isHome: Bool
    var isNeutralSite = false

    var body: some View {
        HStack {
            Text(isHome ? "vs" : (isNeutralSite ? "" : "@"))
                .font(.caption)
                .foregroundColor(.secondary)
                .frame(width: 20)

            Text(team.rankedAbbreviation)
                .font(.body)
                .fontWeight(.medium)

            if let record = team.record {
                Text("(\(record))")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Spacer()

            if let score = team.score {
                Text("\(score)")
                    .font(.title3)
                    .fontWeight(.bold)
                    .monospacedDigit()
            }
        }
    }
}

#Preview {
    NavigationStack {
        ScoresView(sport: .mlb)
    }
    .environmentObject(AppSettings())
}

