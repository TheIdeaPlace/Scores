//
//  VenuesTests.swift
//  SportsScoresTests
//
//  The Venues screen's rule against the grid Windows is also held to, what's asked of ESPN
//  and what's made of its failures, against real payloads with a stand-in for it, and
//  college hockey's polls.
//

import XCTest
@testable import SportsScores

private struct VenueGrid: Decodable {
    struct League: Decodable {
        let league: String
        let path: String
        let query: String
    }
    struct Month: Decodable {
        let year: Int
        let month: Int
        let league: String
        let months: [String]
    }
    struct Game: Decodable {
        let venue: String
        let times: Int
    }
    struct Team: Decodable {
        let id: String
        let name: String
        let abbreviation: String
    }
    struct Venue: Decodable {
        let id: String
        let name: String
        let city: String
        let state: String
        let location: String
        let indoor: Bool?
        let home_teams: [Team]
        let summary: String
        let facts: [String]
    }
    struct Case: Decodable {
        let fixture: String
        let league: String
        let why: String
        let games: [Game]?
        let venues: [Venue]
    }
    let leagues: [League]
    let months: [Month]
    let cases: [Case]

    static func load() throws -> VenueGrid {
        let url = Fixtures.repoRoot.appendingPathComponent("tests/fixtures/venues_grid.json")
        return try JSONDecoder().decode(VenueGrid.self, from: Data(contentsOf: url))
    }
}

private func sport(_ league: String) throws -> Sport {
    try XCTUnwrap(Sport(rawValue: league), league)
}

final class VenueGridTests: XCTestCase {
    private func events(of item: VenueGrid.Case) throws -> [VenueScoreboard.Event] {
        let board = try JSONDecoder().decode(VenueScoreboard.self, from: Fixtures.data(item.fixture))
        guard let games = item.games else { return board.events }
        var picked: [VenueScoreboard.Event] = []
        for game in games {
            let event = board.events.first { $0.competition?.venue?.name == game.venue }
            let found = try XCTUnwrap(event, game.venue)
            picked.append(contentsOf: Array(repeating: found, count: game.times))
        }
        return picked
    }

    func testTheSameVenuesAsWindows() throws {
        let grid = try VenueGrid.load()
        XCTAssertGreaterThanOrEqual(grid.cases.count, 19)
        for item in grid.cases {
            let label = "\(item.fixture) as \(item.league): \(item.why)"
            let league = try sport(item.league)
            let venues = LeagueVenue.venues(from: try events(of: item), in: league)
            XCTAssertEqual(venues.map(\.name), item.venues.map(\.name), label)
            for (venue, expected) in zip(venues, item.venues) {
                XCTAssertEqual(venue.id, expected.id, label)
                XCTAssertEqual(venue.city, expected.city, label)
                XCTAssertEqual(venue.state, expected.state, label)
                XCTAssertEqual(venue.location, expected.location, label)
                XCTAssertEqual(venue.indoor, expected.indoor, "\(label): \(venue.name)")
                XCTAssertEqual(venue.homeTeams.map(\.id), expected.home_teams.map(\.id), label)
                XCTAssertEqual(venue.homeTeams.map(\.name), expected.home_teams.map(\.name), label)
                XCTAssertEqual(venue.homeTeams.map(\.abbreviation), expected.home_teams.map(\.abbreviation), label)
                XCTAssertEqual(venue.summary, expected.summary, label)
                XCTAssertEqual(venue.facts(in: league), expected.facts, label)
            }
        }
    }

    func testTheSameMonthsAsWindows() throws {
        let grid = try VenueGrid.load()
        XCTAssertGreaterThan(grid.months.count, 70)
        for item in grid.months {
            let months = VenueRules.months(for: try sport(item.league), year: item.year, month: item.month)
            XCTAssertEqual(months, item.months, "\(item.league) in \(item.year)-\(item.month)")
        }
    }

    func testTheSameRequestsAsWindows() throws {
        let service = ESPNAPIService.shared
        let grid = try VenueGrid.load()
        for item in grid.leagues {
            let league = try sport(item.league)
            XCTAssertEqual(league.apiPath, item.path)
            let url = service.venueScoreboardURLString(for: league, month: "202611", coverage: .allDivisionI)
            XCTAssertEqual(url, "https://site.api.espn.com/apis/site/v2/sports/\(item.path)/scoreboard?dates=202611&\(item.query)")
        }
    }

    func testCollegeFootballFollowsTheCoverageSetting() {
        let service = ESPNAPIService.shared
        XCTAssertEqual(service.venueQuery(for: .ncaaf, coverage: .fbs), "groups=80&limit=400")
        XCTAssertEqual(service.venueQuery(for: .ncaaf, coverage: .allDivisionI), "groups=90&limit=400")
    }

    func testTheLeaguesWindowsOffersAndNoOthers() throws {
        let grid = try VenueGrid.load()
        let offered = grid.leagues.map(\.league).sorted()
        var everySport: [Sport] = Sport.allCases
        everySport += Sport.soccerLeagues
        everySport += Sport.golfTours
        everySport += Sport.racingSeries
        everySport += [Sport.cfl, Sport.worldCup, Sport.worldCupWomens]
        let shown = everySport.filter(\.hasVenues).map(\.rawValue).sorted()
        XCTAssertEqual(shown, offered)
    }
}

final class VenueWordsTests: XCTestCase {
    private func venue(location: (String, String) = ("Brooklyn", "NY"), indoor: Bool? = true,
                       teams: [VenueHomeTeam] = [VenueHomeTeam(id: "17", name: "Brooklyn Nets", abbreviation: "BKN")]) -> LeagueVenue {
        LeagueVenue(id: "1", name: "Barclays Center", city: location.0, state: location.1, indoor: indoor, homeTeams: teams)
    }

    func testVoiceOverLabels() {
        XCTAssertEqual(venue().quickAccessibilityLabel, "Barclays Center, Brooklyn, NY, Indoor, Brooklyn Nets")
        XCTAssertEqual(venue().fullAccessibilityLabel,
                       "Venue: Barclays Center. Location: Brooklyn, NY. Type: Indoor. Home team: Brooklyn Nets")
        let two = [VenueHomeTeam(id: "1", name: "A", abbreviation: ""), VenueHomeTeam(id: "2", name: "B", abbreviation: "")]
        XCTAssertTrue(venue(teams: two).fullAccessibilityLabel.hasSuffix("Home teams: A, B"))
    }

    func testOnlyWhatIsKnownIsSaid() {
        let bare = venue(location: ("", ""), indoor: nil)
        XCTAssertEqual(bare.summary, "Barclays Center - Brooklyn Nets")
        XCTAssertEqual(bare.quickAccessibilityLabel, "Barclays Center, Brooklyn Nets")
        XCTAssertEqual(bare.fullAccessibilityLabel, "Venue: Barclays Center. Home team: Brooklyn Nets")
        XCTAssertNil(bare.typeDetailLine)
        XCTAssertEqual(bare.tableRow, ["Barclays Center", "Not listed", "Not listed", "Brooklyn Nets"])
        XCTAssertEqual(bare.facts(in: .nba), ["National Basketball Association venue", "Home of the Brooklyn Nets"])
        let noState = venue(location: ("Toronto", ""))
        XCTAssertEqual(noState.location, "Toronto")
        XCTAssertTrue(noState.facts(in: .nba).contains("Located in Toronto"))
        let words = bare.summary + noState.summary + bare.facts(in: .nba).joined() + noState.facts(in: .nba).joined()
        XCTAssertFalse(words.contains("Unknown"))
    }

    func testDetailLines() {
        XCTAssertEqual(venue().typeDetailLine, "Type: Indoor stadium")
        XCTAssertEqual(venue(indoor: false).typeDetailLine, "Type: Outdoor stadium")
        XCTAssertEqual(venue().homeTeams[0].detailLine, "Brooklyn Nets (BKN)")
        XCTAssertEqual(VenueHomeTeam(id: "1", name: "A", abbreviation: "").detailLine, "A")
    }

    func testFactsFromTheName() {
        func facts(_ name: String, _ sport: Sport, indoor: Bool?) -> [String] {
            LeagueVenue(id: "1", name: name, city: "", state: "", indoor: indoor).facts(in: sport)
        }
        XCTAssertTrue(facts("Wrigley Field", .mlb, indoor: false).contains("Classic baseball 'Field' naming"))
        XCTAssertTrue(facts("Fenway Park", .mlb, indoor: false).contains("Traditional baseball 'Park' naming"))
        XCTAssertTrue(facts("A Dome", .nfl, indoor: true).contains("Weather never affects games here"))
        XCTAssertFalse(facts("A Dome", .nfl, indoor: false).contains("Weather never affects games here"))
    }
}

final class VenueDecodingTests: XCTestCase {
    /// A real board with one of its games changed. Lambeau Field is the one to lose.
    private func board(changingLambeau change: (inout [String: Any]) -> Void) throws -> [VenueScoreboard.Event] {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Fixtures.data("scoreboard_NFL_202611.json")) as? [String: Any])
        var events = try XCTUnwrap(object["events"] as? [[String: Any]])
        let index = try XCTUnwrap(events.firstIndex { event in
            let competition = (event["competitions"] as? [[String: Any]])?.first
            return (competition?["venue"] as? [String: Any])?["fullName"] as? String == "Lambeau Field"
        })
        var competitions = try XCTUnwrap(events[index]["competitions"] as? [[String: Any]])
        change(&competitions[0])
        events[index]["competitions"] = competitions
        object["events"] = events
        let data = try JSONSerialization.data(withJSONObject: object)
        return try JSONDecoder().decode(VenueScoreboard.self, from: data).events
    }

    private func homeCompetitorIndex(_ competition: [String: Any]) -> Int {
        let competitors = competition["competitors"] as? [[String: Any]] ?? []
        return competitors.firstIndex { $0["homeAway"] as? String == "home" } ?? 0
    }

    private func changeHomeTeam(_ competition: inout [String: Any], to team: Any) {
        var competitors = competition["competitors"] as? [[String: Any]] ?? []
        competitors[homeCompetitorIndex(competition)]["team"] = team
        competition["competitors"] = competitors
    }

    func testAGameWithAHoleCostsOnlyItself() throws {
        let holes: [(String, (inout [String: Any]) -> Void)] = [
            ("no venue", { $0["venue"] = NSNull() }),
            ("no id", { $0["venue"] = ["id": NSNull(), "fullName": "No Id"] as [String: Any] }),
            ("null competitors", { $0["competitors"] = NSNull() }),
            ("no competitors", { $0["competitors"] = [Any]() }),
            ("null team", { self.changeHomeTeam(&$0, to: NSNull()) }),
            ("no team name", { self.changeHomeTeam(&$0, to: ["id": "9", "displayName": NSNull(), "name": NSNull()] as [String: Any]) }),
            ("no team id", { self.changeHomeTeam(&$0, to: ["id": 0, "displayName": "A"] as [String: Any]) }),
        ]
        for (label, hole) in holes {
            let names = LeagueVenue.venues(from: try board(changingLambeau: hole), in: .nfl).map(\.name)
            XCTAssertFalse(names.contains("Lambeau Field"), label)
            XCTAssertTrue(names.contains("MetLife Stadium"), label)
            XCTAssertTrue(names.contains("Highmark Stadium"), label)
        }
    }

    func testANumberAsAnIdIsTheSameId() throws {
        let events = try board { competition in
            var venue = competition["venue"] as? [String: Any] ?? [:]
            venue["id"] = 3798
            competition["venue"] = venue
        }
        let lambeau = LeagueVenue.venues(from: events, in: .nfl).first { $0.name == "Lambeau Field" }
        XCTAssertEqual(lambeau?.id, "3798")
    }

    func testNoAddressSaysNoLocationAndNoStateIsJustTheCity() throws {
        let noAddress = try board { competition in
            var venue = competition["venue"] as? [String: Any] ?? [:]
            venue["address"] = NSNull()
            competition["venue"] = venue
        }
        let lambeau = LeagueVenue.venues(from: noAddress, in: .nfl).first { $0.name == "Lambeau Field" }
        XCTAssertEqual(lambeau?.summary, "Lambeau Field [Outdoor] - Green Bay Packers")

        let noState = try board { competition in
            var venue = competition["venue"] as? [String: Any] ?? [:]
            venue["address"] = ["city": "Green Bay"]
            competition["venue"] = venue
        }
        let city = LeagueVenue.venues(from: noState, in: .nfl).first { $0.name == "Lambeau Field" }
        XCTAssertEqual(city?.location, "Green Bay")
    }

    func testNotSayingIndoorIsNotSayingOutdoor() throws {
        let events = try board { competition in
            var venue = competition["venue"] as? [String: Any] ?? [:]
            venue["indoor"] = nil
            competition["venue"] = venue
        }
        let lambeau = LeagueVenue.venues(from: events, in: .nfl).first { $0.name == "Lambeau Field" }
        XCTAssertNil(lambeau?.indoor)
    }

    func testBlankEventsCostOnlyThemselves() throws {
        let json = Data(#"{"events":[null,{},{"competitions":null},{"competitions":[null]},7]}"#.utf8)
        let events = try JSONDecoder().decode(VenueScoreboard.self, from: json).events
        XCTAssertTrue(LeagueVenue.venues(from: events, in: .nfl).isEmpty)
    }

    func testAnAnswerWithNoGamesInItIsNotAFailure() throws {
        for body in ["{}", #"{"events":[]}"#, #"{"events":null}"#, "[]", "null"] {
            let board = try JSONDecoder().decode(VenueScoreboard.self, from: Data(body.utf8))
            XCTAssertTrue(board.events.isEmpty, body)
        }
    }

    func testSomethingThatIsNotJSONIsAFailure() {
        XCTAssertThrowsError(try JSONDecoder().decode(VenueScoreboard.self, from: Data("<html>".utf8)))
    }
}

/// Stands in for ESPN, by the month asked for.
private final class VenueStandInESPN: URLProtocol {
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

    static var months: [String] {
        lock.withLock {
            requests.compactMap { url in
                URLComponents(string: url)?.queryItems?.first { $0.name == "dates" }?.value
            }
        }
    }

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

final class VenueRequestTests: XCTestCase {
    private var service: ESPNAPIService!
    private let noGames = Data(#"{"events":[]}"#.utf8)

    private var november2026: Date {
        Calendar.current.date(from: DateComponents(year: 2026, month: 11, day: 4, hour: 12))!
    }

    private func nfl() throws -> Data {
        try Fixtures.data("scoreboard_NFL_202611.json")
    }

    override func setUp() {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [VenueStandInESPN.self]
        service = ESPNAPIService(session: URLSession(configuration: config))
    }

    func testAMonthWithGamesIsTheOnlyOneAskedFor() async throws {
        let board = try nfl()
        VenueStandInESPN.reset { _ in .body(board) }
        let venues = try await service.fetchVenues(for: .nfl, now: november2026)
        XCTAssertEqual(venues.map(\.name), ["Highmark Stadium", "Lambeau Field", "MetLife Stadium"])
        XCTAssertEqual(VenueStandInESPN.months, ["202611"])
    }

    func testTheResultIsCachedAndPullToRefreshAsksAgain() async throws {
        let board = try nfl()
        VenueStandInESPN.reset { _ in .body(board) }
        _ = try await service.fetchVenues(for: .nfl, now: november2026)
        _ = try await service.fetchVenues(for: .nfl, now: november2026)
        XCTAssertEqual(VenueStandInESPN.months.count, 1)
        _ = try await service.fetchVenues(for: .nfl, now: november2026, ignoringCache: true)
        XCTAssertEqual(VenueStandInESPN.months.count, 2)
    }

    func testAServerErrorDoesNotLoseTheLeagueAndTheMonthGetsAnotherChance() async throws {
        let board = try nfl()
        VenueStandInESPN.reset { $0.contains("dates=202611") ? .status(500) : .body(board) }
        let venues = try await service.fetchVenues(for: .nfl, now: november2026)
        XCTAssertFalse(venues.isEmpty)
        XCTAssertEqual(VenueStandInESPN.months, ["202611", "202609"])
        _ = try await service.fetchVenues(for: .nfl, now: november2026)
        XCTAssertEqual(VenueStandInESPN.months, ["202611", "202609", "202611", "202609"])
    }

    func testEveryMonthEmptyIsNoVenuesAfterThreeTries() async throws {
        let empty = noGames
        VenueStandInESPN.reset { _ in .body(empty) }
        let venues = try await service.fetchVenues(for: .nfl, now: november2026)
        XCTAssertTrue(venues.isEmpty)
        XCTAssertEqual(VenueStandInESPN.months, ["202611", "202609", "202512"])
    }

    func testAnEmptyMonthFallsBackAndIsCached() async throws {
        let board = try nfl()
        let empty = noGames
        VenueStandInESPN.reset { $0.contains("dates=202611") ? .body(empty) : .body(board) }
        _ = try await service.fetchVenues(for: .nfl, now: november2026)
        XCTAssertEqual(VenueStandInESPN.months, ["202611", "202609"])
        _ = try await service.fetchVenues(for: .nfl, now: november2026)
        XCTAssertEqual(VenueStandInESPN.months.count, 2)
    }

    private func assertDidNotAnswer(_ sport: Sport = .nfl, file: StaticString = #filePath, line: UInt = #line) async {
        do {
            _ = try await service.fetchVenues(for: sport, now: november2026)
            XCTFail("it should have thrown", file: file, line: line)
        } catch {
            XCTAssertEqual(error.localizedDescription, "ESPN did not answer. Try again in a minute.", file: file, line: line)
        }
    }

    func testEveryMonthFailingIsAnErrorNotNoVenues() async throws {
        for status in [500, 404] {
            VenueStandInESPN.reset { _ in .status(status) }
            await assertDidNotAnswer()
            XCTAssertEqual(VenueStandInESPN.months.count, 3)
        }
        VenueStandInESPN.reset { _ in .body(Data("<html>".utf8)) }
        await assertDidNotAnswer()
        XCTAssertEqual(VenueStandInESPN.months.count, 3)
    }

    func testAFailedMonthAndEmptyOnesIsStillAnError() async {
        let empty = noGames
        VenueStandInESPN.reset { $0.contains("dates=202611") ? .status(500) : .body(empty) }
        await assertDidNotAnswer()
    }

    func testNoNetworkStopsAtTheFirstMonth() async {
        for code in [URLError.Code.timedOut, .notConnectedToInternet] {
            VenueStandInESPN.reset { _ in .failure(code) }
            await assertDidNotAnswer()
            XCTAssertEqual(VenueStandInESPN.months.count, 1)
        }
    }

    func testAFailureIsNotCached() async throws {
        VenueStandInESPN.reset { _ in .status(500) }
        await assertDidNotAnswer()
        let board = try nfl()
        VenueStandInESPN.reset { _ in .body(board) }
        let venues = try await service.fetchVenues(for: .nfl, now: november2026)
        XCTAssertFalse(venues.isEmpty)
    }

    func testALeagueWithNoVenuesAsksForNothing() async throws {
        VenueStandInESPN.reset { _ in .status(500) }
        let venues = try await service.fetchVenues(for: .soccerEPL, now: november2026)
        XCTAssertTrue(venues.isEmpty)
        XCTAssertTrue(VenueStandInESPN.months.isEmpty)
    }

    func testTheCollegeLookAheadWithNothingYetUsesLastSeason() async throws {
        let board = try Fixtures.data("scoreboard_NCAAH_202602.json")
        let empty = noGames
        VenueStandInESPN.reset { $0.contains("dates=202702") ? .body(empty) : .body(board) }
        let venues = try await service.fetchVenues(for: .ncaah, now: november2026)
        XCTAssertFalse(venues.isEmpty)
        XCTAssertEqual(VenueStandInESPN.months, ["202702", "202602"])
    }

    @MainActor
    func testTheScreenSaysSoWhenESPNDoesNotAnswerAndRetryBringsItBack() async throws {
        let model = VenuesViewModel(apiService: service)
        XCTAssertTrue(model.isLoading, "nothing should read as no venues before the first answer")

        VenueStandInESPN.reset { _ in .status(500) }
        await model.fetchVenues(for: .nfl)
        XCTAssertEqual(model.errorMessage, "ESPN did not answer. Try again in a minute.")
        XCTAssertTrue(model.venues.isEmpty)
        XCTAssertFalse(model.isLoading)

        let board = try nfl()
        VenueStandInESPN.reset { _ in .body(board) }
        await model.fetchVenues(for: .nfl)
        XCTAssertNil(model.errorMessage)
        XCTAssertFalse(model.venues.isEmpty)
        XCTAssertFalse(model.isLoading)
    }

    @MainActor
    func testComingBackFromDetailsDoesNotAskAgain() async throws {
        let board = try nfl()
        let model = VenuesViewModel(apiService: service)
        VenueStandInESPN.reset { _ in .body(board) }
        await model.fetchVenues(for: .nfl)
        let asked = VenueStandInESPN.months.count
        await model.fetchVenues(for: .nfl)
        XCTAssertEqual(VenueStandInESPN.months.count, asked)
        XCTAssertFalse(model.isLoading)
    }

    @MainActor
    func testNoGamesReadsAsEmptyNotAnError() async {
        let empty = noGames
        let model = VenuesViewModel(apiService: service)
        VenueStandInESPN.reset { _ in .body(empty) }
        await model.fetchVenues(for: .nfl)
        XCTAssertNil(model.errorMessage)
        XCTAssertTrue(model.venues.isEmpty)
        XCTAssertFalse(model.isLoading)
    }
}

final class VenueTableActivationTests: XCTestCase {
    func testActivatingACellOpensItsRow() throws {
        let table = AccessibleDataTableView(frame: CGRect(x: 0, y: 0, width: 300, height: 300))
        var opened: [Int] = []
        table.onActivateRow = { opened.append($0) }
        table.activationHint = "Opens venue details"
        table.columnHeaders = ["Venue", "Location"]
        table.dataRows = [["A", "B"], ["C", "D"]]

        let cell = try XCTUnwrap(table.accessibilityDataTableCellElement(forRow: 2, column: 1) as? DataTableCellElement)
        XCTAssertTrue(cell.accessibilityActivate())
        XCTAssertEqual(opened, [1])
        let first = try XCTUnwrap(table.accessibilityDataTableCellElement(forRow: 1, column: 0) as? DataTableCellElement)
        XCTAssertEqual(first.accessibilityHint, "Opens venue details")
        XCTAssertNil(cell.accessibilityHint)

        let header = try XCTUnwrap(table.accessibilityDataTableCellElement(forRow: 0, column: 0) as? DataTableCellElement)
        XCTAssertFalse(header.accessibilityActivate())
        XCTAssertEqual(opened, [1])
    }

    func testATableWhoseRowsOpenNothingLeavesActivationAlone() throws {
        let table = AccessibleDataTableView(frame: CGRect(x: 0, y: 0, width: 300, height: 300))
        table.columnHeaders = ["Rank"]
        table.dataRows = [["1"]]
        let cell = try XCTUnwrap(table.accessibilityDataTableCellElement(forRow: 1, column: 0) as? DataTableCellElement)
        XCTAssertFalse(cell.accessibilityActivate())
    }
}

// MARK: - College hockey's polls

final class CollegeHockeyPollsTests: XCTestCase {
    private func polls(_ fixture: String) throws -> [RankingsPoll] {
        let response = try JSONDecoder().decode(RankingsAPIResponse.self, from: Fixtures.data(fixture))
        return response.rankings.map { RankingsPoll(from: $0) }
    }

    func testEveryCollegeSportHasPollsAndNoOtherDoes() {
        var everySport: [Sport] = Sport.allCases
        everySport += Sport.soccerLeagues
        everySport.append(.cfl)
        let expected: Set<Sport> = [.ncaaf, .ncaam, .ncaawb, .ncaah, .ncaawh]
        XCTAssertEqual(Set(everySport.filter(\.hasPolls)), expected)
    }

    func testMensPoll() throws {
        let poll = try XCTUnwrap(try polls("rankings_NCAAH.json").first)
        XCTAssertEqual(poll.name, "USCHO Men's Poll")
        XCTAssertEqual(poll.ranks.map(\.current), [1, 4, 6, 6, 17], "two teams level at 6")
        XCTAssertEqual(poll.ranks[0].teamDisplayName, "Wisconsin Badgers")
        XCTAssertEqual(poll.ranks[0].recordSummary, "6-0")
        XCTAssertEqual(poll.ranks[1].recordSummary, "5-2-1", "hockey has ties")
        XCTAssertEqual(poll.ranks[4].movementText, "NR", "new to the poll")
    }

    func testWomensPoll() throws {
        let poll = try XCTUnwrap(try polls("rankings_NCAAWH.json").first)
        XCTAssertEqual(poll.name, "USCHO Women's Poll")
        XCTAssertEqual(poll.ranks.first?.teamDisplayName, "Ohio State Buckeyes")
    }

    /// ESPN sends 0.0 for every team here. It would read as "0 points" down the whole list.
    func testNoTeamHasPointsItDoesNotHave() throws {
        for fixture in ["rankings_NCAAH.json", "rankings_NCAAWH.json"] {
            let poll = try XCTUnwrap(try polls(fixture).first)
            XCTAssertFalse(poll.ranks.isEmpty, fixture)
            XCTAssertTrue(poll.ranks.allSatisfy { $0.points == nil }, fixture)
        }
    }

    func testFootballKeepsItsPoints() throws {
        let poll = try XCTUnwrap(try polls("rankings_NCAAF.json").first)
        XCTAssertTrue(poll.ranks.contains { ($0.points ?? 0) > 0 })
    }

    func testTheRequestReadsTheFixture() async throws {
        let body = try Fixtures.data("rankings_NCAAH.json")
        VenueStandInESPN.reset { _ in .body(body) }
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [VenueStandInESPN.self]
        let service = ESPNAPIService(session: URLSession(configuration: config))
        let polls = try await service.fetchRankings(for: .ncaah)
        XCTAssertEqual(polls.count, 1)
        XCTAssertEqual(VenueStandInESPN.requests, ["https://site.api.espn.com/apis/site/v2/sports/hockey/mens-college-hockey/rankings"])
    }
}
