//
//  DivisionStandings.swift
//  SportsScores
//
//  A pro league's division standings from ESPN's `/standings?level=3`. On Windows:
//  division_standings.py. tests/fixtures/division_standings_grid.json holds both.
//
//  Without `level=3`, ESPN answers MLB, the NFL, the NBA and the NHL by conference (or league),
//  and its `gamesBehind` there counts from the conference leader. The app used to split that
//  answer into divisions from a table of team abbreviations and keep the conference figure, so a
//  division leader read as games back (Denver 0.5 back while leading the AFC West), and teams
//  with the same record came out in whatever order the sort left them.
//
//  With `level=3`, every division is its own group under its conference and `gamesBehind`
//  counts from the division leader. MLB also sends `divisionGamesBehind`, the same figure, which
//  is read first. The teams within a group are not in order (the NBA's come worst first), so
//  they are put in order by ESPN's `playoffSeed`, which carries the league's tiebreakers.
//
//  Nothing here knows which team is in which division: the groups come from the answer. If ESPN
//  ever answers with conferences only, those are the groups, with their own games back.
//

import Foundation

enum DivisionStandings {
    typealias Entry = APIStandingsGroup.APIStandings.APIStandingsEntry

    /// The leagues whose standings are asked for by division, and the query that does it.
    static let leagues: Set<Sport> = [.mlb, .nfl, .nba, .nhl]
    static let divisionsQuery = "level=3"

    /// ESPN's leader, and what a missing figure reads as.
    static let noGamesBack = "-"

    struct Group {
        /// The division's name as both apps show it: "AL East", "AFC North", "Atlantic".
        let name: String
        /// The conference it sits under, or its own name when it is a conference.
        let conference: String
        /// Its teams in standing order.
        let entries: [Entry]
    }

    private static let leaguePrefixes = [("American League ", "AL "), ("National League ", "NL ")]
    private static let divisionSuffix = " Division"

    /// "American League East" is "AL East", "Atlantic Division" is "Atlantic", and "AFC East"
    /// stays as it is.
    static func label(_ raw: String) -> String {
        var name = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        for (long, short) in leaguePrefixes where name.hasPrefix(long) {
            name = short + name.dropFirst(long.count)
            break
        }
        if name.hasSuffix(divisionSuffix), name.count > divisionSuffix.count {
            name = String(name.dropLast(divisionSuffix.count))
        }
        return name
    }

    /// ESPN's games back for a team, as it writes it ("-", "2.5", "6"): the division figure
    /// when there is one, otherwise the group's own.
    static func gamesBack(_ entry: Entry) -> String {
        for name in ["divisionGamesBehind", "gamesBehind"] {
            guard let stat = entry.stats.first(where: { $0.name == name }) else { continue }
            let text = stat.displayValue.trimmingCharacters(in: .whitespacesAndNewlines)
            if !text.isEmpty { return text }
        }
        return noGamesBack
    }

    /// "2.5" as 2.5; ESPN's "-" (the leader) and anything unreadable as 0.
    private static func number(_ text: String) -> Double {
        Double(text) ?? 0
    }

    private static func seed(_ entry: Entry) -> Int? {
        guard let stat = entry.stats.first(where: { $0.name == "playoffSeed" }) else { return nil }
        let seed = Int(stat.value)
        return seed > 0 ? seed : nil
    }

    /// A group's teams in standing order. The answer's own order won't do: the NBA's divisions
    /// come worst first and MLB's in no order at all. ESPN's playoff seed has the league's
    /// tiebreakers in it, and within one group it ranks the teams as the group does, so it
    /// decides; a team without one goes after those with one, by games back. Ties keep the
    /// answer's order.
    static func standingOrder(_ entries: [Entry]) -> [Entry] {
        entries.enumerated().sorted { a, b in
            let seedA = seed(a.element), seedB = seed(b.element)
            if (seedA == nil) != (seedB == nil) { return seedA != nil }
            if let seedA, let seedB, seedA != seedB { return seedA < seedB }
            let backA = number(gamesBack(a.element)), backB = number(gamesBack(b.element))
            if backA != backB { return backA < backB }
            return a.offset < b.offset
        }
        .map(\.element)
    }

    /// Every group in the answer that has teams, in ESPN's order of groups, each group's teams
    /// in standing order. A team appears once: if ESPN ever repeats one, its first group keeps it.
    static func groups(_ root: APIStandingsGroup) -> [Group] {
        var seen = Set<String>()
        return walk(root, conference: "", depth: 0).compactMap { group in
            let kept = group.entries.filter { entry in
                let id = entry.team.id
                if !id.isEmpty, seen.contains(id) { return false }
                seen.insert(id)
                return true
            }
            return kept.isEmpty ? nil
                : Group(name: group.name, conference: group.conference, entries: standingOrder(kept))
        }
    }

    private static func walk(_ node: APIStandingsGroup, conference: String, depth: Int) -> [Group] {
        var groups: [Group] = []
        if !node.standings.entries.isEmpty {
            groups.append(Group(name: label(node.name), conference: conference,
                                entries: node.standings.entries))
        }
        // The root is the league; its children are the conferences, and everything below a
        // conference is in it.
        for child in node.children ?? [] {
            groups += walk(child, conference: depth == 0 ? child.name : conference, depth: depth + 1)
        }
        return groups
    }

    /// Team id to the name of the group it is in.
    static func teamDivisions(_ root: APIStandingsGroup) -> [String: String] {
        var divisions: [String: String] = [:]
        for group in groups(root) {
            for entry in group.entries where !entry.team.id.isEmpty {
                divisions[entry.team.id] = group.name
            }
        }
        return divisions
    }

    /// Every team under a conference (an MLB league), whatever level its divisions are at.
    static func conferenceEntries(_ root: APIStandingsGroup, conference: String) -> [Entry] {
        groups(root).filter { $0.conference == conference }.flatMap(\.entries)
    }
}
