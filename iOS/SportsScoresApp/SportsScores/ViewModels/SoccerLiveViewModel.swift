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
    @Published var isRetrying = false

    private let apiService = ESPNAPIService.shared
    private var latestFetch = 0

    struct LeagueGames: Identifiable {
        let id = UUID()
        let sport: Sport   // will always be a soccer league case
        let games: [Game]
    }

    /// Leaves an error showing until it has something else to show, since swapping in the
    /// spinner would take VoiceOver off Retry. Only the newest of these publishes: Retry can
    /// overlap the timer, and a request that's failing can take a long time to say so.
    func fetchAllGames() async {
        latestFetch += 1
        let thisFetch = latestFetch
        isLoading = errorMessage == nil && liveGames.isEmpty && completedGames.isEmpty && upcomingGames.isEmpty

        let now = Date()
        // The scoreboard day, as on Windows and on Live Scores. With no date ESPN can answer with
        // a league's next match, days off.
        let startOfToday = ScoreboardDay.today(now: now)

        // Fetch all soccer leagues in parallel.
        // DateFormatter is NOT thread-safe — each task creates its own inside Game.init.
        // nil is a league that failed, which isn't the same as one with no games.
        let results: [(Sport, [Game]?)] = await withTaskGroup(of: (Sport, [Game]?).self) { group in
            for league in Sport.soccerLeagues {
                group.addTask {
                    do {
                        let games = try await self.apiService.fetchGames(for: league, date: startOfToday)
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

        guard thisFetch == latestFetch else { return }
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
            // A league that failed keeps what it last showed, until its day is over.
            let todaysGames = fetched?.filter { ScoreboardDay.belongsOnToday($0, now: now) }
                ?? (liveGames + completedGames + upcomingGames)
                    .filter { $0.sport == league }
                    .flatMap { $0.games }
                    .filter { ScoreboardDay.startsOnToday($0.date, now: now) }
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

    /// Retry stays on the screen while it runs, and what came of it is the error still here, or none.
    func retry() async -> String? {
        isRetrying = true
        await fetchAllGames()
        isRetrying = false
        return errorMessage
    }
}
