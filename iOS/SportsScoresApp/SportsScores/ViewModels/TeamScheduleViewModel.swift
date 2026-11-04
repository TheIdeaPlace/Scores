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
    @Published var selectedYear: Int

    private let apiService = ESPNAPIService.shared
    private let teamId: String
    private let sport: Sport

    // Available years to display in the picker (current year and 4 prior)
    let availableYears: [Int]

    init(teamId: String, sport: Sport) {
        self.teamId = teamId
        self.sport = sport
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
        isLoading = true
        errorMessage = nil
        let fetched: [ScheduleGame]
        do {
            fetched = try await apiService.fetchTeamSeasonSchedule(
                teamId: teamId,
                sport: sport,
                season: selectedYear
            )
        } catch {
            // Not the fallback below: a failed request isn't an off-season, and last
            // season's games would read as this season's with no sign anything went wrong.
            errorMessage = "Could not load the schedule. Check your connection and try again."
            games = []
            isLoading = false
            return
        }

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
            errorMessage = "No schedule data available for \(sport.seasonDisplayName(year: selectedYear))."
        }
        games = fetched
        isLoading = false
    }

    func changeYear(_ year: Int) async {
        selectedYear = year
        await fetchSchedule()
    }
}
