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

    func testGroup90HasEveryConferenceUnderItsOwnName() throws {
        let groups = try response("NCAAF_group90").groupsWithEntries.map(\.name)
        XCTAssertEqual(Set(groups), CollegeFootball.allConferences)
        XCTAssertEqual(groups.count, 25, "\(groups)")
    }

    func testAnFCSTeamReadsItsOverallRecord() throws {
        let team = try XCTUnwrap(try entries("NCAAF_group90").first { $0.team.displayName == "Montana State Bobcats" })
        XCTAssertEqual(team.stats.wins, 8)
        XCTAssertEqual(team.stats.losses, 1)
    }

    func testLivePayloadsDecode() throws {
        for file in try Fixtures.live("standings") {
            let decoded = try JSONDecoder().decode(APIStandingsResponse.self, from: Data(contentsOf: file))
            XCTAssertFalse(decoded.groupsWithEntries.isEmpty, file.lastPathComponent)
        }
    }
}

/// Team schedules on real answers, the same payloads and expected text as
/// tests/unit/replay/test_schedule.py and test_game_labels.py on Windows.
final class TeamScheduleTests: XCTestCase {
    private func games(_ fixture: String) throws -> [ScheduleGame] {
        let response = try JSONDecoder().decode(TeamScheduleAPIResponse.self, from: Fixtures.data(fixture))
        let games = response.events.compactMap { $0.toScheduleGame() }
        XCTAssertEqual(games.count, response.events.count, "\(fixture) lost a game")
        return games
    }

    private func game(id: String = "1", date: Date = Date(timeIntervalSince1970: 0), statusType: String = "STATUS_SCHEDULED",
                      home: Int? = nil, away: Int? = nil,
                      completed: Bool? = nil, state: String? = nil) -> ScheduleGame {
        ScheduleGame(id: id, date: date, name: "A at H",
                     awayTeam: .init(id: "A", abbreviation: "A", displayName: "Away", score: away),
                     homeTeam: .init(id: "H", abbreviation: "H", displayName: "Home", score: home),
                     statusText: "", statusType: statusType, seasonType: 2, venueName: nil,
                     espnCompleted: completed, espnState: state)
    }

    // MARK: Labels

    func testSuperBowlTakesItsNoteOverItsWeek() throws {
        let last = try XCTUnwrap(try games("schedule_NFL_26_post.json").last)
        XCTAssertEqual(last.label, "Super Bowl LX")
        XCTAssertTrue(last.isNeutralSite)
    }

    func testPreseasonFootballTakesItsWeek() throws {
        XCTAssertEqual(try games("schedule_NFL_26_pre.json").map(\.label),
                       ["Preseason Week 1", "Preseason Week 2", "Preseason Week 3"])
    }

    func testPreseasonWithNoWeekTakesTheSeasonTypeName() throws {
        XCTAssertEqual(try games("schedule_WNBA_8_pre.json").first?.label, "Preseason")
    }

    func testCollegePlayoffAndAConferenceTitleGame() throws {
        XCTAssertEqual(try games("schedule_NCAAF_333_post.json").map(\.label),
                       ["College Football Playoff First Round Game",
                        "College Football Playoff Quarterfinal at the Rose Bowl Presented by Prudential"])
        // Filed under the regular season, like FCS playoffs.
        XCTAssertEqual(try games("schedule_NCAAF_333_reg.json").first?.label, "SEC Championship")
    }

    func testWNBAPlayoffRounds() throws {
        XCTAssertEqual(try games("schedule_WNBA_8_post.json").map(\.label),
                       ["First Round - Game 1", "WNBA Semifinals - Game 1"])
    }

    func testAnEverydayWeekHasNoLabel() throws {
        XCTAssertEqual(try games("schedule_NFL_26_reg.json").compactMap(\.label), [])
    }

    func testSoccerSeasonIdsAreNotMistakenForAPostseason() throws {
        // seasonType.type here is 14308, and has to stay out of the 1-and-3 test.
        let results = try games("schedule_EPL_359_results.json")
        XCTAssertTrue(results.allSatisfy { $0.seasonType > 3 })
        XCTAssertEqual(results.compactMap(\.label), [])
    }

    func testANoteWithNoHeadlineIsNoLabel() throws {
        let labels = try games("schedule_UCL_359_2025.json").map(\.label)
        XCTAssertEqual(labels.count, 3)
        XCTAssertTrue(labels.contains("Paris Saint-Germain win 4-3 on penalties"))
        XCTAssertTrue(labels.contains(where: { $0?.hasPrefix("2nd Leg") == true }))
        XCTAssertTrue(labels.contains(where: { $0 == nil }), "the league phase game's note has no headline")
    }

    // MARK: Status

    func testFullTimeIsCompletedAndHasScores() throws {
        for game in try games("schedule_EPL_359_results.json") {
            XCTAssertEqual(game.statusType, "STATUS_FULL_TIME")
            XCTAssertTrue(game.isCompleted)
            XCTAssertFalse(game.isInProgress)
            XCTAssertNotNil(game.homeTeam.score)
            XCTAssertEqual(game.toGame().status.state, "post")
        }
    }

    func testAFinalOnPenaltiesIsCompletedAndADraw() throws {
        let shootout = try XCTUnwrap(try games("schedule_UCL_359_2025.json").first { $0.statusType == "STATUS_FINAL_PEN" })
        XCTAssertTrue(shootout.isCompleted)
        XCTAssertEqual(shootout.outcome(forTeamId: "359"), .tie)
    }

    func testFixturesAreToComeWithNoScores() throws {
        for game in try games("schedule_EPL_359_fixture.json") {
            XCTAssertFalse(game.isCompleted)
            XCTAssertFalse(game.isInProgress)
            XCTAssertNil(game.homeTeam.score)
            XCTAssertNil(game.outcome(forTeamId: "359"))
        }
    }

    func testFinishedStatusesWithNoWordFromESPN() {
        // CFL games come with no `completed` of their own, and go by the status name.
        for name in ["STATUS_FINAL", "STATUS_FULL_TIME", "STATUS_FINAL_PEN", "STATUS_FINAL_AET"] {
            XCTAssertTrue(game(statusType: name).isCompleted, name)
        }
        XCTAssertFalse(game(statusType: "STATUS_SCHEDULED").isCompleted)
        XCTAssertTrue(game(statusType: "STATUS_IN_PROGRESS").isInProgress)
    }

    func testESPNsOwnWordDecidesOtherStatuses() {
        // Saved in scoreboard_events_by_status.json: a forfeit is finished, a postponement
        // is not, and halftime and a delay are under way.
        XCTAssertTrue(game(statusType: "STATUS_FORFEIT", completed: true, state: "post").isCompleted)
        XCTAssertFalse(game(statusType: "STATUS_POSTPONED", completed: false, state: "post").isCompleted)
        XCTAssertFalse(game(statusType: "STATUS_POSTPONED", completed: false, state: "post").isInProgress)
        XCTAssertTrue(game(statusType: "STATUS_HALFTIME", completed: false, state: "in").isInProgress)
        XCTAssertTrue(game(statusType: "STATUS_DELAYED", completed: false, state: "in").isInProgress)
    }

    func testAGameCalledOffIsOverWithNothingPlayed() {
        for name in ["STATUS_POSTPONED", "STATUS_CANCELED"] {
            let calledOff = game(statusType: name, completed: false, state: "post")
            XCTAssertTrue(calledOff.isCalledOff, name)
            XCTAssertFalse(calledOff.isCompleted, name)
            XCTAssertEqual(calledOff.toGame().status.state, "post", "not a game still to come")
        }
    }

    func testOtherGamesAreNotCalledOff() {
        XCTAssertFalse(game(statusType: "STATUS_FINAL", completed: true, state: "post").isCalledOff)
        XCTAssertFalse(game(statusType: "STATUS_SCHEDULED", completed: false, state: "pre").isCalledOff)
        XCTAssertFalse(game(statusType: "STATUS_HALFTIME", completed: false, state: "in").isCalledOff)
        // CFL games say neither.
        XCTAssertFalse(game(statusType: "STATUS_SCHEDULED").isCalledOff)
    }

    // MARK: Outcome

    func testAPreseasonTieIsNotALoss() throws {
        let raiders = try XCTUnwrap(try games("schedule_NFL_26_pre.json").first)
        XCTAssertEqual(raiders.homeTeam.score, 23)
        XCTAssertEqual(raiders.outcome(forTeamId: "26"), .tie)
    }

    func testOutcomeIsForTheTeamAsked() throws {
        let superBowl = try XCTUnwrap(try games("schedule_NFL_26_post.json").last)
        XCTAssertEqual(superBowl.awayTeam.id, "26")
        XCTAssertEqual(superBowl.outcome(forTeamId: "26"), .win)
        XCTAssertEqual(superBowl.outcome(forTeamId: "17"), .loss)
    }

    // MARK: What gets asked for

    func testEverySoccerLeagueAndWorldCupGoesByResultsAndFixtures() {
        for sport in Sport.soccerLeagues + [.worldCup, .worldCupWomens] {
            XCTAssertTrue(sport.usesSoccerSchedule, sport.rawValue)
        }
    }

    func testOtherSportsGoBySeasonTypeAndAskForAllThree() {
        for sport in Sport.allCases {
            XCTAssertFalse(sport.usesSoccerSchedule, sport.rawValue)
        }
        XCTAssertEqual(TeamScheduleQueries.seasonTypes, [1, 2, 3])
        XCTAssertEqual(TeamScheduleQueries.seasonType(3, season: 2025), "season=2025&seasontype=3")
    }

    func testSoccerQueriesSendNoSeasonType() {
        XCTAssertEqual(TeamScheduleQueries.soccerResults(season: 2026), "season=2026")
        XCTAssertEqual(TeamScheduleQueries.soccerFixtures, "fixture=true")
    }

    func testAPastSoccerSeasonAsksForNoFixtures() throws {
        let response = try JSONDecoder().decode(TeamScheduleAPIResponse.self,
                                                from: Fixtures.data("schedule_EPL_359_2025.json"))
        XCTAssertEqual(response.season?.year, 2026)
        let next = TeamScheduleQueries.afterSoccerResults(season: 2025, currentSeason: 2026,
                                                          espnSeason: response.season?.year)
        XCTAssertFalse(next.fixtures)
        XCTAssertNil(next.earlierResults)
    }

    func testTheCurrentSoccerSeasonAsksForFixtures() {
        let next = TeamScheduleQueries.afterSoccerResults(season: 2026, currentSeason: 2026, espnSeason: 2026)
        XCTAssertTrue(next.fixtures)
        XCTAssertNil(next.earlierResults)
    }

    func testAResponseNamingNoSeasonIsTakenAsTheOneAskedFor() {
        let next = TeamScheduleQueries.afterSoccerResults(season: 2026, currentSeason: 2026, espnSeason: nil)
        XCTAssertTrue(next.fixtures)
        XCTAssertNil(next.earlierResults)
    }

    func testAcrossTheNewYearTheSeasonInPlayIsAskedForToo() {
        // February 2027: season=2027 is empty for the Premier League, whose season.year is 2026.
        let next = TeamScheduleQueries.afterSoccerResults(season: 2027, currentSeason: 2027, espnSeason: 2026)
        XCTAssertTrue(next.fixtures)
        XCTAssertEqual(next.earlierResults, 2026)
    }

    func testOnlyTheYearBeforeCountsAsESPNsSeasonBehindOurs() {
        // The Women's World Cup's season.year stays at 2023 between tournaments. This used to
        // ask for 2023's games and show them as current.
        let next = TeamScheduleQueries.afterSoccerResults(season: 2026, currentSeason: 2026, espnSeason: 2023)
        XCTAssertTrue(next.fixtures)
        XCTAssertNil(next.earlierResults)
    }

    func testPickingTheSeasonESPNCallsCurrentAsksForFixtures() {
        let next = TeamScheduleQueries.afterSoccerResults(season: 2026, currentSeason: 2027, espnSeason: 2026)
        XCTAssertTrue(next.fixtures)
        XCTAssertNil(next.earlierResults)
    }

    func testMLSFixturesCanBeNextSeasons() throws {
        let response = try JSONDecoder().decode(TeamScheduleAPIResponse.self,
                                                from: Fixtures.data("schedule_MLS_18418_fixture.json"))
        XCTAssertEqual(response.season?.year, 2026)
        XCTAssertFalse(response.events.isEmpty)
    }

    // MARK: Merging

    func testResultsAndFixturesMergeInDateOrder() throws {
        let merged = TeamScheduleQueries.merged([try games("schedule_EPL_359_results.json"),
                                                 try games("schedule_EPL_359_fixture.json")])
        XCTAssertEqual(merged.count, 6)
        XCTAssertEqual(merged.map(\.date), merged.map(\.date).sorted())
        XCTAssertEqual(merged.prefix(3).filter(\.isCompleted).count, 3)
        XCTAssertEqual(merged.suffix(3).filter(\.isCompleted).count, 0)
    }

    func testAGameInBothListsKeepsItsResult() {
        let played = game(id: "9", statusType: "STATUS_FULL_TIME", home: 1, away: 0, completed: true, state: "post")
        let stillListed = game(id: "9", completed: false, state: "pre")
        let merged = TeamScheduleQueries.merged([[played], [stillListed]])
        XCTAssertEqual(merged.count, 1)
        XCTAssertTrue(merged[0].isCompleted)
    }

    func testAllThreeFootballSeasonTypesMergeWithTheSuperBowlLast() throws {
        let merged = TeamScheduleQueries.merged([try games("schedule_NFL_26_post.json"),
                                                 try games("schedule_NFL_26_reg.json"),
                                                 try games("schedule_NFL_26_pre.json")])
        XCTAssertEqual(merged.count, 8)
        XCTAssertEqual(merged.first?.label, "Preseason Week 1")
        XCTAssertEqual(merged.last?.label, "Super Bowl LX")
    }
}

/// Stands in for ESPN behind a real URLSession, so the real fetching code runs.
final class StubESPN: URLProtocol {
    enum Reply {
        case body(Data)
        case delayed(TimeInterval, Data)
        case status(Int)
        case failure(URLError)
    }

    private static let lock = NSLock()
    private static var handler: ((URL) -> Reply)?
    private static var seen: [URL] = []

    static func answer(_ handler: @escaping (URL) -> Reply) {
        lock.lock(); defer { lock.unlock() }
        self.handler = handler
        seen = []
    }

    static var requests: [URL] {
        lock.lock(); defer { lock.unlock() }
        return seen
    }

    static func session() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubESPN.self]
        return URLSession(configuration: config)
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        guard let url = request.url else { return }
        Self.lock.lock()
        Self.seen.append(url)
        let reply = Self.handler?(url) ?? .status(599)
        Self.lock.unlock()
        switch reply {
        case .failure(let error):
            client?.urlProtocol(self, didFailWithError: error)
            return
        case .body(let data):
            respond(status: 200, data: data)
        case .delayed(let seconds, let data):
            // Weak: a request cancelled in the meantime has nobody to answer.
            DispatchQueue.global().asyncAfter(deadline: .now() + seconds) { [weak self] in
                self?.respond(status: 200, data: data)
            }
        case .status(let code):
            respond(status: code, data: Data("{}".utf8))
        }
    }

    private func respond(status: Int, data: Data) {
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
}

/// What happens when ESPN doesn't answer, the same rules as Windows: a failure throws, it
/// never reads as an empty season or falls back to last season, and a cancelled request is
/// neither a failure nor an empty season.
@MainActor
final class TeamScheduleFailureTests: XCTestCase {
    private let empty = Data(#"{"events":[]}"#.utf8)
    private let timedOut = StubESPN.Reply.failure(URLError(.timedOut))

    private func thrown(_ service: ESPNAPIService, sport: Sport = .nfl, season: Int) async -> Error? {
        do {
            _ = try await service.fetchTeamSeasonSchedule(teamId: sport.isFootball ? "26" : "359", sport: sport, season: season)
            return nil
        } catch {
            return error
        }
    }

    /// All three of Seattle's season types, with `failing` answering `reply`.
    private func seahawks(failing: String? = nil, reply: StubESPN.Reply? = nil) throws {
        let pre = try Fixtures.data("schedule_NFL_26_pre.json")
        let regular = try Fixtures.data("schedule_NFL_26_reg.json")
        let post = try Fixtures.data("schedule_NFL_26_post.json")
        StubESPN.answer { url in
            let query = url.query ?? ""
            if let failing, let reply, query.contains(failing) { return reply }
            if query.contains("seasontype=1") { return .body(pre) }
            return .body(query.contains("seasontype=2") ? regular : post)
        }
    }

    // MARK: Season types

    func testEverySeasonTypeAnswering() async throws {
        try seahawks()
        let games = try await ESPNAPIService(session: StubESPN.session())
            .fetchTeamSeasonSchedule(teamId: "26", sport: .nfl, season: 2025)
        XCTAssertEqual(games.count, 8)
        XCTAssertEqual(games.last?.label, "Super Bowl LX")
        // Only this season's: URLSession can still start a request of the previous test's
        // cancelled task after that test ends, and it lands in the same static list.
        let queries = Set(StubESPN.requests.compactMap(\.query).filter { $0.contains("season=2025") })
        XCTAssertEqual(queries, ["season=2025&seasontype=1", "season=2025&seasontype=2", "season=2025&seasontype=3"])
    }

    func testATimeoutOnAnySeasonTypeThrows() async throws {
        for failing in ["seasontype=1", "seasontype=2", "seasontype=3"] {
            try seahawks(failing: failing, reply: timedOut)
            let error = await thrown(ESPNAPIService(session: StubESPN.session()), season: 2025)
            XCTAssertEqual((error as? URLError)?.code, .timedOut, failing)
        }
    }

    func testADroppedConnectionOnAnySeasonTypeThrows() async throws {
        for failing in ["seasontype=1", "seasontype=2", "seasontype=3"] {
            try seahawks(failing: failing, reply: .failure(URLError(.networkConnectionLost)))
            let error = await thrown(ESPNAPIService(session: StubESPN.session()), season: 2025)
            XCTAssertNotNil(error, failing)
        }
    }

    func testAServerErrorOnAnySeasonTypeThrows() async throws {
        for failing in ["seasontype=1", "seasontype=2", "seasontype=3"] {
            try seahawks(failing: failing, reply: .status(500))
            let error = await thrown(ESPNAPIService(session: StubESPN.session()), season: 2025)
            XCTAssertNotNil(error, failing)
            XCTAssertFalse(error?.isNothingThere ?? true, failing)
        }
    }

    func testNothingThereOnTheRegularSeasonThrows() async throws {
        try seahawks(failing: "seasontype=2", reply: .status(404))
        let error = await thrown(ESPNAPIService(session: StubESPN.session()), season: 2025)
        XCTAssertNotNil(error)
    }

    func testNothingThereOnPreseasonOrPostseasonLeavesOutOnlyThat() async throws {
        for (failing, count) in [("seasontype=1", 5), ("seasontype=3", 5)] {
            try seahawks(failing: failing, reply: .status(404))
            let games = try await ESPNAPIService(session: StubESPN.session())
                .fetchTeamSeasonSchedule(teamId: "26", sport: .nfl, season: 2025)
            XCTAssertEqual(games.count, count, failing)
        }
    }

    func testBadBodiesThrow() async {
        StubESPN.answer { _ in .body(Data("<html>".utf8)) }
        let error = await thrown(ESPNAPIService(session: StubESPN.session()), season: 2025)
        XCTAssertNotNil(error)
    }

    // MARK: Soccer

    private func arsenal(failing: String? = nil, reply: StubESPN.Reply? = nil) throws {
        let results = try Fixtures.data("schedule_EPL_359_results.json")
        let fixtures = try Fixtures.data("schedule_EPL_359_fixture.json")
        StubESPN.answer { url in
            let query = url.query ?? ""
            if let failing, let reply, query.contains(failing) { return reply }
            return .body(query.contains("fixture=true") ? fixtures : results)
        }
    }

    func testAPastSoccerSeasonAsksForItsResultsAndNothingElse() async throws {
        try arsenal()
        let games = try await ESPNAPIService(session: StubESPN.session())
            .fetchTeamSeasonSchedule(teamId: "359", sport: .soccerEPL, season: 2020)
        XCTAssertEqual(StubESPN.requests.compactMap(\.query), ["season=2020"])
        XCTAssertEqual(games.count, 3)
    }

    func testTheCurrentSoccerSeasonAsksForResultsAndFixturesWithNoSeasonType() async throws {
        try arsenal()
        let season = Sport.soccerEPL.currentSeasonYear
        let games = try await ESPNAPIService(session: StubESPN.session())
            .fetchTeamSeasonSchedule(teamId: "359", sport: .soccerEPL, season: season)
        let queries = StubESPN.requests.compactMap(\.query)
        XCTAssertEqual(queries.first, "season=\(season)")
        XCTAssertEqual(queries.last, "fixture=true")
        XCTAssertFalse(queries.contains { $0.contains("seasontype") })
        XCTAssertEqual(games.count, 6)
    }

    func testAFailureOnEitherSoccerListThrows() async throws {
        let season = Sport.soccerEPL.currentSeasonYear
        for failing in ["season=", "fixture=true"] {
            for reply in [timedOut, StubESPN.Reply.status(500)] {
                try arsenal(failing: failing, reply: reply)
                let error = await thrown(ESPNAPIService(session: StubESPN.session()), sport: .soccerEPL, season: season)
                XCTAssertNotNil(error, failing)
            }
        }
    }

    func testNothingThereOnSoccerFixturesKeepsTheResults() async throws {
        try arsenal(failing: "fixture=true", reply: .status(404))
        let games = try await ESPNAPIService(session: StubESPN.session())
            .fetchTeamSeasonSchedule(teamId: "359", sport: .soccerEPL, season: Sport.soccerEPL.currentSeasonYear)
        XCTAssertEqual(games.count, 3)
    }

    func testNothingThereOnSoccerResultsThrows() async throws {
        try arsenal(failing: "season=", reply: .status(404))
        let error = await thrown(ESPNAPIService(session: StubESPN.session()), sport: .soccerEPL,
                                 season: Sport.soccerEPL.currentSeasonYear)
        XCTAssertNotNil(error)
    }

    // MARK: The schedule screen

    private func screen() -> TeamScheduleViewModel {
        TeamScheduleViewModel(teamId: "26", sport: .nfl, apiService: ESPNAPIService(session: StubESPN.session()))
    }

    func testAFailureSaysSoAndDoesNotFallBackToLastSeason() async throws {
        let viewModel = screen()
        let season = viewModel.selectedYear
        let regular = try Fixtures.data("schedule_NFL_26_reg.json")
        let failure = timedOut
        StubESPN.answer { url in
            (url.query ?? "").contains("season=\(season)&") ? failure : .body(regular)
        }
        await viewModel.fetchSchedule()
        XCTAssertTrue(viewModel.loadFailed)
        XCTAssertNotNil(viewModel.errorMessage)
        XCTAssertTrue(viewModel.games.isEmpty)
        XCTAssertEqual(viewModel.selectedYear, season)
        XCTAssertFalse(StubESPN.requests.contains { ($0.query ?? "").contains("season=\(season - 1)") })
        XCTAssertFalse(viewModel.isLoading)
    }

    func testAServerErrorDoesNotFallBackEither() async throws {
        let viewModel = screen()
        let season = viewModel.selectedYear
        StubESPN.answer { _ in .status(503) }
        await viewModel.fetchSchedule()
        XCTAssertTrue(viewModel.loadFailed)
        XCTAssertEqual(viewModel.selectedYear, season)
    }

    func testAnEmptyCurrentSeasonFallsBackToTheLastOne() async throws {
        let viewModel = screen()
        let season = viewModel.selectedYear
        let regular = try Fixtures.data("schedule_NFL_26_reg.json")
        let nothing = empty
        StubESPN.answer { url in
            .body((url.query ?? "").contains("season=\(season - 1)&seasontype=2") ? regular : nothing)
        }
        await viewModel.fetchSchedule()
        XCTAssertEqual(viewModel.selectedYear, season - 1)
        XCTAssertEqual(viewModel.games.count, 2)
        XCTAssertFalse(viewModel.loadFailed)
        XCTAssertNil(viewModel.errorMessage)
    }

    func testAnEmptyPastSeasonSaysSoAndIsNotAFailure() async throws {
        let viewModel = screen()
        let nothing = empty
        StubESPN.answer { _ in .body(nothing) }
        await viewModel.changeYear(viewModel.selectedYear - 2)
        XCTAssertFalse(viewModel.loadFailed)
        XCTAssertNotNil(viewModel.errorMessage)
    }

    func testACancelledRequestIsNeitherAFailureNorEmptyAndKeepsTheGames() async throws {
        let viewModel = screen()
        try seahawks()
        await viewModel.fetchSchedule()
        XCTAssertEqual(viewModel.games.count, 8)

        let season = viewModel.selectedYear
        StubESPN.answer { _ in .failure(URLError(.cancelled)) }
        await viewModel.fetchSchedule()
        XCTAssertEqual(viewModel.games.count, 8)
        XCTAssertNil(viewModel.errorMessage)
        XCTAssertFalse(viewModel.loadFailed)
        XCTAssertFalse(viewModel.isLoading)
        XCTAssertEqual(viewModel.selectedYear, season)
    }

    func testCancellingTheTaskIsNotAFailure() async throws {
        let viewModel = screen()
        let season = viewModel.selectedYear
        try seahawks()
        let task = Task { await viewModel.fetchSchedule() }
        task.cancel()
        await task.value
        XCTAssertNil(viewModel.errorMessage)
        XCTAssertFalse(viewModel.loadFailed)
        XCTAssertFalse(viewModel.isLoading)
        XCTAssertEqual(viewModel.selectedYear, season, "and no fallback to last season")
    }

    func testCancellationErrorsAreRecognised() {
        XCTAssertTrue(CancellationError().isCancellation)
        XCTAssertTrue(URLError(.cancelled).isCancellation)
        XCTAssertFalse(URLError(.timedOut).isCancellation)
        XCTAssertFalse(APIError.invalidResponse.isCancellation)
    }

    // MARK: Team Hub

    private func hub() -> TeamHubViewModel {
        TeamHubViewModel(teamId: "26", sport: .nfl, apiService: ESPNAPIService(session: StubESPN.session()),
                         fetchRegularSeason: { _, _ in [] })
    }

    /// Team info answers at once, and the schedule as `schedule` says.
    private func teamInfoThenSchedule(_ schedule: StubESPN.Reply) throws {
        let team = try Fixtures.data("team_NFL_9.json")
        StubESPN.answer { url in url.path.hasSuffix("/schedule") ? schedule : .body(team) }
    }

    func testInfoAsksAgainWhenItsScheduleWasCancelled() async throws {
        let viewModel = hub()
        try teamInfoThenSchedule(.failure(URLError(.cancelled)))
        await viewModel.loadInfo()
        XCTAssertNotNil(viewModel.teamInfo)
        XCTAssertTrue(viewModel.schedule.isEmpty)
        XCTAssertNil(viewModel.errorSchedule)

        try seahawks()
        await viewModel.loadInfo()
        XCTAssertEqual(viewModel.schedule.count, 8)
    }

    func testCancellingLoadInfoForRealAndCallingItAgain() async throws {
        let viewModel = hub()
        try teamInfoThenSchedule(.delayed(2, Data(#"{"events":[]}"#.utf8)))
        let task = Task { await viewModel.loadInfo() }
        for _ in 0..<500 where viewModel.teamInfo == nil {
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        XCTAssertNotNil(viewModel.teamInfo)
        task.cancel()
        await task.value
        XCTAssertTrue(viewModel.schedule.isEmpty)
        XCTAssertNil(viewModel.errorSchedule)

        try seahawks()
        await viewModel.loadInfo()
        XCTAssertEqual(viewModel.schedule.count, 8)
    }

    func testInfoDoesNotAskAgainOnceTheScheduleHasAnswered() async throws {
        let viewModel = hub()
        let nothing = empty
        let team = try Fixtures.data("team_NFL_9.json")
        StubESPN.answer { url in .body(url.path.hasSuffix("/schedule") ? nothing : team) }
        await viewModel.loadInfo()
        XCTAssertTrue(viewModel.schedule.isEmpty)
        let asked = StubESPN.requests.count
        await viewModel.loadInfo()
        XCTAssertEqual(StubESPN.requests.count, asked)
    }

    func testInfoDoesNotAskAgainAfterAFailureItIsShowing() async throws {
        let viewModel = hub()
        try teamInfoThenSchedule(timedOut)
        await viewModel.loadInfo()
        XCTAssertNotNil(viewModel.errorSchedule)
        let asked = StubESPN.requests.count
        await viewModel.loadInfo()
        XCTAssertEqual(StubESPN.requests.count, asked)
    }

    func testTeamHubReadsNothingThereAsNoScheduleNotAFailure() async {
        let viewModel = hub()
        StubESPN.answer { _ in .status(404) }
        await viewModel.loadSchedule()
        XCTAssertNil(viewModel.errorSchedule)
        XCTAssertTrue(viewModel.schedule.isEmpty)
    }

    // MARK: Team Hub's season

    func testTeamHubShowsTheLastSeasonWhenTheCurrentOneIsEmpty() async throws {
        let season = Sport.nfl.currentSeasonYear
        let regular = try Fixtures.data("schedule_NFL_26_reg.json")
        let nothing = empty
        StubESPN.answer { url in
            .body((url.query ?? "").contains("season=\(season - 1)&seasontype=2") ? regular : nothing)
        }
        let viewModel = hub()
        await viewModel.loadSchedule()
        XCTAssertEqual(viewModel.schedule.count, 2)
        XCTAssertNil(viewModel.errorSchedule)
    }

    func testTeamHubDoesNotFallBackAfterAFailure() async {
        let season = Sport.nfl.currentSeasonYear
        let failure = timedOut
        StubESPN.answer { _ in failure }
        let viewModel = hub()
        await viewModel.loadSchedule()
        XCTAssertNotNil(viewModel.errorSchedule)
        XCTAssertFalse(StubESPN.requests.contains { ($0.query ?? "").contains("season=\(season - 1)") })
    }

    // MARK: A favorite's card

    private func cardGames(_ sport: Sport = .nfl) async throws -> [ScheduleGame] {
        try await ESPNAPIService(session: StubESPN.session())
            .fetchFavoriteCardSchedule(teamId: sport.isFootball ? "26" : "359", sport: sport)
    }

    func testAFavoriteKeepsItsGamesWhenOnePartFails() async throws {
        for failing in ["seasontype=1", "seasontype=2", "seasontype=3"] {
            for reply in [timedOut, StubESPN.Reply.status(500)] {
                try seahawks(failing: failing, reply: reply)
                let games = try await cardGames()
                XCTAssertFalse(games.isEmpty, failing)
                XCTAssertLessThan(games.count, 8, failing)
            }
        }
    }

    func testAFavoriteWithEveryPartFailingThrows() async {
        let failure = timedOut
        StubESPN.answer { _ in failure }
        do {
            _ = try await cardGames()
            XCTFail("Expected an error")
        } catch {
            XCTAssertEqual((error as? URLError)?.code, .timedOut)
        }
    }

    func testASoccerFavoriteKeepsWhicheverListLoaded() async throws {
        try arsenal(failing: "fixture=true", reply: .status(500))
        let results = try await cardGames(.soccerEPL)
        XCTAssertEqual(results.count, 3)
        XCTAssertTrue(results.allSatisfy(\.isCompleted))

        try arsenal(failing: "season=", reply: .status(500))
        let fixtures = try await cardGames(.soccerEPL)
        XCTAssertEqual(fixtures.count, 3)
        XCTAssertFalse(fixtures.contains(where: \.isCompleted))
    }

    func testASoccerFavoriteWithBothListsFailingThrows() async {
        let failure = timedOut
        StubESPN.answer { _ in failure }
        do {
            _ = try await cardGames(.soccerEPL)
            XCTFail("Expected an error")
        } catch {}
    }

    // MARK: Statuses ESPN means as failures

    func testOnly400And404MeanNothingThere() async throws {
        for status in [403, 429, 500, 503] {
            for failing in ["seasontype=1", "seasontype=2", "seasontype=3"] {
                try seahawks(failing: failing, reply: .status(status))
                let error = await thrown(ESPNAPIService(session: StubESPN.session()), season: 2025)
                XCTAssertNotNil(error, "\(status) on \(failing)")
                XCTAssertFalse(error?.isNothingThere ?? true, "\(status) on \(failing)")
            }
        }
        for status in [400, 404] {
            try seahawks(failing: "seasontype=3", reply: .status(status))
            let games = try await ESPNAPIService(session: StubESPN.session())
                .fetchTeamSeasonSchedule(teamId: "26", sport: .nfl, season: 2025)
            XCTAssertEqual(games.count, 5)
            try seahawks(failing: "seasontype=2", reply: .status(status))
            let error = await thrown(ESPNAPIService(session: StubESPN.session()), season: 2025)
            XCTAssertEqual(error?.isNothingThere, true)
        }
    }

    func testOneUnreadableGameAloneOnAPageCostsOnlyThatGame() async throws {
        // A team with one bowl game, whose event can't be read. Windows just skips the row.
        try seahawks(failing: "seasontype=3", reply: .body(Data(#"{"events":[{"id":"1"}]}"#.utf8)))
        let games = try await ESPNAPIService(session: StubESPN.session())
            .fetchTeamSeasonSchedule(teamId: "26", sport: .nfl, season: 2025)
        XCTAssertEqual(games.count, 5)
    }

    // MARK: Refreshes and picking a year

    func testNothingThereReadsAsNoScheduleWithNoFallback() async {
        let viewModel = screen()
        let season = viewModel.selectedYear
        StubESPN.answer { _ in .status(404) }
        await viewModel.fetchSchedule()
        XCTAssertNotNil(viewModel.errorMessage)
        XCTAssertFalse(viewModel.loadFailed)
        XCTAssertEqual(viewModel.selectedYear, season)
        XCTAssertFalse(StubESPN.requests.contains { ($0.query ?? "").contains("season=\(season - 1)") })
    }

    func testAFailedRefreshKeepsTheListAndSaysSoSeparately() async throws {
        let viewModel = screen()
        try seahawks()
        await viewModel.fetchSchedule()
        XCTAssertEqual(viewModel.games.count, 8)

        let failure = timedOut
        StubESPN.answer { _ in failure }
        await viewModel.fetchSchedule()
        XCTAssertEqual(viewModel.games.count, 8)
        XCTAssertTrue(viewModel.refreshFailed)
        XCTAssertFalse(viewModel.loadFailed)
        XCTAssertNil(viewModel.errorMessage)
        XCTAssertFalse(viewModel.isLoading)

        try seahawks()
        await viewModel.fetchSchedule()
        XCTAssertFalse(viewModel.refreshFailed)
    }

    func testPickingAYearAfterAFailedRefreshStartsClean() async throws {
        let viewModel = screen()
        try seahawks()
        await viewModel.fetchSchedule()
        let failure = timedOut
        StubESPN.answer { _ in failure }
        await viewModel.fetchSchedule()
        XCTAssertTrue(viewModel.refreshFailed)

        await viewModel.changeYear(viewModel.selectedYear - 1)
        XCTAssertFalse(viewModel.refreshFailed)
        XCTAssertTrue(viewModel.games.isEmpty, "the old year's games don't stand in for this one")
        XCTAssertTrue(viewModel.loadFailed)
    }

    func testAnOlderReplyArrivingLastDoesNotReplaceTheSeasonPicked() async throws {
        let viewModel = screen()
        let slowYear = viewModel.selectedYear - 1
        let quickYear = viewModel.selectedYear - 2
        let regular = try Fixtures.data("schedule_NFL_26_reg.json")
        let post = try Fixtures.data("schedule_NFL_26_post.json")
        let nothing = empty
        StubESPN.answer { url in
            let query = url.query ?? ""
            if query == "season=\(slowYear)&seasontype=2" { return .delayed(0.5, regular) }
            if query == "season=\(quickYear)&seasontype=2" { return .body(post) }
            return .body(nothing)
        }

        let slow = Task { await viewModel.changeYear(slowYear) }
        for _ in 0..<500 where !StubESPN.requests.contains(where: { ($0.query ?? "").contains("season=\(slowYear)") }) {
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        await viewModel.changeYear(quickYear)
        XCTAssertEqual(viewModel.games.count, 3)
        XCTAssertFalse(viewModel.isLoading)

        await slow.value
        XCTAssertEqual(viewModel.selectedYear, quickYear)
        XCTAssertEqual(viewModel.games.count, 3, "still the season picked")
        XCTAssertEqual(viewModel.games.last?.label, "Super Bowl LX")
        XCTAssertFalse(viewModel.isLoading)
    }

    func testAnOlderFailureArrivingLastIsIgnoredToo() async throws {
        let viewModel = screen()
        let slowYear = viewModel.selectedYear - 1
        let quickYear = viewModel.selectedYear - 2
        let post = try Fixtures.data("schedule_NFL_26_post.json")
        let nothing = empty
        StubESPN.answer { url in
            let query = url.query ?? ""
            if query == "season=\(slowYear)&seasontype=2" { return .delayed(0.5, Data("<html>".utf8)) }
            return .body(query == "season=\(quickYear)&seasontype=2" ? post : nothing)
        }

        let slow = Task { await viewModel.changeYear(slowYear) }
        for _ in 0..<500 where !StubESPN.requests.contains(where: { ($0.query ?? "").contains("season=\(slowYear)") }) {
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        await viewModel.changeYear(quickYear)
        await slow.value
        XCTAssertEqual(viewModel.games.count, 3)
        XCTAssertFalse(viewModel.loadFailed)
        XCTAssertNil(viewModel.errorMessage)
    }

    // MARK: A game called off with its date ahead

    private func futureGame(id: String, days: Int, completed: Bool, state: String) -> ScheduleGame {
        ScheduleGame(id: id, date: Date().addingTimeInterval(TimeInterval(days) * 86_400), name: "A at H",
                     awayTeam: .init(id: "26", abbreviation: "A", displayName: "Away", score: nil),
                     homeTeam: .init(id: "H", abbreviation: "H", displayName: "Home", score: nil),
                     statusText: state == "post" ? "Postponed" : "Scheduled",
                     statusType: state == "post" ? "STATUS_POSTPONED" : "STATUS_SCHEDULED", seasonType: 2,
                     venueName: nil, espnCompleted: completed, espnState: state)
    }

    func testAPostponedGameIsNotTheNextGameButStaysListedAsUpcoming() {
        let viewModel = hub()
        viewModel.schedule = [futureGame(id: "rainout", days: 2, completed: false, state: "post"),
                              futureGame(id: "next", days: 5, completed: false, state: "pre")]
        XCTAssertEqual(viewModel.upcomingGame?.id, "next")
        XCTAssertEqual(viewModel.upcomingGames.map(\.id), ["rainout", "next"])
    }

    func testAPostponedGameAloneLeavesNoNextGame() {
        let viewModel = hub()
        viewModel.schedule = [futureGame(id: "rainout", days: 2, completed: false, state: "post")]
        XCTAssertNil(viewModel.upcomingGame)
    }

    func testTheFavoriteCardsNextGameSkipsAPostponedOne() {
        // What FavoriteTeamCardView.nextGame asks.
        let schedule = [futureGame(id: "rainout", days: 2, completed: false, state: "post"),
                        futureGame(id: "next", days: 5, completed: false, state: "pre")]
        XCTAssertEqual(schedule.nextToPlay(after: Date())?.id, "next")
        XCTAssertNil([schedule[0]].nextToPlay(after: Date()))
    }

    private func teamInfo(nextEventState state: String, completed: Bool) async throws -> TeamHubTeamInfo {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Fixtures.data("team_NFL_9.json")) as? [String: Any])
        var team = try XCTUnwrap(object["team"] as? [String: Any])
        var events = try XCTUnwrap(team["nextEvent"] as? [[String: Any]])
        var competitions = try XCTUnwrap(events[0]["competitions"] as? [[String: Any]])
        competitions[0]["status"] = ["type": ["completed": completed, "state": state]]
        competitions[0]["timeValid"] = true
        events[0]["competitions"] = competitions
        events[0]["date"] = "2099-01-03T18:00Z"
        events[0]["timeValid"] = true
        team["nextEvent"] = events
        object["team"] = team
        let body = try JSONSerialization.data(withJSONObject: object)
        StubESPN.answer { _ in .body(body) }
        return try await ESPNAPIService(session: StubESPN.session()).fetchTeamHubInfo(teamId: "9", sport: .nfl)
    }

    func testTeamInfosNextGameIsNotOneCalledOff() async throws {
        let scheduled = try await teamInfo(nextEventState: "pre", completed: false)
        XCTAssertNotNil(scheduled.nextGame)
        let calledOff = try await teamInfo(nextEventState: "post", completed: false)
        XCTAssertNil(calledOff.nextGame)
    }

    func testTeamHubSaysSoOnAFailure() async {
        let viewModel = hub()
        let failure = timedOut
        StubESPN.answer { _ in failure }
        await viewModel.loadSchedule()
        XCTAssertNotNil(viewModel.errorSchedule)
        XCTAssertTrue(viewModel.schedule.isEmpty)
        XCTAssertFalse(viewModel.isLoadingSchedule)
    }

    func testTeamHubDoesNotCountCancellationAsAFailureAndAsksAgainNextTime() async throws {
        let viewModel = hub()
        StubESPN.answer { _ in .failure(URLError(.cancelled)) }
        await viewModel.loadSchedule()
        XCTAssertNil(viewModel.errorSchedule)
        XCTAssertFalse(viewModel.isLoadingSchedule)

        try seahawks()
        await viewModel.loadSchedule()
        XCTAssertEqual(viewModel.schedule.count, 8)
    }
}

enum CollegeFootball {
    static let fcsConferences: Set<String> = [
        "Big Sky Conference", "Coastal Athletic Association", "FCS Independents", "Ivy League",
        "Mid-Eastern Athletic Conference", "Missouri Valley Football Conference", "Northeast Conference",
        "Ohio Valley Conference", "Patriot League", "Pioneer Football League", "Southern Conference",
        "Southland Conference", "Southwestern Athletic Conference", "United Athletic Conference",
    ]
    static let fbsConferences: Set<String> = [
        "American Conference", "Atlantic Coast Conference", "Big 12 Conference", "Big Ten Conference",
        "Conference USA", "FBS Independents", "Mid-American Conference", "Mountain West Conference",
        "Pac-12 Conference", "Southeastern Conference", "Sun Belt Conference",
    ]
    static var allConferences: Set<String> { fcsConferences.union(fbsConferences) }
}

/// Team Hub's conference list and the Transactions team list, which read standings their own way.
final class ConferenceListTests: XCTestCase {
    private func groups(_ data: Data) throws -> [ConferenceGroup] {
        try JSONDecoder().decode(ConferencesAPIResponse.self, from: data).conferenceGroups
    }

    private func groups(_ file: String) throws -> [ConferenceGroup] {
        try groups(Fixtures.data(file))
    }

    func testGroup90GivesEveryConferenceAndNeverFBSOrFCS() throws {
        let names = try groups("standings_NCAAF_group90.json").map(\.name)
        XCTAssertEqual(Set(names), CollegeFootball.allConferences)
        XCTAssertEqual(names.count, 25, "\(names)")
        XCTAssertFalse(names.contains("FBS"))
        XCTAssertFalse(names.contains("FCS"))
    }

    func testFBSComesBeforeFCS() throws {
        let names = try groups("standings_NCAAF_group90.json").map(\.name)
        let firstFCS = try XCTUnwrap(names.firstIndex { CollegeFootball.fcsConferences.contains($0) })
        let lastFBS = try XCTUnwrap(names.lastIndex { CollegeFootball.fbsConferences.contains($0) })
        XCTAssertLessThan(lastFBS, firstFCS, "\(names)")
    }

    func testTheBigSkyHoldsMontanaState() throws {
        let bigSky = try XCTUnwrap(try groups("standings_NCAAF_group90.json").first { $0.name == "Big Sky Conference" })
        XCTAssertEqual(bigSky.teams.map(\.displayName), ["Montana Grizzlies", "Montana State Bobcats"])
        XCTAssertEqual(bigSky.teams.last?.id, "147")
    }

    func testTheSunBeltKeepsItsSubDivisionsInsideIt() throws {
        // FBS on its own: the Sun Belt's teams are a level below the conference.
        let names = try groups("standings_NCAAF.json").map(\.name)
        XCTAssertEqual(names, ["American Conference", "Sun Belt Conference"])
        let sunBelt = try XCTUnwrap(try groups("standings_NCAAF.json").last)
        XCTAssertTrue(sunBelt.teams.contains { $0.displayName == "App State Mountaineers" })
    }

    func testTheSunBeltNestedUnderDivisionOneToo() throws {
        // ESPN's own nodes one level further down, the deepest this tree could go.
        let fbs = try JSONSerialization.jsonObject(with: Fixtures.data("standings_NCAAF.json"))
        let wrapped = try JSONSerialization.data(withJSONObject: [
            "name": "NCAA Division I", "isConference": false, "children": [fbs],
        ])
        let names = try groups(wrapped).map(\.name)
        XCTAssertEqual(names, ["American Conference", "Sun Belt Conference"])
    }

    func testSportsThatSendNoFlagStillListTheirConferences() throws {
        // Women's college basketball and college hockey don't send isConference.
        let hockey = try groups("standings_NCAAH.json")
        XCTAssertFalse(hockey.isEmpty)
        XCTAssertTrue(hockey.allSatisfy { !$0.teams.isEmpty })
        XCTAssertFalse(try groups("standings_NCAAWB.json").isEmpty)
        XCTAssertFalse(try groups("standings_NCAAM.json").isEmpty)
    }

    func testEntriesAtTheRootAreLeftToTheFallback() throws {
        XCTAssertEqual(try groups("standings_NCAAWH.json").count, 0)
    }

    func testOneBadTeamCostsOnlyThatTeam() throws {
        let json = """
        {"children": [{"id": "20", "name": "Big Sky Conference", "isConference": true, "standings": {"entries": [
            {"team": {"id": "147", "displayName": "Montana State Bobcats", "abbreviation": "MTST"}},
            {"team": {"id": "149"}}
        ]}}]}
        """
        let bigSky = try XCTUnwrap(try groups(Data(json.utf8)).first)
        XCTAssertEqual(bigSky.teams.map(\.id), ["147"])
    }
}

/// Answers every request from the routes, in order, by the first text found in the URL.
final class StubbedESPN: URLProtocol {
    static var routes: [(text: String, status: Int, body: Data)] = []
    static var requested: [String] = []

    static func service(_ routes: [(text: String, status: Int, body: Data)]) -> ESPNAPIService {
        self.routes = routes
        requested = []
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubbedESPN.self]
        return ESPNAPIService(session: URLSession(configuration: config))
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        let url = request.url!
        Self.requested.append(url.absoluteString)
        let route = Self.routes.first { url.absoluteString.contains($0.text) }
        let response = HTTPURLResponse(url: url, statusCode: route?.status ?? 404, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: route?.body ?? Data())
        client?.urlProtocolDidFinishLoading(self)
    }
}

/// `fetchTeamsForSport`, which Transactions and Team Hub's fallback both rely on.
final class TeamListRequestTests: XCTestCase {
    private func everyTeam() throws -> (text: String, status: Int, body: Data) {
        // A real team list, there to be found if the code goes looking for it.
        ("/teams", 200, try Fixtures.data("teams_NBA.json"))
    }

    private func assertThrowsWithoutAskingForEveryTeam(_ standings: (text: String, status: Int, body: Data)) async throws {
        let service = StubbedESPN.service([standings, try everyTeam()])
        do {
            let teams = try await service.fetchTeamsForSport(sport: .ncaaf)
            XCTFail("Expected an error, got \(teams.count) teams")
        } catch {
            XCTAssertEqual(StubbedESPN.requested.count, 1, "\(StubbedESPN.requested)")
            XCTAssertTrue(StubbedESPN.requested[0].contains("/standings?group="), StubbedESPN.requested[0])
        }
    }

    func testCollegeFootballListsTheTeamsInItsStandings() async throws {
        let body = try Fixtures.data("standings_NCAAF_group90.json")
        let service = StubbedESPN.service([("/standings", 200, body), try everyTeam()])
        let teams = try await service.fetchTeamsForSport(sport: .ncaaf)
        XCTAssertEqual(teams.count, 26)
        XCTAssertTrue(teams.contains { $0.displayName == "Montana State Bobcats" })
        XCTAssertEqual(StubbedESPN.requested.count, 1, "one request, not the list of 762 as well")
    }

    func testAFailedStandingsRequestIsAnError() async throws {
        try await assertThrowsWithoutAskingForEveryTeam(("/standings", 500, Data()))
    }

    func testStandingsWithNoConferencesAreAnError() async throws {
        try await assertThrowsWithoutAskingForEveryTeam(("/standings", 200, Data(#"{"name": "FBS"}"#.utf8)))
    }

    func testStandingsWithTooFewTeamsToTrustAreAnError() async throws {
        // A real answer trimmed to 6 teams, under what fetchConferencesWithTeams accepts.
        try await assertThrowsWithoutAskingForEveryTeam(("/standings", 200, try Fixtures.data("standings_NCAAF.json")))
    }

    func testOtherSportsAskTheTeamListForEveryTeam() async throws {
        let service = StubbedESPN.service([try everyTeam()])
        let teams = try await service.fetchTeamsForSport(sport: .ncaam)
        XCTAssertEqual(teams.count, 3)
        XCTAssertEqual(StubbedESPN.requested.count, 1)
        XCTAssertTrue(StubbedESPN.requested[0].hasSuffix("/basketball/mens-college-basketball/teams?limit=1000"),
                      StubbedESPN.requested[0])
    }

    func testAFailedTeamListIsAnError() async throws {
        let service = StubbedESPN.service([("/teams", 500, Data())])
        do {
            _ = try await service.fetchTeamsForSport(sport: .ncaam)
            XCTFail("Expected an error")
        } catch {}
    }
}

final class TeamHubDecodingTests: XCTestCase {
    private func schedule(with extra: [Any], keepingRealEvents: Bool = true) throws -> Data {
        let data = try Fixtures.data("schedule_NFL_26_post.json")
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let events = try XCTUnwrap(object["events"] as? [Any])
        object["events"] = (keepingRealEvents ? events : []) + extra
        return try JSONSerialization.data(withJSONObject: object)
    }

    private func decodeSchedule(_ data: Data) throws -> TeamScheduleAPIResponse {
        try JSONDecoder().decode(TeamScheduleAPIResponse.self, from: data)
    }

    func testABlankEventCostsOnlyItself() throws {
        let response = try decodeSchedule(schedule(with: [[String: Any]()]))
        XCTAssertEqual(response.events.count, 3)
    }

    func testAnEventThatCanNotBeReadCostsOnlyItself() throws {
        let response = try decodeSchedule(schedule(with: [["id": "1"]]))
        XCTAssertEqual(response.events.count, 3)
    }

    func testAPageWithNothingReadableIsStillAnError() throws {
        let unreadable = Array(repeating: ["id": "1"] as [String: Any], count: 4)
        XCTAssertThrowsError(try decodeSchedule(schedule(with: unreadable, keepingRealEvents: false)))
    }

    func testAShortPageWithNothingReadableIsNoReasonToLoseTheSeason() throws {
        // A postseason page can be one bowl game.
        for count in 1...3 {
            let unreadable = Array(repeating: ["id": "1"] as [String: Any], count: count)
            let response = try decodeSchedule(schedule(with: unreadable, keepingRealEvents: false))
            XCTAssertTrue(response.events.isEmpty)
        }
    }

    func testTheScoreboardStaysStrictAboutAShortList() throws {
        // A board of one unreadable event is still an error: only team schedules have short pages.
        let data = try JSONSerialization.data(withJSONObject: ["events": [["id": "1"]]])
        XCTAssertThrowsError(try Fixtures.decodeScoreboard(data))
    }

    func testTheDayShowsTheYearOnlyWhenItIsNotThisOne() throws {
        let calendar = Calendar.current
        let now = try XCTUnwrap(calendar.date(from: DateComponents(year: 2026, month: 11, day: 3, hour: 12)))
        let sameYear = try XCTUnwrap(calendar.date(from: DateComponents(year: 2026, month: 2, day: 21, hour: 12)))
        let nextYear = try XCTUnwrap(calendar.date(from: DateComponents(year: 2027, month: 5, day: 1, hour: 12)))
        let lastYear = try XCTUnwrap(calendar.date(from: DateComponents(year: 2025, month: 9, day: 7, hour: 12)))
        XCTAssertFalse(ScheduleDayText.text(for: sameYear, now: now).contains("20"))
        XCTAssertTrue(ScheduleDayText.text(for: nextYear, now: now).hasSuffix(", 2027"))
        XCTAssertTrue(ScheduleDayText.text(for: lastYear, now: now).hasSuffix(", 2025"))
    }

    func testAScheduleMostlyUnreadableIsStillAnError() throws {
        // A short list would look normal, so ESPN dropping a field can't be left to pass as one.
        let unreadable = Array(repeating: ["id": "1"] as [String: Any], count: 9)
        XCTAssertThrowsError(try decodeSchedule(schedule(with: unreadable)))
    }

    func testAScheduleOfOnlyBlanksIsAnEmptySeason() throws {
        let response = try decodeSchedule(schedule(with: [[String: Any]()], keepingRealEvents: false))
        XCTAssertTrue(response.events.isEmpty)
    }

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

/// Team Hub's record and standing are the regular season's, by the same rules as Windows, on
/// ESPN's answers of Nov 4, 2026. `/teams/{id}` with no season has whatever the league is doing now.
@MainActor
final class TeamHubRecordTests: XCTestCase {
    private func answering(season: StubESPN.Reply, plain: Data, regular: StubESPN.Reply) {
        StubESPN.answer { url in
            if url.path.hasSuffix("/season") { return season }
            if (url.query ?? "").contains("seasontype=2") { return regular }
            return .body(plain)
        }
    }

    private func info(_ teamId: String, _ sport: Sport, season: String, plain: String, regular: String) async throws -> TeamHubTeamInfo {
        answering(season: .body(try Fixtures.data(season)), plain: try Fixtures.data(plain),
                  regular: .body(try Fixtures.data(regular)))
        return try await ESPNAPIService(session: StubESPN.session()).fetchTeamHubInfo(teamId: teamId, sport: sport)
    }

    /// The plain answer's fixture must be the bug, or the tests below prove nothing.
    private func plainTeam(_ file: String) throws -> TeamInfoAPIResponse.TeamInfoTeamData {
        try JSONDecoder().decode(TeamInfoAPIResponse.self, from: Fixtures.data(file)).team
    }

    func testATeamInThePlayoffs() async throws {
        XCTAssertEqual(try plainTeam("team_WNBA_8.json").record?.items?.first?.summary, "0-2")
        let lynx = try await info("8", .wnba, season: "season_WNBA.json", plain: "team_WNBA_8.json",
                                  regular: "team_WNBA_8_regular.json")
        XCTAssertEqual(lynx.overallRecord, "33-11")
        XCTAssertEqual(lynx.homeRecord, "15-7")
        XCTAssertEqual(lynx.awayRecord, "18-4")
        XCTAssertEqual(lynx.standingSummary, "1st in Western Conference", "and not a conference called a division")
        XCTAssertEqual(lynx.displayName, "Minnesota Lynx")
    }

    func testATeamThatMissedThem() async throws {
        XCTAssertEqual(try plainTeam("team_WNBA_14.json").record?.items?.first?.summary, "0-0")
        let storm = try await info("14", .wnba, season: "season_WNBA.json", plain: "team_WNBA_14.json",
                                   regular: "team_WNBA_14_regular.json")
        XCTAssertEqual(storm.overallRecord, "8-36")
        XCTAssertEqual(storm.standingSummary, "8th in Western Conference")
    }

    func testItAsksForTheSeasonAsWellAsTheType() async throws {
        // seasontype=2 alone doesn't work: Atlanta stays 8-4.
        _ = try await info("8", .wnba, season: "season_WNBA.json", plain: "team_WNBA_8.json",
                           regular: "team_WNBA_8_regular.json")
        XCTAssertTrue(StubESPN.requests.contains {
            $0.path.hasSuffix("/basketball/wnba/teams/8") && $0.query == "season=2026&seasontype=2"
        })
        XCTAssertTrue(StubESPN.requests.contains { $0.path.hasSuffix("/basketball/leagues/wnba/season") })
    }

    func testMLBInItsPlayoffsKeepsTheRecordAndCorrectsTheStanding() async throws {
        XCTAssertEqual(try plainTeam("team_MLB_19.json").standingSummary, "5th in NL West")
        let dodgers = try await info("19", .mlb, season: "season_MLB.json", plain: "team_MLB_19.json",
                                     regular: "team_MLB_19_regular.json")
        XCTAssertEqual(dodgers.overallRecord, "100-62")
        XCTAssertEqual(dodgers.standingSummary, "1st in NL West")
    }

    func testALeagueInItsRegularSeason() async throws {
        let nets = try await info("17", .nba, season: "season_NBA.json", plain: "team_NBA_17.json",
                                  regular: "team_NBA_17_regular.json")
        XCTAssertEqual(nets.overallRecord, "1-6")
        XCTAssertEqual(nets.standingSummary, "5th in Atlantic Division")
    }

    /// With its next game moved to 2099, since whether it's to come depends on today.
    private func farAway(_ file: String) throws -> (data: Data, gameId: String) {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Fixtures.data(file)) as? [String: Any])
        var team = try XCTUnwrap(object["team"] as? [String: Any])
        var events = try XCTUnwrap(team["nextEvent"] as? [[String: Any]])
        events[0]["date"] = "2099-01-03T18:00Z"
        team["nextEvent"] = events
        object["team"] = team
        return (try JSONSerialization.data(withJSONObject: object), try XCTUnwrap(events[0]["id"] as? String))
    }

    func testTheNextGameIsNotTheOneTheRegularSeasonAnswerHas() async throws {
        // Asked for a season, ESPN has the Nets' next game in January, not the next day's.
        let plain = try farAway("team_NBA_17.json")
        let regular = try farAway("team_NBA_17_regular.json")
        XCTAssertNotEqual(plain.gameId, regular.gameId)
        answering(season: .body(try Fixtures.data("season_NBA.json")), plain: plain.data, regular: .body(regular.data))
        let nets = try await ESPNAPIService(session: StubESPN.session()).fetchTeamHubInfo(teamId: "17", sport: .nba)
        XCTAssertEqual(nets.nextGame?.gameId, plain.gameId)
    }

    func testCollegeHockeyHasARecordOnlyThisWayAndNoStandingInNothing() async throws {
        XCTAssertNil(try plainTeam("team_NCAAH_130.json").record)
        let michigan = try await info("130", .ncaah, season: "season_NBA.json", plain: "team_NCAAH_130.json",
                                      regular: "team_NCAAH_130_regular.json")
        XCTAssertEqual(michigan.overallRecord, "8-1")
        XCTAssertNil(michigan.standingSummary, "ESPN says a bare 1st of every college hockey team")
    }

    func testAPreseasonShowsTheLastSeason() async throws {
        var season = try XCTUnwrap(JSONSerialization.jsonObject(with: Fixtures.data("season_NBA.json")) as? [String: Any])
        var type = try XCTUnwrap(season["type"] as? [String: Any])
        type["type"] = 1
        season["type"] = type
        answering(season: .body(try JSONSerialization.data(withJSONObject: season)),
                  plain: try Fixtures.data("team_NBA_17.json"),
                  regular: .body(try Fixtures.data("team_NBA_17_regular.json")))
        _ = try await ESPNAPIService(session: StubESPN.session()).fetchTeamHubInfo(teamId: "17", sport: .nba)
        XCTAssertTrue(StubESPN.requests.contains { $0.query == "season=2026&seasontype=2" })
    }

    func testSoccerAsksForNoSeason() async throws {
        // `isSoccer` is false for the World Cups, and they still have no season type 2.
        let arsenal = try Fixtures.data("team_EPL_359.json")
        for sport in [Sport.soccerEPL, .worldCup, .worldCupWomens] {
            StubESPN.answer { _ in .body(arsenal) }
            let info = try await ESPNAPIService(session: StubESPN.session()).fetchTeamHubInfo(teamId: "359", sport: sport)
            XCTAssertEqual(StubESPN.requests.count, 1, sport.rawValue)
            XCTAssertEqual(info.overallRecord, "8-0-1", sport.rawValue)
            XCTAssertEqual(info.standingSummary, "1st in English Premier League", sport.rawValue)
            XCTAssertFalse(info.recordIsRegularSeasonOnly, sport.rawValue)
            XCTAssertFalse(info.recordUnavailable, sport.rawValue)
        }
    }

    func testACollegeRecordSaysWhenItLeavesOutThePostseason() async throws {
        // Michigan basketball's 2026 reads 31-3 here and 37-3 in Standings.
        let postseason = try await info("130", .ncaah, season: "season_WNBA.json", plain: "team_NCAAH_130.json",
                                        regular: "team_NCAAH_130_regular.json")
        XCTAssertTrue(postseason.recordIsRegularSeasonOnly)
        let regularSeason = try await info("130", .ncaah, season: "season_NBA.json", plain: "team_NCAAH_130.json",
                                           regular: "team_NCAAH_130_regular.json")
        XCTAssertFalse(regularSeason.recordIsRegularSeasonOnly)
        let proLeague = try await info("8", .wnba, season: "season_WNBA.json", plain: "team_WNBA_8.json",
                                       regular: "team_WNBA_8_regular.json")
        XCTAssertFalse(proLeague.recordIsRegularSeasonOnly)
    }

    func testAFailureIsToldFromATeamWithNoRecord() async throws {
        let plain = try Fixtures.data("team_WNBA_8.json")
        let season = try Fixtures.data("season_WNBA.json")
        let service = { ESPNAPIService(session: StubESPN.session()) }

        answering(season: .failure(URLError(.timedOut)), plain: plain, regular: .status(500))
        var lynx = try await service().fetchTeamHubInfo(teamId: "8", sport: .wnba)
        XCTAssertTrue(lynx.recordUnavailable, "no season")

        answering(season: .body(season), plain: plain, regular: .failure(URLError(.timedOut)))
        lynx = try await service().fetchTeamHubInfo(teamId: "8", sport: .wnba)
        XCTAssertTrue(lynx.recordUnavailable, "a timeout")

        answering(season: .body(season), plain: plain, regular: .status(503))
        lynx = try await service().fetchTeamHubInfo(teamId: "8", sport: .wnba)
        XCTAssertTrue(lynx.recordUnavailable, "a server error")

        answering(season: .body(season), plain: plain, regular: .status(404))
        lynx = try await service().fetchTeamHubInfo(teamId: "8", sport: .wnba)
        XCTAssertFalse(lynx.recordUnavailable, "ESPN has nothing there")
        XCTAssertNil(lynx.overallRecord)

        // Failing with a record still to show, in the league's regular season.
        answering(season: .body(try Fixtures.data("season_NBA.json")), plain: try Fixtures.data("team_NBA_17.json"),
                  regular: .status(500))
        let nets = try await service().fetchTeamHubInfo(teamId: "17", sport: .nba)
        XCTAssertFalse(nets.recordUnavailable)
    }

    func testNoSeasonKeepsThePageAndNoRecordFromThePlayoffs() async throws {
        answering(season: .status(500), plain: try Fixtures.data("team_WNBA_8.json"),
                  regular: .body(try Fixtures.data("team_WNBA_8_regular.json")))
        let lynx = try await ESPNAPIService(session: StubESPN.session()).fetchTeamHubInfo(teamId: "8", sport: .wnba)
        XCTAssertEqual(lynx.displayName, "Minnesota Lynx")
        XCTAssertNil(lynx.overallRecord)
        XCTAssertNil(lynx.homeRecord)
        XCTAssertNil(lynx.standingSummary)
    }

    func testNoRegularSeasonInThePlayoffsHasNoPlayoffRecord() async throws {
        for failure in [StubESPN.Reply.status(500), .status(404), .failure(URLError(.timedOut)), .body(Data("{}".utf8))] {
            answering(season: .body(try Fixtures.data("season_WNBA.json")), plain: try Fixtures.data("team_WNBA_8.json"),
                      regular: failure)
            let lynx = try await ESPNAPIService(session: StubESPN.session()).fetchTeamHubInfo(teamId: "8", sport: .wnba)
            XCTAssertEqual(lynx.displayName, "Minnesota Lynx")
            XCTAssertNil(lynx.overallRecord)
            XCTAssertNil(lynx.standingSummary)
        }
    }

    func testNoRegularSeasonInItKeepsTheSameNumbers() async throws {
        answering(season: .body(try Fixtures.data("season_NBA.json")), plain: try Fixtures.data("team_NBA_17.json"),
                  regular: .status(500))
        let nets = try await ESPNAPIService(session: StubESPN.session()).fetchTeamHubInfo(teamId: "17", sport: .nba)
        XCTAssertEqual(nets.overallRecord, "1-6")
        XCTAssertEqual(nets.standingSummary, "5th in Atlantic Division")
    }

    func testACancelledRequestThrowsSoTheNextCallAsksAgain() async throws {
        // A page kept with no record would never ask again: loadInfo stops once it has one.
        let plain = try Fixtures.data("team_WNBA_8.json")
        let season = try Fixtures.data("season_WNBA.json")
        let replies: [(StubESPN.Reply, StubESPN.Reply)] = [
            (.failure(URLError(.cancelled)), .status(500)),
            (.body(season), .failure(URLError(.cancelled))),
        ]
        for (seasonReply, regularReply) in replies {
            answering(season: seasonReply, plain: plain, regular: regularReply)
            do {
                _ = try await ESPNAPIService(session: StubESPN.session()).fetchTeamHubInfo(teamId: "8", sport: .wnba)
                XCTFail("it should have thrown")
            } catch {
                XCTAssertTrue(error.isCancellation)
            }
        }
    }

    func testTheCurrentSeasonDecodes() throws {
        let playoffs = try JSONDecoder().decode(CurrentSeasonResponse.self, from: Fixtures.data("season_WNBA.json"))
        XCTAssertFalse(playoffs.isRegularSeason)
        XCTAssertEqual(playoffs.regularSeasonYear, 2026)
        let regular = try JSONDecoder().decode(CurrentSeasonResponse.self, from: Fixtures.data("season_NBA.json"))
        XCTAssertTrue(regular.isRegularSeason)
        XCTAssertEqual(regular.regularSeasonYear, 2027)
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
    func testTheCoverageSettingPicksTheCollegeFootballStandings() {
        let service = ESPNAPIService.shared
        XCTAssertTrue(service.standingsURLString(for: .ncaaf, coverage: .allDivisionI)
            .hasSuffix("/football/college-football/standings?group=90"))
        XCTAssertTrue(service.standingsURLString(for: .ncaaf, coverage: .fbs)
            .hasSuffix("/football/college-football/standings?group=80"))
    }

    func testOnlyCollegeFootballSendsAStandingsGroup() {
        for sport in [Sport.nfl, .ncaam, .ncaawb, .ncaah] {
            XCTAssertTrue(ESPNAPIService.shared.standingsURLString(for: sport, coverage: .fbs).hasSuffix("/standings"),
                          sport.displayName)
        }
    }

    func testTeamListsAskForEveryTeam() {
        // ESPN stops at 50 without a limit, which left most college teams out of Transactions.
        XCTAssertTrue(ESPNAPIService.shared.teamsURLString(for: .ncaam).hasSuffix("/teams?limit=1000"))
    }

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

final class DraftDecodingTests: XCTestCase {
    private func picks() throws -> [DraftPick] {
        struct Draft: Decodable { let picks: [DraftPick] }
        return try JSONDecoder().decode(Draft.self, from: Fixtures.data("draft_site_NFL_2026.json")).picks
    }

    func testASchoolReadsAsItsNameNotItsShortName() throws {
        let pick = try XCTUnwrap(try picks().first { $0.overall == 84 })
        XCTAssertEqual(pick.athlete?.team?.collegeName, "Georgia State")
        XCTAssertNotEqual(pick.athlete?.team?.shortDisplayName, "Georgia State", "the fixture should show the difference")
    }

    func testAPositionAnOldDraftLeavesOutOfItsList() {
        XCTAssertEqual(NFLDraftViewModel.positionsLeftOut["91"], "C")
        XCTAssertEqual(NFLDraftViewModel.positionsLeftOut["22"], "PK")
    }
}
