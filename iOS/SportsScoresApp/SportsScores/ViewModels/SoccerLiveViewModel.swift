//
//  SoccerLiveViewModel.swift
//  SportsScores
//

import Foundation

@MainActor
class SoccerLiveViewModel: ObservableObject {
    @Published var liveGames: [LeagueGames] = []
    @Published var completedGames: [LeagueGames] = []
    @Published var upcomingGames: [LeagueGames] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let apiService = ESPNAPIService.shared

    struct LeagueGames: Identifiable {
        let id = UUID()
        let sport: Sport   // will always be a soccer league case
        let games: [Game]
    }

    func fetchAllGames() async {
        isLoading = liveGames.isEmpty && completedGames.isEmpty && upcomingGames.isEmpty
        errorMessage = nil

        let now = Date()

        // Fetch all soccer leagues in parallel.
        // DateFormatter is NOT thread-safe — each task creates its own inside Game.init.
        let results: [(Sport, [Game])] = await withTaskGroup(of: (Sport, [Game]).self) { group in
            for league in Sport.soccerLeagues {
                group.addTask {
                    do {
                        let games = try await self.apiService.fetchGames(for: league)
                        return (league, games)
                    } catch {
                        print("Failed to fetch \(league.displayName): \(error)")
                        return (league, [])
                    }
                }
            }
            var collected: [(Sport, [Game])] = []
            for await pair in group { collected.append(pair) }
            return collected.sorted {
                (Sport.soccerLeagues.firstIndex(of: $0.0) ?? Int.max) <
                (Sport.soccerLeagues.firstIndex(of: $1.0) ?? Int.max)
            }
        }

        var live: [LeagueGames] = []
        var completed: [LeagueGames] = []
        var upcoming: [LeagueGames] = []

        for (league, games) in results {
            let todaysGames = games.filter { ScoreboardDay.belongsOnToday($0, now: now) }
            // Suspended matches are halted, not over — they belong with the live ones.
            let liveG      = todaysGames.filter { $0.status.isLive || $0.status.isSuspended }
            let completedG = todaysGames.filter { $0.status.isCompleted && !$0.status.isSuspended }
            let upcomingG  = todaysGames.filter { !$0.status.isLive && !$0.status.isCompleted
                                                  && !$0.status.isSuspended }

            if !liveG.isEmpty      { live.append(LeagueGames(sport: league, games: liveG)) }
            if !completedG.isEmpty { completed.append(LeagueGames(sport: league, games: completedG)) }
            if !upcomingG.isEmpty  { upcoming.append(LeagueGames(sport: league, games: upcomingG)) }
        }

        liveGames = live
        completedGames = completed
        upcomingGames = upcoming

        if live.isEmpty && completed.isEmpty && upcoming.isEmpty {
            errorMessage = "No soccer games scheduled today"
        }

        isLoading = false
    }

    func refresh() async {
        await fetchAllGames()
    }
}
