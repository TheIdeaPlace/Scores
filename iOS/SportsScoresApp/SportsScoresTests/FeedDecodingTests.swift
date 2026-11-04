//
//  FeedDecodingTests.swift
//  SportsScoresTests
//
//  The real Swift models against the real ESPN payloads in tests/fixtures/espn, the
//  same files the Windows tests use. A required field ESPN leaves out fails the whole
//  decode, which is how one bench player with no full name took out about one in five
//  women's college basketball games (#121).
//
//  GameDetails decodes each section on its own and a play at a time, so a bad section or
//  play disappears rather than throwing. Decoding without a throw proves little there,
//  which is why the tests below count what came through against the raw payload.
//
//  Set LIVE_PAYLOADS (TEST_RUNNER_LIVE_PAYLOADS for xcodebuild) to a folder of payloads
//  saved by `tools/validate_espn.py --save-payloads`, and the same checks run on today's.
//  The live tests skip when it isn't set, and fail when it's set and has nothing in it.
//

import XCTest
@testable import SportsScores

enum Fixtures {
    /// The simulator shares the Mac's file system, so the repo's own files can be read.
    static let repoRoot = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent()   // SportsScoresTests
        .deletingLastPathComponent()   // SportsScoresApp
        .deletingLastPathComponent()   // iOS
        .deletingLastPathComponent()

    static let folder = repoRoot.appendingPathComponent("tests/fixtures/espn")

    static func data(_ name: String) throws -> Data {
        try Data(contentsOf: folder.appendingPathComponent(name))
    }

    /// Fixture files whose names start with `prefix`.
    static func named(_ prefix: String) throws -> [URL] {
        try FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)
            .filter { $0.lastPathComponent.hasPrefix(prefix) && $0.pathExtension == "json" }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
    }

    /// One key of a JSON object, as its own JSON.
    static func subobject(_ key: String, of data: Data) throws -> Data {
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let value = try XCTUnwrap(object[key], "no \(key)")
        return try JSONSerialization.data(withJSONObject: value)
    }

    static func decodeScoreboard(_ data: Data) throws -> ScoreboardResponse {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601   // as ESPNAPIService does
        return try decoder.decode(ScoreboardResponse.self, from: data)
    }

    /// Decodes a summary the way ESPNAPIService does.
    static func decodeDetails(_ data: Data) throws -> GameDetails {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(GameDetails.self, from: data)
    }

    /// How many items a top-level array of a JSON object holds, before any are dropped.
    static func rawCount(_ key: String, of data: Data) throws -> Int {
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        return try XCTUnwrap(object[key] as? [Any], "no \(key)").count
    }

    /// How many real entries a scoreboard's `events` holds, leaving out ESPN's stray {}.
    static func realEventCount(of data: Data) throws -> Int {
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let events = try XCTUnwrap(object["events"] as? [[String: Any]], "no events")
        return events.filter { !$0.isEmpty }.count
    }

    /// Payloads saved from live ESPN, by kind. Skips the test when this isn't a live run.
    /// A run of one league (LIVE_PAYLOADS_PARTIAL) can lack a kind, such as standings out of season.
    static func live(_ kind: String) throws -> [URL] {
        guard let path = ProcessInfo.processInfo.environment["LIVE_PAYLOADS"], !path.isEmpty else {
            throw XCTSkip("LIVE_PAYLOADS isn't set")
        }
        let files = try FileManager.default.contentsOfDirectory(at: URL(fileURLWithPath: path),
                                                                includingPropertiesForKeys: nil)
            .filter { $0.lastPathComponent.hasPrefix(kind + "-") }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
        if (ProcessInfo.processInfo.environment["LIVE_PAYLOADS_PARTIAL"] ?? "").isEmpty {
            XCTAssertFalse(files.isEmpty, "LIVE_PAYLOADS is \(path), and it has no \(kind)- files")
        }
        return files
    }
}

final class BoxScoreDecodingTests: XCTestCase {
    private func box(_ url: URL) throws -> GameDetails.Boxscore {
        let data = try Fixtures.subobject("boxscore", of: Data(contentsOf: url))
        return try JSONDecoder().decode(GameDetails.Boxscore.self, from: data)
    }

    private func box(league: String) throws -> GameDetails.Boxscore {
        let file = try XCTUnwrap(try Fixtures.named("box_\(league)_").first, "no fixture for \(league)")
        return try box(file)
    }

    func testEveryBoxScoreFixtureDecodes() throws {
        let files = try Fixtures.named("box_")
        XCTAssertGreaterThanOrEqual(files.count, 10)
        for file in files {
            XCTAssertNoThrow(try box(file), file.lastPathComponent)
        }
    }

    func testGameDetailsSurvivesAnAthleteWithOnlyAShortName() throws {
        // The shape of the payload that failed 29 of 145 NCAAWB games.
        let json = """
        {"boxscore": {"teams": [], "players": [{"team": {"displayName": "South Carolina Gamecocks",
         "abbreviation": "SC"}, "statistics": [{"names": ["MIN"], "athletes": [
           {"active": false, "stats": [], "didNotPlay": true, "athlete": {"links": [], "shortName": "J. Loubens"}},
           {"active": true, "stats": ["20"], "athlete": {"displayName": "Ta'Niya Latson"}}
         ]}]}]}}
        """
        let details = try JSONDecoder().decode(GameDetails.self, from: Data(json.utf8))
        let athletes = try XCTUnwrap(details.boxscore?.players?.first?.statistics.first?.athletes)
        XCTAssertEqual(athletes.count, 2, "the short-name player should be kept, and the game should open")
    }

    func testBasketballTabsHaveNamesAndShooting() throws {
        for league in ["NBA", "WNBA", "NCAAM", "NCAAWB"] {
            let players = try XCTUnwrap(try box(league: league).players, league)
            let group = try XCTUnwrap(players.first?.statistics.first, league)
            XCTAssertEqual(group.groupTitle, "Players", league)
            let profile = BoxScoreProfiles.profile(for: try XCTUnwrap(Sport(rawValue: league)))
            let table = group.table(essentialOnly: true, profile: profile)
            XCTAssertFalse(table.columns.isEmpty, league)
            XCTAssertTrue(table.columns.contains { $0.uppercased() == "FG" }, "\(league): no shooting in \(table.columns)")
            XCTAssertEqual(table.rows.last?.name, BoxPlayerTable.totalsName, league)
        }
    }

    func testNoGroupOfAnySportIsCalledUnknownOrBlankInEssential() throws {
        for league in ["NFL", "NCAAF", "NBA", "WNBA", "NCAAM", "NCAAWB", "NHL", "MLB"] {
            let players = try XCTUnwrap(try box(league: league).players, league)
            let profile = BoxScoreProfiles.profile(for: try XCTUnwrap(Sport(rawValue: league)))
            // Football and hockey only have `labels`. If those stopped reading as headers,
            // every group would lose its content and the loop below would check nothing.
            XCTAssertTrue(players.allSatisfy { team in team.statistics.contains(where: \.hasContent) },
                          "\(league): a team has no group with anything to show")
            for team in players {
                for group in team.statistics where group.hasContent {
                    XCTAssertFalse(group.groupTitle.lowercased().contains("unknown"), league)
                    let table = group.table(essentialOnly: true, profile: profile)
                    XCTAssertFalse(table.columns.isEmpty, "\(league) \(group.groupTitle) is blank in Essential")
                    XCTAssertFalse(table.rows.isEmpty, "\(league) \(group.groupTitle) has no rows")
                }
            }
        }
    }

    func testFootballGroupsReadAsWords() throws {
        let players = try XCTUnwrap(try box(league: "NFL").players)
        let titles = Set(players.flatMap { $0.statistics.map(\.groupTitle) })
        XCTAssertTrue(titles.isSuperset(of: ["Passing", "Rushing", "Receiving", "Defense"]), "\(titles)")
        XCTAssertTrue(titles.contains("Kick Returns") || titles.contains("Punt Returns"), "\(titles)")
        XCTAssertFalse(titles.contains("Kickreturns"))
    }

    func testEssentialTeamStatsAreNotBlank() throws {
        for league in ["NFL", "NCAAF", "NBA", "NCAAM", "NCAAWB", "NHL"] {
            let teams = try box(league: league).teams
            let profile = BoxScoreProfiles.profile(for: try XCTUnwrap(Sport(rawValue: league)))
            let rows = profile.essentialTeamRows(of: try XCTUnwrap(teams.first?.statistics, league))
            XCTAssertFalse(rows.isEmpty, league)
        }
    }

    func testCollegeHockeyHasNothingToShow() throws {
        for league in ["NCAAH", "NCAAWH"] {
            let groups = try XCTUnwrap(try box(league: league).players).flatMap(\.statistics)
            XCTAssertTrue(groups.allSatisfy { !$0.hasContent }, league)
        }
    }

    func testEveryBoxScoreFixtureComesThroughAWholeGame() throws {
        for file in try Fixtures.named("box_") {
            let details = try Fixtures.decodeDetails(Data(contentsOf: file))
            XCTAssertNotNil(details.boxscore, file.lastPathComponent)
        }
    }

    func testLivePayloadsDecode() throws {
        for file in try Fixtures.live("summary") {
            let details = try Fixtures.decodeDetails(Data(contentsOf: file))
            XCTAssertNotNil(details.boxscore, "\(file.lastPathComponent): the box score was dropped")
            XCTAssertNotNil(details.header, "\(file.lastPathComponent): the header was dropped")
        }
    }
}

final class GameDetailsDecodingTests: XCTestCase {
    func testNoRealPlayIsDropped() throws {
        let files = try Fixtures.named("plays_")
        XCTAssertGreaterThanOrEqual(files.count, 4)
        for file in files {
            let data = try Data(contentsOf: file)
            let plays = try XCTUnwrap(try Fixtures.decodeDetails(data).plays, file.lastPathComponent)
            XCTAssertEqual(plays.count, try Fixtures.rawCount("plays", of: data), file.lastPathComponent)
            XCTAssertFalse(plays.isEmpty, file.lastPathComponent)
        }
    }

    func testTheHeaderOfARealGameIsRead() throws {
        for prefix in ["plays_", "details_"] {
            for file in try Fixtures.named(prefix) {
                let details = try Fixtures.decodeDetails(Data(contentsOf: file))
                XCTAssertNotNil(details.header, file.lastPathComponent)
            }
        }
    }

    func testEspnsNoLocationValuesDoNotCountAsLocations() throws {
        // A real game: some plays have shot coordinates, and others ESPN's sentinel.
        let file = try XCTUnwrap(try Fixtures.named("plays_NBA_").first)
        let plays = try XCTUnwrap(try Fixtures.decodeDetails(Data(contentsOf: file)).plays)
        let coordinates = plays.compactMap(\.coordinate)
        let located = coordinates.filter { PlayAudioGeometry.hasLocation($0, for: .nba) }
        XCTAssertFalse(located.isEmpty)
        XCTAssertLessThan(located.count, coordinates.count)
    }

    func testAllOfAFootballGamesPiecesAreRead() throws {
        let data = try Fixtures.data("details_NFL_pieces.json")
        let details = try Fixtures.decodeDetails(data)
        XCTAssertNotNil(details.gameInfo)
        XCTAssertEqual(details.pickcenter?.count, try Fixtures.rawCount("pickcenter", of: data))
        XCTAssertEqual(details.injuries?.count, try Fixtures.rawCount("injuries", of: data))
        XCTAssertFalse(try XCTUnwrap(details.pickcenter).isEmpty)
        XCTAssertFalse(try XCTUnwrap(details.injuries).isEmpty)
    }

    func testCollegeHockeyPiecesAreRead() throws {
        let details = try Fixtures.decodeDetails(Fixtures.data("details_NCAAH_pieces.json"))
        XCTAssertNotNil(details.gameInfo)
    }
}

final class ScoreboardDecodingTests: XCTestCase {
    func testEventsInEveryStatusReadAsThatStatus() throws {
        struct Expected { let live: Bool, completed: Bool, postponed: Bool }
        let expected: [String: Expected] = [
            "STATUS_SCHEDULED": Expected(live: false, completed: false, postponed: false),
            "STATUS_IN_PROGRESS": Expected(live: true, completed: false, postponed: false),
            "STATUS_HALFTIME": Expected(live: true, completed: false, postponed: false),
            "STATUS_END_PERIOD": Expected(live: true, completed: false, postponed: false),
            "STATUS_FINAL": Expected(live: false, completed: true, postponed: false),
            "STATUS_DELAYED": Expected(live: true, completed: false, postponed: false),
            "STATUS_POSTPONED": Expected(live: false, completed: true, postponed: true),
            "STATUS_FORFEIT": Expected(live: false, completed: true, postponed: false),
        ]
        let response = try Fixtures.decodeScoreboard(Fixtures.data("scoreboard_events_by_status.json"))
        XCTAssertEqual(response.events.count, expected.count)

        // Game falls back to now if it can't read the date, which would otherwise pass unseen.
        let compact = DateFormatter()
        compact.locale = Locale(identifier: "en_US_POSIX")
        compact.timeZone = TimeZone(identifier: "UTC")
        compact.dateFormat = "yyyy-MM-dd'T'HH:mm'Z'"

        var seen = Set<String>()
        for event in response.events {
            let game = try Game(from: event)
            let name = try XCTUnwrap(game.status.name, event.id)
            seen.insert(name)
            let want = try XCTUnwrap(expected[name], "a status this test doesn't know: \(name)")
            XCTAssertEqual(game.status.isLive, want.live, name)
            XCTAssertEqual(game.status.isCompleted, want.completed, name)
            XCTAssertEqual(game.status.isPostponed, want.postponed, name)
            XCTAssertEqual(game.id, event.id, name)
            XCTAssertFalse(game.homeTeam.displayName.isEmpty, name)
            XCTAssertFalse(game.awayTeam.displayName.isEmpty, name)
            if game.timeValid != false {
                XCTAssertEqual(game.date, try XCTUnwrap(compact.date(from: event.date), name), name)
            }
        }
        XCTAssertEqual(seen, Set(expected.keys))
    }

    private func board(with extra: [Any], keepingRealEvents: Bool = true) throws -> Data {
        let data = try Fixtures.data("scoreboard_events_by_status.json")
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let events = try XCTUnwrap(object["events"] as? [Any])
        object["events"] = (keepingRealEvents ? events : []) + extra
        return try JSONSerialization.data(withJSONObject: object)
    }

    func testABlankEventCostsOnlyItself() throws {
        // ESPN's board for week 8 of college football in 2025 has a literal {} in it.
        let response = try Fixtures.decodeScoreboard(board(with: [[String: Any]()]))
        XCTAssertEqual(response.events.count, 8)
    }

    func testAnEventThatCanNotBeReadCostsOnlyItself() throws {
        let response = try Fixtures.decodeScoreboard(board(with: [["id": "1"]]))
        XCTAssertEqual(response.events.count, 8)
    }

    func testABoardWithNothingReadableIsStillAnError() throws {
        let data = try board(with: [[String: Any](), ["id": "1"]], keepingRealEvents: false)
        XCTAssertThrowsError(try Fixtures.decodeScoreboard(data))
    }

    func testABoardMostlyUnreadableIsStillAnError() throws {
        // A short list would look normal, so ESPN dropping a field can't be left to pass as one.
        let unreadable = Array(repeating: ["id": "1"] as [String: Any], count: 9)
        XCTAssertThrowsError(try Fixtures.decodeScoreboard(board(with: unreadable)))
    }

    func testABoardOfOnlyBlanksIsAnEmptySlate() throws {
        let response = try Fixtures.decodeScoreboard(board(with: [[String: Any]()], keepingRealEvents: false))
        XCTAssertTrue(response.events.isEmpty)
    }

    func testTheRestOfTheBoardIsStillRead() throws {
        let data = try Fixtures.data("scoreboard_events_by_status.json")
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        object["week"] = ["number": 9, "text": "Week 9"]
        object["season"] = ["year": 2026]
        object["leagues"] = [["calendar": [[String: Any]]()]]
        let response = try Fixtures.decodeScoreboard(JSONSerialization.data(withJSONObject: object))
        XCTAssertEqual(response.week?.number, 9)
        XCTAssertEqual(response.season?.year, 2026)
        XCTAssertEqual(response.leagues?.count, 1)
    }

    func testAnEmptySlateIsNotAnError() throws {
        let response = try Fixtures.decodeScoreboard(board(with: [], keepingRealEvents: false))
        XCTAssertTrue(response.events.isEmpty)
    }

    func testLosingTheEventsKeyIsStillAnError() throws {
        XCTAssertThrowsError(try Fixtures.decodeScoreboard(Data(#"{"leagues": []}"#.utf8)))
    }

    func testLivePayloadsDecode() throws {
        for file in try Fixtures.live("scoreboard") {
            let data = try Data(contentsOf: file)
            let response = try Fixtures.decodeScoreboard(data)
            // An event that can't be read disappears, so count them: this is what catches
            // ESPN dropping a required field from some games.
            XCTAssertEqual(response.events.count, try Fixtures.realEventCount(of: data), file.lastPathComponent)
            for event in response.events {
                XCTAssertNoThrow(try Game(from: event), "\(file.lastPathComponent): \(event.id)")
            }
        }
    }
}

final class StandingsDecodingTests: XCTestCase {
    private func response(_ league: String) throws -> APIStandingsResponse {
        try JSONDecoder().decode(APIStandingsResponse.self, from: Fixtures.data("standings_\(league).json"))
    }

    private func entries(_ league: String) throws -> [StandingsEntry] {
        try response(league).groupsWithEntries.flatMap { $0.standings.entries.map { StandingsEntry(fromAPIEntry: $0) } }
    }

    func testEveryLeagueDecodes() throws {
        for league in ["NFL", "NBA", "WNBA", "NHL", "NCAAF", "NCAAM", "NCAAWB", "NCAAH", "NCAAWH"] {
            XCTAssertFalse(try entries(league).isEmpty, league)
        }
    }

    func testCollegeFootballReadsTheOverallRecordNotASplit() throws {
        let utsa = try XCTUnwrap(try entries("NCAAF").first { $0.team.displayName == "UTSA Roadrunners" })
        XCTAssertEqual(utsa.stats.wins, 7)
        XCTAssertEqual(utsa.stats.losses, 1)
    }

    func testWomensCollegeHockeyHasItsEntriesAtTheRoot() throws {
        let yale = try XCTUnwrap(try entries("NCAAWH").first { $0.team.displayName == "Yale Bulldogs" })
        XCTAssertEqual(yale.stats.wins, 2)
    }

    func testTheSunBeltsNestingIsWalked() throws {
        let groups = try response("NCAAF").groupsWithEntries.map(\.name)
        XCTAssertTrue(groups.contains { $0.contains("Sun Belt") }, "\(groups)")
    }

    func testLivePayloadsDecode() throws {
        for file in try Fixtures.live("standings") {
            let decoded = try JSONDecoder().decode(APIStandingsResponse.self, from: Data(contentsOf: file))
            XCTAssertFalse(decoded.groupsWithEntries.isEmpty, file.lastPathComponent)
        }
    }
}

final class TeamHubDecodingTests: XCTestCase {
    func testSchedulesDecode() throws {
        let files = try Fixtures.named("schedule_")
        XCTAssertFalse(files.isEmpty)
        for file in files {
            let response = try JSONDecoder().decode(TeamScheduleAPIResponse.self, from: Data(contentsOf: file))
            XCTAssertFalse(response.events.isEmpty, file.lastPathComponent)
        }
    }

    func testTeamInfoDecodes() throws {
        let response = try JSONDecoder().decode(TeamInfoAPIResponse.self, from: Fixtures.data("team_NHL_utah.json"))
        XCTAssertFalse(response.team.id.isEmpty)
    }

    private func games(_ file: String) throws -> [ScheduleGame] {
        try JSONDecoder().decode(TeamScheduleAPIResponse.self, from: Fixtures.data(file))
            .events.compactMap { $0.toScheduleGame() }
    }

    func testTheNetsPlayAtBarclaysWhateverTheirFranchiseSays() throws {
        let team = try JSONDecoder().decode(TeamInfoAPIResponse.self, from: Fixtures.data("team_NBA_17.json"))
        XCTAssertEqual(team.team.franchise?.venue?.fullName, "Prudential Center")
        let venue = try games("schedule_NBA_17.json").mostUsedHomeVenue(teamId: "17")
        XCTAssertEqual(venue?.name, "Barclays Center")
        XCTAssertEqual(venue?.city, "Brooklyn")
    }

    func testMostOfTheHomeGamesBeatsTheLatest() throws {
        // The Athletics played most of their season in Sacramento, then some in Las Vegas.
        let schedule = try games("schedule_MLB_11.json")
        XCTAssertEqual(schedule.last?.venueName, "Las Vegas Ballpark")
        let venue = schedule.mostUsedHomeVenue(teamId: "11")
        XCTAssertEqual(venue?.name, "Sutter Health Park")
        XCTAssertEqual(venue?.city, "Sacramento")
    }

    func testTheLaterVenueWinsATie() throws {
        var schedule = try games("schedule_MLB_11.json")
        let sutter = try XCTUnwrap(schedule.firstIndex { $0.venueName == "Sutter Health Park" })
        schedule.remove(at: sutter)
        XCTAssertEqual(schedule.mostUsedHomeVenue(teamId: "11")?.name, "Las Vegas Ballpark")
    }

    func testANeutralSiteIsNotAHomeGame() throws {
        // ESPN lists the Falcons as home in Madrid, and that game is the later one.
        let schedule = try games("schedule_NFL_1.json")
        XCTAssertEqual(schedule.last?.isNeutralSite, true)
        XCTAssertEqual(schedule.last?.homeTeam.id, "1")
        XCTAssertEqual(schedule.mostUsedHomeVenue(teamId: "1")?.name, "Mercedes-Benz Stadium")
    }

    func testAnotherTeamsHomeGamesAreNotThisTeams() throws {
        let schedule = try games("schedule_NBA_17.json")
        XCTAssertEqual(schedule.mostUsedHomeVenue(teamId: "2")?.name, "TD Garden")
        XCTAssertNil(schedule.mostUsedHomeVenue(teamId: "99999"))
    }

    func testSpringTrainingIsNotAHome() throws {
        // More games at Hohokam here than at either home park, and it isn't one.
        let spring = try games("schedule_MLB_11_spring.json")
        XCTAssertEqual(spring.first?.seasonType, 1)
        XCTAssertEqual(spring.filter { $0.homeTeam.id == "11" && $0.venueName == "Hohokam Stadium" }.count, 4)
        XCTAssertNil(spring.mostUsedHomeVenue(teamId: "11"))
        let season = try spring + games("schedule_MLB_11.json")
        XCTAssertEqual(season.mostUsedHomeVenue(teamId: "11")?.name, "Sutter Health Park")
    }

    /// A hub for the Nets, with the out of date venue ESPN's team page has for them.
    @MainActor
    private func nets(sport: Sport = .nba, regularSeason: @escaping () async throws -> [ScheduleGame]) -> TeamHubViewModel {
        let hub = TeamHubViewModel(teamId: "17", sport: sport) { _, _ in try await regularSeason() }
        hub.teamInfo = TeamHubTeamInfo(
            teamId: "17", displayName: "Brooklyn Nets", abbreviation: "BKN", location: "Brooklyn",
            color: nil, alternateColor: nil, primaryLogoURL: nil, overallRecord: nil,
            homeRecord: nil, awayRecord: nil, standingSummary: nil,
            venueName: "Prudential Center", venueCity: "Newark", coachName: nil, nextGame: nil)
        return hub
    }

    @MainActor
    func testTheVenueWaitsForTheSchedules() throws {
        let hub = nets { [] }
        hub.isLoadingSchedule = true
        XCTAssertNil(hub.teamVenue)
        hub.isLoadingSchedule = false
        hub.isLoadingHomeVenue = true
        XCTAssertNil(hub.teamVenue)
    }

    @MainActor
    func testAnEmptySeasonYearAsksForTheRegularSeasonBeforeTheFranchiseVenue() async throws {
        // currentSeasonYear rolls forward before ESPN has that schedule: from July the Nets'
        // schedule is empty, and this read Prudential Center.
        let season = try games("schedule_NBA_17.json")
        var asked = 0
        let hub = nets { asked += 1; return season }
        XCTAssertTrue(hub.schedule.isEmpty)
        await hub.loadHomeVenue()
        XCTAssertEqual(asked, 1)
        XCTAssertEqual(hub.teamVenue?.name, "Barclays Center")
        XCTAssertEqual(hub.teamVenue?.city, "Brooklyn")
    }

    @MainActor
    func testNoHomeGameOnTheScheduleAsksToo() async throws {
        // A preseason alone says nothing about where a team plays.
        let season = try games("schedule_MLB_11.json")
        let hub = TeamHubViewModel(teamId: "11", sport: .mlb) { _, _ in season }
        hub.schedule = try games("schedule_MLB_11_spring.json")
        await hub.loadHomeVenue()
        XCTAssertEqual(hub.teamVenue?.name, "Sutter Health Park")
    }

    @MainActor
    func testAScheduleWithHomeGamesAsksForNothingMore() async throws {
        var asked = 0
        let hub = nets { asked += 1; return [] }
        hub.schedule = try games("schedule_NBA_17.json")
        await hub.loadHomeVenue()
        XCTAssertEqual(asked, 0)
        XCTAssertEqual(hub.teamVenue?.name, "Barclays Center")
    }

    @MainActor
    func testTheFranchiseVenueIsWhatsLeftOnceBothAreEmpty() async throws {
        let hub = nets { [] }
        await hub.loadHomeVenue()
        XCTAssertEqual(hub.teamVenue?.name, "Prudential Center")
        XCTAssertEqual(hub.teamVenue?.city, "Newark")
    }

    @MainActor
    func testLosingTheRequestKeepsTheFranchiseVenue() async throws {
        let hub = nets { throw APIError.invalidResponse }
        await hub.loadHomeVenue()
        XCTAssertFalse(hub.isLoadingHomeVenue)
        XCTAssertEqual(hub.teamVenue?.name, "Prudential Center")
    }

    @MainActor
    func testAWorldCupTeamHasNoHome() async throws {
        // A team reaches this from a World Cup game's details. Its "home" games are
        // tournament draws, so Brazil would read MetLife Stadium.
        var asked = 0
        let hub = TeamHubViewModel(teamId: "17", sport: .worldCup) { _, _ in asked += 1; return [] }
        hub.schedule = try games("schedule_NBA_17.json")
        XCTAssertNil(hub.teamVenue)
        hub.schedule = []
        await hub.loadHomeVenue()
        XCTAssertEqual(asked, 0)
        XCTAssertNil(hub.teamVenue)
    }

    @MainActor
    func testTheCFLHasNoESPNScheduleToAskFor() async throws {
        var asked = 0
        let hub = TeamHubViewModel(teamId: "17", sport: .cfl) { _, _ in asked += 1; return [] }
        await hub.loadHomeVenue()
        XCTAssertEqual(asked, 0)
    }

    func testTheRegularSeasonRequestNamesNoSeason() {
        let api = ESPNAPIService.shared
        let nfl = api.regularSeasonScheduleURL(teamId: "14", sport: .nfl)
        XCTAssertTrue(nfl.hasSuffix("/football/nfl/teams/14/schedule?seasontype=2"), nfl)
        XCTAssertFalse(nfl.contains("season="), nfl)
        // ESPN's soccer season types have their own numbers, so 2 finds nothing.
        let epl = api.regularSeasonScheduleURL(teamId: "359", sport: .soccerEPL)
        XCTAssertTrue(epl.hasSuffix("/soccer/eng.1/teams/359/schedule"), epl)
    }

    func testRostersDecode() throws {
        // ESPN's NFL roster is grouped by position, and its NBA roster is flat.
        let nfl = try JSONDecoder().decode(RosterAPIResponse.self, from: Fixtures.data("roster_NFL_9.json"))
        XCTAssertFalse(try XCTUnwrap(nfl.athletes).isEmpty)
        let nba = try JSONDecoder().decode(FlatRosterAPIResponse.self, from: Fixtures.data("roster_NBA_15.json"))
        XCTAssertFalse(try XCTUnwrap(nba.athletes).isEmpty)
    }
}

final class DrivesTests: XCTestCase {
    func testALiveDriveIsListedOnce() throws {
        // ESPN lists the drive in progress under both `previous` and `current`.
        let json = """
        {"current": {"id": "2", "description": "live"},
         "previous": [{"id": "1", "description": "done"}, {"id": "2", "description": "live"}]}
        """
        let drives = try JSONDecoder().decode(GameDetails.DrivesContainer.self, from: Data(json.utf8))
        XCTAssertEqual(drives.all.map(\.id), ["1", "2"])
    }

    func testRealDrivesDecode() throws {
        let data = try Fixtures.subobject("drives", of: Fixtures.data("drives_NCAAF_2OT.json"))
        let drives = try JSONDecoder().decode(GameDetails.DrivesContainer.self, from: data)
        XCTAssertFalse(drives.all.isEmpty)
    }
}

final class ScoreboardDayTests: XCTestCase {
    private func date(_ day: Int, _ hour: Int) -> Date {
        var parts = DateComponents()
        parts.year = 2026; parts.month = 11; parts.day = day; parts.hour = hour
        return Calendar.current.date(from: parts)!
    }

    func testAfterMidnightItIsStillLastNight() {
        XCTAssertEqual(ScoreboardDay.today(now: date(3, 0)), date(2, 0))
        XCTAssertEqual(ScoreboardDay.today(now: date(3, 4)), date(2, 0))
    }

    func testFiveAMIsTheNewDay() {
        XCTAssertEqual(ScoreboardDay.today(now: date(3, 5)), date(3, 0))
    }

    func testTheEveningIsToday() {
        XCTAssertEqual(ScoreboardDay.today(now: date(2, 23)), date(2, 0))
    }

    func testHelpersAgree() {
        XCTAssertTrue(ScoreboardDay.isToday(date(2, 19), now: date(3, 1)))
        XCTAssertTrue(ScoreboardDay.isTomorrow(date(3, 19), now: date(3, 1)))
        XCTAssertTrue(ScoreboardDay.isYesterday(date(1, 19), now: date(3, 1)))
    }
}

final class RequestShapeTests: XCTestCase {
    /// ESPN's scoreboard answers `dates=START-END` with a 400 since September 2026. That
    /// broke the week arrows and the World Cup bracket, and nothing noticed until a bug
    /// bash (#70). Transactions is a different endpoint and still takes a range.
    func testNoScoreboardRequestUsesADateRange() throws {
        let services = Fixtures.repoRoot.appendingPathComponent("iOS/SportsScoresApp/SportsScores/Services")
        let files = try FileManager.default.contentsOfDirectory(at: services, includingPropertiesForKeys: nil)
            .filter { $0.pathExtension == "swift" }
        XCTAssertFalse(files.isEmpty)
        // Only sees ranges written in the URL, such as dates=\(a)-\(fmt.string(from: b)). A
        // range built up in a variable first can't be caught by reading the source.
        let range = try NSRegularExpression(pattern: #"dates=\\\(.*\)-\\\("#)
        var ranges = 0
        for file in files {
            let lines = try String(contentsOf: file, encoding: .utf8).components(separatedBy: .newlines)
            for (index, line) in lines.enumerated() where !line.trimmingCharacters(in: .whitespaces).hasPrefix("//") {
                guard range.firstMatch(in: line, range: NSRange(line.startIndex..., in: line)) != nil else { continue }
                ranges += 1
                let context = lines[max(0, index - 3)...index].joined(separator: " ")
                XCTAssertTrue(context.contains("/transactions"), "\(file.lastPathComponent):\(index + 1): \(line)")
            }
        }
        XCTAssertEqual(ranges, 1, "the pattern should still find the one in fetchTransactions, or it finds nothing")
    }
}
