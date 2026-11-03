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
    
    private let apiService = ESPNAPIService.shared
    
    struct SportGames: Identifiable {
        let id = UUID()
        let sport: Sport
        let games: [Game]
    }
    
    func fetchAllGames() async {
        isLoading = liveGames.isEmpty && completedGames.isEmpty && upcomingGames.isEmpty
        errorMessage = nil

        // Today's date boundaries for filtering
        let calendar = Calendar.current
        let now = Date()
        // Last night's scoreboard until 5 AM, so a game still running stays put.
        let startOfToday = ScoreboardDay.today(now: now)
        let endOfToday = calendar.date(byAdding: .day, value: 1, to: startOfToday)!

        // Fetch all sports in parallel. We always pass today's local date so that ESPN
        // returns today's scoreboard. Without a date param ESPN sometimes returns the
        // previous day's games (observed consistently for MLB spring training), which
        // then get filtered out by the local-day boundary check below.
        // Soccer leagues are included here so they appear in the all-sports view.
        let allLeagues = Sport.allCases + Sport.soccerLeagues
        let results: [(Sport, [Game])] = await withTaskGroup(of: (Sport, [Game]).self) { group in
            for sport in allLeagues {
                group.addTask {
                    do {
                        let games = try await self.apiService.fetchGames(for: sport, date: startOfToday)
                        return (sport, games)
                    } catch {
                        print("Failed to fetch games for \(sport.rawValue): \(error)")
                        return (sport, [])
                    }
                }
            }
            var collected: [(Sport, [Game])] = []
            for await pair in group { collected.append(pair) }
            // Restore consistent ordering (allLeagues order)
            return collected.sorted {
                (allLeagues.firstIndex(of: $0.0) ?? allLeagues.count) <
                (allLeagues.firstIndex(of: $1.0) ?? allLeagues.count)
            }
        }

        var live: [SportGames] = []
        var completed: [SportGames] = []
        var upcoming: [SportGames] = []

        for (sport, games) in results {
            // Restrict every sport to today — no special football exemption. A game
            // being played is on today by definition, whatever day it started.
            let relevantGames = games.filter {
                $0.status.isLive || ($0.date >= startOfToday && $0.date < endOfToday)
            }

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

        if live.isEmpty && completed.isEmpty && upcoming.isEmpty {
            errorMessage = "No games scheduled today"
        }

        isLoading = false
    }
    
    func refresh() async {
        await fetchAllGames()
    }
}
