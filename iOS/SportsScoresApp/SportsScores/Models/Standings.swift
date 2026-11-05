//
//  Standings.swift
//  SportsScores
//
//  Created on 1/4/26.
//

import Foundation

struct StandingsGroup: Identifiable {
    let id = UUID()
    let name: String
    let entries: [StandingsEntry]
}

/// A team's row in a soccer table, as Windows has it: soccer.py, and
/// tests/fixtures/soccer_grid.json holds both. A record is wins, draws, losses, and points rank
/// the table, so baseball's percentage and games back would say nothing.
struct SoccerTableRow {
    static let headers = ["Pos", "Team", "GP", "W", "D", "L", "GF", "GA", "GD", "Pts", "Status"]
    /// A blank cell would be silent in VoiceOver.
    static let noStatus = "N/A"

    /// Where ESPN puts this team, with its tiebreakers. If there's no rank, its place in the answer.
    let position: Int
    let gamesPlayed: Int
    let wins: Int
    let draws: Int
    let losses: Int
    let goalsFor: Int
    let goalsAgainst: Int
    let goalDifference: String
    let points: Int
    let status: String

    func cells(team: String) -> [String] {
        [String(position), team, String(gamesPlayed), String(wins), String(draws), String(losses),
         String(goalsFor), String(goalsAgainst), goalDifference, String(points), status]
    }

    /// The values alone, as Windows's Quick List has them.
    func quickText(team: String) -> String {
        cells(team: team).joined(separator: ", ")
    }

    /// Each value with its heading, as Windows's Full List has them.
    func fullText(team: String) -> String {
        zip(Self.headers, cells(team: team)).map { "\($0): \($1)" }.joined(separator: "; ")
    }
}

/// A team's place in the wild card picture.
///
/// `nil` on ordinary division standings. The playoff cut line lives in `status`
/// rather than being drawn, so VoiceOver speaks who is in.
struct WildCardStanding {
    /// "-" for a division leader, otherwise MLB's official wild card rank.
    let position: String
    /// "AL East leader", "Wild card 1", or "" for teams outside the spots.
    let status: String
    /// Games back of the last wild card spot ("+8.5", "-", "0.5").
    let gamesBack: String

    /// Status as words. A bare "-" is not spoken at all at the default
    /// punctuation level in either VoiceOver or NVDA, so a team outside the
    /// spots would read as silence — indistinguishable from a cell that failed
    /// to populate. Every surface uses this rather than a dash.
    var spokenStatus: String {
        status.isEmpty ? "Not in a playoff spot" : status
    }

    /// Position as words, for the same reason: leaders carry "-", not a number.
    var positionText: String {
        position == "-" ? "Division leader" : position
    }
}

struct StandingsEntry: Identifiable {
    let id = UUID()
    let rank: Int
    let team: TeamInfo
    var stats: StandingsStats
    /// Set only on wild card standings; nil for division/conference groups.
    var wildCard: WildCardStanding? = nil
    /// Set only on a soccer league's table, whose columns are its own.
    var soccer: SoccerTableRow? = nil
    
    struct TeamInfo {
        let id: String
        let name: String
        let abbreviation: String
        let displayName: String
        let logo: String?

        var cityName: String {
            guard displayName.hasSuffix(name) else { return displayName }
            let city = String(displayName.dropLast(name.count)).trimmingCharacters(in: .whitespaces)
            return city.isEmpty ? displayName : city
        }

        func voiceOverName(for preference: TeamNamePreference) -> String {
            switch preference {
            case .full:         return displayName
            case .mascot:       return name
            case .city:         return cityName
            case .abbreviation: return abbreviation
            }
        }
    }
    
    struct StandingsStats {
        let wins: Int
        let losses: Int
        let winPercent: Double
        let gamesBack: String
        let streak: String
        let record: String
        // Raw scoring totals (MLB=runs, NFL/NBA/NHL=points/goals)
        let pointsFor: Int?
        let pointsAgainst: Int?
        // Extended: present for some sports only
        let ties: Int?          // NFL
        let otLosses: Int?      // NHL
        let nhlPoints: Int?     // NHL standings points
        let avgPointsFor: Double?    // NBA PPG
        let avgPointsAgainst: Double? // NBA opp PPG
        let homeRecord: String?
        let roadRecord: String?
        let lastTenRecord: String?
        let divisionRecord: String?
        let playoffSeed: Int?
        let differential: String?   // formatted e.g. "+61", "-7"

        var displayWinPercent: String {
            let formatted = String(format: "%.3f", winPercent)
            return formatted.hasPrefix("0") ? String(formatted.dropFirst()) : formatted
        }
    }
    
    // For table view display
    var tableRow: [String] {
        [
            "\(rank)",
            team.abbreviation,
            "\(stats.wins)",
            "\(stats.losses)",
            stats.displayWinPercent,
            stats.gamesBack,
            stats.streak,
            stats.record
        ]
    }
    
    // For quick list display
    var quickListText: String {
        if let wc = wildCard {
            // Leaders have no rank, so lead with the team rather than a bare "-".
            let lead = wc.position == "-" ? "" : "\(wc.position). "
            return "\(lead)\(team.abbreviation), \(stats.wins)-\(stats.losses), "
                + "\(stats.displayWinPercent), WCGB: \(wc.gamesBack), \(stats.streak), "
                + "\(wc.spokenStatus)"
        }
        var text = "\(team.abbreviation), \(stats.wins)-\(stats.losses), \(stats.displayWinPercent), GB: \(stats.gamesBack)"
        if let l10 = stats.lastTenRecord { text += ", L10: \(l10)" }
        return text
    }

    // The NHL ranks by points and has overtime losses, not percentages and games back.
    var nhlQuickListText: String {
        var text = "\(team.abbreviation), \(stats.wins)-\(stats.losses)-\(stats.otLosses ?? 0), \(stats.nhlPoints ?? 0) PTS"
        if let l10 = stats.lastTenRecord { text += ", L10: \(l10)" }
        return text
    }

    var nhlFullListText: String {
        var text = "Team: \(team.displayName); Wins: \(stats.wins); Losses: \(stats.losses); OT Losses: \(stats.otLosses ?? 0); Points: \(stats.nhlPoints ?? 0); Streak: \(stats.streak)"
        if let l10 = stats.lastTenRecord { text += "; Last 10: \(l10)" }
        return text
    }

    // For full list display
    var fullListText: String {
        if let wc = wildCard {
            return "Position: \(wc.positionText); Team: \(team.displayName); Wins: \(stats.wins); "
                + "Losses: \(stats.losses); Win%: \(stats.displayWinPercent); "
                + "Wild card games back: \(wc.gamesBack); Streak: \(stats.streak); "
                + "Record: \(stats.record); Status: \(wc.spokenStatus)"
        }
        var text = "\(rank > 0 ? "Rank: \(rank); " : "")Team: \(team.displayName); Wins: \(stats.wins); Losses: \(stats.losses); Win%: \(stats.displayWinPercent); Games Back: \(stats.gamesBack); Streak: \(stats.streak); Record: \(stats.record)"
        if let l10 = stats.lastTenRecord { text += "; Last 10: \(l10)" }
        return text
    }
}

// MARK: - Shared entry-building helper
extension StandingsEntry {
    /// Build a StandingsEntry from a raw API entry, populating all extended fields.
    init(fromAPIEntry apiEntry: APIStandingsGroup.APIStandings.APIStandingsEntry) {
        typealias AS = APIStandingsGroup.APIStandings.APIStandingsEntry.APIStat
        // ESPN repeats a stat once per split (home, road, conference), with the same
        // `name` and a different `type`, so the name alone doesn't say which you get.
        func stat(_ name: String, type: String? = nil) -> AS? {
            let wanted = type ?? name.lowercased()
            return apiEntry.stats.first(where: { $0.name == name && $0.type == wanted })
                ?? apiEntry.stats.first(where: { $0.name == name })
        }
        let overall = stat("overall", type: "total")?.displayValue
        // College football sends no losses or win percentage, only "7-1".
        let wins = Int(stat("wins")?.value ?? 0)
        let losses = stat("losses").map { Int($0.value) } ?? Self.losses(fromRecord: overall)
        let ties = stat("ties").map { Int($0.value) } ?? stat("tiegames").map { Int($0.value) }
        let decided = Double(wins + losses + (ties ?? 0))
        let computedPercent = decided > 0 ? (Double(wins) + Double(ties ?? 0) / 2) / decided : 0
        let t = apiEntry.team
        self.wildCard = nil
        self.rank = Int(stat("rank")?.value ?? 0)
        self.team = TeamInfo(
            id: t.id, name: t.name, abbreviation: t.abbreviation,
            displayName: t.displayName, logo: t.logos?.first?.href
        )
        self.stats = StandingsStats(
            wins:          wins,
            losses:        losses,
            winPercent:    stat("winPercent")?.value ?? computedPercent,
            gamesBack:     stat("divisionGamesBehind")?.displayValue ?? stat("gamesBehind")?.displayValue ?? "-",
            streak:        stat("streak")?.displayValue ?? "-",
            record:        overall ?? "-",
            pointsFor:     stat("pointsFor").map { Int($0.value) },
            pointsAgainst: stat("pointsAgainst").map { Int($0.value) },
            ties:          ties,
            otLosses:      stat("otLosses").map { Int($0.value) }
                            ?? stat("OTLosses").map { Int($0.value) },
            nhlPoints:     stat("points").map { Int($0.value) },
            avgPointsFor:  stat("avgPointsFor")?.value,
            avgPointsAgainst: stat("avgPointsAgainst")?.value,
            homeRecord:    stat("Home")?.displayValue,
            roadRecord:    stat("Road")?.displayValue,
            // The NHL's reads "7-2-1, 0 PTS", and that zero means nothing.
            lastTenRecord: stat("Last Ten Games")?.displayValue
                .components(separatedBy: ", ").first,
            divisionRecord: stat("vs. Div.")?.displayValue ?? stat("divisionRecord")?.displayValue,
            playoffSeed:   stat("playoffSeed").map { Int($0.value) },
            differential:  stat("differential")?.displayValue
        )
    }

    /// The second number of a record such as "7-1" or "5-1-0", 0 if it has none.
    private static func losses(fromRecord record: String?) -> Int {
        let parts = (record ?? "").split(separator: "-")
        return parts.count > 1 ? Int(parts[1]) ?? 0 : 0
    }
}

// MARK: - API Response Models
extension StandingsGroup {
    init(from apiResponse: APIStandingsGroup) throws {
        self.name = apiResponse.name
        self.entries = apiResponse.standings.entries.map { StandingsEntry(fromAPIEntry: $0) }
    }

    /// A soccer league's table, in the order of ESPN's rank. The answer's own order won't do: in
    /// MLS and a cup's groups, it reads 4th, 8th, 3rd. On Windows: parse_soccer_standings.
    init(soccerTable group: APIStandingsGroup) {
        self.name = group.name
        self.entries = group.standings.entries.enumerated().map { index, apiEntry -> StandingsEntry in
            var entry = StandingsEntry(fromAPIEntry: apiEntry)
            entry.soccer = SoccerTableRow(fromAPIEntry: apiEntry, place: index + 1)
            return entry
        }
        .sorted { ($0.soccer?.position ?? 0) < ($1.soccer?.position ?? 0) }
    }
}

extension SoccerTableRow {
    init(fromAPIEntry entry: APIStandingsGroup.APIStandings.APIStandingsEntry, place: Int) {
        func stat(_ name: String) -> APIStandingsGroup.APIStandings.APIStandingsEntry.APIStat? {
            entry.stats.first { $0.name == name }
        }
        // ESPN can send a null, which reads as 0 here, so its text gets a say.
        func number(_ name: String) -> Int {
            guard let stat = stat(name) else { return 0 }
            return stat.value != 0 ? Int(stat.value) : Int(stat.displayValue) ?? 0
        }
        let difference = number("pointDifferential")
        let differenceText = stat("pointDifferential")?.displayValue ?? ""
        let rank = number("rank")
        self.position = rank != 0 ? rank : place
        self.gamesPlayed = number("gamesPlayed")
        self.wins = number("wins")
        self.draws = number("ties")
        self.losses = number("losses")
        self.goalsFor = number("pointsFor")
        self.goalsAgainst = number("pointsAgainst")
        self.goalDifference = differenceText.isEmpty ? (difference > 0 ? "+\(difference)" : String(difference)) : differenceText
        self.points = number("points")
        // ESPN's can end in a stray tab.
        let note = (entry.note?.description ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        self.status = note.isEmpty ? Self.noStatus : note
    }
}

/// One node of ESPN's standings tree. Leagues nest differently: a node can hold
/// entries, children, or nothing (College Hockey America has a `standings` with no
/// `entries`; the Sun Belt has only East and West children).
struct APIStandingsGroup: Codable {
    let name: String
    let standings: APIStandings
    let children: [APIStandingsGroup]?

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        name = (try? container.decodeIfPresent(String.self, forKey: .name)) ?? ""
        standings = (try? container.decodeIfPresent(APIStandings.self, forKey: .standings))
            ?? APIStandings()
        children = try? container.decodeIfPresent([APIStandingsGroup].self, forKey: .children)
    }

    /// This node and everything under it that actually has teams, in order.
    var groupsWithEntries: [APIStandingsGroup] {
        (standings.entries.isEmpty ? [] : [self])
            + (children ?? []).flatMap { $0.groupsWithEntries }
    }

    struct APIStandings: Codable {
        let entries: [APIStandingsEntry]

        init() { entries = [] }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            entries = container.lossyArray(forKey: .entries) ?? []
        }

        struct APIStandingsEntry: Codable {
            let team: APITeam
            let stats: [APIStat]
            /// Where a place in a soccer table leads, such as "Champions League".
            let note: APINote?

            struct APINote: Codable {
                let description: String?
            }
            
            struct APITeam: Codable {
                let id: String
                let name: String
                let abbreviation: String
                let displayName: String
                let logos: [APILogo]?
                
                struct APILogo: Codable {
                    let href: String
                }
            }
            
            struct APIStat: Codable {
                let name: String
                let displayName: String?   // absent on some ESPN stats (e.g. "overall")
                /// Which split this is: "wins", "total", "homerecord_wins".
                let type: String?
                let value: Double          // defaulted to 0 when ESPN omits the field
                let displayValue: String

                // Custom decoder: ESPN omits `value` on record-string stats like
                // "overall" (W-L), "Home", "Road", "vs. Div.", etc.  Without
                // this, a single missing `value` causes the *entire* standings
                // response to fail with a DecodingError.
                init(from decoder: Decoder) throws {
                    let c = try decoder.container(keyedBy: CodingKeys.self)
                    self.name         = try  c.decode(String.self,         forKey: .name)
                    self.displayName  = try  c.decodeIfPresent(String.self, forKey: .displayName)
                    self.type         = try? c.decodeIfPresent(String.self, forKey: .type)
                    self.value        = (try? c.decodeIfPresent(Double.self, forKey: .value)) ?? 0
                    self.displayValue = try  c.decode(String.self,         forKey: .displayValue)
                }

                enum CodingKeys: String, CodingKey {
                    case name, displayName, type, value, displayValue
                }
            }
        }
    }
}

/// The root of the tree. Women's college hockey keeps its entries here, with no
/// children at all.
struct APIStandingsResponse: Codable {
    let children: [APIStandingsGroup]
    let root: APIStandingsGroup

    init(from decoder: Decoder) throws {
        root = try APIStandingsGroup(from: decoder)
        children = root.children ?? []
    }

    func encode(to encoder: Encoder) throws {
        try root.encode(to: encoder)
    }

    /// Every group in the tree that has teams.
    var groupsWithEntries: [APIStandingsGroup] { root.groupsWithEntries }
}
