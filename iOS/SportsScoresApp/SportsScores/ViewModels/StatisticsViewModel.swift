//
//  StatisticsViewModel.swift
//  SportsScores
//
//  Phase 5 — League-wide stat leaders.
//  Fetches player and team leaders from ESPN for the current sport/season.
//

import Foundation

@MainActor
class StatisticsViewModel: ObservableObject {
    @Published var playerCategories: [LeagueLeaderCategory] = []
    @Published var teamCategories: [LeagueLeaderCategory] = []
    @Published var isLoadingPlayers = false
    @Published var isLoadingTeams = false
    @Published var playerError: String?
    @Published var teamError: String?

    private let apiService = ESPNAPIService.shared
    /// The same words as Windows, rather than the request's own error text.
    private static let unavailable = "ESPN isn't providing these right now. Try again in a minute."

    func fetchLeaders(for sport: Sport) async {
        isLoadingPlayers = playerCategories.isEmpty
        isLoadingTeams = teamCategories.isEmpty
        playerError = nil
        teamError = nil

        // Kick off both fetches concurrently; each updates its own state on completion.
        async let playerTask = apiService.fetchLeagueLeaders(for: sport)
        async let teamTask = apiService.fetchTeamLeaders(for: sport)

        do {
            playerCategories = try await playerTask
        } catch {
            playerError = Self.unavailable
        }
        isLoadingPlayers = false

        do {
            teamCategories = try await teamTask
        } catch {
            teamError = Self.unavailable
        }
        isLoadingTeams = false
    }

    func refresh(for sport: Sport) async {
        await fetchLeaders(for: sport)
    }
}
