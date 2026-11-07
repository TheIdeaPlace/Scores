//
//  GolfViewModel.swift
//  SportsScores
//
//  Manages fetching and navigating golf tournament data.
//  Owns the full season calendar, the currently-displayed tournament,
//  and prev/next navigation through the calendar.
//

import Foundation

@MainActor
class GolfViewModel: ObservableObject {

    // MARK: - Published state

    @Published var tournament: GolfTournament?
    @Published var calendar: [GolfCalendarEntry] = []
    @Published var selectedCalendarIndex: Int?
    @Published var isLoading = false
    @Published var errorMessage: String?
    /// This season's events by id, with each finished one's winner, for the schedule.
    @Published var seasonEvents: [String: GolfSeasonEvent] = [:]
    /// The schedule's winners couldn't be loaded; the calendar still shows without them.
    @Published var seasonFailed = false

    private let apiService: ESPNAPIService
    private let clock: () -> Date

    init(apiService: ESPNAPIService = .shared, clock: @escaping () -> Date = Date.init) {
        self.apiService = apiService
        self.clock = clock
    }

    // MARK: - Navigation helpers

    var canGoBack: Bool {
        (selectedCalendarIndex ?? 0) > 0
    }

    var canGoForward: Bool {
        guard let idx = selectedCalendarIndex else { return false }
        return idx < calendar.count - 1
    }

    var tournamentNavLabel: String {
        tournament?.name ?? (calendar.indices.contains(selectedCalendarIndex ?? -1)
            ? calendar[selectedCalendarIndex!].name
            : "Tournament")
    }

    // MARK: - Initial load

    /// Fetches the currently featured tournament and builds the season calendar.
    func fetchCurrentTournament(for sport: Sport) async {
        isLoading = tournament == nil
        errorMessage = nil
        do {
            let result = try await apiService.fetchGolfTournament(for: sport)
            calendar = result.calendar
            tournament = result.tournament
            syncCalendarIndex()
        } catch {
            errorMessage = APIError.unavailable("the leaderboard")
        }
        isLoading = false
    }

    func refresh(for sport: Sport) async {
        errorMessage = nil
        do {
            guard let idx = selectedCalendarIndex, calendar.indices.contains(idx) else {
                await fetchCurrentTournament(for: sport)
                return
            }
            let entry = calendar[idx]
            let result = try await apiService.fetchGolfTournament(for: sport, startDate: entry.startDate,
                                                                  eventID: entry.id)
            tournament = result.tournament
            // Refresh calendar too in case season rolled over
            if !result.calendar.isEmpty { calendar = result.calendar }
        } catch {
            errorMessage = APIError.unavailable("the leaderboard")
        }
    }

    // MARK: - Navigation

    func goBack(for sport: Sport) async {
        guard let idx = selectedCalendarIndex, idx > 0 else { return }
        await navigate(to: idx - 1, for: sport)
    }

    func goForward(for sport: Sport) async {
        guard let idx = selectedCalendarIndex, idx < calendar.count - 1 else { return }
        await navigate(to: idx + 1, for: sport)
    }

    func navigate(to index: Int, for sport: Sport) async {
        guard calendar.indices.contains(index) else { return }
        selectedCalendarIndex = index
        isLoading = true
        errorMessage = nil
        do {
            let entry = calendar[index]
            // By id as well as date: a week with an opposite-field event lists two.
            let result = try await apiService.fetchGolfTournament(for: sport, startDate: entry.startDate,
                                                                  eventID: entry.id)
            tournament = result.tournament
        } catch {
            errorMessage = APIError.unavailable("the leaderboard")
        }
        isLoading = false
    }

    // MARK: - Season winners

    /// Who won each finished event this season, from the same request Windows' schedule
    /// makes. A failure leaves what was shown and says so under the schedule.
    func fetchSeason(for sport: Sport) async {
        let year = Calendar(identifier: .gregorian).component(.year, from: clock())
        do {
            let events = try await apiService.fetchGolfSeason(for: sport, year: year)
            seasonEvents = Dictionary(events.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
            seasonFailed = false
        } catch {
            seasonFailed = true
        }
    }

    // MARK: - Private helpers

    private func syncCalendarIndex() {
        guard let t = tournament else {
            // No active event — try to point to the nearest upcoming tournament
            let now = Date()
            if let idx = calendar.firstIndex(where: { $0.startDate >= now }) {
                selectedCalendarIndex = idx
            } else {
                selectedCalendarIndex = calendar.indices.last
            }
            return
        }
        if let idx = calendar.firstIndex(where: { $0.id == t.id }) {
            selectedCalendarIndex = idx
        }
    }
}
