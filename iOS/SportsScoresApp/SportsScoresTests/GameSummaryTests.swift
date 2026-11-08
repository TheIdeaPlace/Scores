//
//  GameSummaryTests.swift
//  SportsScoresTests
//
//  What the game detail screen reads from ESPN's /summary, on real payloads: weather,
//  attendance, standings, the game story, scoring plays, injury details and odds.
//  tests/unit/replay/test_summary_pieces.py holds Windows to the same weather, attendance,
//  standings and odds on the same fixtures. The rest of Windows's text is built in its UI,
//  which has no tests, so those were compared by reading it.
//

import XCTest
@testable import SportsScores

final class GameSummaryTests: XCTestCase {
    private let finalNFL = "summary_final_NFL_401873036.json"
    private let preNFL = "summary_pre_NFL_401873037.json"
    private let finalEPL = "summary_final_EPL_401879251.json"
    private let overtimeNCAAF = "summary_final_NCAAF_401757313_2OT.json"

    private func fixture(_ name: String) throws -> GameDetails {
        try Fixtures.decodeDetails(Fixtures.data(name))
    }

    private func details(_ json: String) throws -> GameDetails {
        try JSONDecoder().decode(GameDetails.self, from: Data(json.utf8))
    }

    private func gameInfo(_ json: String) throws -> GameDetails.GameInfo {
        try JSONDecoder().decode(GameDetails.GameInfo.self, from: Data(json.utf8))
    }

    private func article(_ json: String) throws -> GameDetails.GameNewsContainer.GameArticle {
        try JSONDecoder().decode(GameDetails.GameNewsContainer.GameArticle.self, from: Data(json.utf8))
    }

    private func injury(_ json: String) throws -> GameDetails.InjuryTeam.PlayerInjury {
        try JSONDecoder().decode(GameDetails.InjuryTeam.PlayerInjury.self, from: Data(json.utf8))
    }

    private func paragraphs(_ story: String) -> [String] {
        GameStoryBlock.blocks(from: story).map(\.text)
    }

    // MARK: Weather

    func testAnOutdoorGameBeforeKickoffHasWeatherAndNoAttendance() throws {
        let info = try XCTUnwrap(try fixture(preNFL).gameInfo)
        XCTAssertEqual(info.weatherText, "Weather: 67°F")
        XCTAssertNil(info.attendanceText)
    }

    func testAPlayedGameHasNoWeather() throws {
        XCTAssertNil(try fixture(finalNFL).gameInfo?.weatherText)
        XCTAssertNil(try fixture("details_NCAAH_pieces.json").gameInfo?.weatherText)
    }

    func testWeatherReadsAsItDoesOnWindows() throws {
        let cases: [(json: String, expected: String?)] = [
            (#"{"weather": {"displayValue": "Rain", "temperature": 50}}"#, "Weather: Rain, 50°F"),
            (#"{"weather": {"displayValue": "Sunny, 72°F", "temperature": 72}}"#, "Weather: Sunny, 72°F"),
            (#"{"weather": {"displayValue": "Rain"}}"#, "Weather: Rain"),
            (#"{"weather": {"displayValue": null, "temperature": 50}}"#, "Weather: 50°F"),
            (#"{"weather": {"displayValue": "", "temperature": 50}}"#, "Weather: 50°F"),
            (#"{"weather": {"displayValue": "Snow", "temperature": 0}}"#, "Weather: Snow, 0°F"),
            (#"{"weather": {"temperature": 0}}"#, "Weather: 0°F"),
            (#"{"weather": {"temperature": 67.0}}"#, "Weather: 67°F"),
            (#"{"weather": {"temperature": 67.5}}"#, "Weather: 67.5°F"),
            (#"{"weather": {"temperature": "67"}}"#, "Weather: 67°F"),
            (#"{"weather": {}}"#, nil),
            (#"{"weather": {"displayValue": null}}"#, nil),
            (#"{"weather": null}"#, nil),
            (#"{}"#, nil),
        ]
        for (json, expected) in cases {
            XCTAssertEqual(try gameInfo(json).weatherText, expected, json)
        }
    }

    // MARK: Attendance

    func testAttendanceOfAPlayedGame() throws {
        XCTAssertEqual(try fixture(finalNFL).gameInfo?.attendanceText, "Attendance: 68,739")
        XCTAssertEqual(try fixture(finalEPL).gameInfo?.attendanceText, "Attendance: 12,041")
        XCTAssertEqual(try fixture("details_NFL_pieces.json").gameInfo?.attendanceText, "Attendance: 64,195")
    }

    func testNoCountIsNoRow() throws {
        XCTAssertEqual(try fixture("details_NCAAH_pieces.json").gameInfo?.attendance, 0)
        XCTAssertNil(try fixture("details_NCAAH_pieces.json").gameInfo?.attendanceText)
        XCTAssertNil(try gameInfo(#"{"attendance": null}"#).attendanceText)
    }

    func testAttendanceInAnyShapeESPNMightSend() throws {
        XCTAssertEqual(try gameInfo(#"{"attendance": "64,195"}"#).attendanceText, "Attendance: 64,195")
        XCTAssertEqual(try gameInfo(#"{"attendance": 64195.0}"#).attendanceText, "Attendance: 64,195")
        XCTAssertEqual(try gameInfo(#"{"attendance": 950}"#).attendanceText, "Attendance: 950")
    }

    func testOddGameInfoCostsOnlyTheOddValue() throws {
        let official = #""officials": [{"fullName": "Shawn Hochuli"}]"#
        for odd in [#""attendance": [1]"#, #""attendance": "sold out""#, #""weather": "Sunny""#,
                    #""weather": {"temperature": {"f": 7}}"#] {
            let info = try gameInfo("{\(odd), \(official)}")
            XCTAssertEqual(info.officials?.first?.fullName, "Shawn Hochuli", odd)
            XCTAssertNil(info.attendanceText, odd)
            XCTAssertNil(info.weatherText, odd)
        }
    }

    // MARK: Standings

    func testAFootballGamesTwoDivisions() throws {
        let tables = try XCTUnwrap(try fixture(finalNFL).standings).tables
        XCTAssertEqual(tables.map(\.title), ["2026 NFC North Standings", "2026 NFC West Standings"])
        let north = tables[0]
        XCTAssertEqual(north.headers, ["Team", "L", "PA", "PF", "T", "PCT", "W", "Any"])
        XCTAssertEqual(north.rows.count, 4)
        XCTAssertEqual(north.rows[0], ["Minnesota", "1", "93", "140", "0", ".857", "6", "6-1"])
        XCTAssertEqual(north.statsText(row: north.rows[0]), "L: 1, PA: 93, PF: 140, T: 0, PCT: .857, W: 6, Any: 6-1")
        XCTAssertEqual(north.spokenText(row: north.rows[0]), "Minnesota, L: 1, PA: 93, PF: 140, T: 0, PCT: .857, W: 6, Any: 6-1")
    }

    func testAWholeLeaguesTable() throws {
        let tables = try XCTUnwrap(try fixture(finalEPL).standings).tables
        XCTAssertEqual(tables.map(\.title), ["English Premier League Standings"])
        XCTAssertEqual(tables[0].rows.count, 20)
        XCTAssertEqual(tables[0].spokenText(row: tables[0].rows[0]),
                       "Arsenal, GP: 9, L: 1, GD: +9, P: 24, D: 0, W: 8, Rank: 1, OVER: 8-0-1")
    }

    func testEveryRowFitsItsHeaders() throws {
        for name in [finalNFL, finalEPL, "game_standings_NFL.json"] {
            let tables = try XCTUnwrap(try fixture(name).standings, name).tables
            XCTAssertFalse(tables.isEmpty, name)
            for table in tables {
                XCTAssertFalse(table.rows.isEmpty, name)
                XCTAssertTrue(table.rows.allSatisfy { $0.count == table.headers.count }, name)
            }
        }
    }

    func testGamesWithNoStandingsHaveNoTables() throws {
        XCTAssertNil(try fixture(preNFL).standings)
        XCTAssertEqual(try details(#"{"standings": {"groups": [{"standings": {"entries": []}}]}}"#).standings?.tables.count, 0)
        XCTAssertEqual(try details(#"{"standings": {}}"#).standings?.tables.count, 0)
        XCTAssertNil(try details(#"{"standings": []}"#).standings)
    }

    func testAStatOneTeamLacksIsLeftUnsaid() throws {
        let json = """
        {"standings": {"groups": [{"standings": {"entries": [
          {"team": "Ann", "stats": [{"name": "wins", "shortDisplayName": "W", "displayValue": "6"}]},
          {"team": "Bea", "stats": [{"name": "wins", "shortDisplayName": "W", "displayValue": "5"},
                                    {"name": "gamesBehind", "abbreviation": "GB", "displayValue": "1"},
                                    {"name": "streak", "displayValue": "W1"}]}
        ]}}]}}
        """
        let table = try XCTUnwrap(try details(json).standings?.tables.first)
        XCTAssertEqual(table.title, "Standings", "a group with no header of its own")
        XCTAssertEqual(table.headers, ["Team", "W", "GB", "streak"])
        XCTAssertEqual(table.rows[0], ["Ann", "6", "", ""])
        XCTAssertEqual(table.spokenText(row: table.rows[0]), "Ann, W: 6")
        XCTAssertEqual(table.spokenText(row: table.rows[1]), "Bea, W: 5, GB: 1, streak: W1")
    }

    func testAnOddEntryOrStatCostsOnlyItself() throws {
        let json = """
        {"standings": {"groups": [{"header": 7, "standings": {"entries": [
          7,
          {"team": 7, "stats": [{"name": "wins", "shortDisplayName": "W", "displayValue": "9"}]},
          {"team": "Ann", "stats": [7, {"name": "wins", "shortDisplayName": "W", "displayValue": 6},
                                    {"name": "pct", "shortDisplayName": 7, "displayValue": 0.5},
                                    {"name": "losses", "shortDisplayName": "L", "displayValue": [1]}]}
        ]}}, 7]}}
        """
        let tables = try XCTUnwrap(try details(json).standings).tables
        XCTAssertEqual(tables.count, 1)
        XCTAssertEqual(tables[0].title, "Standings")
        XCTAssertEqual(tables[0].headers, ["Team", "W", "pct", "L"])
        XCTAssertEqual(tables[0].rows, [["Ann", "6", "0.5", ""]], "and no row for a team with no name")
    }

    // MARK: Game story

    func testAPlayedGameHasAStory() throws {
        let game = try fixture(finalNFL)
        let story = try XCTUnwrap(game.gameStory)
        XCTAssertEqual(story.headline, "Caleb Williams and Jeffery Simmons lead the Bears past the Seahawks 34-17")
        XCTAssertEqual(story.type, "Recap")
    }

    func testAPlayedGamesStoryIsNotAlsoInTheNews() throws {
        let game = try fixture(finalNFL)
        XCTAssertEqual(game.relatedArticles.map(\.id), [50383054, 50371800])
    }

    func testAStoryInTheNewsIsNotListedThereToo() throws {
        let game = try details(#"""
        {"header": {"competitions": [{"competitors": [], "status": {"type": {"state": "post"}}}]},
         "article": {"id": 1, "headline": "Recap", "story": "Words"},
         "news": {"articles": [{"id": 2, "headline": "Other"}, {"id": 1, "headline": "Recap"}]}}
        """#)
        XCTAssertEqual(game.gameStory?.id, 1)
        XCTAssertEqual(game.relatedArticles.map(\.id), [2])
    }

    func testAGameCalledOffHasNoStoryAndItsPreviewStaysInTheNews() throws {
        for name in ["STATUS_POSTPONED", "STATUS_CANCELED"] {
            let game = try details(#"""
            {"header": {"competitions": [{"competitors": [],
                "status": {"type": {"state": "post", "name": "\#(name)"}}}]},
             "article": {"id": 1, "type": "Preview", "headline": "Preview", "story": "Words"}}
            """#)
            XCTAssertNil(game.gameStory, name)
            XCTAssertEqual(game.relatedArticles.map(\.id), [1], name)
        }
    }

    func testAPreviewIsNotAStoryButLeadsTheNews() throws {
        let game = try fixture(preNFL)
        XCTAssertNil(game.gameStory)
        XCTAssertEqual(game.relatedArticles.map(\.id), [50380295, 50383054, 50371800])
        XCTAssertEqual(game.relatedArticles.first?.type, "Preview")
    }

    func testTheGamesOwnArticleIsListedOnce() throws {
        let game = try details(#"""
        {"article": {"id": 1, "headline": "Preview"},
         "news": {"articles": [{"id": 2, "headline": "Other"}, {"id": 1, "headline": "Preview"}]}}
        """#)
        XCTAssertEqual(game.relatedArticles.map(\.id), [1, 2])
    }

    func testAnArticleWithNoHeadlineIsNoStory() throws {
        let game = try details(#"""
        {"header": {"competitions": [{"competitors": [], "status": {"type": {"state": "post"}}}]},
         "article": {"id": 1, "headline": "", "story": "Words"}}
        """#)
        XCTAssertNil(game.gameStory)
        XCTAssertTrue(game.relatedArticles.isEmpty)
    }

    func testGamesWithNoArticleHaveNothingToList() throws {
        let game = try fixture("details_NCAAH_pieces.json")
        XCTAssertNil(game.article)
        XCTAssertNil(game.gameStory)
        XCTAssertTrue(game.relatedArticles.isEmpty)
    }

    func testAnAPStoryReadsAsParagraphsAndHeadings() throws {
        let blocks = try XCTUnwrap(try fixture(finalNFL).gameStory).storyBlocks
        let headings = blocks.compactMap { block -> String? in
            if case .heading(let text) = block { return text }
            return nil
        }
        XCTAssertEqual(headings, ["Caleb covers his cleats", "Injuries", "Up next"])

        let opening = try XCTUnwrap(blocks.first)
        XCTAssertTrue(opening.text.hasPrefix("SEATTLE -- Jeffery Simmons ran out of the tunnel"), opening.text)
        XCTAssertEqual(blocks.last?.text, "See AP’s full NFL coverage here")

        let upNext = try XCTUnwrap(blocks.firstIndex(of: .heading("Up next")))
        XCTAssertEqual(blocks[upNext + 1], .paragraph("Bears: Host Tampa Bay on Sunday night."))
    }

    func testNoMarkupIsLeftInAnyStory() throws {
        for name in [finalNFL, preNFL, finalEPL] {
            let blocks = try XCTUnwrap(try fixture(name).article, name).storyBlocks
            XCTAssertGreaterThan(blocks.count, 5, name)
            for block in blocks {
                XCTAssertFalse(block.text.contains("<"), block.text)
                XCTAssertFalse(block.text.contains("href"), block.text)
                XCTAssertFalse(block.text.contains("\n"), block.text)
                XCTAssertFalse(block.text.contains("---"), block.text)
                XCTAssertFalse(block.text.contains("-- —"), block.text)
            }
        }
    }

    func testASoccerStoryInParagraphTagsLosesItsPhoto() throws {
        let blocks = try XCTUnwrap(try fixture(finalEPL).gameStory).storyBlocks
        XCTAssertTrue(try XCTUnwrap(blocks.first).text.hasPrefix("A calamitous error from Leeds goalkeeper James Trafford set in-form"))
        XCTAssertFalse(blocks.contains { $0.text.contains("Evanilson opened the scoring for Bournemouth against Leeds.") },
                       "that's a photo's caption")
    }

    func testStoryMarkup() {
        XCTAssertEqual(paragraphs(""), [])
        XCTAssertEqual(paragraphs("   \n\n  "), [])
        XCTAssertEqual(paragraphs("one\n     more\n\n\n   two"), ["one more", "two"])
        XCTAssertEqual(paragraphs("one\r\n\r\ntwo"), ["one", "two"])
        XCTAssertEqual(paragraphs(#"<a href="x"><a href="y">Chicago Bears</a></a> <em>won</em>"#), ["Chicago Bears won"])
        XCTAssertEqual(paragraphs("Tom &amp; Jerry&#39;s &lt;3&nbsp;now"), ["Tom & Jerry's <3 now"])
        XCTAssertEqual(paragraphs("------\n\nwords\n\n..."), ["words"])
        XCTAssertEqual(paragraphs("Plays on Wednesday. ------\n\nwell-known"), ["Plays on Wednesday.", "well-known"])
        XCTAssertEqual(GameStoryBlock.blocks(from: "before<hl2>Next</hl2>after"),
                       [.paragraph("before"), .heading("Next"), .paragraph("after")])
        XCTAssertEqual(GameStoryBlock.blocks(from: "<HL2 class=\"a\">Next\nup</HL2>"), [.heading("Next up")])
        XCTAssertEqual(GameStoryBlock.blocks(from: "<hl2></hl2>"), [])
        XCTAssertEqual(paragraphs("<p>one</p><p>two<br>three</p>"), ["one", "two", "three"])
    }

    func testADescriptionLosesItsDash() throws {
        let story = try XCTUnwrap(try fixture(finalNFL).gameStory)
        XCTAssertTrue(try XCTUnwrap(story.plainDescription).hasPrefix("Jeffery Simmons ran out of the tunnel"))
        XCTAssertNil(try article(#"{"description": " — "}"#).plainDescription)
        XCTAssertNil(try article(#"{"description": null}"#).plainDescription)
    }

    func testTheDescriptionIsNotHeardTwice() throws {
        for name in [finalNFL, preNFL, finalEPL] {
            XCTAssertNil(try XCTUnwrap(try fixture(name).article, name).descriptionNotInStory, name)
        }
    }

    func testADescriptionThatAddsSomethingIsKept() throws {
        XCTAssertEqual(try article(#"{"description": "Words of its own.", "story": "Other words."}"#).descriptionNotInStory,
                       "Words of its own.")
        XCTAssertEqual(try article(#"{"description": "All there is."}"#).descriptionNotInStory, "All there is.")
    }

    func testAnOddArticleKeepsWhatItCan() throws {
        let odd = try article(#"{"id": "abc", "headline": "Headline", "links": 7, "story": 7}"#)
        XCTAssertNil(odd.id)
        XCTAssertEqual(odd.headline, "Headline")
        XCTAssertEqual(odd.storyBlocks, [])
    }

    func testAnOddNewsArticleCostsOnlyItself() throws {
        let game = try details(#"{"news": {"articles": [7, {"id": 2, "headline": "Other"}]}}"#)
        XCTAssertEqual(game.relatedArticles.map(\.id), [2])
    }

    // MARK: Scoring plays

    func testAFootballGamesScoringByQuarter() throws {
        let periods = try fixture(finalNFL).scoringSummary(isFootball: true)
        XCTAssertEqual(periods.map(\.title), ["Quarter 1", "Quarter 2", "Quarter 3", "Quarter 4"])
        XCTAssertEqual(periods.map(\.plays.count), [1, 4, 1, 3])
        let first = try XCTUnwrap(periods.first?.plays.first)
        XCTAssertEqual(first.teamAndClock, "Chicago Bears - 5:25")
        XCTAssertEqual(first.spokenText,
                       "Chicago Bears, 5:25: Luther Burden III 1 Yd pass from Caleb Williams (Cairo Santos Kick)")
    }

    func testOvertimeScoresAreInOvertime() throws {
        let periods = try fixture(overtimeNCAAF).scoringSummary(isFootball: true)
        XCTAssertEqual(periods.map(\.title), ["Quarter 1", "Quarter 2", "Quarter 3", "Quarter 4", "OT", "2OT"])
        XCTAssertEqual(periods.map(\.plays.count), [2, 2, 2, 4, 2, 1])
    }

    func testAPeriodKeepsTheNameESPNGivesIt() throws {
        let game = try details(#"""
        {"scoringPlays": [{"text": "Goal", "period": {"number": 1, "displayName": "First Half"}},
                          {"text": "Goal", "period": {"number": 2}}]}
        """#)
        XCTAssertEqual(game.scoringSummary(isFootball: false).map(\.title), ["First Half", "Period 2"])
    }

    func testAGameWithNoScoringPlaysHasNoSummary() throws {
        for name in [preNFL, finalEPL, "details_NFL_pieces.json"] {
            XCTAssertTrue(try fixture(name).scoringSummary(isFootball: true).isEmpty, name)
        }
    }

    func testARowWithNoWordsOrThatCanNotBeReadIsLeftOut() throws {
        let game = try details(#"""
        {"scoringPlays": [7, {"text": "", "period": {"number": 1}}, {"period": {"number": 1}},
                          {"text": 7, "period": {"number": 1}},
                          {"text": "Score", "period": {"number": 2}}]}
        """#)
        let periods = game.scoringSummary(isFootball: true)
        XCTAssertEqual(periods.map(\.title), ["Quarter 2"])
        XCTAssertEqual(periods.first?.plays.count, 1)
        XCTAssertEqual(periods.first?.plays.first?.teamAndClock, "")
        XCTAssertEqual(periods.first?.plays.first?.spokenText, "Score")
    }

    func testAnOddClockOrTeamDoesNotLoseTheScore() throws {
        let game = try details(#"""
        {"scoringPlays": [{"text": "Touchdown", "period": {"number": 2}, "clock": "soon",
                           "team": {"displayName": "Bears"}},
                          {"text": "Field Goal", "period": 2, "clock": {"displayValue": "1:00"}, "team": 7}]}
        """#)
        let plays = game.scoringSummary(isFootball: true).flatMap(\.plays)
        XCTAssertEqual(plays.map(\.spokenText), ["Bears: Touchdown", "1:00: Field Goal"])
    }

    // MARK: Injuries

    func testAnInjuryReadsItsDetails() throws {
        let teams = try XCTUnwrap(try fixture(finalNFL).injuries)
        XCTAssertEqual(teams.map { $0.injuries?.count }, [5, 5])
        let shaheed = try XCTUnwrap(teams[0].injuries?.first)
        // Windows reads "Not Specified" and the date as ESPN writes it. See detailLines.
        XCTAssertEqual(shaheed.detailLines, ["Type: Knee", "Return Date: Nov 8, 2026"])
        XCTAssertEqual(shaheed.spokenText, "Rashid Shaheed, WR, Status: Questionable, Type: Knee, Return Date: Nov 8, 2026")

        let monangai = try XCTUnwrap(teams[1].injuries?.first { $0.athlete?.displayName == "Kyle Monangai" })
        XCTAssertEqual(monangai.detailLines, ["Type: Toe", "Details: Sprain", "Return Date: Nov 8, 2026"])
    }

    func testAnInjuryWithNoDetailsSaysOnlyWhatItHas() throws {
        let plain = try injury(#"{"status": "Out", "athlete": {"displayName": "Ann Lee", "position": {"abbreviation": "RB"}}}"#)
        XCTAssertEqual(plain.detailLines, [])
        XCTAssertEqual(plain.spokenText, "Ann Lee, RB, Status: Out")

        let noPosition = try injury(#"{"status": "Out", "athlete": {"displayName": "Ann Lee"}, "details": {}}"#)
        XCTAssertEqual(noPosition.spokenText, "Ann Lee, Status: Out")
    }

    func testEmptyInjuryValuesAreLeftOut() throws {
        let empty = try injury(#"{"details": {"type": " ", "detail": "NOT SPECIFIED", "returnDate": ""}}"#)
        XCTAssertEqual(empty.detailLines, [])
        XCTAssertEqual(empty.spokenText, "")
    }

    func testAnInjuryWithNothingToSayIsNotListed() throws {
        let game = try details(#"""
        {"injuries": [{"team": {"displayName": "Bears"},
                       "injuries": [{}, {"status": "Out", "athlete": {"displayName": "Ann Lee"}}]},
                      {"team": {"displayName": "Lions"}, "injuries": [{}]}]}
        """#)
        let teams = try XCTUnwrap(game.injuries)
        XCTAssertEqual(teams.map(\.listedInjuries.count), [1, 0])
    }

    func testAReturnDateThatIsNotAPlainDateIsShownAsItCame() throws {
        let odd = try injury(#"{"details": {"returnDate": "Week 12"}}"#)
        XCTAssertEqual(odd.detailLines, ["Return Date: Week 12"])
    }

    func testAnOddInjuryCostsOnlyItsOwnOddValue() throws {
        let oddDetails = try injury(#"{"status": "Out", "details": "Knee", "athlete": {"displayName": "Ann Lee"}}"#)
        XCTAssertEqual(oddDetails.spokenText, "Ann Lee, Status: Out")

        let game = try details(#"""
        {"injuries": [{"team": 7, "injuries": [7, {"status": "Out", "athlete": {"displayName": "Ann Lee"}}]},
                      {"team": {"displayName": "Bears"}, "injuries": "none"}]}
        """#)
        let teams = try XCTUnwrap(game.injuries)
        XCTAssertEqual(teams.count, 2)
        XCTAssertEqual(teams[0].injuries?.count, 1)
        XCTAssertEqual(teams[1].team?.displayName, "Bears")
        XCTAssertNil(teams[1].injuries)
    }

    // MARK: Odds

    func testTheLineOfRealGames() throws {
        XCTAssertEqual(try fixture(finalNFL).bettingLine?.details, "SEA -3")
        XCTAssertEqual(try fixture(finalNFL).bettingLine?.overUnder, 46.5)
        XCTAssertEqual(try fixture(preNFL).bettingLine?.details, "JAX -10")
        XCTAssertEqual(try fixture(finalEPL).bettingLine?.details, "BOU +105")
        XCTAssertEqual(try fixture("details_NFL_pieces.json").bettingLine?.details, "WSH -5.5")
    }

    func testOddsComeBeforePickcenterAsOnWindows() throws {
        let game = try details(#"""
        {"odds": [{"details": "A -1"}], "pickcenter": [{"details": "B -2"}]}
        """#)
        XCTAssertEqual(game.bettingLine?.details, "A -1")
    }

    func testALineWithNothingInItIsPassedOver() throws {
        for odds in [#"[]"#, #"[{}]"#, #"[{"details": ""}]"#, #"[{"overUnder": 0}]"#, #"[{"details": "", "overUnder": 0}]"#] {
            let game = try details(#"{"odds": \#(odds), "pickcenter": [{"details": "B -2"}]}"#)
            XCTAssertEqual(game.bettingLine?.details, "B -2", odds)
        }
        XCTAssertEqual(try details(#"{"odds": [{"overUnder": 41.5}]}"#).bettingLine?.overUnder, 41.5)
        XCTAssertNil(try details(#"{"odds": [], "pickcenter": [{}]}"#).bettingLine)
        XCTAssertNil(try details(#"{}"#).bettingLine)
    }

    func testALineSaysOnlyWhatItHas() throws {
        let line = { (json: String) throws -> GameDetails.OddsEntry in
            try JSONDecoder().decode(GameDetails.OddsEntry.self, from: Data(json.utf8))
        }
        let whole = try line(#"{"details": "JAX -10", "overUnder": 39.5}"#)
        XCTAssertEqual(whole.shownParts, ["Line: JAX -10", "O/U: 39.5"])
        XCTAssertEqual(whole.spokenText, "Line: JAX -10. Over/under: 39.5")

        let noTotal = try line(#"{"details": "SEA -3", "overUnder": 0}"#)
        XCTAssertEqual(noTotal.shownParts, ["Line: SEA -3"])
        XCTAssertEqual(noTotal.spokenText, "Line: SEA -3")

        let noSpread = try line(#"{"details": " ", "overUnder": 41.5}"#)
        XCTAssertEqual(noSpread.shownParts, ["O/U: 41.5"])
        XCTAssertEqual(noSpread.spokenText, "Over/under: 41.5")

        XCTAssertEqual(try line(#"{"details": "A -1", "overUnder": "41.5", "provider": 7}"#).spokenText,
                       "Line: A -1. Over/under: 41.5")
    }

    // MARK: The whole game

    func testOddSectionsDoNotCostTheGame() throws {
        let game = try details(#"""
        {"article": 7, "scoringPlays": "none", "standings": [], "gameInfo": 7, "injuries": "none", "news": 7,
         "odds": [{"details": "A -1"}]}
        """#)
        XCTAssertNil(game.article)
        XCTAssertNil(game.scoringPlays)
        XCTAssertNil(game.standings)
        XCTAssertNil(game.gameInfo)
        XCTAssertNil(game.injuries)
        XCTAssertNil(game.news)
        XCTAssertEqual(game.bettingLine?.details, "A -1")
    }

    func testEveryPieceOfTheRealPayloadsComesThrough() throws {
        let data = try Fixtures.data(finalNFL)
        let game = try Fixtures.decodeDetails(data)
        XCTAssertEqual(game.scoringPlays?.count, try Fixtures.rawCount("scoringPlays", of: data))
        XCTAssertEqual(game.injuries?.count, try Fixtures.rawCount("injuries", of: data))
        XCTAssertEqual(game.pickcenter?.count, try Fixtures.rawCount("pickcenter", of: data))
        XCTAssertNotNil(game.article)
        XCTAssertNotNil(game.standings)
        XCTAssertNotNil(game.header)
    }
}

/// Going back to a game from its story loads it again, and VoiceOver mustn't lose its place.
@MainActor
final class GameDetailReloadTests: XCTestCase {
    private func screen() -> GameDetailViewModel {
        let game = Game(id: "401873036", name: "Bears at Seahawks", shortName: "CHI @ SEA", date: Date(),
                        status: Game.GameStatus(state: "post", detail: "Final", period: nil, clock: nil, name: nil),
                        homeTeam: Game.Team(id: "26", name: "Seahawks", abbreviation: "SEA",
                                            displayName: "Seattle Seahawks", score: 17, record: nil, logo: nil),
                        awayTeam: Game.Team(id: "3", name: "Bears", abbreviation: "CHI",
                                            displayName: "Chicago Bears", score: 34, record: nil, logo: nil),
                        venue: nil, broadcasts: [], situation: nil, seasonType: 2)
        return GameDetailViewModel(game: game, sport: .nfl, apiService: ESPNAPIService(session: StubESPN.session()))
    }

    private func summary() throws -> Data {
        try Fixtures.data("summary_final_NFL_401873036.json")
    }

    /// Runs a load until its request has gone out, then gives back the unfinished load.
    private func startLoading(_ viewModel: GameDetailViewModel) async throws -> Task<Void, Never> {
        let task = Task { _ = await viewModel.loadDetails() }
        for _ in 0..<500 where StubESPN.requests.isEmpty {
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        XCTAssertFalse(StubESPN.requests.isEmpty)
        return task
    }

    func testTheFirstLoadShowsTheSpinner() async throws {
        let viewModel = screen()
        let body = try summary()
        StubESPN.answer { _ in .delayed(0.5, body) }
        let task = try await startLoading(viewModel)
        XCTAssertTrue(viewModel.isLoading)
        await task.value
        XCTAssertFalse(viewModel.isLoading)
        XCTAssertNotNil(viewModel.gameDetails)
    }

    func testAFailedFirstLoadSaysSo() async {
        let viewModel = screen()
        StubESPN.answer { _ in .status(500) }
        await viewModel.loadDetails()
        XCTAssertNil(viewModel.gameDetails)
        XCTAssertNotNil(viewModel.errorMessage)
        XCTAssertFalse(viewModel.isLoading)
    }

    func testComingBackRefreshesWithNoSpinner() async throws {
        let viewModel = screen()
        let body = try summary()
        StubESPN.answer { _ in .body(body) }
        await viewModel.loadDetails()
        XCTAssertNotNil(viewModel.gameDetails)

        StubESPN.answer { _ in .delayed(0.5, body) }
        let task = try await startLoading(viewModel)
        XCTAssertFalse(viewModel.isLoading, "a spinner would replace the tabs VoiceOver is in")
        XCTAssertNotNil(viewModel.gameDetails)
        await task.value
        XCTAssertNotNil(viewModel.gameDetails)
        XCTAssertFalse(viewModel.isLoading)
    }

    func testAFailedRefreshKeepsWhatIsShowing() async throws {
        let viewModel = screen()
        let body = try summary()
        StubESPN.answer { _ in .body(body) }
        let first = await viewModel.loadDetails()
        XCTAssertTrue(first, "a load that worked says so, for a refresh asked out loud")

        for failure in [StubESPN.Reply.status(500), StubESPN.Reply.failure(URLError(.notConnectedToInternet))] {
            StubESPN.answer { _ in failure }
            let loaded = await viewModel.loadDetails()
            XCTAssertFalse(loaded, "a failed refresh says so, so the screen can")
            XCTAssertNotNil(viewModel.gameDetails)
            XCTAssertNil(viewModel.errorMessage)
            XCTAssertFalse(viewModel.isLoading)
        }
    }

    func testACancelledLoadIsNoFailure() async {
        let viewModel = screen()
        StubESPN.answer { _ in .failure(URLError(.cancelled)) }
        await viewModel.loadDetails()
        XCTAssertNil(viewModel.errorMessage)
        XCTAssertFalse(viewModel.isLoading)
    }
}
