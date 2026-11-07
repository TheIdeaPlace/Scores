//
//  OnIce.swift
//  SportsScores
//
//  Who is on the ice right now, from an NHL game's summary. on_ice.py on Windows;
//  both are held to tests/fixtures/on_ice_grid.json. Change both together.
//
//  ESPN's `onIce` block holds one entry per team, athlete ids only. The names, jersey
//  numbers and positions come from the same summary's box score, whose player groups
//  are `forwards`, `defenses` and `goalies`, so no second request is needed. The block
//  is in a finished game's summary too, as the last shift; it's shown only while the
//  game is being played, and not in an intermission. College hockey summaries have no
//  `onIce` block at all.
//

import Foundation

struct OnIcePlayer: Codable, Equatable {
    let id: String
    let name: String
    let lastName: String
    let jersey: String
    let position: String
    /// "forward", "defense", "goalie", or "" when ESPN doesn't say.
    let group: String

    /// As read out: "Oliver Bjorkstrand, number 28, Right Wing".
    var spokenText: String {
        var parts = [name]
        if !jersey.isEmpty { parts.append("number \(jersey)") }
        if !position.isEmpty { parts.append(position) }
        return parts.filter { !$0.isEmpty }.joined(separator: ", ")
    }
}

struct OnIceTeam: Codable, Equatable {
    let id: String
    let name: String
    let shortName: String
    let homeAway: String
    /// Forwards, then defense, then the goalie; ESPN's order within each.
    let players: [OnIcePlayer]

    /// "New York Rangers, 6 on the ice".
    var heading: String { "\(name), \(players.count) on the ice" }
}

enum OnIce {
    static let inPlay = "ROSTER_WHEREABOUTS_IN_PLAY"
    static let intermission = "STATUS_END_PERIOD"

    /// The one line that stands for them all, by last name:
    /// "On the ice: Rangers: Bjorkstrand, Zibanejad; Kraken: Beniers, Dunn".
    static func summaryLine(_ teams: [OnIceTeam]) -> String {
        guard !teams.isEmpty else { return "" }
        let sides = teams.map { team in
            "\(team.shortName): " + team.players.map(\.lastName).joined(separator: ", ")
        }
        return "On the ice: " + sides.joined(separator: "; ")
    }

    fileprivate static let groupByBox = ["forwards": "forward", "defenses": "defense", "goalies": "goalie"]
    fileprivate static let groupByPosition = ["C": "forward", "LW": "forward", "RW": "forward", "F": "forward",
                                              "W": "forward", "D": "defense", "G": "goalie"]
    fileprivate static let groupOrder = ["forward": 0, "defense": 1, "goalie": 2]
}

/// Read from the root of a summary. `teams` is empty when the game isn't being played
/// or ESPN says nothing; no part of it can fail the summary.
struct OnIceLineup: Decodable {
    let teams: [OnIceTeam]

    private enum Keys: String, CodingKey { case header, boxscore, onIce }

    init(from decoder: Decoder) throws {
        let root = try decoder.container(keyedBy: Keys.self)
        let header = try? root.decodeIfPresent(Header.self, forKey: .header)
        guard let competition = header?.competitions.first, competition.isLive else { teams = []; return }

        var onIce: [String: [Entry]] = [:]
        let blocks: [IceTeam] = root.lossyArray(forKey: .onIce) ?? []
        for block in blocks where !block.teamId.isEmpty {
            onIce[block.teamId] = block.entries
        }
        guard !onIce.isEmpty else { teams = []; return }

        let boxscore = try? root.decodeIfPresent(Box.self, forKey: .boxscore)
        let box = boxscore?.playersByTeam ?? [:]
        var result: [OnIceTeam] = []
        for team in competition.teams {
            let roster = box[team.id] ?? [:]
            var seen = Set<String>()
            var players: [OnIcePlayer] = []
            for entry in onIce[team.id] ?? [] {
                if !entry.whereabouts.isEmpty && entry.whereabouts != OnIce.inPlay { continue }
                guard !seen.contains(entry.athleteId), let player = roster[entry.athleteId] else { continue }
                seen.insert(entry.athleteId)
                players.append(player)
            }
            guard !players.isEmpty else { continue }
            // Stable: ESPN's order within a group.
            let ordered = players.enumerated().sorted { a, b in
                let ga = OnIce.groupOrder[a.element.group] ?? 3
                let gb = OnIce.groupOrder[b.element.group] ?? 3
                return ga == gb ? a.offset < b.offset : ga < gb
            }.map { $0.element }
            result.append(OnIceTeam(id: team.id, name: team.name, shortName: team.shortName,
                                    homeAway: team.homeAway, players: ordered))
        }
        teams = result
    }

    // MARK: - The parts of the summary read here, each lenient

    /// Text with whitespace trimmed; "" for anything that isn't text.
    private static func text<K: CodingKey>(_ c: KeyedDecodingContainer<K>, _ key: K) -> String {
        let value: String? = try? c.decodeIfPresent(String.self, forKey: key)
        return value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }

    /// An id ESPN may send as text or a number.
    private static func id<K: CodingKey>(_ c: KeyedDecodingContainer<K>, _ key: K) -> String {
        let number: Int? = try? c.decodeIfPresent(Int.self, forKey: key)
        if let number { return String(number) }
        return text(c, key)
    }

    private static func first(_ values: String...) -> String {
        values.first { !$0.isEmpty } ?? ""
    }

    private struct Header: Decodable {
        let competitions: [Competition]
        private enum Keys: String, CodingKey { case competitions }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: Keys.self)
            competitions = c.lossyArray(forKey: .competitions) ?? []
        }
    }

    private struct Competition: Decodable {
        let state: String
        let statusName: String
        let period: Int?
        /// Away first.
        let teams: [HeaderTeam]

        /// Being played: not a delay at period 0, and not an intermission, when the block
        /// still holds the period's last shift.
        var isLive: Bool { state == "in" && period != 0 && statusName != OnIce.intermission }

        private enum Keys: String, CodingKey { case status, competitors }
        private enum StatusKeys: String, CodingKey { case type, period }
        private enum TypeKeys: String, CodingKey { case state, name }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: Keys.self)
            let status = try? c.nestedContainer(keyedBy: StatusKeys.self, forKey: .status)
            period = status.flatMap { container -> Int? in
                let value: Int? = try? container.decodeIfPresent(Int.self, forKey: .period)
                return value
            }
            let type = status.flatMap { try? $0.nestedContainer(keyedBy: TypeKeys.self, forKey: .type) }
            state = type.map { OnIceLineup.text($0, .state) } ?? ""
            statusName = type.map { OnIceLineup.text($0, .name) } ?? ""
            let competitors: [HeaderTeam] = c.lossyArray(forKey: .competitors) ?? []
            teams = competitors.filter { !$0.id.isEmpty && !$0.name.isEmpty }
                .enumerated()
                .sorted { a, b in
                    let ra = a.element.homeAway == "away" ? 0 : 1
                    let rb = b.element.homeAway == "away" ? 0 : 1
                    return ra == rb ? a.offset < b.offset : ra < rb
                }
                .map { $0.element }
        }
    }

    private struct HeaderTeam: Decodable {
        let id: String
        let name: String
        let shortName: String
        let homeAway: String

        private enum Keys: String, CodingKey { case homeAway, team }
        private enum TeamKeys: String, CodingKey { case id, displayName, name, abbreviation, shortDisplayName }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: Keys.self)
            homeAway = OnIceLineup.text(c, .homeAway)
            guard let t = try? c.nestedContainer(keyedBy: TeamKeys.self, forKey: .team) else {
                id = ""; name = ""; shortName = ""; return
            }
            id = OnIceLineup.id(t, .id)
            let display = OnIceLineup.text(t, .displayName)
            let nickname = OnIceLineup.text(t, .name)
            name = OnIceLineup.first(display, nickname, OnIceLineup.text(t, .abbreviation))
            shortName = OnIceLineup.first(OnIceLineup.text(t, .shortDisplayName), nickname, name)
        }
    }

    private struct Box: Decodable {
        /// Team id to athlete id to the player as shown.
        let playersByTeam: [String: [String: OnIcePlayer]]

        private enum Keys: String, CodingKey { case players }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: Keys.self)
            var byTeam: [String: [String: OnIcePlayer]] = [:]
            let teams: [BoxTeam] = c.lossyArray(forKey: .players) ?? []
            for team in teams {
                var players = byTeam[team.id] ?? [:]
                for group in team.groups {
                    let boxGroup = OnIce.groupByBox[group.name] ?? ""
                    for athlete in group.athletes where !athlete.id.isEmpty && !athlete.name.isEmpty {
                        guard players[athlete.id] == nil else { continue }
                        players[athlete.id] = OnIcePlayer(
                            id: athlete.id,
                            name: athlete.name,
                            lastName: OnIceLineup.first(athlete.lastName, athlete.name),
                            jersey: athlete.jersey,
                            position: athlete.position,
                            group: boxGroup.isEmpty ? (OnIce.groupByPosition[athlete.abbreviation] ?? "") : boxGroup)
                    }
                }
                byTeam[team.id] = players
            }
            playersByTeam = byTeam
        }
    }

    private struct BoxTeam: Decodable {
        let id: String
        let groups: [BoxGroup]
        private enum Keys: String, CodingKey { case team, statistics }
        private enum TeamKeys: String, CodingKey { case id }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: Keys.self)
            id = (try? c.nestedContainer(keyedBy: TeamKeys.self, forKey: .team)).map { OnIceLineup.id($0, .id) } ?? ""
            groups = c.lossyArray(forKey: .statistics) ?? []
        }
    }

    private struct BoxGroup: Decodable {
        let name: String
        let athletes: [BoxAthlete]
        private enum Keys: String, CodingKey { case name, athletes }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: Keys.self)
            name = OnIceLineup.text(c, .name)
            athletes = c.lossyArray(forKey: .athletes) ?? []
        }
    }

    private struct BoxAthlete: Decodable {
        let id: String
        let name: String
        let lastName: String
        let jersey: String
        let position: String
        let abbreviation: String

        private enum Keys: String, CodingKey { case athlete }
        private enum AthleteKeys: String, CodingKey { case id, displayName, shortName, lastName, jersey, position }
        private enum PositionKeys: String, CodingKey { case displayName, name, abbreviation }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: Keys.self)
            let a = try c.nestedContainer(keyedBy: AthleteKeys.self, forKey: .athlete)
            id = OnIceLineup.id(a, .id)
            name = OnIceLineup.first(OnIceLineup.text(a, .displayName), OnIceLineup.text(a, .shortName))
            lastName = OnIceLineup.text(a, .lastName)
            jersey = OnIceLineup.text(a, .jersey)
            let p = try? a.nestedContainer(keyedBy: PositionKeys.self, forKey: .position)
            position = p.map { OnIceLineup.first(OnIceLineup.text($0, .displayName), OnIceLineup.text($0, .name)) } ?? ""
            abbreviation = p.map { OnIceLineup.text($0, .abbreviation) } ?? ""
        }
    }

    private struct IceTeam: Decodable {
        let teamId: String
        let entries: [Entry]
        private enum Keys: String, CodingKey { case teamId, entries }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: Keys.self)
            teamId = OnIceLineup.id(c, .teamId)
            entries = c.lossyArray(forKey: .entries) ?? []
        }
    }

    private struct Entry: Decodable {
        let athleteId: String
        let whereabouts: String
        private enum Keys: String, CodingKey { case athleteid, whereabouts }
        private enum WhereKeys: String, CodingKey { case name }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: Keys.self)
            athleteId = OnIceLineup.id(c, .athleteid)
            whereabouts = (try? c.nestedContainer(keyedBy: WhereKeys.self, forKey: .whereabouts))
                .map { OnIceLineup.text($0, .name) } ?? ""
        }
    }
}
