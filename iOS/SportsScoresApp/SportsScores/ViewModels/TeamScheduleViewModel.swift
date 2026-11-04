//
//  TeamScheduleViewModel.swift
//  SportsScores
//
//  Created on 2/26/26.
//

import Foundation

@MainActor
class TeamScheduleViewModel: ObservableObject {
    @Published var games: [ScheduleGame] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    /// True when `errorMessage` is a failed request, which trying again might fix, rather
    /// than a season with nothing in it.
    @Published var loadFailed = false
    /// True when a refresh failed with games showing. They stay, since that may be the list
    /// someone is partway through, and this says they may be out of date. It lasts until a
    /// load works, so returning from game details on a bad connection doesn't say it again.
    @Published var refreshFailed = false
    @Published var selectedYear: Int

    private let apiService: ESPNAPIService
    private let teamId: String
    private let sport: Sport
    /// Picking a year during a slow load starts another. Only the newest may touch the
    /// list: an older reply arriving last would leave the wrong season under the picker.
    private var generation = 0

    // Available years to display in the picker (current year and 4 prior)
    let availableYears: [Int]

    init(teamId: String, sport: Sport, apiService: ESPNAPIService = .shared) {
        self.teamId = teamId
        self.sport = sport
        self.apiService = apiService
        let year = Self.defaultSeasonYear(for: sport)
        self.selectedYear = year
        self.availableYears = (0..<5).map { year - $0 }
    }

    /// Returns the season year to request from ESPN for a given sport.
    /// See `Sport.seasonYear(containing:)` for the per-sport conventions —
    /// notably the winter sports, where the 2026-27 season is `season=2027`
    /// and ESPN turns the year over in the summer, not in October.
    static func defaultSeasonYear(for sport: Sport) -> Int {
        sport.currentSeasonYear
    }

    /// Human-readable label for a season year — "2026-27" for the NHL's
    /// `season=2027`, plain "2026" for MLB and the WNBA.
    func seasonLabel(_ year: Int) -> String {
        sport.seasonDisplayName(year: year)
    }

    func fetchSchedule() async {
        generation += 1
        let thisLoad = generation
        isLoading = true
        errorMessage = nil
        loadFailed = false
        let fetched: [ScheduleGame]
        do {
            fetched = try await apiService.fetchTeamSeasonSchedule(
                teamId: teamId,
                sport: sport,
                season: selectedYear
            )
        } catch {
            guard thisLoad == generation else { return }
            isLoading = false
            if error.isCancellation {
                // The view went away mid-load, and nothing is known about the schedule. Keep
                // what's there, and the next load, when it's back, asks again.
            } else if error.isNothingThere {
                // ESPN says it has nothing there: no schedule, and no sign of an off-season.
                errorMessage = noScheduleMessage
                refreshFailed = false
                games = []
            } else if !games.isEmpty {
                refreshFailed = true
            } else {
                // Not the fallback below: a failed request isn't an off-season, and last
                // season's games would read as this season's with no sign anything went wrong.
                errorMessage = "Could not load the schedule. Check your connection and try again."
                loadFailed = true
            }
            return
        }
        guard thisLoad == generation else { return }

        // ESPN publishes a new season's schedule some weeks after the previous
        // one ends, so in that gap the current season year comes back empty.
        // Fall back to the season that just finished rather than showing
        // nothing at all.
        if fetched.isEmpty && selectedYear == Self.defaultSeasonYear(for: sport) {
            selectedYear -= 1
            await fetchSchedule()
            return
        }

        if fetched.isEmpty {
            errorMessage = noScheduleMessage
        }
        refreshFailed = false
        games = fetched
        isLoading = false
    }

    private var noScheduleMessage: String {
        "No schedule data available for \(sport.seasonDisplayName(year: selectedYear))."
    }

    func changeYear(_ year: Int) async {
        selectedYear = year
        // The view keeps a list up during a refresh, but this one is the wrong season.
        games = []
        refreshFailed = false
        await fetchSchedule()
    }
}
