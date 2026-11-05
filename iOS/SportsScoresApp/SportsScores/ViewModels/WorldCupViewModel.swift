//
//  WorldCupViewModel.swift
//  SportsScores
//
//  Manages all state for the World Cup hub:
//    • Groups tab  — group standings
//    • Scores tab  — games for the selected date (±7 days from today)
//    • Bracket tab — games for the selected tournament phase
//

import Foundation

@MainActor
final class WorldCupViewModel: ObservableObject {

    // MARK: - Published state

    @Published var groups: [WorldCupGroup] = []
    @Published var isLoadingGroups = false
    @Published var groupsError: String? = nil

    @Published var games: [Game] = []
    @Published var isLoadingGames = false
    @Published var gamesError: String? = nil
    @Published var selectedDate: Date

    @Published var bracketGames: [Game] = []
    @Published var isLoadingBracket = false
    @Published var bracketError: String? = nil
    @Published var selectedPhaseId: String

    /// Full knockout bracket model — powers inline placeholder resolution and the
    /// "Path to the Cup" feature. Loaded once across all knockout rounds.
    @Published var bracket: WorldCupBracket? = nil
    @Published var isLoadingFullBracket = false
    private var fullBracketLoaded = false
    /// Official match numbers never change for a tournament, so cache them and only
    /// fetch the ones we haven't seen — keeps refreshes (results/counts) cheap.
    private var cachedMatchNumbers: [String: Int] = [:]

    // MARK: - Configuration

    let sport: Sport
    let phases: [WorldCupPhase]

    // MARK: - Private

    private let api = ESPNAPIService.shared
    private let navRange = 7
    private var newDayObserver: Task<Void, Never>?

    // MARK: - Init

    init(sport: Sport) {
        self.sport = sport
        self.phases = sport == .worldCup ? WorldCupPhase.wc2026 : WorldCupPhase.wwc2027
        self.selectedDate = ScoreboardDay.today()

        // Pre-select the currently active phase, or the first phase.
        let now = Date()
        let active = phases.first(where: { now >= $0.startDate && now <= $0.endDate })
                  ?? phases.last
        self.selectedPhaseId = active?.id ?? phases.first?.id ?? "1"

        newDayObserver = Task { [weak self] in
            for await _ in NotificationCenter.default.notifications(named: .appReturnedToNewDay) {
                await self?.goToToday()
            }
        }
    }

    deinit { newDayObserver?.cancel() }

    // MARK: - Load all

    func loadAll() async {
        async let g: () = loadGroups()
        async let s: () = loadGamesForDate()
        _ = await (g, s)
    }

    // MARK: - Groups

    func loadGroups() async {
        isLoadingGroups = true
        groupsError = nil
        do {
            groups = try await api.fetchWorldCupStandings(for: sport)
        } catch {
            groupsError = "Could not load group standings."
        }
        isLoadingGroups = false
    }

    // MARK: - Scores (date-based)

    func loadGamesForDate() async {
        isLoadingGames = true
        gamesError = nil
        do {
            games = try await api.fetchGames(for: sport, date: selectedDate)
        } catch {
            gamesError = "Could not load games."
        }
        isLoadingGames = false
    }

    // MARK: - Date navigation

    private var navStart: Date {
        Calendar.current.date(byAdding: .day, value: -navRange,
                              to: ScoreboardDay.today()) ?? Date()
    }
    private var navEnd: Date {
        Calendar.current.date(byAdding: .day, value: navRange,
                              to: ScoreboardDay.today()) ?? Date()
    }

    var canNavigateBackward: Bool { selectedDate > navStart }
    var canNavigateForward:  Bool { selectedDate < navEnd }
    var isOnToday: Bool { ScoreboardDay.isToday(selectedDate) }

    var dateHeaderText: String {
        if ScoreboardDay.isToday(selectedDate) { return "Today's Matches" }
        let fmt = DateFormatter()
        fmt.dateFormat = "EEEE"
        return "\(fmt.string(from: selectedDate))'s Matches"
    }

    var dateAccessibilityText: String {
        if ScoreboardDay.isToday(selectedDate) { return "Today" }
        if ScoreboardDay.isYesterday(selectedDate) { return "Yesterday" }
        if ScoreboardDay.isTomorrow(selectedDate) { return "Tomorrow" }
        let fmt = DateFormatter()
        fmt.dateFormat = "EEEE, MMMM d"
        return fmt.string(from: selectedDate)
    }

    func goBack() async {
        guard canNavigateBackward else { return }
        selectedDate = Calendar.current.date(byAdding: .day, value: -1, to: selectedDate) ?? selectedDate
        await loadGamesForDate()
    }

    func goForward() async {
        guard canNavigateForward else { return }
        selectedDate = Calendar.current.date(byAdding: .day, value: 1, to: selectedDate) ?? selectedDate
        await loadGamesForDate()
    }

    func goToToday() async {
        selectedDate = ScoreboardDay.today()
        await loadGamesForDate()
    }

    // MARK: - Bracket (phase-based)

    var selectedPhase: WorldCupPhase? {
        phases.first(where: { $0.id == selectedPhaseId })
    }

    func loadBracket(for phase: WorldCupPhase) async {
        selectedPhaseId = phase.id
        guard phase.id != "1" else { return } // Group Stage shows the groups view, no game list needed
        isLoadingBracket = true
        bracketError = nil
        do {
            bracketGames = try await api.fetchGamesRange(for: sport,
                                                         startDate: phase.startDate,
                                                         endDate: phase.endDate)
        } catch {
            bracketError = "Could not load bracket matches."
        }
        isLoadingBracket = false
    }

    // MARK: - Full bracket (all knockout rounds)

    /// Maps a phase to its knockout round (group stage / unknown → nil).
    private func knockoutRound(for phase: WorldCupPhase) -> KnockoutRound? {
        let label = phase.label.lowercased()
        if label.contains("round of 32") { return .roundOf32 }
        if label.contains("round of 16") { return .roundOf16 }
        if label.contains("quarter")     { return .quarterfinals }
        if label.contains("semi")        { return .semifinals }
        if label.contains("3rd") || label.contains("third") { return .thirdPlace }
        if label.contains("final")       { return .final }
        return nil
    }

    /// Fetches every knockout round (plus group standings) and builds the bracket
    /// model used for placeholder resolution and the Path to the Cup view.
    func loadFullBracket(force: Bool = false) async {
        if fullBracketLoaded && !force { return }
        isLoadingFullBracket = true

        if groups.isEmpty { await loadGroups() }

        let knockoutPhases = phases.compactMap { phase -> (KnockoutRound, WorldCupPhase)? in
            guard let round = knockoutRound(for: phase) else { return nil }
            return (round, phase)
        }

        // Fetch each round's games concurrently.
        let results = await withTaskGroup(of: (KnockoutRound, [Game]).self) { group -> [(KnockoutRound, [Game])] in
            for (round, phase) in knockoutPhases {
                group.addTask { [api, sport] in
                    let games = (try? await api.fetchGamesRange(
                        for: sport, startDate: phase.startDate, endDate: phase.endDate)) ?? []
                    return (round, games)
                }
            }
            var collected: [(KnockoutRound, [Game])] = []
            for await item in group { collected.append(item) }
            return collected
        }

        var roundGames: [KnockoutRound: [Game]] = [:]
        for (round, games) in results where !games.isEmpty {
            roundGames[round] = games
        }

        // Official match numbers (from the core API) are required to order knockout
        // matches correctly — ESPN's placeholders reference them, and they don't
        // match kickoff or event-id order.
        let allIds = roundGames.values.flatMap { $0.map(\.id) }
        let missing = allIds.filter { cachedMatchNumbers[$0] == nil }
        if !missing.isEmpty {
            let fetched = await api.fetchMatchNumbers(for: sport, eventIds: missing)
            for (id, number) in fetched { cachedMatchNumbers[id] = number }
        }

        bracket = WorldCupBracket(roundGames: roundGames,
                                  matchNumbers: cachedMatchNumbers,
                                  groups: groups)
        fullBracketLoaded = bracket?.hasKnockoutGames ?? false
        isLoadingFullBracket = false
    }

    // MARK: - Game grouping helpers (used by Scores tab)

    /// Suspended matches group with the live ones — halted, not abandoned.
    var inProgressGames: [Game]  { games.filter { $0.status.isLive || $0.status.isSuspended } }
    var upcomingGames: [Game]    { games.filter { !$0.status.isLive && !$0.status.isCompleted
                                                  && !$0.status.isPostponed && !$0.status.isCancelled
                                                  && !$0.status.isSuspended } }
    var completedGames: [Game]   { games.filter { $0.status.isCompleted && !$0.status.isSuspended } }
    var postponedGames: [Game]   { games.filter { $0.status.isPostponed || $0.status.isCancelled } }
}
