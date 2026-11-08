//
//  WinProbability.swift
//  SportsScores
//
//  An MLB game's win probability, from the summary's `winprobability`: one entry
//  per play, the home team's chance as a fraction. win_probability.py is the
//  Windows twin; both are held to tests/fixtures/win_probability_grid.json.
//  Change both together.
//

import Foundation

enum WinProbability {
    /// A fraction from 0 to 1 as a whole percent, rounded half up and kept in 0 to 100.
    static func percent(_ fraction: Double) -> Int {
        guard fraction.isFinite else { return 0 }
        return max(0, min(100, Int(floor(fraction * 100 + 0.5))))
    }

    /// Who is more likely to win, and how likely: "Mets 70%". "Even, 50%" when neither is.
    static func leaderText(homeFraction: Double, home: String, away: String) -> String {
        let homePercent = percent(homeFraction)
        let awayPercent = 100 - homePercent
        if homePercent > awayPercent { return "\(home) \(homePercent)%" }
        if awayPercent > homePercent { return "\(away) \(awayPercent)%" }
        return "Even, 50%"
    }
}

extension GameDetails {
    /// The short names to say for each side ("Mets"), from the summary's header;
    /// "Home" and "Away" when it doesn't say. win_probability.team_names on Windows.
    var sideNames: (home: String, away: String) {
        var home = "Home", away = "Away"
        for competitor in header?.competitions.first?.competitors ?? [] {
            guard let name = competitor.team.spokenName else { continue }
            if competitor.homeAway == "home" { home = name }
            if competitor.homeAway == "away" { away = name }
        }
        return (home, away)
    }

    /// Team id to its short name, for the season series. season_series.team_names on Windows.
    var teamNamesByID: [String: String] {
        var names: [String: String] = [:]
        for competitor in header?.competitions.first?.competitors ?? [] {
            if let id = competitor.team.id, !id.isEmpty, let name = competitor.team.spokenName {
                names[id] = name
            }
        }
        return names
    }
}

extension GameDetails.GameHeader.HeaderCompetition.HeaderCompetitor.HeaderTeam {
    /// The nickname, else the shortest name ESPN gives.
    var spokenName: String? {
        [name, shortDisplayName, abbreviation, displayName]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .first { !$0.isEmpty }
    }
}
