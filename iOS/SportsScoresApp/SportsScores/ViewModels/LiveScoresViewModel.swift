//
//  LiveScoresViewModel.swift
//  SportsScores
//
//  Created on 1/4/26.
//

import Foundation

@MainActor
class LiveScoresViewModel: ObservableObject {
    @Published var liveGames: [SportGames] = []
    @Published var completedGames: [SportGames] = []
    @Published var upcomingGames: [SportGames] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    /// Says which leagues didn't answer, under what the others did.
    @Published var failureNote: String?

    private let apiService = ESPNAPIService.shared
    
    struct SportGames: Identifiable {
        let id = UUID()
        let sport: Sport
        let games: [Game]
    }
    
    /// A refresh on the timer leaves an error showing until it has something else to show, since
    /// swapping in the spinner takes VoiceOver off Retry. Retry itself shows progress.
    func fetchAllGames(retrying: Bool = false) async {
        if retrying { errorMessage = nil }
        isLoading = errorMessage == nil && liveGames.isEmpty && completedGames.isEmpty && upcomingGames.isEmpty

        // Today's date boundaries for filtering
        let now = Date()
        // Last night's scoreboard until 5 AM, so a game still running stays put.
        let startOfToday = ScoreboardDay.today(now: now)

        // Fetch all sports in parallel. We always pass the scoreboard day so that ESPN
        // returns today's scoreboard. Without a date param ESPN sometimes returns the
        // previous day's games (observed consistently for MLB spring training), which
        // then get filtered out by the day check below.
        // Soccer leagues are included here so they appear in the all-sports view.
        let allLeagues = Sport.allCases + Sport.soccerLeagues
        // nil is a league that failed, which isn't the same as one with no games.
        let results: [(Sport, [Game]?)] = await withTaskGroup(of: (Sport, [Game]?).self) { group in
            for sport in allLeagues {
                group.addTask {
                    do {
                        let games = try await self.apiService.fetchGames(for: sport, date: startOfToday)
                        return (sport, games)
                    } catch {
                        print("Failed to fetch games for \(sport.rawValue): \(error)")
                        return (sport, nil)
                    }
                }
            }
            var collected: [(Sport, [Game]?)] = []
            for await pair in group { collected.append(pair) }
            // Restore consistent ordering (allLeagues order)
            return collected.sorted {
                (allLeagues.firstIndex(of: $0.0) ?? allLeagues.count) <
                (allLeagues.firstIndex(of: $1.0) ?? allLeagues.count)
            }
        }

        // Leaving the screen cancels this, and says nothing about ESPN.
        guard !Task.isCancelled else {
            isLoading = false
            return
        }

        var live: [SportGames] = []
        var completed: [SportGames] = []
        var upcoming: [SportGames] = []
        var failed: [String] = []

        for (sport, fetched) in results {
            if fetched == nil { failed.append(sport.displayName) }
            // A league that failed keeps what it last showed.
            let games = fetched ?? (liveGames + completedGames + upcomingGames)
                .filter { $0.sport == sport }
                .flatMap { $0.games }
            // Restrict every sport to today — no special football exemption.
            let relevantGames = games.filter { ScoreboardDay.belongsOnToday($0, now: now) }

            // Suspended games are halted, not over — they belong with the live ones.
            let liveGamesForSport      = relevantGames.filter { $0.status.isLive || $0.status.isSuspended }
            let completedGamesForSport = relevantGames.filter { $0.status.isCompleted && !$0.status.isSuspended }
            let upcomingGamesForSport  = relevantGames.filter { !$0.status.isLive && !$0.status.isCompleted
                                                                && !$0.status.isSuspended }

            if !liveGamesForSport.isEmpty     { live.append(SportGames(sport: sport, games: liveGamesForSport)) }
            if !completedGamesForSport.isEmpty { completed.append(SportGames(sport: sport, games: completedGamesForSport)) }
            if !upcomingGamesForSport.isEmpty  { upcoming.append(SportGames(sport: sport, games: upcomingGamesForSport)) }
        }

        liveGames = live
        completedGames = completed
        upcomingGames = upcoming

        let showing = !(live.isEmpty && completed.isEmpty && upcoming.isEmpty)
        failureNote = showing && !failed.isEmpty ? APIError.liveScoresFailure(failed, showing: true) : nil
        errorMessage = showing ? nil
            : (failed.isEmpty ? "No games scheduled today" : APIError.liveScoresFailure(failed, showing: false))

        isLoading = false
    }
    
    func refresh() async {
        await fetchAllGames()
    }
}
