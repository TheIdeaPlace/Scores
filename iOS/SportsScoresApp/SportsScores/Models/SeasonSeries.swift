//
//  SeasonSeries.swift
//  SportsScores
//
//  How the two teams in an MLB game have done against each other, from the
//  summary's `seasonseries`. season_series.py is the Windows twin; both are held
//  to tests/fixtures/season_series_grid.json. Change both together.
//
//  ESPN's own `summary` sentence can be wrong (in a World Series game it said
//  "TB leads series 3-2" for five games Milwaukee won four of), so the record is
//  counted from the finished games' winner flags. In a postseason game the
//  `current` series is the playoff's games again and is left out.
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

    static func recordText(_ entry: Entry, names: [String: String]) -> String {
        let total = games(entry)
        let finished = entry.events.filter(\.isFinished)
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
        let decided = finished.count >= total || leadWins * 2 > total
        if leadWins == trailWins {
            return "\(decided ? "Split" : "Tied") \(leadWins)-\(trailWins)"
        }
        let team = teams[leadID]
        let name = nonBlank(names[leadID]) ?? nonBlank(team?.displayName) ?? nonBlank(team?.abbreviation) ?? "Unknown"
        return "\(name) \(decided ? "won" : "lead") \(leadWins)-\(trailWins)"
    }

    static func shown(_ entries: [Entry], names: [String: String]) -> [Shown] {
        ordered(entries).map { Shown(label: label($0), text: recordText($0, names: names), games: games($0)) }
    }

    /// "Regular Season Series: Mets won 7-6", the first series shown; empty with none.
    static func summaryLine(_ entries: [Entry], names: [String: String]) -> String {
        guard let first = shown(entries, names: names).first else { return "" }
        return "\(first.label): \(first.text)"
    }
}
