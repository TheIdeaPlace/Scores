//
//  BoxScoreTables.swift
//  SportsScores
//
//  Turns ESPN's box score into what BoxScoreView shows: which groups get a tab,
//  what they're called, which columns and rows Essential Stats keeps, and how a
//  row reads. Foundation only, so it can be run against real ESPN payloads off
//  the device. box_score.py does the same job on Windows.
//

import Foundation

typealias PlayerStatGroup = GameDetails.Boxscore.TeamPlayers.PlayerStatGroup
typealias TeamStatEntry = GameDetails.Boxscore.TeamStats.StatEntry

// MARK: - Player tables

extension PlayerStatGroup {
    /// The name the group is looked up by. Basketball's one group has none.
    var groupKey: String { (type ?? name ?? "players").lowercased() }

    /// A group gets a tab only when it has somebody to show. ESPN sends empty
    /// groups routinely: all of college hockey, and football's interceptions and
    /// returns whenever there weren't any.
    var hasContent: Bool { !athletes.isEmpty && !columnHeaders.isEmpty }

    /// "Players", "Defense", "Kick Returns".
    var groupTitle: String {
        guard let raw = type ?? name, !raw.isEmpty else { return "Players" }
        switch raw {
        case "defensive", "defenses": return "Defense"
        default: break
        }
        // kickReturns -> Kick Returns
        var title = ""
        for character in raw {
            if character.isUppercase && !title.isEmpty { title.append(" ") }
            title.append(character)
        }
        return title.capitalized
    }

    func table(essentialOnly: Bool, profile: BoxScoreProfile) -> BoxPlayerTable {
        let headers = columnHeaders
        // A group the profile doesn't know shows everything, as does one where
        // the profile matches nothing: better too many columns than none.
        var kept = Array(headers.indices)
        if essentialOnly, let essential = profile.essentialPlayerStats[groupKey] {
            let matched = kept.filter { essential.contains(headers[$0].lowercased()) }
            if !matched.isEmpty { kept = matched }
        }
        let keptValues: ([String]) -> [String] = { values in
            kept.map { $0 < values.count ? values[$0] : "" }
        }

        var rows = athletes.map { entry -> BoxPlayerTable.Row in
            let position = entry.athlete.position?.abbreviation ?? ""
            // No stats at all means the player sat out, whatever `didNotPlay` says.
            guard !entry.stats.isEmpty, entry.didNotPlay != true else {
                return .init(name: entry.athlete.displayName, position: position,
                             stats: [], kind: .didNotPlay)
            }
            return .init(name: entry.athlete.displayName, position: position,
                         stats: keptValues(entry.stats), kind: .player)
        }
        if let totals, totals.contains(where: { !$0.isEmpty }) {
            rows.append(.init(name: BoxPlayerTable.totalsName, position: "",
                              stats: keptValues(totals), kind: .totals))
        }
        return BoxPlayerTable(columns: kept.map { headers[$0] }, rows: rows)
    }
}

/// One player tab, ready to render in any of the three view modes.
struct BoxPlayerTable {
    static let totalsName = "Totals"
    static let didNotPlayText = "Did not play"

    let columns: [String]
    let rows: [Row]

    /// Football payloads carry no positions: don't offer a column of blanks.
    var showsPosition: Bool { rows.contains { !$0.position.isEmpty } }

    struct Row {
        enum Kind { case player, didNotPlay, totals }

        let name: String
        let position: String
        let stats: [String]
        let kind: Kind

        /// "LeBron James (F)", or just the name when there's no position.
        var title: String { position.isEmpty ? name : "\(name) (\(position))" }

        /// "PTS: 22, REB: 10". Blank cells, such as minutes on a Totals row, are
        /// left out rather than read as a label with nothing after it.
        func statsText(columns: [String]) -> String {
            guard kind != .didNotPlay else { return BoxPlayerTable.didNotPlayText }
            return zip(columns, stats)
                .filter { !$0.1.isEmpty }
                .map { "\($0): \($1)" }
                .joined(separator: ", ")
        }

        /// What VoiceOver reads for the row in Quick List.
        func spokenText(columns: [String]) -> String {
            let text = statsText(columns: columns)
            return text.isEmpty ? title : "\(title), \(text)"
        }
    }

    /// The header and rows for the accessible data table. A player who sat out
    /// says so in the first stat column, and every row has the same width so
    /// VoiceOver's column positions stay true.
    func accessibleGrid() -> (headers: [String], rows: [[String]]) {
        let lead = showsPosition ? ["Player", "Pos"] : ["Player"]
        let grid = rows.map { row -> [String] in
            let leadCells = showsPosition ? [row.name, row.position] : [row.name]
            if row.kind == .didNotPlay {
                return leadCells + [BoxPlayerTable.didNotPlayText]
                    + Array(repeating: "", count: max(columns.count - 1, 0))
            }
            return leadCells + row.stats
        }
        return (lead + columns, grid)
    }
}

// MARK: - Team stats

extension Array where Element == GameDetails.Boxscore.TeamStats {
    /// One entry per statistic across both teams, in first-seen order. Taken from
    /// every team because the first can be empty, and de-duplicated by name
    /// because ESPN repeats some rows (the NFL lists interceptions twice).
    var comparisonEntries: [TeamStatEntry] {
        var seen = Set<String>()
        return flatMap { $0.statistics }.filter { seen.insert($0.name).inserted }
    }

    /// True when ESPN sent no team statistics at all.
    var hasNoStatistics: Bool { allSatisfy { $0.statistics.isEmpty } }

    /// MLB wraps its statistics in categories; every other sport has flat rows.
    var hasNestedStatistics: Bool {
        contains { $0.statistics.contains { $0.isNested } }
    }
}

extension BoxScoreProfile {
    /// The team rows Essential Stats keeps. Falls back to every row when the
    /// profile matches none of them, which is what season averages look like
    /// before a game and every sport without a profile.
    func essentialTeamRows(of entries: [TeamStatEntry]) -> [TeamStatEntry] {
        let matched = entries.filter { essentialTeamStats.contains($0.name) }
        return matched.isEmpty ? entries : matched
    }
}

// MARK: - Box Score Profiles

struct BoxScoreProfile {
    /// Essential team rows, by ESPN's `boxscore.teams[].statistics[].name`.
    let essentialTeamStats: Set<String>

    /// Essential player columns by group, lowercased. The group is `groupKey`,
    /// and the columns are the headers as they appear in `columnHeaders`.
    let essentialPlayerStats: [String: Set<String>]
}

enum BoxScoreProfiles {

    // MARK: - MLB

    static let mlb = BoxScoreProfile(
        essentialTeamStats: [
            // Batting — names match ESPN's boxscore.teams[].statistics[].stats[].name
            "hits", "runs", "runnersLeftOnBase", "homeRuns", "RBIs", "walks", "strikeouts",
            // Pitching
            "earnedRuns", "strikeouts", "walks", "homeRuns"
        ],
        essentialPlayerStats: [
            "batting":  ["h-ab", "ab", "r", "h", "rbi", "bb", "k", "avg"],
            "pitching": ["ip", "h", "r", "er", "bb", "k", "era"]
        ]
    )

    // MARK: - NFL / NCAAF

    static let football = BoxScoreProfile(
        essentialTeamStats: [
            "firstDowns", "thirdDownEff", "totalYards", "netPassingYards", "rushingYards",
            "turnovers", "totalPenaltiesYards", "possessionTime"
        ],
        essentialPlayerStats: [
            "passing": ["c/att", "yds", "td", "int"],
            "rushing": ["car", "yds", "avg", "td"],
            "receiving": ["rec", "yds", "avg", "td"],
            "fumbles": ["fum", "lost"],
            "defensive": ["tot", "sacks", "tfl", "pd"],
            "interceptions": ["int", "yds", "td"],
            "kickreturns": ["no", "yds", "avg", "td"],
            "puntreturns": ["no", "yds", "avg", "td"],
            "kicking": ["fg", "xp", "pts"],
            "punting": ["no", "yds", "avg"]
        ]
    )

    // MARK: - NBA / NCAAM / NCAAWB / WNBA

    static let basketball = BoxScoreProfile(
        essentialTeamStats: [
            "fieldGoalsMade-fieldGoalsAttempted", "fieldGoalPct",
            "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "threePointFieldGoalPct",
            "freeThrowsMade-freeThrowsAttempted", "freeThrowPct",
            "totalRebounds", "assists", "turnovers", "steals", "blocks"
        ],
        essentialPlayerStats: [
            "players": ["min", "pts", "fg", "3pt", "ft", "reb", "ast", "to", "stl", "blk"]
        ]
    )

    // MARK: - NHL / NCAAH / NCAAWH

    private static let hockeySkater: Set<String> = ["g", "a", "+/-", "s", "ht", "bs"]

    static let hockey = BoxScoreProfile(
        essentialTeamStats: [
            "shotsTotal", "hits", "blockedShots", "giveaways", "takeaways", "faceoffPercent",
            "powerPlayGoals", "powerPlayOpportunities", "powerPlayPct"
        ],
        essentialPlayerStats: [
            "forwards": hockeySkater,
            "defenses": hockeySkater,
            "skaters": hockeySkater,
            "goalies": ["ga", "sa", "sv", "sv%"]
        ]
    )

    // MARK: - Profile Lookup by Sport

    static func profile(for sport: Sport) -> BoxScoreProfile {
        switch sport {
        case .mlb:
            return mlb
        case .nfl, .ncaaf:
            return football
        case .nba, .ncaam, .ncaawb, .wnba:
            return basketball
        case .nhl, .ncaah, .ncaawh:
            return hockey
        default:
            // Soccer and any future sports — no sport-specific profile; show raw stats as-is.
            return BoxScoreProfile(
                essentialTeamStats: [],
                essentialPlayerStats: [:]
            )
        }
    }
}
