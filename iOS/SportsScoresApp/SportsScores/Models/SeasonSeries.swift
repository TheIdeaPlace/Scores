//
//  SeasonSeries.swift
//  SportsScores
//
//  How the two teams in an MLB game have done against each other, from the
//  summary's `seasonseries`. season_series.py is the Windows twin; both are held
//  to tests/fixtures/season_series_grid.json. Change both together.
//
//  The record is counted from the finished games' winner flags, as of the game
//  being looked at: `events` runs to the end of the series, but game 4 of a World
//  Series says "Brewers lead 3-1", as ESPN does, not how it ended. ESPN's own
//  `summary` sentence isn't read: in that game its `current` series said "TB leads
//  series 3-2". In a postseason game `current` is the playoff's games again and is
//  left out. A playoff series is won at more than half its games; any other only
//  once every game is played.
//

import Foundation

enum SeasonSeries {
    struct Shown: Equatable {
        /// "World Series", "Regular Season Series".
        let label: String
        /// "Mets lead 7-5", "Mets won 7-6", "Tied 2-2", "Split 3-3", "No games played yet".
        let text: String
        let games: Int
    }

    typealias Entry = GameDetails.SeasonSeriesEntry

    private static func nonBlank(_ text: String?) -> String? {
        guard let trimmed = text?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty else { return nil }
        return trimmed
    }

    /// The series to show, in order, without one that repeats the games of one before it.
    static func ordered(_ entries: [Entry]) -> [Entry] {
        let ranked = entries.enumerated().sorted { a, b in
            a.element.displayOrder != b.element.displayOrder
                ? a.element.displayOrder < b.element.displayOrder
                : a.offset < b.offset
        }.map(\.element)
        var seen: [Set<String>] = []
        var shown: [Entry] = []
        for entry in ranked {
            let ids = Set(entry.events.compactMap { nonBlank($0.id) })
            if !ids.isEmpty && seen.contains(ids) { continue }
            seen.append(ids)
            shown.append(entry)
        }
        return shown
    }

    static func label(_ entry: Entry) -> String {
        if entry.type == "playoff", let round = nonBlank(entry.round) { return round }
        return nonBlank(entry.title) ?? "Series"
    }

    static func games(_ entry: Entry) -> Int {
        if let total = entry.totalCompetitions, total > 0 { return total }
        return entry.events.count
    }

    /// The record as of `thisGame` when it is one of the series' games; every game otherwise.
    static func recordText(_ entry: Entry, names: [String: String], thisGame: String) -> String {
        let total = games(entry)
        let ids = entry.events.map { nonBlank($0.id) ?? "" }
        var counted = entry.events
        if !thisGame.isEmpty, let index = ids.firstIndex(of: thisGame) {
            counted = Array(entry.events[...index])
        }
        let finished = counted.filter(\.isFinished)
        var wins: [String: Int] = [:]
        var order: [String] = []
        var teams: [String: Entry.SeriesEvent.Competitor.Team] = [:]
        for event in entry.events {
            for competitor in event.competitors {
                guard let team = competitor.team, let id = nonBlank(team.id) else { continue }
                if wins[id] == nil {
                    wins[id] = 0
                    order.append(id)
                    teams[id] = team
                }
            }
        }
        for event in finished {
            for competitor in event.competitors where competitor.winner == true {
                if let id = nonBlank(competitor.team?.id), let count = wins[id] { wins[id] = count + 1 }
            }
        }
        guard !finished.isEmpty, !wins.isEmpty else { return "No games played yet" }
        let ranked = order.enumerated().sorted { a, b in
            let (wa, wb) = (wins[a.element] ?? 0, wins[b.element] ?? 0)
            return wa != wb ? wa > wb : a.offset < b.offset
        }.map(\.element)
        let leadID = ranked[0]
        let leadWins = wins[leadID] ?? 0
        let trailWins = ranked.count > 1 ? (wins[ranked[1]] ?? 0) : 0
        let decided = finished.count >= total || (entry.type == "playoff" && leadWins * 2 > total)
        if leadWins == trailWins {
            return "\(decided ? "Split" : "Tied") \(leadWins)-\(trailWins)"
        }
        let team = teams[leadID]
        let name = nonBlank(names[leadID]) ?? nonBlank(team?.displayName) ?? nonBlank(team?.abbreviation) ?? "Unknown"
        return "\(name) \(decided ? "won" : "lead") \(leadWins)-\(trailWins)"
    }

    static func shown(_ entries: [Entry], names: [String: String], thisGame: String) -> [Shown] {
        ordered(entries).map {
            Shown(label: label($0), text: recordText($0, names: names, thisGame: thisGame), games: games($0))
        }
    }

    /// "Regular Season Series: Mets lead 7-5", the first series shown; empty with none.
    static func summaryLine(_ entries: [Entry], names: [String: String], thisGame: String) -> String {
        guard let first = shown(entries, names: names, thisGame: thisGame).first else { return "" }
        return "\(first.label): \(first.text)"
    }
}
