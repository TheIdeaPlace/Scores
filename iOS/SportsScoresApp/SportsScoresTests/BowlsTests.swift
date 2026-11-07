//
//  BowlsTests.swift
//  SportsScoresTests
//
//  Bowls & Playoffs on the real postseason scoreboard, tests/fixtures/espn/bowls_NCAAF.json,
//  and the request it makes, which is the one the Windows dialog makes.
//

import XCTest
@testable import SportsScores

final class BowlsListTests: XCTestCase {
    private func fixtureGames() throws -> [PostseasonGame] {
        let response = try Fixtures.decodeScoreboard(try Fixtures.data("bowls_NCAAF.json"))
        return try PostseasonList.games(from: response)
    }

    private func game(_ id: String, in games: [PostseasonGame]) throws -> PostseasonGame {
        try XCTUnwrap(games.first { $0.id == id }, "no game \(id)")
    }

    func testEveryGameComesThroughWithItsName() throws {
        let games = try fixtureGames()
        XCTAssertEqual(games.count, 5)
        XCTAssertEqual(try game("401874421", in: games).title, "Cricket Celebration Bowl")
        XCTAssertEqual(try game("401874322", in: games).title,
                       "College Football Playoff National Championship Presented by AT&T")
    }

    /// The fixture's competition type ids are strings, which put every game among the
    /// bowls on Windows. Here each goes to its round.
    func testEachGameIsInItsRound() throws {
        let games = try fixtureGames()
        XCTAssertEqual(try game("401874322", in: games).round, .championship)
        XCTAssertEqual(try game("401874300", in: games).round, .semifinal)
        XCTAssertEqual(try game("401874299", in: games).round, .quarterfinal)
        XCTAssertEqual(try game("401874421", in: games).round, .bowl)
    }

    /// ESPN gives the playoff's first-round games type 1, a plain game. The headline says
    /// what it is, so it isn't filed among the bowls as Windows files it.
    func testAFirstRoundGameOfTypeOneIsThePlayoffsFirstRound() throws {
        let first = try game("401874295", in: try fixtureGames())
        XCTAssertEqual(first.round, .firstRound)
    }

    func testThePlayoffComesFirstInTheOrderItsPlayedThenTheBowls() throws {
        let sections = PostseasonList.sections(try fixtureGames())
        XCTAssertEqual(sections.map(\.round), [.firstRound, .quarterfinal, .semifinal, .championship, .bowl])
        XCTAssertEqual(sections.map(\.heading), [
            "Playoff First Round, 1 game",
            "Playoff Quarterfinals, 1 game",
            "Playoff Semifinals, 1 game",
            "National Championship, 1 game",
            "Bowl Games, 1 game",
        ])
    }

    func testTheCompetitionTypeIdIsReadAsANumber() throws {
        let response = try Fixtures.decodeScoreboard(try Fixtures.data("bowls_NCAAF.json"))
        let types = response.events.compactMap { $0.competitions.first?.type?.id }
        XCTAssertEqual(Set(types), [33, 35, 40, 42, 1])
    }

    func testRoundsFromTheHeadline() {
        XCTAssertEqual(PostseasonRound.from(headline: "College Football Playoff First Round Game", typeID: 1), .firstRound)
        XCTAssertEqual(PostseasonRound.from(headline: "College Football Playoff Quarterfinal at the Rose Bowl", typeID: 40), .quarterfinal)
        XCTAssertEqual(PostseasonRound.from(headline: "CFP Semifinal at the Orange Bowl", typeID: 35), .semifinal)
        // Another division's playoff isn't the College Football Playoff.
        XCTAssertEqual(PostseasonRound.from(headline: "NCAA Division I FCS Playoff - First Round", typeID: 1), .bowl)
        XCTAssertEqual(PostseasonRound.from(headline: "NCAA Division I Football Championship", typeID: 33), .bowl)
        XCTAssertEqual(PostseasonRound.from(headline: "Duke's Mayo Bowl", typeID: 42), .bowl)
        // With no headline, the type is all there is.
        XCTAssertEqual(PostseasonRound.from(headline: nil, typeID: 33), .championship)
        XCTAssertEqual(PostseasonRound.from(headline: "", typeID: 35), .semifinal)
        XCTAssertEqual(PostseasonRound.from(headline: nil, typeID: 42), .bowl)
        XCTAssertEqual(PostseasonRound.from(headline: nil, typeID: nil), .bowl)
    }

    func testAHeadingsGamesAreInKickoffOrder() throws {
        let games = try fixtureGames()
        // Every game as a bowl, to put several under one heading.
        let asBowls = games.map { PostseasonGame(game: $0.game, title: $0.title, round: .bowl) }
        let section = try XCTUnwrap(PostseasonList.sections(asBowls).first)
        XCTAssertEqual(section.games.map(\.id),
                       ["401874421", "401874295", "401874299", "401874300", "401874322"])
    }

    func testNoGamesIsNoSections() {
        XCTAssertTrue(PostseasonList.sections([]).isEmpty)
    }

    func testVoiceOverReadsTheNameTheTeamsAndWhen() throws {
        let celebration = try game("401874421", in: try fixtureGames())
        XCTAssertTrue(celebration.teamsUndecided)
        let central = try XCTUnwrap(TimeZone(identifier: "America/Chicago"))
        let label = PostseasonList.accessibilityLabel(celebration, teamNames: .full, timeZone: central)
        XCTAssertTrue(label.hasPrefix("Cricket Celebration Bowl, Teams to be announced, Saturday, December 12 at 11:00 AM, at Mercedes-Benz Stadium"),
                      label)
        XCTAssertTrue(label.hasSuffix(", on ABC"), label)
        XCTAssertEqual(PostseasonList.shownDate(celebration.game, timeZone: central), "Sat 12/12 11:00 AM")
    }

    func testOneTeamKnownIsSaid() throws {
        let first = try game("401874295", in: try fixtureGames())
        let known = Game.Team(id: "194", name: "Buckeyes", abbreviation: "OSU",
                              displayName: "Ohio State Buckeyes", score: nil, record: nil, logo: nil)
        var game = first.game
        game = Game(id: game.id, name: game.name, shortName: game.shortName, date: game.date,
                    status: game.status, homeTeam: known, awayTeam: game.awayTeam, venue: nil,
                    broadcasts: [], situation: nil, seasonType: 3)
        let item = PostseasonGame(game: game, title: first.title, round: first.round)
        XCTAssertFalse(item.teamsUndecided)
        XCTAssertEqual(PostseasonList.matchup(item) { $0.displayName }, "TBD at Ohio State Buckeyes")
    }
}

/// Stands in for ESPN, answering each URL as told.
private final class BowlsStandInESPN: URLProtocol {
    enum Reply {
        case body(Data)
        case status(Int)
        case failure(URLError.Code)
    }

    static let lock = NSLock()
    static var requests: [String] = []
    static var reply: (String) -> Reply = { _ in .status(500) }

    static func reset(_ reply: @escaping (String) -> Reply) {
        lock.withLock {
            self.requests = []
            self.reply = reply
        }
    }

    static var asked: [String] { lock.withLock { requests } }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        guard let url = request.url else { return }
        let text = url.absoluteString
        let reply = Self.lock.withLock { () -> Reply in
            Self.requests.append(text)
            return Self.reply(text)
        }
        switch reply {
        case .failure(let code):
            client?.urlProtocol(self, didFailWithError: URLError(code))
        case .status(let status):
            finish(url, status: status, body: Data())
        case .body(let body):
            finish(url, status: 200, body: body)
        }
    }

    private func finish(_ url: URL, status: Int, body: Data) {
        let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }
}

final class BowlsRequestTests: XCTestCase {
    private var service: ESPNAPIService!
    private let noGames = Data(#"{"events":[]}"#.utf8)

    override func setUp() {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [BowlsStandInESPN.self]
        service = ESPNAPIService(session: URLSession(configuration: config))
    }

    func testTheSameRequestAsWindows() {
        XCTAssertEqual(service.postseasonURLString(for: .ncaaf, ncaafCoverage: .fbs),
                       "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?seasontype=3&groups=80&limit=400")
    }

    /// `seasontype=3&groups=90` is empty, so All Division I asks again as FBS.
    func testAllDivisionIEmptyAsksAgainAsFBS() async throws {
        let bowls = try Fixtures.data("bowls_NCAAF.json")
        let empty = noGames
        BowlsStandInESPN.reset { url in url.contains("groups=90") ? .body(empty) : .body(bowls) }
        let games = try await service.fetchPostseasonGames(for: .ncaaf, ncaafCoverage: .allDivisionI)
        XCTAssertEqual(games.count, 5)
        let asked = BowlsStandInESPN.asked
        XCTAssertEqual(asked.count, 2)
        XCTAssertTrue(asked[0].contains("seasontype=3&groups=90&limit=400"), asked[0])
        XCTAssertTrue(asked[1].contains("seasontype=3&groups=80&limit=400"), asked[1])
    }

    func testFBSAsksOnce() async throws {
        let bowls = try Fixtures.data("bowls_NCAAF.json")
        BowlsStandInESPN.reset { _ in .body(bowls) }
        let games = try await service.fetchPostseasonGames(for: .ncaaf, ncaafCoverage: .fbs)
        XCTAssertEqual(games.count, 5)
        XCTAssertEqual(BowlsStandInESPN.asked.count, 1)
    }

    /// The FBS request is the real answer here, so its failure isn't "no bowl games".
    func testTheFBSRequestFailingIsAFailureNotNoGames() async {
        let empty = noGames
        BowlsStandInESPN.reset { url in url.contains("groups=90") ? .body(empty) : .status(503) }
        do {
            _ = try await service.fetchPostseasonGames(for: .ncaaf, ncaafCoverage: .allDivisionI)
            XCTFail("a failed request read as no games")
        } catch {}
    }

    func testNoConnectionIsAFailure() async {
        BowlsStandInESPN.reset { _ in .failure(.notConnectedToInternet) }
        do {
            _ = try await service.fetchPostseasonGames(for: .ncaaf, ncaafCoverage: .fbs)
            XCTFail("no connection read as no games")
        } catch {}
    }

    func testOutOfSeasonIsNoGames() async throws {
        let empty = noGames
        BowlsStandInESPN.reset { _ in .body(empty) }
        let games = try await service.fetchPostseasonGames(for: .ncaaf, ncaafCoverage: .allDivisionI)
        XCTAssertTrue(games.isEmpty)
    }

    func testANotFoundIsNoGames() async throws {
        BowlsStandInESPN.reset { _ in .status(404) }
        let games = try await service.fetchPostseasonGames(for: .ncaaf, ncaafCoverage: .fbs)
        XCTAssertTrue(games.isEmpty)
    }

    @MainActor
    func testTheScreenSaysSoWhenESPNDoesNotAnswerAndRetryBringsItBack() async throws {
        BowlsStandInESPN.reset { _ in .status(500) }
        let model = BowlsViewModel(apiService: service)
        await model.load(for: .ncaaf, coverage: .fbs)
        XCTAssertEqual(model.errorMessage, "ESPN isn't providing bowl games right now. Try again in a minute.")
        XCTAssertTrue(model.sections.isEmpty)
        XCTAssertFalse(model.isLoading)

        let bowls = try Fixtures.data("bowls_NCAAF.json")
        BowlsStandInESPN.reset { _ in .body(bowls) }
        // Coming back to the screen doesn't ask again after a failure; Retry does.
        await model.load(for: .ncaaf, coverage: .fbs)
        XCTAssertTrue(BowlsStandInESPN.asked.isEmpty)
        await model.retry(for: .ncaaf, coverage: .fbs)
        XCTAssertNil(model.errorMessage)
        XCTAssertEqual(model.sections.count, 5)
    }

    @MainActor
    func testARefreshThatFailsKeepsTheList() async throws {
        let bowls = try Fixtures.data("bowls_NCAAF.json")
        BowlsStandInESPN.reset { _ in .body(bowls) }
        let model = BowlsViewModel(apiService: service)
        await model.load(for: .ncaaf, coverage: .fbs)
        XCTAssertEqual(model.sections.count, 5)

        BowlsStandInESPN.reset { _ in .status(500) }
        await model.refresh(for: .ncaaf, coverage: .fbs)
        XCTAssertTrue(model.refreshFailed)
        XCTAssertNil(model.errorMessage)
        XCTAssertEqual(model.sections.count, 5)
    }
}
