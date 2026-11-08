//
//  TeamStatsTests.swift
//  SportsScoresTests
//
//  League team statistics and a team's ranks on its Team Hub, on real byteam and core API
//  payloads with a stand-in for ESPN. tests/fixtures/team_stat_directions.json is the shared
//  reference for which way a stat ranks; tests/unit/test_team_stats.py holds Windows to it.
//

import XCTest
@testable import SportsScores

final class TeamStatDirectionGridTests: XCTestCase {
    private struct Grid: Decodable {
        struct Row: Decodable {
            let sport: String?
            let split: String
            let section: String
            let stat: String
            let higherIsBetter: Bool
        }
        struct RankCase: Decodable {
            let why: String
            let higherIsBetter: Bool
            let values: [Double]
            let ranks: [Int]
        }
        let lowIsGood: [String: [String]]
        let countsOfTries: [String: [String]]
        let catalog: [String: [Row]]
        let beyondTheCatalog: [Row]
        let rankGrid: [RankCase]
    }

    private func grid() throws -> Grid {
        let url = Fixtures.repoRoot.appendingPathComponent("tests/fixtures/team_stat_directions.json")
        return try JSONDecoder().decode(Grid.self, from: Data(contentsOf: url))
    }

    func testTheTableMatches() throws {
        let shared = try grid().lowIsGood.mapValues { Set($0) }
        XCTAssertEqual(TeamStatCatalog.lowIsGood, shared)
    }

    func testTheCountsOfTriesMatch() throws {
        let shared = try grid().countsOfTries.mapValues { Set($0) }
        XCTAssertEqual(TeamStatCatalog.countsOfTries, shared)
    }

    func testTheCatalogIsTheSharedOneInTheSameOrder() throws {
        let catalog = try grid().catalog
        let sports: [(String, Sport)] = [("baseball", .mlb), ("football", .nfl), ("basketball", .nba), ("hockey", .nhl)]
        XCTAssertEqual(Set(catalog.keys), Set(sports.map { $0.0 }))
        for (key, sport) in sports {
            let specs = TeamStatCatalog.specs(for: sport)
            let rows = try XCTUnwrap(catalog[key])
            XCTAssertEqual(specs.map(\.key), rows.map { ($0.split == "opponent" ? "opponent." : "") + "\($0.section).\($0.stat)" })
            XCTAssertEqual(specs.map(\.higherIsBetter), rows.map(\.higherIsBetter))
        }
    }

    func testEverySpecGoesTheWayTheTableSays() throws {
        for (key, rows) in try grid().catalog {
            for row in rows {
                let higher = TeamStatCatalog.higherIsBetter(sportKey: key, section: row.section, stat: row.stat,
                                                            opponent: row.split == "opponent")
                XCTAssertEqual(higher, row.higherIsBetter, "\(key) \(row.split) \(row.section).\(row.stat)")
            }
        }
    }

    func testTheRest() throws {
        for row in try grid().beyondTheCatalog {
            let higher = TeamStatCatalog.higherIsBetter(sportKey: try XCTUnwrap(row.sport), section: row.section,
                                                        stat: row.stat, opponent: row.split == "opponent")
            XCTAssertEqual(higher, row.higherIsBetter, "\(row.split) \(row.section).\(row.stat)")
        }
    }

    func testTheRankGrid() throws {
        for item in try grid().rankGrid {
            let ranks = item.values.map {
                TeamStatRanks.rank(of: $0, among: item.values, higherIsBetter: item.higherIsBetter)
            }
            XCTAssertEqual(ranks, item.ranks, item.why)
        }
    }

    func testOrdinals() {
        let reads = [1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 11: "11th", 12: "12th", 13: "13th", 21: "21st", 22: "22nd",
                     101: "101st", 111: "111th", 113: "113th", 118: "118th", 123: "123rd", 302: "302nd"]
        for (number, text) in reads {
            XCTAssertEqual(TeamStatRanks.ordinal(number), text)
        }
    }

    func testTheColorsBandsAreOfTheLeaguesOwnSize() {
        XCTAssertEqual(TeamStatRanks.band(rank: 8, of: 32), .top)
        XCTAssertEqual(TeamStatRanks.band(rank: 9, of: 32), .middle)
        XCTAssertEqual(TeamStatRanks.band(rank: 20, of: 32), .middle)
        XCTAssertEqual(TeamStatRanks.band(rank: 21, of: 32), .bottom)
        XCTAssertEqual(TeamStatRanks.band(rank: 3, of: 15), .top)
        XCTAssertEqual(TeamStatRanks.band(rank: 8, of: 15), .middle, "the top 8 of 15 aren't the top quarter")
        XCTAssertEqual(TeamStatRanks.band(rank: 118, of: 302), .middle)
        XCTAssertEqual(TeamStatRanks.band(rank: 21, of: 302), .top)
        XCTAssertEqual(TeamStatRanks.band(rank: 290, of: 302), .bottom)
        XCTAssertEqual(TeamStatRanks.band(rank: 1, of: nil), .unknown)
        XCTAssertEqual(TeamStatRanks.band(rank: 1, of: 0), .unknown)
    }

    func testHowARankReads() {
        XCTAssertEqual(TeamStatRanks.display(rank: 9, tied: false, outOf: nil), "9th")
        XCTAssertEqual(TeamStatRanks.display(rank: 9, tied: true, outOf: nil), "Tied-9th")
        XCTAssertEqual(TeamStatRanks.display(rank: 118, tied: false, outOf: 302), "118th of 302")
        XCTAssertEqual(TeamStatRanks.display(rank: 118, tied: true, outOf: 302), "Tied-118th of 302")
    }
}

/// Stands in for ESPN. A route's answer is real data, and the byteam ones say they're from the
/// season that was asked for, since "this season" depends on the day the tests run.
private final class TeamStatsESPN: URLProtocol {
    static let lock = NSLock()
    static var requests = [String]()
    static var answer: (String) -> (Int, Data) = { _ in (404, Data()) }
    static var networkError: URLError.Code?
    /// The core API's /season, by default the regular season, long under way, in the year the
    /// calendar says, so that Team Hub's asking by the calendar matches.
    static var seasonType = 2
    static var seasonStart = "2020-01-01T07:00Z"
    static var seasonStatus = 200

    static func reset(_ answer: @escaping (String) -> (Int, Data)) {
        lock.withLock {
            requests = []
            networkError = nil
            seasonType = 2
            seasonStart = "2020-01-01T07:00Z"
            seasonStatus = 200
            self.answer = answer
        }
    }

    static func year(in url: String) -> Int {
        if url.contains("/football/") { return Sport.nfl.currentSeasonYear }
        if url.contains("/baseball/") { return Sport.mlb.currentSeasonYear }
        if url.contains("/wnba/") { return Sport.wnba.currentSeasonYear }
        return Sport.nba.currentSeasonYear
    }

    private static func season(for url: String) -> Data {
        guard let data = try? Fixtures.data("season_NBA.json"),
              var object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              var type = object["type"] as? [String: Any] else { return Data() }
        object["year"] = year(in: url)
        type["type"] = seasonType
        type["startDate"] = seasonStart
        object["type"] = type
        return (try? JSONSerialization.data(withJSONObject: object)) ?? Data()
    }

    static var seasonRequests: [String] {
        lock.withLock { requests.filter { $0.hasSuffix("/season") } }
    }

    static var teamListRequests: [String] {
        lock.withLock { requests.filter { $0.contains("/teams?limit=1000") } }
    }

    static var byteamRequests: [String] {
        lock.withLock { requests.filter { $0.contains("/statistics/byteam") } }
    }

    static var coreRequests: [String] {
        lock.withLock { requests.filter { $0.contains("/seasons/") } }
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        guard let url = request.url else { return }
        let (error, reply) = Self.lock.withLock { () -> (URLError.Code?, (Int, Data)) in
            Self.requests.append(url.absoluteString)
            let reply = url.absoluteString.hasSuffix("/season")
                ? (Self.seasonStatus, Self.season(for: url.absoluteString))
                : Self.answer(url.absoluteString)
            return (Self.networkError, reply)
        }
        if let error {
            client?.urlProtocol(self, didFailWithError: URLError(error))
            return
        }
        let response = HTTPURLResponse(url: url, statusCode: reply.0, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: reply.1)
        client?.urlProtocolDidFinishLoading(self)
    }
}

/// A real payload saying it's from the season in the URL. The rest of it is as ESPN sent it.
private func byteam(_ name: String, askedBy url: String) -> (Int, Data) {
    guard let data = try? Fixtures.data(name),
          var object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
          var season = object["requestedSeason"] as? [String: Any],
          let range = url.range(of: #"season=\d+"#, options: .regularExpression),
          let year = Int(url[range].dropFirst("season=".count)) else {
        return (200, (try? Fixtures.data(name)) ?? Data())
    }
    season["year"] = year
    object["requestedSeason"] = season
    return (200, (try? JSONSerialization.data(withJSONObject: object)) ?? Data())
}

private func core(_ name: String) -> (Int, Data) {
    (200, (try? Fixtures.data(name)) ?? Data())
}

final class TeamStatsFixtureTests: XCTestCase {
    func testEveryByteamFixtureDecodes() throws {
        let files = try Fixtures.named("byteam_")
        XCTAssertGreaterThanOrEqual(files.count, 14)
        for file in files {
            let data = try Data(contentsOf: file)
            let response = try JSONDecoder().decode(TeamStatsByTeamResponse.self, from: data)
            XCTAssertEqual(response.teams?.count, try Fixtures.rawCount("teams", of: data), file.lastPathComponent)
            XCTAssertNotNil(response.requestedSeason?.type?.type, file.lastPathComponent)
        }
    }

    func testPaginationAndTheSeasonAreRead() throws {
        let response = try JSONDecoder().decode(TeamStatsByTeamResponse.self, from: Fixtures.data("byteam_NCAAM_2026.json"))
        XCTAssertEqual(response.pagination?.count, 722)
        XCTAssertEqual(response.requestedSeason?.year, 2026)
        XCTAssertEqual(response.requestedSeason?.type?.name, "Regular Season")
    }

    func testFootballHasNoPagination() throws {
        let response = try JSONDecoder().decode(TeamStatsByTeamResponse.self, from: Fixtures.data("byteam_NFL.json"))
        XCTAssertNil(response.pagination)
    }

    func testEveryCoreFixtureDecodes() throws {
        for name in ["core_team_stats_NBA_29.json", "core_team_stats_NCAAM_150.json", "core_team_stats_NFL_22.json",
                     "core_team_stats_NCAAF_333_2025.json", "core_team_stats_NCAAF_149.json"] {
            let response = try JSONDecoder().decode(CoreTeamStatisticsResponse.self, from: Fixtures.data(name))
            XCTAssertFalse(response.splits?.categories?.isEmpty ?? true, name)
        }
    }
}

final class DivisionOneTests: XCTestCase {
    private func load(_ name: String) throws -> TeamStatsByTeamResponse {
        try JSONDecoder().decode(TeamStatsByTeamResponse.self, from: Fixtures.data(name))
    }

    private func ids(_ teams: [LeagueTeamStats.Team]) -> Set<String> {
        Set(teams.compactMap(\.team.id))
    }

    private func onTheList(_ name: String) throws -> Set<String> {
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: Fixtures.data(name)) as? [String: Any])
        let sports = try XCTUnwrap(object["sports"] as? [[String: Any]])
        let leagues = try XCTUnwrap(sports.first?["leagues"] as? [[String: Any]])
        let teams = try XCTUnwrap(leagues.first?["teams"] as? [[String: Any]])
        return Set(teams.compactMap { ($0["team"] as? [String: Any])?["id"] as? String })
    }

    func testASchoolWithOneGameIsDroppedLateInASeason() throws {
        let response = try load("byteam_NCAAM_2026.json")
        XCTAssertTrue(ids(response.teams ?? []).contains("2145"), "the fixture should have UCCS, with one game")
        var expected = ids(response.teams ?? [])
        expected.remove("2145")
        let kept = LeagueTeamStats.divisionOneTeams(in: response, teamList: try onTheList("teams_NCAAM.json"))
        XCTAssertEqual(ids(kept), expected)
    }

    func testOpeningWeekTellsThemApartThoughEveryoneHasPlayedOnce() throws {
        let response = try load("byteam_NCAAM.json")
        let kept = LeagueTeamStats.divisionOneTeams(in: response, teamList: try onTheList("teams_NCAAM.json"))
        XCTAssertLessThan(kept.count, response.teams?.count ?? 0, "the fixture should have a non-Division I school")
        XCTAssertTrue(ids(kept).contains("150"), "Duke")
        XCTAssertTrue(ids(kept).isDisjoint(with: ["2358", "2650"]), "Lyon and Tougaloo")
    }

    func testASchoolMovingUpStaysWithNoOpponentsNumbers() throws {
        let response = try load("byteam_NCAAWB.json")
        let teams = response.teams ?? []
        XCTAssertEqual(teams.filter { !LeagueTeamStats.hasOpponents($0) }.count, 4, "the fixture should have 2 of each")
        let kept = LeagueTeamStats.divisionOneTeams(in: response, teamList: try onTheList("teams_NCAAWB.json"))
        let names = Set(kept.compactMap(\.team.displayName))
        XCTAssertTrue(names.isSuperset(of: ["East Texas A&M Lions", "Southern Indiana Screaming Eagles"]), "\(names)")
        XCTAssertEqual(kept.count, teams.count - 2)
    }

    func testAnEmptyTeamListOnlyKeepsThoseWithOpponentsNumbers() throws {
        XCTAssertEqual(LeagueTeamStats.divisionOneTeams(in: try load("byteam_NCAAWB.json"), teamList: []).count, 4)
    }

    func testOnlyCollegeBasketballHasOtherDivisions() {
        XCTAssertTrue(TeamStatCatalog.listHasOtherDivisions(.ncaam))
        XCTAssertTrue(TeamStatCatalog.listHasOtherDivisions(.ncaawb))
        for sport: Sport in [.ncaaf, .nba, .wnba, .nfl, .nhl, .mlb] {
            XCTAssertFalse(TeamStatCatalog.listHasOtherDivisions(sport), "\(sport)")
        }
    }

    func testNoListMeansNoFilter() throws {
        let response = try load("byteam_NCAAWB.json")
        XCTAssertEqual(LeagueTeamStats(response, sport: .ncaaf).teams.count, response.teams?.count)
    }
}

final class CoreSeasonTests: XCTestCase {
    private func decoded(type: Int, start: String?) throws -> CoreSeasonResponse {
        let startJSON = start.map { "\"\($0)\"" } ?? "null"
        return try JSONDecoder().decode(CoreSeasonResponse.self,
                                        from: Data(#"{"year":2027,"type":{"type":\#(type),"startDate":\#(startJSON)}}"#.utf8))
    }

    private let start = Date(timeIntervalSince1970: 1_792_479_600)  // 2026-10-20T07:00Z

    func testTheRealPayloadDecodes() throws {
        let season = try JSONDecoder().decode(CoreSeasonResponse.self, from: Fixtures.data("season_NBA.json"))
        XCTAssertEqual(season.latestRegularSeasonYear, 2027)
        XCTAssertNotNil(season.type?.startDate)
    }

    func testAPreseasonMeansLastSeason() throws {
        XCTAssertEqual(try decoded(type: 1, start: nil).latestRegularSeasonYear, 2026)
        XCTAssertEqual(try decoded(type: 3, start: nil).latestRegularSeasonYear, 2027)
    }

    func testJustBegan() throws {
        let season = try decoded(type: 2, start: "2026-10-20T07:00Z")
        XCTAssertTrue(season.regularSeasonJustBegan(now: start.addingTimeInterval(60)))
        XCTAssertTrue(season.regularSeasonJustBegan(now: start.addingTimeInterval(2.9 * 86400)))
        XCTAssertFalse(season.regularSeasonJustBegan(now: start.addingTimeInterval(3.1 * 86400)))
        XCTAssertFalse(season.regularSeasonJustBegan(now: start.addingTimeInterval(-60)))
    }

    func testOnlyARegularSeasonWithADateCounts() throws {
        XCTAssertFalse(try decoded(type: 3, start: "2026-10-20T07:00Z").regularSeasonJustBegan(now: start))
        XCTAssertFalse(try decoded(type: 2, start: nil).regularSeasonJustBegan(now: start))
        XCTAssertFalse(try decoded(type: 2, start: "whenever").regularSeasonJustBegan(now: start))
    }
}

final class TeamStatsRequestTests: XCTestCase {
    private var service: ESPNAPIService!

    override func setUp() {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [TeamStatsESPN.self]
        service = ESPNAPIService(session: URLSession(configuration: config))
    }

    private func category(_ categories: [LeagueLeaderCategory], _ key: String) throws -> LeagueLeaderCategory {
        try XCTUnwrap(categories.first { $0.name == key }, key)
    }

    // MARK: Which season

    func testAsksForTheRegularSeasonOfThisSeasonAtOnce() async throws {
        TeamStatsESPN.reset { byteam("byteam_NBA.json", askedBy: $0) }
        let categories = try await service.fetchTeamLeaders(for: .nba, limit: 50)
        XCTAssertFalse(categories.isEmpty)
        let asked = TeamStatsESPN.byteamRequests
        XCTAssertEqual(asked.count, 1)
        XCTAssertTrue(asked[0].contains("season=\(Sport.nba.currentSeasonYear)&seasontype=2"), asked[0])
        XCTAssertTrue(asked[0].contains("limit=500"), asked[0])
        XCTAssertEqual(try category(categories, "offensive.avgPoints").leaders.count, 30)
    }

    func testThePlayoffTeamsAreNotWhatItShowsOutOfSeason() async throws {
        // ESPN's own default, once a season ends: the 8 playoff teams, where it has 15.
        TeamStatsESPN.reset { url in
            byteam(url.contains("seasontype=2") ? "byteam_WNBA.json" : "byteam_WNBA_default.json", askedBy: url)
        }
        let categories = try await service.fetchTeamLeaders(for: .wnba, limit: 50)
        XCTAssertEqual(try category(categories, "offensive.avgPoints").leaders.count, 15)
        XCTAssertEqual(TeamStatsESPN.byteamRequests.count, 1)
    }

    func testMLBsWholeLeagueNotItsPlayoffTeams() async throws {
        TeamStatsESPN.reset { url in
            byteam(url.contains("seasontype=2") ? "byteam_MLB.json" : "byteam_MLB_default.json", askedBy: url)
        }
        let categories = try await service.fetchTeamLeaders(for: .mlb, limit: 50)
        let raw = try JSONDecoder().decode(TeamStatsByTeamResponse.self, from: Fixtures.data("byteam_MLB.json"))
        XCTAssertEqual(try category(categories, "batting.runs").leaders.count, raw.teams?.count)
    }

    func testANewSeasonWithNothingYetIsLastSeasons() async throws {
        let thisYear = Sport.nfl.currentSeasonYear
        TeamStatsESPN.reset { url in
            url.contains("season=\(thisYear)&") ? (200, Data("{}".utf8)) : byteam("byteam_NFL.json", askedBy: url)
        }
        let categories = try await service.fetchTeamLeaders(for: .nfl)
        XCTAssertFalse(categories.isEmpty)
        let asked = TeamStatsESPN.byteamRequests
        XCTAssertEqual(asked.count, 2)
        XCTAssertTrue(asked[1].contains("season=\(thisYear - 1)&seasontype=2"), asked[1])
    }

    private func iso(daysAgo: Double) -> String {
        let format = DateFormatter()
        format.locale = Locale(identifier: "en_US_POSIX")
        format.timeZone = TimeZone(secondsFromGMT: 0)
        format.dateFormat = "yyyy-MM-dd'T'HH:mm'Z'"
        return format.string(from: Date().addingTimeInterval(-daysAgo * 86400))
    }

    func testA500AsARegularSeasonBeginsIsLastSeasonLabelled() async throws {
        let thisYear = Sport.nba.currentSeasonYear
        TeamStatsESPN.reset { url in
            url.contains("season=\(thisYear)&") ? (500, Data()) : byteam("byteam_NBA.json", askedBy: url)
        }
        TeamStatsESPN.lock.withLock { TeamStatsESPN.seasonStart = iso(daysAgo: 0.2) }
        let categories = try await service.fetchTeamLeaders(for: .nba)
        XCTAssertFalse(categories.isEmpty)
        XCTAssertEqual(TeamStatsESPN.byteamRequests.count, 2)
        XCTAssertTrue(TeamStatsESPN.byteamRequests[1].contains("season=\(thisYear - 1)&"))
    }

    func testAOneOff500InMidSeasonIsAnErrorNotLastSeason() async throws {
        // An NBA 500 in January used to show last season's numbers as current for 15 minutes.
        let thisYear = Sport.nba.currentSeasonYear
        TeamStatsESPN.reset { url in
            url.contains("season=\(thisYear)&") ? (500, Data()) : byteam("byteam_NBA.json", askedBy: url)
        }
        do {
            _ = try await service.fetchTeamLeaders(for: .nba)
            XCTFail("it should have thrown")
        } catch is APIError {
            XCTAssertEqual(TeamStatsESPN.byteamRequests.count, 1)
        }
    }

    func testA500AWeekIntoASeasonIsAnError() async throws {
        TeamStatsESPN.reset { _ in (500, Data()) }
        TeamStatsESPN.lock.withLock { TeamStatsESPN.seasonStart = iso(daysAgo: 7) }
        do {
            _ = try await service.fetchTeamLeaders(for: .nba)
            XCTFail("it should have thrown")
        } catch is APIError {
            XCTAssertEqual(TeamStatsESPN.byteamRequests.count, 1)
        }
    }

    func testLastSeasonFailingTooIsAnError() async throws {
        TeamStatsESPN.reset { _ in (500, Data()) }
        TeamStatsESPN.lock.withLock { TeamStatsESPN.seasonStart = iso(daysAgo: 0.2) }
        do {
            _ = try await service.fetchTeamLeaders(for: .nba)
            XCTFail("it should have thrown")
        } catch is APIError {
            XCTAssertEqual(TeamStatsESPN.byteamRequests.count, 2)
        }
    }

    func testNoSuchSeasonEitherYearIsAnError() async throws {
        TeamStatsESPN.reset { _ in (404, Data()) }
        do {
            _ = try await service.fetchTeamLeaders(for: .nba)
            XCTFail("it should have thrown")
        } catch is APIError {
            XCTAssertEqual(TeamStatsESPN.byteamRequests.count, 2)
        }
    }

    func testAPreseasonMeansLastSeasonsRegularSeason() async throws {
        let thisYear = Sport.nba.currentSeasonYear
        TeamStatsESPN.reset { byteam("byteam_NBA.json", askedBy: $0) }
        TeamStatsESPN.lock.withLock { TeamStatsESPN.seasonType = 1 }
        _ = try await service.fetchTeamLeaders(for: .nba)
        XCTAssertTrue(TeamStatsESPN.byteamRequests[0].contains("season=\(thisYear - 1)&"))
    }

    func testNotKnowingTheSeasonIsAnError() async throws {
        TeamStatsESPN.reset { byteam("byteam_NBA.json", askedBy: $0) }
        TeamStatsESPN.lock.withLock { TeamStatsESPN.seasonStatus = 500 }
        do {
            _ = try await service.fetchTeamLeaders(for: .nba)
            XCTFail("it should have thrown")
        } catch is APIError {
            XCTAssertTrue(TeamStatsESPN.byteamRequests.isEmpty)
        }
    }

    // MARK: Saying which season

    func testTheListSaysWhichSeason() async throws {
        TeamStatsESPN.reset { byteam("byteam_NBA.json", askedBy: $0) }
        let categories = try await service.fetchTeamLeaders(for: .nba)
        XCTAssertEqual(categories.first?.seasonLabel, "2026-27 Regular Season")
        XCTAssertTrue(categories.allSatisfy { $0.seasonLabel == categories.first?.seasonLabel })
    }

    func testAPastCollegeFootballSeasonSaysSeasonNotPostseason() async throws {
        TeamStatsESPN.reset { byteam("byteam_NCAAF_2025.json", askedBy: $0) }
        let categories = try await service.fetchTeamLeaders(for: .ncaaf)
        XCTAssertEqual(categories.first?.seasonLabel, "2025 Season")
    }

    func testPastWhatBothWaysCanReachItSaysSo() async throws {
        TeamStatsESPN.reset { [self] in answerByDirection($0) }
        let categories = try await service.fetchTeamLeaders(for: .ncaam)
        XCTAssertEqual(categories.first?.seasonLabel, "2025-26 Regular Season, some teams missing")
    }

    func testAWholeListDoesntSaySo() throws {
        let response = try JSONDecoder().decode(TeamStatsByTeamResponse.self, from: Fixtures.data("byteam_NBA.json"))
        XCTAssertEqual(response.seasonLabel, "2026-27 Regular Season")
    }

    func testNoSeasonNoLabel() {
        XCTAssertNil(TeamStatsByTeamResponse(teams: [], categories: nil, pagination: nil, requestedSeason: nil).seasonLabel)
    }

    // MARK: Division I

    func testEveryDivisionOneTeamIsListedAndNoOneElse() async throws {
        TeamStatsESPN.reset { url in
            url.contains("/teams?") ? core("teams_NCAAWB.json") : byteam("byteam_NCAAWB.json", askedBy: url)
        }
        let categories = try await service.fetchTeamLeaders(for: .ncaawb, limit: .max)
        let names = Set(try category(categories, "offensive.avgPoints").leaders.compactMap { $0.teamNames?.displayName })
        XCTAssertTrue(names.isSuperset(of: ["East Texas A&M Lions", "Southern Indiana Screaming Eagles"]), "\(names)")
        XCTAssertEqual(names.count, 6)
        XCTAssertEqual(TeamStatsESPN.teamListRequests.count, 1)
    }

    func testTheTeamListFailingFailsTheLot() async throws {
        TeamStatsESPN.reset { url in
            url.contains("/teams?") ? (500, Data()) : byteam("byteam_NCAAWB.json", askedBy: url)
        }
        do {
            _ = try await service.fetchTeamLeaders(for: .ncaawb)
            XCTFail("real teams would be missing, and the ranks after them wrong")
        } catch is APIError {
            XCTAssertEqual(TeamStatsESPN.teamListRequests.count, 1)
        }
    }

    func testOnlyCollegeBasketballAsksForTheTeamList() async throws {
        TeamStatsESPN.reset { byteam("byteam_NCAAF.json", askedBy: $0) }
        _ = try await service.fetchTeamLeaders(for: .ncaaf)
        XCTAssertTrue(TeamStatsESPN.teamListRequests.isEmpty)
    }

    func testNothingForEitherSeasonIsNothingToShow() async throws {
        TeamStatsESPN.reset { _ in (200, Data("{}".utf8)) }
        let categories = try await service.fetchTeamLeaders(for: .nba)
        XCTAssertTrue(categories.isEmpty)
    }

    func testAStalledNetworkIsAnErrorNotAnotherSeason() async throws {
        TeamStatsESPN.reset { _ in (200, Data()) }
        TeamStatsESPN.lock.withLock { TeamStatsESPN.networkError = .timedOut }
        do {
            _ = try await service.fetchTeamLeaders(for: .nba)
            XCTFail("it should have thrown")
        } catch is URLError {
            XCTAssertEqual(TeamStatsESPN.seasonRequests.count, 1)
            XCTAssertTrue(TeamStatsESPN.byteamRequests.isEmpty)
        }
    }

    func testAStalledNetworkAfterTheSeasonIsNotAnotherSeasonEither() async throws {
        TeamStatsESPN.reset { url in
            if url.contains("/statistics/byteam") {
                TeamStatsESPN.networkError = .timedOut
            }
            return (200, Data())
        }
        do {
            _ = try await service.fetchTeamLeaders(for: .nba)
            XCTFail("it should have thrown")
        } catch is URLError {
            XCTAssertEqual(TeamStatsESPN.byteamRequests.count, 1)
        }
    }

    func testNullShowingZeroRanksAsZero() throws {
        // Hockey's shootout columns: an NHL team yet to go to one has "0" with a null.
        let response = try JSONDecoder().decode(TeamStatsByTeamResponse.self, from: Fixtures.data("byteam_NHL.json"))
        let league = LeagueTeamStats(response, sport: .nhl)
        XCTAssertEqual(league.rows(section: "offensive", stat: "shootoutAttempts").count, response.teams?.count)
    }

    func testAPreseasonAnswerIsNotShown() async throws {
        let thisYear = Sport.nba.currentSeasonYear
        TeamStatsESPN.reset { url in
            let (status, data) = byteam("byteam_NBA.json", askedBy: url)
            guard url.contains("season=\(thisYear)&"),
                  var object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
                  var season = object["requestedSeason"] as? [String: Any] else { return (status, data) }
            season["type"] = ["type": 1, "name": "Preseason"]
            object["requestedSeason"] = season
            return (status, (try? JSONSerialization.data(withJSONObject: object)) ?? Data())
        }
        _ = try await service.fetchTeamLeaders(for: .nba)
        XCTAssertTrue(TeamStatsESPN.byteamRequests.last?.contains("season=\(thisYear - 1)&") ?? false)
    }

    func testAPayloadIsAskedForOnceAcrossItsUsers() async throws {
        TeamStatsESPN.reset { byteam("byteam_NBA.json", askedBy: $0) }
        _ = try await service.fetchTeamLeaders(for: .nba)
        _ = try await service.fetchTeamLeaders(for: .nba, limit: 50)
        XCTAssertEqual(TeamStatsESPN.byteamRequests.count, 1)
    }

    // MARK: Past the most ESPN returns

    private func answerByDirection(_ url: String) -> (Int, Data) {
        if url.contains("/teams?") { return core("teams_NCAAM.json") }
        if url.contains(":desc") { return byteam("byteam_NCAAM_2026_desc.json", askedBy: url) }
        if url.contains(":asc") { return byteam("byteam_NCAAM_2026_asc.json", askedBy: url) }
        return byteam("byteam_NCAAM_2026.json", askedBy: url)
    }

    func testAListCutShortIsAskedForEachWay() async throws {
        TeamStatsESPN.reset { [self] in answerByDirection($0) }
        let categories = try await service.fetchTeamLeaders(for: .ncaam, limit: .max)
        let asked = TeamStatsESPN.byteamRequests
        XCTAssertEqual(asked.count, 3)
        XCTAssertFalse(asked[0].contains("sort="))
        XCTAssertTrue(asked[1].contains("sort=offensive.avgTurnovers:desc"), asked[1])
        XCTAssertTrue(asked[2].contains("sort=offensive.avgTurnovers:asc"), asked[2])

        var wanted = Set<String>()
        for name in ["byteam_NCAAM_2026.json", "byteam_NCAAM_2026_desc.json", "byteam_NCAAM_2026_asc.json"] {
            let raw = try JSONDecoder().decode(TeamStatsByTeamResponse.self, from: Fixtures.data(name))
            wanted.formUnion((raw.teams ?? []).compactMap(\.team.displayName))
        }
        wanted = wanted.filter { !$0.hasPrefix("Colorado Colorado Springs") }  // one game
        let listed = try category(categories, "offensive.avgPoints").leaders.compactMap { $0.teamNames?.displayName }
        XCTAssertEqual(Set(listed), wanted)
        XCTAssertEqual(listed.count, wanted.count, "each team once")
    }

    func testAFailurePartWayFailsTheLot() async throws {
        for direction in [":desc", ":asc"] {
            let config = URLSessionConfiguration.ephemeral
            config.protocolClasses = [TeamStatsESPN.self]
            let fresh = ESPNAPIService(session: URLSession(configuration: config))
            TeamStatsESPN.reset { [self] url in url.contains(direction) ? (500, Data()) : answerByDirection(url) }
            do {
                _ = try await fresh.fetchTeamLeaders(for: .ncaam)
                XCTFail("a list with teams cut out still looks whole, with the ranks after them wrong")
            } catch is APIError {
                XCTAssertFalse(TeamStatsESPN.byteamRequests.contains { $0.contains("season=\(Sport.ncaam.currentSeasonYear - 1)") },
                               "not last season instead")
            }
        }
    }

    func testAListThatFitsIsAskedForOnce() async throws {
        TeamStatsESPN.reset { byteam("byteam_NBA.json", askedBy: $0) }
        _ = try await service.fetchTeamLeaders(for: .nba)
        XCTAssertFalse(TeamStatsESPN.byteamRequests.contains { $0.contains("sort=") })
    }

    func testFootballHasNoColumnToSortBySoNeverAsks() async throws {
        TeamStatsESPN.reset { url in
            guard let data = try? Fixtures.data("byteam_NFL.json"),
                  var object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { return (500, Data()) }
            object["pagination"] = ["count": 400]
            return (200, (try? JSONSerialization.data(withJSONObject: object)) ?? Data())
        }
        _ = try await service.fetchTeamLeaders(for: .nfl)
        XCTAssertFalse(TeamStatsESPN.byteamRequests.contains { $0.contains("sort=") })
    }

    // MARK: Direction

    private func values(_ category: LeagueLeaderCategory) -> [Double] {
        category.leaders.compactMap { Double($0.displayValue.replacingOccurrences(of: ",", with: "")) }
    }

    func testLowestFirstWhereLowIsGood() async throws {
        TeamStatsESPN.reset { byteam("byteam_NBA.json", askedBy: $0) }
        let categories = try await service.fetchTeamLeaders(for: .nba, limit: .max)
        for key in ["offensive.avgTurnovers", "general.avgFouls", "opponent.offensive.avgPoints"] {
            let numbers = values(try category(categories, key))
            XCTAssertEqual(numbers, numbers.sorted(), key)
            XCTAssertLessThan(numbers.first ?? 0, numbers.last ?? 0, key)
        }
    }

    func testHighestFirstWhereHighIsGood() async throws {
        TeamStatsESPN.reset { byteam("byteam_NBA.json", askedBy: $0) }
        let categories = try await service.fetchTeamLeaders(for: .nba, limit: .max)
        let numbers = values(try category(categories, "offensive.avgPoints"))
        XCTAssertEqual(numbers, numbers.sorted(by: >))
    }

    func testTeamsLevelShareARankAndTheNextRankCountsThem() async throws {
        TeamStatsESPN.reset { byteam("byteam_NFL.json", askedBy: $0) }
        let categories = try await service.fetchTeamLeaders(for: .nfl, limit: .max)
        let leaders = try category(categories, "miscellaneous.totalGiveaways").leaders
        let numbers = values(try category(categories, "miscellaneous.totalGiveaways"))
        XCTAssertEqual(numbers, numbers.sorted())
        XCTAssertLessThan(Set(numbers).count, numbers.count, "the fixture should have a tie")
        for (entry, number) in zip(leaders, numbers) {
            XCTAssertEqual(entry.rank, 1 + numbers.filter { $0 < number }.count, entry.athleteName)
        }
    }

    func testTheLimitCutsTheList() async throws {
        TeamStatsESPN.reset { byteam("byteam_NBA.json", askedBy: $0) }
        let categories = try await service.fetchTeamLeaders(for: .nba, limit: 3)
        XCTAssertEqual(try category(categories, "offensive.avgPoints").leaders.count, 3)
    }

    // MARK: Team Hub agrees with the league list

    private func hub(sport: Sport, teamId: String, core coreFile: String, byteam byteamFile: String) async throws -> [TeamStatRanking] {
        TeamStatsESPN.reset { url in
            if url.contains("/seasons/") { return core(coreFile) }
            if url.contains("/teams?") { return core("teams_NCAAM.json") }
            return byteam(byteamFile, askedBy: url)
        }
        return try await service.fetchTeamStatRankings(teamId: teamId, sport: sport)
    }

    /// Every own-split stat the list shows that the Team Hub also has, read off the list for this team.
    private func assertAgree(sport: Sport, teamId: String, teamName: String, rankings: [TeamStatRanking],
                             core coreFile: String, atLeast: Int, file: StaticString = #filePath, line: UInt = #line) async throws {
        let list = try await service.fetchTeamLeaders(for: sport, limit: .max)
        let response = try JSONDecoder().decode(CoreTeamStatisticsResponse.self, from: Fixtures.data(coreFile))
        var checked = 0
        for spec in TeamStatCatalog.specs(for: sport) where spec.split == .own {
            let stat = response.splits?.categories?
                .first { $0.name?.lowercased() == spec.section.lowercased() }?
                .stats?.first { $0.name == spec.stat }
            guard let shown = stat?.displayName, let category = list.first(where: { $0.name == spec.key }),
                  let row = rankings.first(where: { $0.categoryDisplayName == shown && $0.teamValue == stat?.displayValue }),
                  let entry = category.leaders.first(where: { $0.teamNames?.displayName == teamName }) else { continue }
            checked += 1
            XCTAssertEqual(row.leagueRank, entry.rank, "\(spec.key)", file: file, line: line)
        }
        XCTAssertGreaterThanOrEqual(checked, atLeast, "enough stats to show they agree", file: file, line: line)
    }

    func testTheHubAgreesWithTheListForAnNBATeam() async throws {
        let rankings = try await hub(sport: .nba, teamId: "29", core: "core_team_stats_NBA_29.json", byteam: "byteam_NBA.json")
        try await assertAgree(sport: .nba, teamId: "29", teamName: "Memphis Grizzlies", rankings: rankings,
                              core: "core_team_stats_NBA_29.json", atLeast: 10)
    }

    func testTheHubAgreesWithTheListForACollegeTeam() async throws {
        let rankings = try await hub(sport: .ncaam, teamId: "150", core: "core_team_stats_NCAAM_150.json", byteam: "byteam_NCAAM.json")
        try await assertAgree(sport: .ncaam, teamId: "150", teamName: "Duke Blue Devils", rankings: rankings,
                              core: "core_team_stats_NCAAM_150.json", atLeast: 10)
    }

    func testTheHubAgreesWithTheListForAnNFLTeam() async throws {
        let rankings = try await hub(sport: .nfl, teamId: "22", core: "core_team_stats_NFL_22.json", byteam: "byteam_NFL.json")
        try await assertAgree(sport: .nfl, teamId: "22", teamName: "Arizona Cardinals", rankings: rankings,
                              core: "core_team_stats_NFL_22.json", atLeast: 5)
    }

    func testAPerGameStatESPNHasNoRankForNowHasOne() async throws {
        let rankings = try await hub(sport: .nba, teamId: "29", core: "core_team_stats_NBA_29.json", byteam: "byteam_NBA.json")
        XCTAssertNotNil(rankings.first { $0.categoryDisplayName == "Points Per Game" })
    }

    func testATotalReadsItsOwnRankNotESPNsPerGameOne() async throws {
        // The core API has the Grizzlies' 192 assists Tied-5th. They're 11th in that list.
        let rankings = try await hub(sport: .nba, teamId: "29", core: "core_team_stats_NBA_29.json", byteam: "byteam_NBA.json")
        let league = try JSONDecoder().decode(TeamStatsByTeamResponse.self, from: Fixtures.data("byteam_NBA.json"))
        let standing = try XCTUnwrap(LeagueTeamStats(league, sport: .nba).standing(ofTeam: "29", section: "offensive", stat: "assists"))
        let assists = try XCTUnwrap(rankings.first { $0.categoryDisplayName == "Assists" })
        XCTAssertEqual(assists.leagueRank, standing.rank)
    }

    func testAProRankHasNoOutOf() async throws {
        let rankings = try await hub(sport: .nba, teamId: "29", core: "core_team_stats_NBA_29.json", byteam: "byteam_NBA.json")
        XCTAssertFalse(rankings.isEmpty)
        XCTAssertFalse(rankings.contains { $0.rankDisplay.contains(" of ") })
        XCTAssertTrue(rankings.allSatisfy { $0.leagueSize == 30 })
    }

    func testACollegeRankSaysWhatItsOutOf() async throws {
        let rankings = try await hub(sport: .ncaam, teamId: "150", core: "core_team_stats_NCAAM_150.json", byteam: "byteam_NCAAM.json")
        XCTAssertFalse(rankings.isEmpty)
        let size = try XCTUnwrap(rankings.first?.leagueSize)
        XCTAssertTrue(rankings.allSatisfy { $0.rankDisplay.hasSuffix(" of \(size)") }, "\(rankings.map(\.rankDisplay))")
    }

    func testCollegeRanksPastThirtyFourAreKept() async throws {
        // With no list to rank against, ESPN's own: Duke's points are Tied-118th.
        TeamStatsESPN.reset { url in
            url.contains("/seasons/") ? core("core_team_stats_NCAAM_150.json") : (404, Data())
        }
        let rankings = try await service.fetchTeamStatRankings(teamId: "150", sport: .ncaam)
        let points = try XCTUnwrap(rankings.first { $0.categoryDisplayName == "Points" })
        XCTAssertEqual(points.rankDisplay, "Tied-118th")
        XCTAssertNil(points.leagueSize)
    }

    func testAProRankPastTheEndOfTheLeagueIsStillHidden() async throws {
        // Kick return fair catch percentage reads 200th in the NFL's core payload.
        TeamStatsESPN.reset { url in
            url.contains("/seasons/") ? core("core_team_stats_NFL_22.json") : (404, Data())
        }
        let rankings = try await service.fetchTeamStatRankings(teamId: "22", sport: .nfl)
        XCTAssertFalse(rankings.isEmpty)
        XCTAssertTrue(rankings.allSatisfy { $0.leagueRank <= 34 }, "\(rankings.map(\.leagueRank).max() ?? 0)")
    }

    func testARankPastTheLeaguesSizeIsHiddenWithTheListToo() async throws {
        let rankings = try await hub(sport: .nfl, teamId: "22", core: "core_team_stats_NFL_22.json", byteam: "byteam_NFL.json")
        let size = try XCTUnwrap(rankings.first?.leagueSize)
        XCTAssertTrue(rankings.allSatisfy { $0.leagueRank <= size })
    }

    func testAType3ListIsNotRankedAgainstType2Numbers() async throws {
        // Alabama's 3,551 passing yards in 2025 are the regular season's, 11th. The list runs
        // through the bowls, where it has 3,953: read against that, 3,551 was "6th of 136".
        let rankings = try await hub(sport: .ncaaf, teamId: "333", core: "core_team_stats_NCAAF_333_2025.json",
                                     byteam: "byteam_NCAAF_2025.json")
        let passing = try XCTUnwrap(rankings.first { $0.teamValue == "3,551" && $0.categoryDisplayName == "Passing Yards" })
        XCTAssertEqual(passing.leagueRank, 11)
        XCTAssertEqual(passing.rankDisplay, "11th")
        XCTAssertNil(passing.leagueSize)
    }

    func testATeamNotOnTheListDoesNotReadOutOfItsSize() async throws {
        // Montana is in FCS, and college football's list is FBS.
        let rankings = try await hub(sport: .ncaaf, teamId: "149", core: "core_team_stats_NCAAF_149.json",
                                     byteam: "byteam_NCAAF.json")
        XCTAssertFalse(rankings.isEmpty)
        XCTAssertFalse(rankings.contains { $0.rankDisplay.contains(" of ") }, "\(rankings.map(\.rankDisplay).prefix(5))")
        XCTAssertTrue(rankings.allSatisfy { $0.leagueSize == nil })
    }

    func testATeamNotOnTheListKeepsARankPastTheListsSize() async throws {
        let rankings = try await hub(sport: .ncaaf, teamId: "149", core: "core_team_stats_NCAAF_149.json",
                                     byteam: "byteam_NCAAF.json")
        let tackles = try XCTUnwrap(rankings.first { $0.categoryDisplayName == "Total Tackles" })
        XCTAssertEqual(tackles.rankDisplay, "Tied-363rd")
    }

    func testAListFromAnotherSeasonIsNotRankedAgainst() async throws {
        let thisYear = Sport.nba.currentSeasonYear
        TeamStatsESPN.reset { url in
            if url.contains("/seasons/") { return core("core_team_stats_NBA_29.json") }
            // This season's list has nothing, so the store settles on last season's.
            return url.contains("season=\(thisYear)&") ? (200, Data("{}".utf8)) : byteam("byteam_NBA.json", askedBy: url)
        }
        let rankings = try await service.fetchTeamStatRankings(teamId: "29", sport: .nba)
        XCTAssertTrue(rankings.allSatisfy { $0.leagueSize == nil })
        XCTAssertNil(rankings.first { $0.categoryDisplayName == "Points Per Game" }, "ESPN has no rank for it")
    }

    // MARK: Team Hub's season

    func testTheHubAsksOnlyForTheRegularSeasonInThisSeasonThenLast() async throws {
        let thisYear = Sport.nfl.currentSeasonYear
        TeamStatsESPN.reset { url in
            if url.contains("/statistics/byteam") { return byteam("byteam_NFL.json", askedBy: url) }
            return url.contains("/seasons/\(thisYear - 1)/types/2/") ? core("core_team_stats_NFL_22.json") : (404, Data())
        }
        let rankings = try await service.fetchTeamStatRankings(teamId: "22", sport: .nfl)
        XCTAssertFalse(rankings.isEmpty)
        let asked = TeamStatsESPN.coreRequests
        XCTAssertEqual(asked.count, 2, "\(asked)")
        XCTAssertTrue(asked[0].contains("/seasons/\(thisYear)/types/2/"), asked[0])
        XCTAssertTrue(asked[1].contains("/seasons/\(thisYear - 1)/types/2/"), asked[1])
    }

    func testTheHubNeverFallsThroughToAPreseason() async throws {
        TeamStatsESPN.reset { url in
            if url.contains("/statistics/byteam") { return (200, Data("{}".utf8)) }
            return url.contains("/types/1/") ? core("core_team_stats_NFL_22.json") : (404, Data())
        }
        let rankings = try await service.fetchTeamStatRankings(teamId: "22", sport: .mlb)
        XCTAssertTrue(rankings.isEmpty)
        XCTAssertFalse(TeamStatsESPN.coreRequests.contains { $0.contains("/types/1/") || $0.contains("/types/3/") })
    }

    func testSoccerIsFiledUnderTypeOne() async throws {
        let sport = try XCTUnwrap(Sport.soccerLeagues.first)
        TeamStatsESPN.reset { _ in (404, Data()) }
        _ = try await service.fetchTeamStatRankings(teamId: "359", sport: sport)
        XCTAssertTrue(TeamStatsESPN.coreRequests.first?.contains("/types/1/") ?? false)
        XCTAssertTrue(TeamStatsESPN.byteamRequests.isEmpty, "ESPN has none, and answers with a 500")
    }

    func testAStalledNetworkOnTheHubIsAnError() async throws {
        TeamStatsESPN.reset { _ in (200, Data()) }
        TeamStatsESPN.lock.withLock { TeamStatsESPN.networkError = .timedOut }
        do {
            _ = try await service.fetchTeamStatRankings(teamId: "22", sport: .nfl)
            XCTFail("it should have thrown")
        } catch is URLError {
            // One timeout before Retry appears: nothing else is asked once the list has stalled.
            XCTAssertEqual(TeamStatsESPN.coreRequests.count, 0)
        }
    }

    func testAFailedCoreRequestIsNoRankingsNotAnError() async throws {
        TeamStatsESPN.reset { url in
            url.contains("/statistics/byteam") ? byteam("byteam_NFL.json", askedBy: url) : (500, Data())
        }
        let rankings = try await service.fetchTeamStatRankings(teamId: "22", sport: .nfl)
        XCTAssertTrue(rankings.isEmpty)
    }

    // MARK: The same as Windows

    private struct HubGrid: Decodable {
        struct Row: Decodable {
            let section: String
            let category: String
            let value: String
            let rank: String
        }
        struct Case: Decodable {
            let sport: String
            let teamId: String
            let core: String
            let byteam: String
            let rows: [Row]
        }
        let team: [Case]
    }

    /// tests/fixtures/team_hub_stats_grid.json holds what Windows's Team Hub shows for the same
    /// answers, grouped by section as TeamStatsTabView shows them.
    func testTheHubReadsAsTheSharedGridSays() async throws {
        let url = Fixtures.repoRoot.appendingPathComponent("tests/fixtures/team_hub_stats_grid.json")
        let grid = try JSONDecoder().decode(HubGrid.self, from: Data(contentsOf: url))
        XCTAssertGreaterThanOrEqual(grid.team.count, 5)
        for item in grid.team {
            // A service of its own, so no case is ranked against a league list another case left in the store.
            let config = URLSessionConfiguration.ephemeral
            config.protocolClasses = [TeamStatsESPN.self]
            service = ESPNAPIService(session: URLSession(configuration: config))
            let sport = try XCTUnwrap(Sport(rawValue: item.sport), item.sport)
            let rankings = try await hub(sport: sport, teamId: item.teamId, core: item.core, byteam: item.byteam)
            let order = rankings.map(\.sectionName).reduce(into: [String]()) { if !$0.contains($1) { $0.append($1) } }
            let shown = order.flatMap { section in rankings.filter { $0.sectionName == section } }
            let rows = shown.map { [$0.sectionName, $0.categoryDisplayName, $0.teamValue, $0.rankDisplay] }
            let expected = item.rows.map { [$0.section, $0.category, $0.value, $0.rank] }
            XCTAssertEqual(rows.count, expected.count, item.core)
            for (index, (row, want)) in zip(rows, expected).enumerated() {
                XCTAssertEqual(row, want, "\(item.core) row \(index)")
            }
        }
    }
}
