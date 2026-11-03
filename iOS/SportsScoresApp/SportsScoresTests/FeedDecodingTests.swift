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

    /// Payloads saved from live ESPN, by kind. Skips the test when this isn't a live run.
    static func live(_ kind: String) throws -> [URL] {
        guard let path = ProcessInfo.processInfo.environment["LIVE_PAYLOADS"], !path.isEmpty else {
            throw XCTSkip("LIVE_PAYLOADS isn't set")
        }
        let files = try FileManager.default.contentsOfDirectory(at: URL(fileURLWithPath: path),
                                                                includingPropertiesForKeys: nil)
            .filter { $0.lastPathComponent.hasPrefix(kind + "-") }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
        XCTAssertFalse(files.isEmpty, "LIVE_PAYLOADS is \(path), and it has no \(kind)- files")
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

    func testAnEmptySlateIsNotAnError() throws {
        let response = try Fixtures.decodeScoreboard(board(with: [], keepingRealEvents: false))
        XCTAssertTrue(response.events.isEmpty)
    }

    func testLosingTheEventsKeyIsStillAnError() throws {
        XCTAssertThrowsError(try Fixtures.decodeScoreboard(Data(#"{"leagues": []}"#.utf8)))
    }

    func testLivePayloadsDecode() throws {
        for file in try Fixtures.live("scoreboard") {
            let response = try Fixtures.decodeScoreboard(Data(contentsOf: file))
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
