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
    /// Says which leagues didn't answer, under what the others did.
    @Published var failureNote: String?

    private let apiService = ESPNAPIService.shared

    struct LeagueGames: Identifiable {
        let id = UUID()
        let sport: Sport   // will always be a soccer league case
        let games: [Game]
    }

    /// A refresh on the timer leaves an error showing until it has something else to show, since
    /// swapping in the spinner takes VoiceOver off Retry. Retry itself shows progress.
    func fetchAllGames(retrying: Bool = false) async {
        if retrying { errorMessage = nil }
        isLoading = errorMessage == nil && liveGames.isEmpty && completedGames.isEmpty && upcomingGames.isEmpty

        let now = Date()

        // Fetch all soccer leagues in parallel.
        // DateFormatter is NOT thread-safe — each task creates its own inside Game.init.
        // nil is a league that failed, which isn't the same as one with no games.
        let results: [(Sport, [Game]?)] = await withTaskGroup(of: (Sport, [Game]?).self) { group in
            for league in Sport.soccerLeagues {
                group.addTask {
                    do {
                        let games = try await self.apiService.fetchGames(for: league)
                        return (league, games)
                    } catch {
                        print("Failed to fetch \(league.displayName): \(error)")
                        return (league, nil)
                    }
                }
            }
            var collected: [(Sport, [Game]?)] = []
            for await pair in group { collected.append(pair) }
            return collected.sorted {
                (Sport.soccerLeagues.firstIndex(of: $0.0) ?? Int.max) <
                (Sport.soccerLeagues.firstIndex(of: $1.0) ?? Int.max)
            }
        }

        // Leaving the screen cancels this, and says nothing about ESPN.
        guard !Task.isCancelled else {
            isLoading = false
            return
        }

        var live: [LeagueGames] = []
        var completed: [LeagueGames] = []
        var upcoming: [LeagueGames] = []
        var failed: [String] = []

        for (league, fetched) in results {
            if fetched == nil { failed.append(league.displayName) }
            // A league that failed keeps what it last showed.
            let games = fetched ?? (liveGames + completedGames + upcomingGames)
                .filter { $0.sport == league }
                .flatMap { $0.games }
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

        let showing = !(live.isEmpty && completed.isEmpty && upcoming.isEmpty)
        failureNote = showing && !failed.isEmpty ? APIError.liveScoresFailure(failed, showing: true) : nil
        errorMessage = showing ? nil
            : (failed.isEmpty ? "No soccer games scheduled today" : APIError.liveScoresFailure(failed, showing: false))

        isLoading = false
    }

    func refresh() async {
        await fetchAllGames()
    }
}
