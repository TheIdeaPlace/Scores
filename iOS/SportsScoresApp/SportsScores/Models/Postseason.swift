//
//  Postseason.swift
//  SportsScores
//
//  College football's bowls and playoff as one list, from the request the Windows
//  app's Bowls & Playoffs makes: `scoreboard?seasontype=3` with the coverage `groups=`.
//  Pure, so the tests can run it on the real ESPN fixture.
//

import Foundation

/// Where a postseason game sits. Cases are in the order the list shows them: the
/// playoff in the order it's played, then every other bowl.
enum PostseasonRound: Int, CaseIterable, Comparable {
    case firstRound, quarterfinal, semifinal, championship, bowl

    var heading: String {
        switch self {
        case .firstRound:   return "Playoff First Round"
        case .quarterfinal: return "Playoff Quarterfinals"
        case .semifinal:    return "Playoff Semifinals"
        case .championship: return "National Championship"
        case .bowl:         return "Bowl Games"
        }
    }

    static func < (lhs: PostseasonRound, rhs: PostseasonRound) -> Bool { lhs.rawValue < rhs.rawValue }

    /// The round from ESPN's note headline, and its competition type when there's no headline.
    ///
    /// The headline comes first because the type alone files games wrong: the playoff's
    /// first-round games come as type 1, a plain game, and the Windows dialog, which looks
    /// for "first round" only on type 42, puts them among the bowls. A round is only the
    /// playoff's when the headline says "College Football Playoff", so another division's
    /// playoff stays with the bowls under its own name.
    static func from(headline: String?, typeID: Int?) -> PostseasonRound {
        let text = (headline ?? "").lowercased()
        if text.isEmpty {
            switch typeID {
            case 33: return .championship
            case 35: return .semifinal
            default: return .bowl
            }
        }
        let isPlayoff = text.contains("college football playoff")
            || text.hasPrefix("cfp ") || text.contains(" cfp ")
        guard isPlayoff else { return .bowl }
        if text.contains("first round") { return .firstRound }
        if text.contains("quarterfinal") { return .quarterfinal }
        if text.contains("semifinal") { return .semifinal }
        if text.contains("championship") { return .championship }
        return .bowl
    }
}

/// One postseason game: the game, its name, and its round.
struct PostseasonGame: Identifiable {
    let game: Game
    /// ESPN's name for it, such as "Cricket Celebration Bowl". Nil when ESPN gives none.
    let title: String?
    let round: PostseasonRound

    var id: String { game.id }

    /// ESPN's placeholder for a team not yet chosen has id -1 or -2 and the name TBD.
    static func isUndecided(_ team: Game.Team) -> Bool {
        team.id.hasPrefix("-") || team.displayName == "TBD" || team.displayName.isEmpty
    }

    var teamsUndecided: Bool {
        Self.isUndecided(game.awayTeam) && Self.isUndecided(game.homeTeam)
    }
}

/// One heading of the list and its games.
struct PostseasonSection: Identifiable {
    let round: PostseasonRound
    let games: [PostseasonGame]

    var id: Int { round.rawValue }

    /// "Bowl Games, 36 games", so a flick says whether the section is worth entering.
    var heading: String {
        "\(round.heading), \(games.count) \(games.count == 1 ? "game" : "games")"
    }
}

enum PostseasonList {
    /// Every game in a postseason scoreboard answer, with its name and round.
    static func games(from response: ScoreboardResponse) throws -> [PostseasonGame] {
        let seasonType = response.season?.type ?? 3
        return try response.events.map { event in
            let competition = event.competitions.first
            let headline = competition?.notes?
                .compactMap { $0.headline?.trimmingCharacters(in: .whitespacesAndNewlines) }
                .first { !$0.isEmpty }
            return PostseasonGame(game: try Game(from: event, seasonType: seasonType),
                                  title: headline,
                                  round: PostseasonRound.from(headline: headline,
                                                              typeID: competition?.type?.id))
        }
    }

    /// The games under their headings, playoff first, each heading's games by kickoff.
    /// Headings with no games are left out.
    static func sections(_ games: [PostseasonGame]) -> [PostseasonSection] {
        let byRound = Dictionary(grouping: games, by: \.round)
        return PostseasonRound.allCases.compactMap { round in
            guard let games = byRound[round], !games.isEmpty else { return nil }
            let sorted = games.sorted { a, b in
                if a.game.date != b.game.date { return a.game.date < b.game.date }
                return (a.title ?? a.game.name) < (b.title ?? b.game.name)
            }
            return PostseasonSection(round: round, games: sorted)
        }
    }

    // MARK: - Words

    private static func formatter(_ format: String, _ timeZone: TimeZone) -> DateFormatter {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = timeZone
        f.dateFormat = format
        return f
    }

    /// "Saturday, December 12 at 11:00 AM", or "..., time to be announced".
    static func spokenDate(_ game: Game, timeZone: TimeZone = .current) -> String {
        let day = formatter("EEEE, MMMM d", timeZone).string(from: game.date)
        if game.timeValid == false { return "\(day), time to be announced" }
        return "\(day) at \(formatter("h:mm a", timeZone).string(from: game.date))"
    }

    /// "Sat 12/12 11:00 AM", or "Sat 12/12, time TBD".
    static func shownDate(_ game: Game, timeZone: TimeZone = .current) -> String {
        let day = formatter("EEE M/d", timeZone).string(from: game.date)
        if game.timeValid == false { return "\(day), time TBD" }
        return "\(day) \(formatter("h:mm a", timeZone).string(from: game.date))"
    }

    /// Where the game stands: live with its clock, final, postponed, or when it starts.
    static func status(_ game: Game, spoken: Bool, timeZone: TimeZone = .current) -> String {
        let status = game.status
        if status.isPostponed { return "Postponed" }
        if status.isCancelled { return "Cancelled" }
        if status.isSuspended { return "Suspended" }
        if status.isLive { return status.displayText }
        if status.isCompleted { return "Final" }
        return spoken ? spokenDate(game, timeZone: timeZone) : shownDate(game, timeZone: timeZone)
    }

    /// The teams with their scores, or that they aren't known yet.
    static func matchup(_ item: PostseasonGame, names: (Game.Team) -> String) -> String {
        if item.teamsUndecided { return "Teams to be announced" }
        let game = item.game
        let away = names(game.awayTeam) + (game.awayTeam.score.map { " \($0)" } ?? "")
        let home = names(game.homeTeam) + (game.homeTeam.score.map { " \($0)" } ?? "")
        return "\(away) \(game.matchupWord) \(home)"
    }

    /// The whole row as VoiceOver reads it, name first, since that's what you look for:
    /// "Cricket Celebration Bowl, Teams to be announced, Saturday, December 12 at 11:00 AM, on ABC".
    static func accessibilityLabel(_ item: PostseasonGame,
                                   teamNames preference: TeamNamePreference,
                                   timeZone: TimeZone = .current) -> String {
        let game = item.game
        var parts: [String] = []
        if let title = item.title { parts.append(title) }
        parts.append(matchup(item) { $0.voiceOverName(for: preference) })
        parts.append(status(game, spoken: true, timeZone: timeZone))
        if game.status.isLive, let situation = game.situation?.displayText, !situation.isEmpty {
            parts.append(situation)
        }
        if let venue = game.venue, !venue.name.isEmpty { parts.append("at \(venue.fullName)") }
        if !game.status.isCompleted,
           let broadcast = game.broadcasts.first(where: { !$0.trimmingCharacters(in: .whitespaces).isEmpty }) {
            parts.append("on \(broadcast)")
        }
        return parts.joined(separator: ", ")
    }
}
