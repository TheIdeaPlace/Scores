//
//  RadioLinks.swift
//  SportsScores
//
//  Where to listen to a game on the radio. The twin of radio_links.py on Windows:
//  both read radio_links.json (this app's copy is held equal to the repo's by
//  tests/unit/test_radio_links_data.py) and both are held to
//  tests/fixtures/radio_links_grid.json. Change both together.
//
//  Everything is a web page that opens in Safari, or in the service's app when it
//  claims the link. The person signs in there if asked; nothing plays in this app.
//

import Foundation

struct ListenOption: Equatable, Hashable, Identifiable {
    let label: String
    let url: URL
    var id: String { url.absoluteString }
}

struct RadioDirectoryTeam: Identifiable {
    let id: String
    let name: String
    let station: String
    let links: [ListenOption]
}

struct RadioLinks {
    struct Link: Decodable {
        let label: String?
        let url: String?
    }
    struct Team: Decodable {
        let name: String?
        let station: String?
        let links: [Link]?
    }
    struct Table: Decodable {
        let links: [Link]?
        let teams: [String: Team]?
    }
    private struct File: Decodable {
        let tables: [String: Table]?
    }

    /// Which table each league reads. A league not here has no radio links yet.
    static let leagueTables: [String: String] = [
        "NFL": "NFL", "NBA": "NBA", "NHL": "NHL",
        "NCAAF": "NCAA", "NCAAM": "NCAA", "NCAAWB": "NCAA",
    ]

    let tables: [String: Table]

    init(tables: [String: Table] = [:]) {
        self.tables = tables
    }

    /// The links file, or no links when it can't be read.
    init(data: Data) {
        let file = try? JSONDecoder().decode(File.self, from: data)
        self.init(tables: file?.tables ?? [:])
    }

    /// The copy bundled with the app, read once.
    static let shared: RadioLinks = {
        guard let url = Bundle.main.url(forResource: "radio_links", withExtension: "json"),
              let data = try? Data(contentsOf: url) else { return RadioLinks() }
        return RadioLinks(data: data)
    }()

    private func table(_ league: String) -> Table? {
        leagueTables[league].flatMap { tables[$0] }
    }

    private static func usable(_ links: [Link]?) -> [ListenOption] {
        (links ?? []).compactMap { link in
            let label = (link.label ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let address = (link.url ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard !label.isEmpty, address.hasPrefix("https://"), let url = URL(string: address) else { return nil }
            return ListenOption(label: label, url: url)
        }
    }

    private static func unique(_ options: [ListenOption]) -> [ListenOption] {
        var seen = Set<String>()
        return options.filter { seen.insert($0.url.absoluteString).inserted }
    }

    /// Places that carry the whole league's games.
    func leagueOptions(_ league: String) -> [ListenOption] {
        Self.usable(table(league)?.links)
    }

    /// One team's own radio, each labelled with the team's name as the screen shows it.
    func teamOptions(_ league: String, teamId: String, teamName: String) -> [ListenOption] {
        guard !teamId.isEmpty, let entry = table(league)?.teams?[teamId] else { return [] }
        var name = teamName.trimmingCharacters(in: .whitespacesAndNewlines)
        if name.isEmpty { name = (entry.name ?? "").trimmingCharacters(in: .whitespacesAndNewlines) }
        return Self.usable(entry.links).map {
            ListenOption(label: name.isEmpty ? $0.label : "\(name): \($0.label)", url: $0.url)
        }
    }

    /// Where to hear a game, nearest first: the away team's radio, the home team's,
    /// then the places that carry the whole league. Away first, as the row reads.
    func gameOptions(_ league: String, awayId: String, awayName: String,
                     homeId: String, homeName: String) -> [ListenOption] {
        Self.unique(teamOptions(league, teamId: awayId, teamName: awayName)
                    + teamOptions(league, teamId: homeId, teamName: homeName)
                    + leagueOptions(league))
    }

    /// Where to hear a team's games: its own radio, then the league-wide places.
    func teamListenOptions(_ league: String, teamId: String, teamName: String) -> [ListenOption] {
        Self.unique(teamOptions(league, teamId: teamId, teamName: teamName) + leagueOptions(league))
    }

    func covers(_ league: String) -> Bool {
        guard let table = table(league) else { return false }
        return !leagueOptions(league).isEmpty || !(table.teams ?? [:]).isEmpty
    }

    /// Every team in a league's table, by name, links or not.
    func directory(_ league: String) -> [RadioDirectoryTeam] {
        (table(league)?.teams ?? [:]).map { id, team in
            RadioDirectoryTeam(id: id, name: team.name ?? id, station: team.station ?? "",
                               links: Self.usable(team.links))
        }
        .sorted { $0.name.lowercased() < $1.name.lowercased() }
    }

    /// The leagues with links, in the order The Bench lists them.
    static let directoryLeagues: [(league: String, title: String)] = [
        ("NFL", "NFL"), ("NBA", "NBA"), ("NHL", "NHL"), ("NCAAF", "College"),
    ]
}

extension Game {
    /// Where to hear this game, with each team named in full, as Windows names them.
    func listenOptions(league: String, links: RadioLinks = .shared) -> [ListenOption] {
        links.gameOptions(league, awayId: awayTeam.id, awayName: awayTeam.displayName,
                          homeId: homeTeam.id, homeName: homeTeam.displayName)
    }
}
