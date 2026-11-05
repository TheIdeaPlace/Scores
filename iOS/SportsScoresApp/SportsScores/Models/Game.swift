//
//  Game.swift
//  SportsScores
//
//  Created on 1/4/26.
//

import Foundation

struct Game: Identifiable, Codable {
    let id: String
    let name: String
    let shortName: String
    let date: Date
    let status: GameStatus
    let homeTeam: Team
    let awayTeam: Team
    let venue: Venue?
    let broadcasts: [String]
    let situation: Situation?
    /// ESPN season type — 1 preseason, 2 regular, 3 postseason (default 2).
    let seasonType: Int
    /// False when ESPN's time is a placeholder (TBD); `date` is then noon local on
    /// the game's date. Nil means known.
    var timeValid: Bool? = nil
    /// True when neither team is at home, such as a bowl game.
    var isNeutralSite: Bool? = nil

    /// Spoken between the teams.
    var matchupWord: String { isNeutralSite == true ? "vs" : "at" }
    /// Shown between the teams.
    var matchupSymbol: String { isNeutralSite == true ? "vs" : "@" }
    var awayPrefix: String { isNeutralSite == true ? "" : "Away: " }
    var homePrefix: String { isNeutralSite == true ? "" : "Home: " }

    private static let displayTBDFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "EEE M/d"
        f.timeZone = TimeZone.current
        return f
    }()

    private static let displayTimeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "h:mm a EEE M/d"
        f.timeZone = TimeZone.current
        return f
    }()

    var displayTime: String {
        if timeValid == false {
            return "Time TBD \(Game.displayTBDFormatter.string(from: date))"
        }
        return Game.displayTimeFormatter.string(from: date)
    }
    
    var scoreDisplay: String {
        // Prioritise non-played status so a postponed/cancelled game with state == "pre"
        // never accidentally shows its scheduled time as if it were a normal upcoming game.
        if status.isPostponed || status.isCancelled {
            let detail = status.detail.trimmingCharacters(in: .whitespacesAndNewlines)
            if !detail.isEmpty { return detail }
            return status.isPostponed ? "Postponed" : "Cancelled"
        } else if status.state == "pre" {
            return displayTime
        } else if awayTeam.score == nil && homeTeam.score == nil {
            return status.displayText
        } else {
            return "\(awayTeam.score ?? 0) - \(homeTeam.score ?? 0)"
        }
    }

    /// Broadcast info is only useful for live/upcoming games and should be hidden for past/final games.
    var shouldShowBroadcastInfo: Bool {
        let hasBroadcast = broadcasts.contains { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        guard hasBroadcast else { return false }
        if status.isLive { return true }
        if status.isCompleted { return false }

        // Treat previous-day/previous-season games as "past" and suppress TV network noise.
        let todayStart = ScoreboardDay.today()
        return date >= todayStart
    }
    
    struct Team: Codable {
        let id: String
        let name: String
        let abbreviation: String
        let displayName: String
        let score: Int?
        let record: String?
        let logo: String?
        /// True when ESPN marks this competitor as the winner of a completed match.
        /// Used by the World Cup bracket to determine advancement reliably (knockout
        /// matches decided on penalties have equal scores, so score alone is insufficient).
        var isWinner: Bool? = nil
        /// Poll rank, 1 to 25, when the team has one.
        var rank: Int? = nil

        /// The abbreviation as shown in a row, with the rank when there is one.
        var rankedAbbreviation: String {
            rank.map { "\($0) \(abbreviation)" } ?? abbreviation
        }

        var displayText: String {
            if let score = score, let record = record {
                return "\(abbreviation) (\(record)) - \(score)"
            } else if let record = record {
                return "\(abbreviation) (\(record))"
            } else if let score = score {
                return "\(abbreviation) - \(score)"
            } else {
                return abbreviation
            }
        }
    }
    
    struct GameStatus: Codable {
        let state: String // "pre", "in", "post"
        let detail: String
        let period: Int?
        let clock: String?
        /// ESPN status identifier, e.g. "STATUS_FINAL", "STATUS_POSTPONED", "STATUS_CANCELED".
        let name: String?
        
        var displayText: String {
            if state == "in",
               period != nil,
               let clock = normalizedClock,
               !detail.contains(clock) {
                return "\(detail) - \(clock)"
            }
            return detail
        }

        /// ESPN sometimes sends placeholder clocks like "0:00"/"0.0".
        /// Treat those as non-informative so VoiceOver doesn't announce trailing zeros.
        private var normalizedClock: String? {
            guard let rawClock = clock?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !rawClock.isEmpty else {
                return nil
            }

            let zeroClockPatterns: Set<String> = [
                "0", "0.0", "0:00", "0:0", "00:00", "00.0", "00"
            ]
            if zeroClockPatterns.contains(rawClock) {
                return nil
            }

            return rawClock
        }
        
        var isLive: Bool {
            state == "in"
        }
        
        var isCompleted: Bool {
            state == "post"
        }

        /// True when the game was postponed and did not take place.
        var isPostponed: Bool {
            if let n = name { return n == "STATUS_POSTPONED" }
            return detail.lowercased() == "postponed"
        }

        /// True when the game was cancelled and will not be played.
        var isCancelled: Bool {
            if let n = name {
                return n == "STATUS_CANCELED" || n == "STATUS_CANCELLED"
            }
            let d = detail.lowercased()
            return d == "canceled" || d == "cancelled"
        }

        /// True when play began and was halted, to be resumed later — a game
        /// suspended in the sixth at 3-2 really does stand at 3-2, so the partial
        /// score is shown rather than replaced by the status word. A game shortened
        /// by weather and called official is STATUS_FINAL ("Final/5"), not this.
        /// Matches the Windows side, where GameData.NOT_PLAYED_STATUS_NAMES
        /// deliberately excludes suspended.
        var isSuspended: Bool {
            if let n = name { return n == "STATUS_SUSPENDED" }
            return detail.lowercased() == "suspended"
        }
    }
    
    struct Venue: Codable {
        let name: String
        let city: String?
        let state: String?
        var country: String? = nil

        /// City + region: "Inglewood, California" for US venues, "Guadalupe, Mexico"
        /// for international ones (where ESPN omits the state).
        var shortLocation: String {
            var parts: [String] = []
            if let city = city, !city.isEmpty { parts.append(city) }
            if let state = state, !state.isEmpty {
                parts.append(state)
            } else if let country = country, !country.isEmpty, country != "USA" {
                parts.append(country)
            }
            return parts.joined(separator: ", ")
        }

        /// Stadium name + location: "SoFi Stadium, Inglewood, California".
        var fullName: String {
            let loc = shortLocation
            return loc.isEmpty ? name : "\(name), \(loc)"
        }
    }
    
    struct Situation: Codable {
        let lastPlay: String?
        let down: Int?
        let distance: Int?
        let possessionText: String?
        let shortDownDistanceText: String?
        // Baseball live situation
        let onFirst: Bool?
        let onSecond: Bool?
        let onThird: Bool?
        let outs: Int?
        let balls: Int?
        let strikes: Int?
        // Baseball pitcher / batter names
        let pitcherName: String?
        let batterName: String?
        let pitcherSummary: String?
        let batterSummary: String?
        // Football red zone
        let isRedZone: Bool?

        /// Human-readable situation text.
        /// For baseball (detected by presence of `balls`/`outs`), returns pitcher, batter,
        /// bases, count and outs — ignoring the raw ESPN pitch-call string.
        /// For all other sports returns lastPlay text or down-distance.
        var displayText: String? {
            if balls != nil || outs != nil || onFirst != nil {
                return baseballSituationText
            }
            if let lastPlay = lastPlay, !lastPlay.isEmpty {
                return lastPlay
            }
            return shortDownDistanceText
        }

        /// Baseball compact situation line — pitcher, batter, bases, count, outs.
        var baseballSituationText: String? {
            guard balls != nil || outs != nil || onFirst != nil else { return nil }
            var parts: [String] = []
            // Pitcher / batter first so identity is always visible
            if let p = pitcherName { parts.append("P: \(p)") }
            if let b = batterName  { parts.append("AB: \(b)") }
            // Bases
            let firstOn  = onFirst  ?? false
            let secondOn = onSecond ?? false
            let thirdOn  = onThird  ?? false
            if firstOn || secondOn || thirdOn {
                var bases: [String] = []
                if firstOn  { bases.append("1st") }
                if secondOn { bases.append("2nd") }
                if thirdOn  { bases.append("3rd") }
                parts.append(bases.joined(separator: " & "))
            } else {
                parts.append("Bases empty")
            }
            // Count
            if let b = balls, let s = strikes { parts.append("\(b)-\(s)") }
            // Outs
            if let o = outs { parts.append("\(o) \(o == 1 ? "out" : "outs")") }
            return parts.joined(separator: " · ")
        }
    }
}

// MARK: - Team Name Helpers

extension Game.Team {
    /// The city or school component of `displayName`.
    ///
    /// Computed by stripping `name` from the end of `displayName`.
    /// - "Milwaukee Brewers" → "Milwaukee"
    /// - "Wisconsin Badgers" → "Wisconsin"
    /// - Falls back to `displayName` if stripping would leave an empty string.
    var cityName: String {
        guard displayName.hasSuffix(name) else { return displayName }
        let city = String(displayName.dropLast(name.count))
            .trimmingCharacters(in: .whitespaces)
        return city.isEmpty ? displayName : city
    }

    /// Returns the team name string appropriate for a VoiceOver label
    /// given the current user preference.
    func voiceOverName(for preference: TeamNamePreference) -> String {
        let spoken: String
        switch preference {
        case .full:         spoken = displayName
        case .mascot:       spoken = name
        case .city:         spoken = cityName
        case .abbreviation: spoken = abbreviation
        }
        return rank.map { "No. \($0) \(spoken)" } ?? spoken
    }
}

// MARK: - API Response Models
extension Game {
    init(from apiResponse: APIGame, seasonType: Int = 2) throws {
        self.id = apiResponse.id
        self.name = apiResponse.name
        self.shortName = apiResponse.shortName
        self.seasonType = seasonType

        // DateFormatter is NOT thread-safe. Create instances locally so concurrent
        // Task group calls (one per sport) each get their own formatters.
        // ESPN returns several ISO-8601 variants; try most common first.
        let dateFormatter = DateFormatter()
        dateFormatter.locale = Locale(identifier: "en_US_POSIX")
        dateFormatter.timeZone = TimeZone(secondsFromGMT: 0)
        let dateFormats = [
            "yyyy-MM-dd'T'HH:mm:ss'Z'",    // most common: 2026-01-05T01:20:00Z
            "yyyy-MM-dd'T'HH:mm'Z'",        // compact (no seconds): 2026-01-05T01:20Z
            "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"  // with milliseconds
        ]
        var parsedDate: Date?
        for fmt in dateFormats {
            dateFormatter.dateFormat = fmt
            if let d = dateFormatter.date(from: apiResponse.date) {
                parsedDate = d
                break
            }
        }
        let competitionTimeValid = apiResponse.competitions.first?.timeValid
        if competitionTimeValid == false, let parsedDate {
            self.date = ScoreboardDay.localNoon(onUTCDayOf: parsedDate)
        } else {
            self.date = parsedDate ?? Date()
        }
        self.timeValid = competitionTimeValid
        self.isNeutralSite = apiResponse.competitions.first?.neutralSite

        // Parse status
        self.status = GameStatus(
            state: apiResponse.status.type.state,
            detail: apiResponse.status.type.detail,
            period: apiResponse.status.period,
            clock: apiResponse.status.displayClock,
            name: apiResponse.status.type.name
        )
        
        // Parse teams
        let competitions = apiResponse.competitions.first
        let homeCompetitor = competitions?.competitors.first(where: { $0.homeAway == "home" })
        let awayCompetitor = competitions?.competitors.first(where: { $0.homeAway == "away" })

        // Suppress scores for pre-game states (show records instead of 0–0) and for
        // postponed/cancelled games where the API returns "0" as a placeholder.
        let isPreGame = apiResponse.status.type.state == "pre"
        // A delayed game that hasn't started is "in" progress at period 0, and 0 to 0.
        let hasNotStarted = apiResponse.status.type.state == "in" && apiResponse.status.period == 0
        let suppressScores = isPreGame || hasNotStarted
            || self.status.isPostponed || self.status.isCancelled

        self.homeTeam = Team(
            id: homeCompetitor?.team.id ?? "",
            name: homeCompetitor?.team.name ?? "",
            abbreviation: homeCompetitor?.team.abbreviation ?? "",
            displayName: homeCompetitor?.team.displayName ?? "",
            // flatMap returns nil when score is nil or non-numeric (e.g. pre-game "").
            score: suppressScores ? nil : homeCompetitor?.score.flatMap({ Int($0) }),
            record: homeCompetitor?.records?.first?.summary,
            logo: homeCompetitor?.team.logo,
            isWinner: homeCompetitor?.winner,
            rank: homeCompetitor?.curatedRank?.pollRank
        )
        
        self.awayTeam = Team(
            id: awayCompetitor?.team.id ?? "",
            name: awayCompetitor?.team.name ?? "",
            abbreviation: awayCompetitor?.team.abbreviation ?? "",
            displayName: awayCompetitor?.team.displayName ?? "",
            score: suppressScores ? nil : awayCompetitor?.score.flatMap({ Int($0) }),
            record: awayCompetitor?.records?.first?.summary,
            logo: awayCompetitor?.team.logo,
            isWinner: awayCompetitor?.winner,
            rank: awayCompetitor?.curatedRank?.pollRank
        )
        
        // Parse venue
        if let venueData = competitions?.venue {
            self.venue = Venue(
                name: venueData.fullName,
                city: venueData.address?.city,
                state: venueData.address?.state,
                country: venueData.address?.country
            )
        } else {
            self.venue = nil
        }
        
        // Parse broadcasts
        self.broadcasts = competitions?.broadcasts?.flatMap { $0.names } ?? []
        
        // Parse situation (last play, down & distance for football; bases/count/outs for baseball)
        if let situationData = competitions?.situation {
            self.situation = Situation(
                lastPlay: situationData.lastPlay?.text,
                down: situationData.down,
                distance: situationData.distance,
                possessionText: situationData.possessionText,
                shortDownDistanceText: situationData.shortDownDistanceText,
                onFirst: situationData.onFirst,
                onSecond: situationData.onSecond,
                onThird: situationData.onThird,
                outs: situationData.outs,
                balls: situationData.balls,
                strikes: situationData.strikes,
                pitcherName: situationData.pitcher?.athlete?.shortName
                             ?? situationData.pitcher?.athlete?.displayName,
                batterName:  situationData.batter?.athlete?.shortName
                             ?? situationData.batter?.athlete?.displayName,
                pitcherSummary: situationData.pitcher?.summary,
                batterSummary:  situationData.batter?.summary,
                isRedZone: situationData.isRedZone
            )
        } else {
            self.situation = nil
        }
    }
}

// MARK: - ESPN API Response Structure
struct APIGame: Codable {
    let id: String
    let name: String
    let shortName: String
    let date: String
    let status: APIStatus
    let competitions: [APICompetition]
    
    struct APIStatus: Codable {
        let type: APIStatusType
        let period: Int?
        let displayClock: String?
        
        struct APIStatusType: Codable {
            let state: String
            let detail: String
            /// ESPN status identifier, e.g. "STATUS_FINAL", "STATUS_POSTPONED", "STATUS_CANCELED".
            let name: String?
        }
    }
    
    struct APICompetition: Codable {
        let competitors: [APICompetitor]
        let venue: APIVenue?
        let broadcasts: [APIBroadcast]?
        let situation: APISituation?
        let timeValid: Bool?
        let neutralSite: Bool?

        struct APICompetitor: Codable {
            let homeAway: String
            let team: APITeam
            let score: String?
            let records: [APIRecord]?
            /// ESPN flags the advancing/winning competitor in completed knockout matches.
            let winner: Bool?
            let curatedRank: APICuratedRank?

            struct APICuratedRank: Codable {
                let current: Int?

                init(from decoder: Decoder) throws {
                    let container = try decoder.container(keyedBy: CodingKeys.self)
                    current = try? container.decodeIfPresent(Int.self, forKey: .current)
                }

                /// ESPN sends 99 for unranked.
                var pollRank: Int? {
                    guard let current, (1...25).contains(current) else { return nil }
                    return current
                }
            }

            struct APITeam: Codable {
                let id: String
                let name: String
                let abbreviation: String
                let displayName: String
                let logo: String?
            }
            
            struct APIRecord: Codable {
                let summary: String
            }
        }
        
        struct APIVenue: Codable {
            let fullName: String
            let address: APIAddress?
            
            struct APIAddress: Codable {
                let city: String?
                let state: String?
                let country: String?
            }
        }
        
        struct APIBroadcast: Codable {
            let names: [String]
        }
        
        struct APISituation: Codable {
            let lastPlay: APILastPlay?
            let down: Int?
            let distance: Int?
            let possessionText: String?
            let shortDownDistanceText: String?
            // Baseball live fields
            let onFirst: Bool?
            let onSecond: Bool?
            let onThird: Bool?
            let outs: Int?
            let balls: Int?
            let strikes: Int?
            // Baseball pitcher / batter
            let pitcher: APISituationPlayer?
            let batter: APISituationPlayer?
            // Football
            let isRedZone: Bool?

            struct APILastPlay: Codable {
                let text: String?
            }

            struct APISituationPlayer: Codable {
                let athlete: APIAthlete?
                let summary: String?

                struct APIAthlete: Codable {
                    let shortName: String?
                    let displayName: String?
                }
            }
        }
    }
}
