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
    @Published var isRetrying = false
    /// Golf tournaments in progress, one per tour, shown above the team games.
    @Published var activeTournaments: [GolfLive] = []

    private let apiService: ESPNAPIService
    private let clock: () -> Date
    private var latestFetch = 0
    /// The scoreboard day `activeTournaments` was last published for. A tour that fails
    /// keeps its tournament only on the same day, the way Windows does.
    private var golfDay: Date?

    /// The app uses `shared` and the real time. Tests pass a service whose session answers
    /// from fixtures, and a clock to cross from one scoreboard day to the next.
    init(apiService: ESPNAPIService = .shared, clock: @escaping () -> Date = Date.init) {
        self.apiService = apiService
        self.clock = clock
    }

    struct SportGames: Identifiable {
        let id = UUID()
        let sport: Sport
        let games: [Game]
    }

    struct GolfLive {
        let sport: Sport
        let tournament: GolfTournament
    }

    /// One tour's answer: its tournament in progress, or nil for none. `failed` is a tour
    /// that didn't answer, which isn't the same as one with nothing on.
    private struct GolfAnswer {
        let tour: Sport
        let tournament: GolfTournament?
        let failed: Bool
    }

    private func fetchGolf(_ enabled: Bool) async -> [GolfAnswer] {
        guard enabled else { return [] }
        return await withTaskGroup(of: GolfAnswer.self) { group in
            for tour in Sport.golfTours {
                group.addTask {
                    do {
                        let result = try await self.apiService.fetchGolfTournament(for: tour)
                        let live = result.tournament.flatMap { $0.isInProgress ? $0 : nil }
                        return GolfAnswer(tour: tour, tournament: live, failed: false)
                    } catch {
                        print("Failed to fetch golf for \(tour.rawValue): \(error)")
                        return GolfAnswer(tour: tour, tournament: nil, failed: true)
                    }
                }
            }
            var collected: [GolfAnswer] = []
            for await answer in group { collected.append(answer) }
            return collected
        }
    }

    /// Leaves an error showing until it has something else to show, since swapping in the
    /// spinner would take VoiceOver off Retry. Only the newest of these publishes: Retry can
    /// overlap the timer, and a request that's failing can take a long time to say so.
    /// `golf` is whether the golf tours are on Live Scores (Settings' golf hub).
    func fetchAllGames(golf: Bool) async {
        latestFetch += 1
        let thisFetch = latestFetch
        isLoading = errorMessage == nil && liveGames.isEmpty && completedGames.isEmpty && upcomingGames.isEmpty
            && activeTournaments.isEmpty

        // Today's date boundaries for filtering
        let now = clock()
        // Last night's scoreboard until 5 AM, so a game still running stays put.
        let startOfToday = ScoreboardDay.today(now: now)

        // Fetch all sports in parallel. We always pass the scoreboard day so that ESPN
        // returns today's scoreboard. Without a date param ESPN sometimes returns the
        // previous day's games (observed consistently for MLB spring training), which
        // then get filtered out by the day check below.
        // Soccer leagues are included here so they appear in the all-sports view.
        let allLeagues = Sport.liveScoresLeagues
        // Golf at the same time: its scoreboards list golfers, not games.
        async let golfAnswers = fetchGolf(golf)
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
        let golfResults = await golfAnswers

        guard thisFetch == latestFetch else { return }
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
            // Restrict every sport to today — no special football exemption. A league that
            // failed keeps what it last showed, until its day is over.
            let relevantGames = fetched?.filter { ScoreboardDay.belongsOnToday($0, now: now) }
                ?? (liveGames + completedGames + upcomingGames)
                    .filter { $0.sport == sport }
                    .flatMap { $0.games }
                    .filter { ScoreboardDay.startsOnToday($0.date, now: now) }

            // Suspended games are halted, not over — they belong with the live ones.
            let liveGamesForSport      = relevantGames.filter { $0.status.isLive || $0.status.isSuspended }
            let completedGamesForSport = relevantGames.filter { $0.status.isCompleted && !$0.status.isSuspended }
            let upcomingGamesForSport  = relevantGames.filter { !$0.status.isLive && !$0.status.isCompleted
                                                                && !$0.status.isSuspended }

            if !liveGamesForSport.isEmpty     { live.append(SportGames(sport: sport, games: liveGamesForSport)) }
            if !completedGamesForSport.isEmpty { completed.append(SportGames(sport: sport, games: completedGamesForSport)) }
            if !upcomingGamesForSport.isEmpty  { upcoming.append(SportGames(sport: sport, games: upcomingGamesForSport)) }
        }

        // A tour that failed keeps the tournament it last showed, while it's still the same
        // scoreboard day; one that answered with nothing on comes off.
        var tournaments: [GolfLive] = []
        let sameDay = golfDay == startOfToday
        for answer in golfResults {
            if answer.failed {
                failed.append(answer.tour.displayName)
                if sameDay, let kept = activeTournaments.first(where: { $0.sport == answer.tour }) {
                    tournaments.append(kept)
                }
            } else if let tournament = answer.tournament {
                tournaments.append(GolfLive(sport: answer.tour, tournament: tournament))
            }
        }

        liveGames = live
        completedGames = completed
        upcomingGames = upcoming
        activeTournaments = tournaments.sorted { $0.sport.rawValue < $1.sport.rawValue }
        golfDay = startOfToday

        let showing = !(live.isEmpty && completed.isEmpty && upcoming.isEmpty && tournaments.isEmpty)
        failureNote = showing && !failed.isEmpty ? APIError.liveScoresFailure(failed, showing: true) : nil
        errorMessage = showing ? nil
            : (failed.isEmpty ? "No games scheduled today" : APIError.liveScoresFailure(failed, showing: false))

        isLoading = false
    }
    
    func refresh(golf: Bool) async {
        await fetchAllGames(golf: golf)
    }

    /// Retry stays on the screen while it runs, and what came of it is the error still here, or none.
    func retry(golf: Bool) async -> String? {
        isRetrying = true
        await fetchAllGames(golf: golf)
        isRetrying = false
        return errorMessage
    }
}
