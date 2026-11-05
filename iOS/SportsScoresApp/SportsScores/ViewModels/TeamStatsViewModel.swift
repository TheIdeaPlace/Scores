//
//  TeamStatsViewModel.swift
//  SportsScores
//
//  Fetches per-team player leaders and league team rankings for the Stats tab
//  in the Team Hub. Loads both in parallel on first access.
//

import Foundation

@MainActor
class TeamStatsViewModel: ObservableObject {
    @Published var playerCategories: [LeagueLeaderCategory] = []
    @Published var teamRankings: [TeamStatRanking] = []
    @Published var isLoadingPlayers = false
    @Published var isLoadingTeamRankings = false
    @Published var playerError: String?
    @Published var teamError: String?

    private var hasLoaded = false
    private let apiService = ESPNAPIService.shared

    func load(teamId: String, teamAbbreviation: String, sport: Sport) async {
        guard !hasLoaded else { return }
        hasLoaded = true
        isLoadingPlayers = true
        isLoadingTeamRankings = true
        playerError = nil
        teamError = nil

        async let playerTask = apiService.fetchLeagueLeadersForTeam(teamId: teamId, teamAbbreviation: teamAbbreviation, sport: sport)
        async let rankingsTask = apiService.fetchTeamStatRankings(teamId: teamId, sport: sport)

        do {
            playerCategories = try await playerTask
        } catch {
            playerError = "Failed to load player stats."
            hasLoaded = false   // so Retry can ask again
        }
        isLoadingPlayers = false

        do {
            teamRankings = try await rankingsTask
        } catch {
            teamError = "Failed to load team stats."
            hasLoaded = false
        }
        isLoadingTeamRankings = false
    }
}
