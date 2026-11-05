//
//  ScoresViewModel.swift
//  SportsScores
//
//  Created on 1/4/26.
//

import Foundation

// MARK: - Auto-refresh interval

enum AutoRefreshInterval: Int, CaseIterable, Identifiable {
    case oneMinute     = 60
    case twoMinutes    = 120
    case fiveMinutes   = 300
    case manual        = 0

    var id: Int { rawValue }

    var label: String {
        switch self {
        case .oneMinute:     return "1m"
        case .twoMinutes:    return "2m"
        case .fiveMinutes:   return "5m"
        case .manual:        return "Manual"
        }
    }
}

@MainActor
class ScoresViewModel: ObservableObject {

    // MARK: - Published state

    @Published var games: [Game] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    // Date navigation (non-football sports)
    @Published var currentDate: Date = ScoreboardDay.today()

    // Week navigation (football)
    @Published var currentWeek: Int?
    @Published var currentSeasonType: Int = 2            // 1 pre / 2 regular / 3 post
    @Published var weekLabel: String = ""
    /// True while the user is viewing the API-resolved current week.
    @Published var isOnCurrentWeek: Bool = true
    /// Set to a specific season year when the user picks a historical season.
    /// `nil` means "let the ESPN API resolve to the current season."
    @Published var currentSeason: Int?
    /// The API-resolved season year (used for the UI label).
    @Published var resolvedSeason: Int = Calendar.current.component(.year, from: Date())

    /// Available season types for the currently selected historical football season.
    /// Empty when viewing the current (live) season — ESPN handles type resolution automatically.
    @Published var availableSeasonTypes: [SeasonTypeInfo] = []

    // MARK: - Private football calendar state

    /// Calendar loaded from the ESPN Core API for the current historical season.
    private var footballCalendar: SeasonCalendar?

    // MARK: - Private CFL round state

    /// Current round index into the CFL season, or nil to resolve the live round.
    private var cflRoundIndex: Int?
    /// Total number of rounds in the CFL season (for navigation bounds).
    private var cflRoundCount: Int = 0

    // MARK: - Computed helpers

    /// Week number bounds for the current season type, derived from the fetched calendar.
    /// `nil` when no calendar has been loaded — no hard bounds are enforced then.
    var currentWeekBounds: (min: Int, max: Int)? {
        guard let cal = footballCalendar else { return nil }
        let count = cal.weekCount(for: currentSeasonType)
        guard count > 0 else { return nil }
        return (min: 1, max: count)
    }

    /// The season type before/after the current one within the loaded calendar,
    /// so week navigation can roll over between preseason, regular, and postseason.
    private func adjacentSeasonType(offset: Int) -> SeasonTypeInfo? {
        guard let cal = footballCalendar,
              let index = cal.seasonTypes.firstIndex(where: { $0.type == currentSeasonType })
        else { return nil }
        let target = index + offset
        guard cal.seasonTypes.indices.contains(target) else { return nil }
        return cal.seasonTypes[target]
    }

    /// True when the back arrow should be disabled (first week of the first season type).
    var isAtWeekStart: Bool {
        if cflRoundCount > 0 { return (cflRoundIndex ?? 0) <= 0 }
        guard let bounds = currentWeekBounds else { return false }
        guard (currentWeek ?? 1) <= bounds.min else { return false }
        return adjacentSeasonType(offset: -1) == nil
    }

    /// True when the forward arrow should be disabled (last week of the last season type).
    var isAtWeekEnd: Bool {
        if cflRoundCount > 0 { return (cflRoundIndex ?? 0) >= cflRoundCount - 1 }
        guard let bounds = currentWeekBounds else { return false }
        guard (currentWeek ?? 1) >= bounds.max else { return false }
        return adjacentSeasonType(offset: 1) == nil
    }

    // MARK: - Sectioned game lists

    /// Suspended games sit here rather than with the postponed ones: they are
    /// unfinished, not abandoned, and their partial score is worth reading.
    var inProgressGames: [Game] { games.filter { $0.status.isLive || $0.status.isSuspended } }
    var upcomingGames:   [Game] {
        games
            .filter {
                !$0.status.isLive &&
                !$0.status.isCompleted &&
                !$0.status.isPostponed &&
                !$0.status.isCancelled &&
                !$0.status.isSuspended
            }
            .sorted { $0.date < $1.date }
    }
    var completedGames:  [Game] { games.filter { $0.status.isCompleted && !$0.status.isPostponed && !$0.status.isCancelled && !$0.status.isSuspended } }
    /// Games that were postponed, cancelled, or otherwise did not take place.
    var postponedGames:  [Game] { games.filter { $0.status.isPostponed || $0.status.isCancelled } }

    // MARK: - Today / current-week state

    /// True when the currently displayed date is calendar today (non-football).
    var isOnToday: Bool { ScoreboardDay.isToday(currentDate) }

    // MARK: - Formatted date label for display

    var dateLabelText: String {
        if ScoreboardDay.isToday(currentDate)     { return "Today" }
        if ScoreboardDay.isYesterday(currentDate) { return "Yesterday" }
        if ScoreboardDay.isTomorrow(currentDate)  { return "Tmrw" }
        let fmt = DateFormatter()
        fmt.dateFormat = "EEE, MMM d"
        return fmt.string(from: currentDate)
    }

    /// Long-form date string used in VoiceOver announcements and accessibility labels.
    var dateAccessibilityString: String {
        if ScoreboardDay.isToday(currentDate)     { return "Today" }
        if ScoreboardDay.isYesterday(currentDate) { return "Yesterday" }
        if ScoreboardDay.isTomorrow(currentDate)  { return "Tomorrow" }
        let fmt = DateFormatter()
        fmt.dateFormat = "EEEE, MMMM d"
        return fmt.string(from: currentDate)
    }

    /// The logical season display year for the currently visible date for non-football sports.
    /// Accounts for the year+1 API convention (e.g. NHL Oct 2026 → display year 2027).
    func displaySeasonYear(for sport: Sport) -> Int {
        sport.seasonYear(containing: currentDate)
    }

    // MARK: - Fetch

    private let apiService = ESPNAPIService.shared

    func fetchGames(for sport: Sport) async {
        isLoading = games.isEmpty
        errorMessage = nil

        do {
            if sport.usesCFLSource {
                // CFL is sourced from the cfl.ca feed and navigates by round/week.
                let result = try await CFLAPIService.shared.fetchRound(index: cflRoundIndex)
                games          = result.games
                cflRoundIndex  = result.roundIndex
                cflRoundCount  = result.roundCount
                weekLabel      = result.label
                isOnCurrentWeek = result.isCurrentRound
            } else if sport.isFootball {
                // Only the "current week of the current season" view lets ESPN
                // resolve things; every explicit week asks for its season by year,
                // because the scoreboard's `week=` param ignores `season=`.
                if currentSeason == nil && isOnCurrentWeek {
                    let result = try await apiService.fetchFootballGames(for: sport)
                    games             = result.games
                    currentWeek       = result.week
                    weekLabel         = result.weekLabel
                    currentSeasonType = result.seasonType
                    resolvedSeason    = result.season
                    // The live scoreboard embeds the whole season calendar —
                    // adopt it so the season-type picker and week bounds work
                    // in the live season too, not just historical ones.
                    if let cal = result.calendar {
                        footballCalendar     = cal
                        availableSeasonTypes = cal.seasonTypes
                    }
                } else {
                    let season = currentSeason ?? resolvedSeason
                    let week = currentWeek ?? 1
                    let result = try await apiService.fetchFootballWeek(
                        sport: sport,
                        season: season,
                        seasonType: currentSeasonType,
                        week: week
                    )
                    games             = result.games
                    currentWeek       = result.week
                    weekLabel         = result.weekLabel
                    currentSeasonType = result.seasonType
                    resolvedSeason    = result.season
                }
            } else {
                games = try await apiService.fetchGames(for: sport, date: currentDate)
            }
            errorMessage = nil  // clear any stale error from a concurrent failing fetch
        } catch {
            errorMessage = APIError.unavailable("scores", source: sport.usesCFLSource ? "The CFL" : "ESPN")
        }

        isLoading = false
    }

    // MARK: - Navigation

    func goForward(for sport: Sport) async {
        if sport.usesCFLSource {
            let next = (cflRoundIndex ?? 0) + 1
            if cflRoundCount > 0 && next > cflRoundCount - 1 { return }
            cflRoundIndex = next
            isOnCurrentWeek = false
        } else if sport.isFootball {
            let nextWeek = (currentWeek ?? 1) + 1
            // Respect bounds when we have a loaded calendar, rolling over into the
            // next season type (preseason → regular → postseason) at the boundary.
            if let bounds = currentWeekBounds, nextWeek > bounds.max {
                guard let next = adjacentSeasonType(offset: 1) else { return }
                currentSeasonType = next.type
                currentWeek       = 1
            } else {
                currentWeek = nextWeek
            }
            isOnCurrentWeek = false
        } else {
            currentDate = Calendar.current.date(byAdding: .day, value: 1, to: currentDate) ?? currentDate
        }
        await fetchGames(for: sport)
    }

    func goBack(for sport: Sport) async {
        if sport.usesCFLSource {
            let prev = (cflRoundIndex ?? 0) - 1
            if prev < 0 { return }
            cflRoundIndex = prev
            isOnCurrentWeek = false
        } else if sport.isFootball {
            let prevWeek = (currentWeek ?? 2) - 1
            // Respect bounds when we have a loaded calendar, rolling back into the
            // previous season type's final week at the boundary.
            if prevWeek < (currentWeekBounds?.min ?? 1) {
                guard let previous = adjacentSeasonType(offset: -1) else { return }
                currentSeasonType = previous.type
                currentWeek       = max(previous.weekCount, 1)
            } else {
                currentWeek = prevWeek
            }
            isOnCurrentWeek = false
        } else {
            currentDate = Calendar.current.date(byAdding: .day, value: -1, to: currentDate) ?? currentDate
        }
        await fetchGames(for: sport)
    }

    func goToDate(_ date: Date, for sport: Sport) async {
        // CFL navigates by round, not by date — resolve to the current round.
        if sport.usesCFLSource {
            await goToToday(for: sport)
            return
        }
        currentDate = Calendar.current.startOfDay(for: date)
        await fetchGames(for: sport)
    }

    /// Navigate to a historical (or current) season.
    ///
    /// - Football: fetches the season calendar from the Core API to discover
    ///   available season types and week counts, then loads week 1 regular season.
    /// - Non-football: jumps to the approximate opening date for the season.
    func goToSeason(_ year: Int, for sport: Sport) async {
        if sport.isFootball {
            // If the user tapped the year that's already the live season,
            // treat it as a "go back to current" action.
            let isLiveSeason = (currentSeason == nil && year == resolvedSeason)
            if isLiveSeason {
                await goToToday(for: sport)
                return
            }

            // Switch to historical mode.
            currentSeason       = year
            currentWeek         = nil
            currentSeasonType   = 2
            isOnCurrentWeek     = false
            footballCalendar    = nil
            availableSeasonTypes = []

            // Load the season calendar: which types exist and how many weeks?
            if let cal = try? await apiService.fetchFootballCalendar(sport: sport, season: year) {
                footballCalendar     = cal
                availableSeasonTypes = cal.seasonTypes
                // Default to regular season week 1; fall back to whatever is available.
                if cal.hasSeasonType(2) {
                    currentSeasonType = 2
                } else if let first = cal.seasonTypes.first {
                    currentSeasonType = first.type
                }
                currentWeek = 1
            } else {
                // Calendar fetch failed — still try week 1 regular season.
                currentWeek = 1
            }
        } else {
            // Non-football: jump to the approximate start of that season.
            currentDate = sport.approximateSeasonStartDate(year: year)
        }
        await fetchGames(for: sport)
    }

    /// Switch to a different season type within the football season being viewed
    /// (historical or live). No-op if the type isn't in the loaded calendar.
    func goToSeasonType(_ type: Int, for sport: Sport) async {
        guard let cal = footballCalendar, cal.hasSeasonType(type) else { return }
        currentSeasonType = type
        currentWeek       = 1
        // Leave "current week" mode so the explicit week is honoured rather than
        // ESPN re-resolving back to whatever it considers current.
        isOnCurrentWeek   = false
        await fetchGames(for: sport)
    }

    func goToToday(for sport: Sport) async {
        currentDate          = ScoreboardDay.today()
        currentWeek          = nil
        currentSeason        = nil   // nil → ESPN resolves to current season
        currentSeasonType    = 2
        isOnCurrentWeek      = true
        footballCalendar     = nil
        availableSeasonTypes = []
        cflRoundIndex        = nil   // re-resolve the live CFL round
        await fetchGames(for: sport)
    }

    func refresh(for sport: Sport) async {
        await fetchGames(for: sport)
    }
}

