//
//  TransactionPagingGridTests.swift
//  SportsScoresTests
//
//  TransactionPaging.swift against tests/fixtures/transactions_paging_grid.json, the grid
//  transactions_paging.py on Windows is held to, and the real /transactions fixtures.
//

import XCTest
@testable import SportsScores

private typealias Cursor = TransactionPaging.Cursor

private struct PagingGrid: Decodable {
    struct Label: Decodable { let year: Int; let month: Int; let label: String }
    struct MonthsBack: Decodable {
        let today: [Int]; let count: Int; let first: [[Int]]; let last: [[Int]]; let around_new_year: [[Int]]?
    }
    struct Start: Decodable { let name: String; let today: [Int]; let jump: [Int]?; let cursor: Cursor }
    struct Request: Decodable {
        let name: String; let league: String; let team: String?; let cursor: Cursor; let params: [String: String]
    }
    struct Keeps: Decodable { let name: String; let cursor: Cursor; let date: String?; let keeps: Bool }
    struct NewestFirst: Decodable { let name: String; let dates: [String?]; let order: [Int] }
    struct Next: Decodable { let name: String; let cursor: Cursor; let has_more: Bool; let next: Cursor? }
    struct NoAnswer: Decodable { let cursor: Cursor; let next: Cursor? }
    struct Continues: Decodable {
        let name: String; let league: String; let found: Int; let requests: Int; let pages: Int
        let cursor: Cursor; let following: Cursor?; let continues: Bool
    }
    struct Counts: Decodable { let name: String; let answered: Int; let kept: Int; let counts: Bool }
    struct JumpNotice: Decodable { let name: String; let jump: [Int]; let team: String?; let dates: [String?]; let text: String? }
    struct NothingFound: Decodable { let name: String; let oldest_year: Int; let jump: [Int]?; let team: String?; let text: String }
    struct Skipped: Decodable { let year: Int; let team: String?; let text: String }
    struct NothingOlder: Decodable { let oldest_year: Int; let team: String?; let text: String }
    struct EndText: Decodable { let team: String?; let text: String }
    struct Items: Decodable { let name: String; let descriptions: [String] }
    struct Describe: Decodable { let name: String; let text: String }

    let earliest_year: Int
    let page_size: Int
    let whole_year_page_size: Int
    let max_requests_per_load: Int
    let max_pages_per_load: Int
    let counts_against_limit: [Counts]
    let labels: [Label]
    let months_back: [MonthsBack]
    let start: [Start]
    let requests: [Request]
    let keeps: [Keeps]
    let newest_first: [NewestFirst]
    let next: [Next]
    let after_no_answer: [NoAnswer]
    let load_continues: [Continues]
    let jump_notice: [JumpNotice]
    let nothing_found: [NothingFound]
    let skipped_text: [Skipped]
    let nothing_older: [NothingOlder]
    let end_text: [EndText]
    let transaction_items: [Items]
    let describe: [Describe]
}

final class TransactionPagingGridTests: XCTestCase {
    private var raw: Data!
    private var grid: PagingGrid!
    private var object: [String: Any]!

    override func setUpWithError() throws {
        raw = try Data(contentsOf: Fixtures.repoRoot.appendingPathComponent("tests/fixtures/transactions_paging_grid.json"))
        grid = try JSONDecoder().decode(PagingGrid.self, from: raw)
        object = try XCTUnwrap(try JSONSerialization.jsonObject(with: raw) as? [String: Any])
    }

    func testConstants() {
        XCTAssertEqual(TransactionPaging.earliestYear, grid.earliest_year)
        XCTAssertEqual(TransactionPaging.pageSize, grid.page_size)
        XCTAssertEqual(TransactionPaging.wholeYearPageSize, grid.whole_year_page_size)
        XCTAssertEqual(TransactionPaging.maxRequestsPerLoad, grid.max_requests_per_load)
        XCTAssertEqual(TransactionPaging.maxPagesPerLoad, grid.max_pages_per_load)
        for item in grid.counts_against_limit {
            XCTAssertEqual(TransactionPaging.countsAgainstLimit(answered: item.answered, kept: item.kept), item.counts, item.name)
        }
    }

    func testLabelsAndMonths() {
        for item in grid.labels {
            XCTAssertEqual(TransactionPaging.monthLabel(year: item.year, month: item.month), item.label)
        }
        for item in grid.months_back {
            let months = TransactionPaging.monthsBack(todayYear: item.today[0], todayMonth: item.today[1]).map { [$0.year, $0.month] }
            XCTAssertEqual(months.count, item.count)
            XCTAssertEqual(Array(months.prefix(item.first.count)), item.first)
            XCTAssertEqual(Array(months.suffix(item.last.count)), item.last)
            if let around = item.around_new_year, let at = months.firstIndex(of: around[0]) {
                XCTAssertEqual(Array(months[at..<(at + 2)]), around)
            }
        }
    }

    func testStart() {
        XCTAssertGreaterThan(grid.start.count, 5)
        for item in grid.start {
            let cursor = TransactionPaging.startCursor(todayYear: item.today[0], todayMonth: item.today[1],
                                                       year: item.jump?[0], month: item.jump?[1])
            XCTAssertEqual(cursor, item.cursor, item.name)
        }
    }

    func testRequests() {
        XCTAssertGreaterThan(grid.requests.count, 5)
        for item in grid.requests {
            let params = TransactionPaging.requestParams(item.cursor, leaguePath: item.league, teamID: item.team)
            XCTAssertEqual(Dictionary(uniqueKeysWithValues: params.map { ($0.name, $0.value) }), item.params, item.name)
            // The order Windows sends them in (its test reads it from the grid's text).
            let expected = ["limit", "page", item.params["dates"] != nil ? "dates" : "season"] + (item.team != nil ? ["team"] : [])
            XCTAssertEqual(params.map(\.name), expected, item.name)
        }
    }

    func testRequestURL() throws {
        let url = try XCTUnwrap(ESPNAPIService.shared.transactionsURL(
            sport: .nfl, cursor: Cursor(year: 2025, month: 9, page: 1), teamID: nil))
        XCTAssertTrue(url.absoluteString.hasSuffix("/football/nfl/transactions?limit=50&page=1&dates=20250101-20250930"),
                      url.absoluteString)
    }

    func testKeepsOrderAndNext() {
        for item in grid.keeps {
            XCTAssertEqual(TransactionPaging.keeps(item.cursor, dateText: item.date), item.keeps, item.name)
        }
        for item in grid.newest_first {
            XCTAssertEqual(TransactionPaging.newestFirst(item.dates), item.order, item.name)
        }
        for item in grid.next {
            XCTAssertEqual(TransactionPaging.nextCursor(item.cursor, hasMore: item.has_more), item.next, item.name)
        }
        for item in grid.after_no_answer {
            XCTAssertEqual(TransactionPaging.afterNoAnswer(item.cursor), item.next)
        }
        for item in grid.load_continues {
            XCTAssertEqual(TransactionPaging.loadContinues(found: item.found, requests: item.requests, cursor: item.cursor,
                                                           following: item.following, leaguePath: item.league,
                                                           pages: item.pages),
                           item.continues, item.name)
        }
    }

    func testWhatIsSaid() {
        for item in grid.jump_notice {
            XCTAssertEqual(TransactionPaging.jumpNotice(year: item.jump[0], month: item.jump[1], dates: item.dates,
                                                        teamName: item.team), item.text, item.name)
        }
        for item in grid.nothing_found {
            let jump = item.jump.map { (year: $0[0], month: $0[1]) }
            XCTAssertEqual(TransactionPaging.nothingFound(oldestYear: item.oldest_year, jumpedTo: jump, teamName: item.team),
                           item.text, item.name)
        }
        for item in grid.skipped_text {
            XCTAssertEqual(TransactionPaging.skippedText(year: item.year, teamName: item.team), item.text)
        }
        for item in grid.nothing_older {
            XCTAssertEqual(TransactionPaging.nothingOlder(oldestYear: item.oldest_year, teamName: item.team), item.text)
        }
        for item in grid.end_text {
            XCTAssertEqual(TransactionPaging.endText(teamName: item.team), item.text)
        }
    }

    /// The items and their text, read through TransactionResponse and TransactionItem as the app reads them.
    func testItemsAndDescriptions() throws {
        let rawItems = try XCTUnwrap(object["transaction_items"] as? [[String: Any]])
        for (item, rawItem) in zip(grid.transaction_items, rawItems) {
            let body = try JSONSerialization.data(withJSONObject: ["pageCount": 1, "transactions": rawItem["listed"]!])
            let response = try JSONDecoder().decode(TransactionResponse.self, from: body)
            XCTAssertEqual(response.transactions.map(\.description), item.descriptions, item.name)
        }
        let rawDescribe = try XCTUnwrap(object["describe"] as? [[String: Any]])
        for (item, rawItem) in zip(grid.describe, rawDescribe) {
            let body = try JSONSerialization.data(withJSONObject: rawItem["item"]!)
            XCTAssertEqual(try JSONDecoder().decode(TransactionItem.self, from: body).description, item.text, item.name)
        }
    }

    // MARK: - Real answers

    private func response(_ name: String) throws -> TransactionResponse {
        try JSONDecoder().decode(TransactionResponse.self, from: Fixtures.data(name))
    }

    func testALeagueWideJumpAnswer() throws {
        let answer = try response("transactions_NFL_2025_09.json")
        XCTAssertEqual(answer.pageCount, 609)
        XCTAssertEqual(answer.transactions.map(\.team.abbreviation), ["BUF", "CLE", "DAL"])
        XCTAssertTrue(answer.transactions.allSatisfy { TransactionPaging.keeps(Cursor(year: 2025, month: 9, page: 1), dateText: $0.dateString) })
    }

    func testATeamsItemsHaveNoTeamUntilGivenOne() throws {
        let answer = try response("transactions_NFL_9_2024.json")
        XCTAssertEqual(answer.transactions.count, 3)
        XCTAssertEqual(answer.transactions[0].team.id, "")
        XCTAssertEqual(answer.transactions[0].description, "Elevated S Omar Brown from the practice squad.")
        let packers = TransactionTeam(id: "9", location: "Green Bay", name: "Packers", abbreviation: "GB",
                                      displayName: "Green Bay Packers", color: nil, logos: nil)
        XCTAssertEqual(answer.transactions[0].withTeam(packers).team.abbreviation, "GB")
    }

    func testSoccerTransfersReadAsSentences() throws {
        let answer = try response("transactions_MLS_2025.json")
        XCTAssertEqual(answer.transactions.first?.description,
                       "Bajung Darboe joins Bayern Munich from LAFC for an undisclosed fee.")
        let team = try response("transactions_EPL_359_2025.json")
        XCTAssertEqual(team.transactions.map(\.description), [
            "Josh Robinson joins Wigan Athletic from Arsenal for an undisclosed fee.",
            "Marquinhos joins Cruzeiro from Arsenal on loan.",
            "Ayden Heaven joins Manchester United from Arsenal for an undisclosed fee.",
        ])
    }

    func testAnEmptyAnswerIsEmptyNotAFailure() throws {
        XCTAssertEqual(try response("transactions_EPL_dates_empty.json").transactions.count, 0)
        let noList = try JSONDecoder().decode(TransactionResponse.self, from: Data(#"{"count":0,"pageIndex":0,"pageCount":0}"#.utf8))
        XCTAssertEqual(noList.transactions.count, 0)
    }

    func testANullListIsNotAnAnswer() {
        XCTAssertThrowsError(try JSONDecoder().decode(TransactionResponse.self,
                                                      from: Data(#"{"pageCount":1,"transactions":null}"#.utf8)))
    }
}
