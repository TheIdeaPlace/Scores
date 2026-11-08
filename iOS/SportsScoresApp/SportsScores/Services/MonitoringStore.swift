//
//  MonitoringStore.swift
//  SportsScores
//
//  The games in Live Scores' Monitoring section (#185), as on Windows (#186).
//

import Foundation

/// A game and the sport it's listed under.
struct GameInSport: Identifiable {
    let game: Game
    let sport: Sport
    var id: String { game.id }
}

/// The games someone is monitoring, in the order added. For this run of the app only: kept
/// in memory, so leaving Live Scores and coming back keeps them, and quitting clears them.
/// Nothing here speaks on its own. There's no speech of score changes; the only thing said is
/// each action's own confirmation, which the actions here return for the view to announce.
@MainActor
final class MonitoringStore: ObservableObject {
    /// The words, the same as Windows says them.
    enum Said {
        static let added = "Added to monitoring"
        static let removed = "Removed from monitoring"
        static let addedFromSportPage = "Added to monitoring, at the top of Live Scores"
        static let onlyToday = "Only today's games can be monitored"
        static func removedFromSection(_ gameName: String) -> String {
            "\(gameName) removed from monitoring"
        }
    }

    /// The custom action's name, and the context menu item's.
    enum ActionName {
        static let monitor = "Monitor"
        static let stop = "Stop Monitoring"
    }

    /// ESPN game ids, in the order added.
    @Published private(set) var gameIDs: [String] = []

    func isMonitored(_ gameID: String) -> Bool {
        gameIDs.contains(gameID)
    }

    /// The action's name for a game's own row: Monitor, or Stop Monitoring once it is.
    func actionName(for gameID: String) -> String {
        isMonitored(gameID) ? ActionName.stop : ActionName.monitor
    }

    /// The action on a game's own row in Live Scores: adds it, or takes it off. Every game
    /// there is on today's scoreboard. Returns what to say.
    func toggleFromLiveScores(_ game: Game) -> String {
        if isMonitored(game.id) {
            remove(game.id)
            return Said.removed
        }
        gameIDs.append(game.id)
        return Said.added
    }

    /// The action on a sport's own scores page, for today's games only, since Live Scores,
    /// the only place a monitored game shows, has only today's. Returns what to say.
    func toggleFromSportPage(_ game: Game, now: Date = Date(),
                             localTimeZone: TimeZone = .current) -> String {
        if isMonitored(game.id) {
            remove(game.id)
            return Said.removed
        }
        guard ScoreboardDay.isOnTodaysScoreboard(game.date, timeValid: game.timeValid, now: now,
                                                 localTimeZone: localTimeZone) else {
            return Said.onlyToday
        }
        gameIDs.append(game.id)
        return Said.addedFromSportPage
    }

    /// Stop Monitoring on a Monitoring row. `shown` is the Monitoring section's game ids as
    /// listed. Returns what to say, which names the game since focus moves to another row,
    /// and the id of the Monitoring row to move to: the next one, or nil for the section's
    /// header when there's none after it.
    func stopFromMonitoringRow(_ game: Game, shown: [String]) -> (said: String, next: String?) {
        let next = MonitoringStore.rowAfter(game.id, in: shown)
        remove(game.id)
        let name = game.name.trimmingCharacters(in: .whitespacesAndNewlines)
        return (Said.removedFromSection(name.isEmpty ? "Game" : name), next)
    }

    /// The row after `gameID` in `shown`, or nil when it's the last or isn't there.
    static func rowAfter(_ gameID: String, in shown: [String]) -> String? {
        guard let at = shown.firstIndex(of: gameID), at + 1 < shown.count else { return nil }
        return shown[at + 1]
    }

    /// The monitored games found among `sections`, in the order added, each with the sport
    /// of the first section it's in. A monitored game that isn't on today's list isn't shown.
    func shown(in sections: [(sport: Sport, games: [Game])]) -> [GameInSport] {
        var found: [String: GameInSport] = [:]
        for section in sections {
            for game in section.games where found[game.id] == nil && isMonitored(game.id) {
                found[game.id] = GameInSport(game: game, sport: section.sport)
            }
        }
        return gameIDs.compactMap { found[$0] }
    }

    private func remove(_ gameID: String) {
        gameIDs.removeAll { $0 == gameID }
    }
}
