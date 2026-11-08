//
//  StatGlossary.swift
//  SportsScores
//
//  ESPN's definition of a statistic, from the glossary that comes with
//  statistics/byteam: each category's `descriptions`, parallel to its `names`.
//
//  The same name can mean different things in two categories. MLB has
//  strikeouts, hits, home runs and walks as a batter's and as a pitcher's, and
//  the NFL has interceptions thrown (passing) and made (defensiveInterceptions),
//  and punt returns made (returning) and allowed (punting). So the glossary is
//  keyed by category and name, never the name alone: a lookup by name gave the
//  pitchers' strikeout leaders the batters' definition (#193).
//
//  A team statistic's key is `section.stat`, or `opponent.section.stat` for what
//  a team's opponents did against it, which takes the same definition. A player
//  leader category from /leaders has a key of its own (`pointsPerGame`,
//  `strikeouts`), and `leaderStats` says which category and name it is. A leader
//  that isn't listed, or whose stat byteam has no definition for, has none: a
//  definition from another category could be the wrong one, as the NFL's sack
//  leaders would get the sacks a passer took.
//
//  The Windows twin is stat_glossary.py. tests/fixtures/stat_glossary_grid.json
//  holds both to the same table and the same answers on real byteam payloads.
//

import Foundation

enum StatGlossary {
    /// Where a stat's definition is in the glossary.
    struct Stat: Equatable {
        let category: String
        let name: String

        init(_ category: String, _ name: String) {
            self.category = category
            self.name = name
        }
    }

    private static let opponent = "opponent"

    /// Sport (the first part of a league's path) → leader key → its stat. From
    /// tools/stat_categories.py, which matched each leader to the stat in a leading
    /// player's own statistics (docs/stat-categories.csv).
    static let leaderStats: [String: [String: Stat]] = [
        "baseball": [
            "avg": Stat("batting", "avg"),
            "hits": Stat("batting", "hits"),
            "homeRuns": Stat("batting", "homeRuns"),
            "MLBRating": Stat("batting", "MLBRating"),
            "onBasePct": Stat("batting", "onBasePct"),
            "OPS": Stat("batting", "OPS"),
            "runs": Stat("batting", "runs"),
            "RBIs": Stat("batting", "RBIs"),
            "slugAvg": Stat("batting", "slugAvg"),
            "stolenBases": Stat("batting", "stolenBases"),
            "WARBR": Stat("batting", "WARBR"),
            "avgGameScore": Stat("pitching", "avgGameScore"),
            "ERA": Stat("pitching", "ERA"),
            "holds": Stat("pitching", "holds"),
            "opponentAvg": Stat("pitching", "opponentAvg"),
            "qualityStarts": Stat("pitching", "qualityStarts"),
            "saves": Stat("pitching", "saves"),
            "strikeouts": Stat("pitching", "strikeouts"),
            "WHIP": Stat("pitching", "WHIP"),
            "wins": Stat("pitching", "wins"),
        ],
        "football": [
            "passesDefended": Stat("defensive", "passesDefended"),
            "sacks": Stat("defensive", "sacks"),
            "totalTackles": Stat("defensive", "totalTackles"),
            "interceptions": Stat("defensiveInterceptions", "interceptions"),
            "interceptionYards": Stat("defensiveInterceptions", "interceptionYards"),
            "kickoffYards": Stat("kicking", "kickoffYards"),
            "passingTouchdowns": Stat("passing", "passingTouchdowns"),
            "passingYards": Stat("passing", "passingYards"),
            "quarterbackRating": Stat("passing", "QBRating"),
            "totalTouchdowns": Stat("passing", "totalTouchdowns"),
            "puntYards": Stat("punting", "puntYards"),
            "receivingTouchdowns": Stat("receiving", "receivingTouchdowns"),
            "receivingYards": Stat("receiving", "receivingYards"),
            "receptions": Stat("receiving", "receptions"),
            "rushingTouchdowns": Stat("rushing", "rushingTouchdowns"),
            "rushingYards": Stat("rushing", "rushingYards"),
            "totalPoints": Stat("scoring", "totalPoints"),
        ],
        "basketball": [
            "blocksPerGame": Stat("defensive", "avgBlocks"),
            "stealsPerGame": Stat("defensive", "avgSteals"),
            "defensiveReboundsPerGame": Stat("defensive", "avgDefensiveRebounds"),
            "doubleDouble": Stat("general", "doubleDouble"),
            "tripleDouble": Stat("general", "tripleDouble"),
            "minutesPerGame": Stat("general", "avgMinutes"),
            "foulsPerGame": Stat("general", "avgFouls"),
            "PER": Stat("general", "PER"),
            "NBARating": Stat("general", "NBARating"),
            "reboundsPerGame": Stat("general", "avgRebounds"),
            "3PointPct": Stat("offensive", "threePointFieldGoalPct"),
            "assistsPerGame": Stat("offensive", "avgAssists"),
            "3PointsMadePerGame": Stat("offensive", "avgThreePointFieldGoalsMade"),
            "3PointMadePerGame": Stat("offensive", "avgThreePointFieldGoalsMade"),
            "fieldGoalPercentage": Stat("offensive", "fieldGoalPct"),
            "FreeThrowPct": Stat("offensive", "freeThrowPct"),
            "offensiveReboundsPerGame": Stat("offensive", "avgOffensiveRebounds"),
            "points": Stat("offensive", "points"),
            "pointsPerGame": Stat("offensive", "avgPoints"),
            "avgTurnovers": Stat("offensive", "avgTurnovers"),
            "turnoversPerGame": Stat("offensive", "avgTurnovers"),
        ],
        "hockey": [
            "avgGoalsAgainst": Stat("defensive", "avgGoalsAgainst"),
            "savePct": Stat("defensive", "savePct"),
            "shutouts": Stat("defensive", "shutouts"),
            "plusMinus": Stat("general", "plusMinus"),
            "wins": Stat("general", "wins"),
            "assists": Stat("offensive", "assists"),
            "goals": Stat("offensive", "goals"),
            "points": Stat("offensive", "points"),
            "penaltyMinutes": Stat("penalties", "penaltyMinutes"),
        ],
    ]

    /// ESPN writes a category's name in two cases (byteam's `defensiveinterceptions`
    /// is the core API's `defensiveInterceptions`), so the category part is
    /// lowercased. A stat name keeps its case.
    static func key(_ category: String, _ name: String) -> String {
        "\(category.lowercased()).\(name)"
    }

    /// Glossary key → definition. A category comes once per split and only the
    /// first copy has names. The first definition that says something wins.
    static func glossary(from categories: [TeamStatsByTeamResponse.CategoryMetadata]) -> [String: String] {
        var found: [String: String] = [:]
        for category in categories {
            guard let section = category.name, let names = category.names,
                  let descriptions = category.descriptions else { continue }
            for (name, text) in zip(names, descriptions) where !name.isEmpty {
                let words = text.split(whereSeparator: \.isWhitespace).joined(separator: " ")
                let entry = key(section, name)
                if !words.isEmpty, found[entry] == nil { found[entry] = words }
            }
        }
        return found
    }

    /// Where a stat the app shows is in the glossary, or nil if there's no telling.
    /// `team` says whether `key` is a team statistic or a player leader category.
    static func stat(sport: String, key: String, team: Bool) -> Stat? {
        guard team else { return leaderStats[sport]?[key] }
        var parts = key.components(separatedBy: ".")
        if parts.first == opponent { parts.removeFirst() }
        guard parts.count == 2, !parts[0].isEmpty, !parts[1].isEmpty else { return nil }
        return Stat(parts[0], parts[1])
    }

    /// ESPN's definition of a stat, or nil where ESPN gives none.
    static func definition(in glossary: [String: String], sport: String, key: String, team: Bool) -> String? {
        stat(sport: sport, key: key, team: team).flatMap { glossary[Self.key($0.category, $0.name)] }
    }
}
