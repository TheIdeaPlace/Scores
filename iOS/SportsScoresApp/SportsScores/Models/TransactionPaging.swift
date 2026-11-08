//
//  TransactionPaging.swift
//  SportsScores
//
//  How the Transactions screen walks ESPN's /transactions: one running list, newest first,
//  that loads older ones as you go, and a jump to the end of any month back to January 2001
//  that keeps going older from there. transactions_paging.py on Windows; both are held to
//  tests/fixtures/transactions_paging_grid.json. Change both together.
//
//  What ESPN does (checked 2026-11-07), in short; the Python file has the long version:
//  - `season=Y` is the calendar year Y in every league, pages newest first.
//  - `dates=` takes a range of up to about a year, so a jump asks for January 1 to the
//    month's last day. A team (`team=`) ignores `dates`, so a team's jump asks for the year
//    and leaves out what's newer than the month. Its items carry no team.
//  - Soccer answers oldest first and ignores `dates`, so a load finishes a soccer year in
//    pages of 200 and puts it newest first. Its items are transfers, and a team's list is
//    `{"in": [...], "out": [...]}`.
//  - Some stretches can't be had at all (NFL 2003, February to August, 404 at any page size).
//    A 400 or 404 is skipped: the list says so and goes on to the year before.
//

import Foundation

enum TransactionPaging {
    static let earliestYear = 2001
    static let pageSize = 50
    static let wholeYearPageSize = 200
    /// One load asks again while it has found nothing, but no more than this many times.
    static let maxRequestsPerLoad = 6
    /// And never more requests than this in one load, whatever they found.
    static let maxPagesPerLoad = 30

    /// Where the next request starts. `month` is the month a jump starts at, and nil once the
    /// list has gone past that year.
    struct Cursor: Codable, Equatable {
        var year: Int
        var month: Int?
        var page: Int
    }

    static let monthNames = ["January", "February", "March", "April", "May", "June", "July",
                             "August", "September", "October", "November", "December"]

    /// "March 2003".
    static func monthLabel(year: Int, month: Int) -> String {
        "\(monthNames[month - 1]) \(year)"
    }

    /// Every month that can be jumped to, newest first: this one back to January 2001.
    static func monthsBack(todayYear: Int, todayMonth: Int) -> [(year: Int, month: Int)] {
        var months: [(year: Int, month: Int)] = []
        var year = todayYear, month = todayMonth
        while year >= earliestYear {
            months.append((year, month))
            month -= 1
            if month == 0 { year -= 1; month = 12 }
        }
        return months
    }

    /// Where the list starts: now, or the end of the month jumped to. This month or a later
    /// one is now; before 2001 is January 2001.
    static func startCursor(todayYear: Int, todayMonth: Int, year: Int? = nil, month: Int? = nil) -> Cursor {
        guard let year, let month, (year, month) < (todayYear, todayMonth) else {
            return Cursor(year: todayYear, month: nil, page: 1)
        }
        if year < earliestYear { return Cursor(year: earliestYear, month: 1, page: 1) }
        return Cursor(year: year, month: month, page: 1)
    }

    /// Soccer: oldest first and no dates, so a year comes in whole.
    static func wholeYearAtOnce(_ leaguePath: String) -> Bool {
        leaguePath.hasPrefix("soccer/")
    }

    static func lastDay(year: Int, month: Int) -> Int {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        let first = calendar.date(from: DateComponents(year: year, month: month, day: 1))!
        return calendar.range(of: .day, in: .month, for: first)!.count
    }

    private static func two(_ number: Int) -> String {
        number < 10 ? "0\(number)" : "\(number)"
    }

    /// The query for a cursor, in the order it is sent.
    static func requestParams(_ cursor: Cursor, leaguePath: String, teamID: String? = nil) -> [(name: String, value: String)] {
        let wholeYear = wholeYearAtOnce(leaguePath)
        let team = (teamID?.isEmpty ?? true) ? nil : teamID
        var params: [(name: String, value: String)] = [
            ("limit", String(wholeYear ? wholeYearPageSize : pageSize)),
            ("page", String(cursor.page)),
        ]
        if let month = cursor.month, team == nil, !wholeYear {
            let y = cursor.year
            params.append(("dates", "\(y)0101-\(y)\(two(month))\(two(lastDay(year: y, month: month)))"))
        } else {
            params.append(("season", String(cursor.year)))
        }
        if let team { params.append(("team", team)) }
        return params
    }

    /// The first ten characters of a date when they read as yyyy-MM-dd, else nil.
    private static func day(_ dateText: String?) -> String? {
        guard let dateText, dateText.count >= 10 else { return nil }
        let day = String(dateText.prefix(10))
        let pattern = day.unicodeScalars.enumerated().allSatisfy { index, scalar in
            index == 4 || index == 7 ? scalar == "-" : CharacterSet.decimalDigits.contains(scalar) && scalar.isASCII
        }
        return pattern ? day : nil
    }

    /// Whether an item belongs where the cursor is: in its year, and no later than the month
    /// jumped to. One with no readable date is kept rather than lost.
    static func keeps(_ cursor: Cursor, dateText: String?) -> Bool {
        guard let day = day(dateText) else { return true }
        guard Int(day.prefix(4)) == cursor.year else { return false }
        guard let month = cursor.month else { return true }
        return day <= "\(cursor.year)-\(two(month))-\(two(lastDay(year: cursor.year, month: month)))"
    }

    /// The order to show one load's items in, as indexes: newest first, ties as ESPN sent
    /// them, and anything with no readable date last.
    static func newestFirst(_ dates: [String?]) -> [Int] {
        let keys = dates.map { day($0) ?? "" }
        return dates.indices.sorted { a, b in
            keys[a] != keys[b] ? keys[a] > keys[b] : a < b
        }
    }

    /// Where to go after an answer: its next page, the year before, or nowhere after 2001.
    static func nextCursor(_ cursor: Cursor, hasMore: Bool) -> Cursor? {
        if hasMore { return Cursor(year: cursor.year, month: cursor.month, page: cursor.page + 1) }
        guard cursor.year - 1 >= earliestYear else { return nil }
        return Cursor(year: cursor.year - 1, month: nil, page: 1)
    }

    /// Where to go when ESPN has no answer (400 or 404) for a cursor: the year before.
    static func afterNoAnswer(_ cursor: Cursor) -> Cursor? {
        nextCursor(cursor, hasMore: false)
    }

    /// Whether a request counts toward maxRequestsPerLoad. A page whose items were all left
    /// out (a team's jump passing over what's newer than the month) doesn't: stopping there
    /// would say the month had none when it hadn't been reached. maxPagesPerLoad still caps it.
    static func countsAgainstLimit(answered: Int, kept: Int) -> Bool {
        answered == 0 || kept > 0
    }

    /// Whether one load asks again after an answer: while it has nothing to show, and in
    /// soccer until the year is finished, so a year never comes out half in order. `requests`
    /// is what counts against maxRequestsPerLoad and `pages` every request, never past
    /// maxPagesPerLoad.
    static func loadContinues(found: Int, requests: Int, cursor: Cursor, following: Cursor?,
                              leaguePath: String, pages: Int) -> Bool {
        guard let following, pages < maxPagesPerLoad else { return false }
        if found > 0 && wholeYearAtOnce(leaguePath) && following.year == cursor.year { return true }
        return found == 0 && requests < maxRequestsPerLoad
    }

    private static func grouped(_ number: Int) -> String {
        let digits = String(number)
        var out = ""
        for (index, character) in digits.enumerated() {
            if index > 0 && (digits.count - index) % 3 == 0 { out.append(",") }
            out.append(character)
        }
        return out
    }

    /// What a transaction says: ESPN's description, or for a soccer transfer, who moved where.
    /// "" if there is nothing to say.
    static func describe(description: String?, athlete: String?, from origin: String?, to destination: String?,
                         type kind: String?, amount: Double?, currencyCode: String?, currencySign: String?) -> String {
        func clean(_ text: String?) -> String { (text ?? "").trimmingCharacters(in: .whitespacesAndNewlines) }
        let given = clean(description)
        if !given.isEmpty { return given }
        let athlete = clean(athlete), origin = clean(origin), destination = clean(destination)
        guard !(athlete.isEmpty && origin.isEmpty && destination.isEmpty) else { return "" }
        var text = athlete.isEmpty ? "A player" : athlete
        if !destination.isEmpty {
            text += " joins \(destination)"
            if !origin.isEmpty { text += " from \(origin)" }
        } else if !origin.isEmpty {
            text += " leaves \(origin)"
        }
        switch kind ?? "" {
        case "Loan": text += " on loan"
        case "Free": text += " on a free transfer"
        case "Undisclosed": text += " for an undisclosed fee"
        case "Swap": text += " in a swap"
        case "Fee":
            if let amount, amount > 0, amount.isFinite {
                let number = grouped(Int(amount))
                if let code = currencyCode, !code.isEmpty {
                    text += " for \(number) \(code)"
                } else if let sign = currencySign, !sign.isEmpty {
                    text += " for \(sign)\(number)"
                } else {
                    text += " for \(number)"
                }
            } else {
                text += " for a fee"
            }
        default: break
        }
        return text + "."
    }

    private static func subject(_ teamName: String?) -> String {
        if let teamName, !teamName.isEmpty { return "\(teamName) transactions" }
        return "transactions"
    }

    /// Said above the list when the month jumped to has none but older ones were found.
    static func jumpNotice(year: Int, month: Int, dates: [String?], teamName: String? = nil) -> String? {
        guard !dates.isEmpty else { return nil }
        let prefix = "\(year)-\(two(month))"
        if dates.contains(where: { $0?.hasPrefix(prefix) == true }) { return nil }
        return "No \(subject(teamName)) in \(monthLabel(year: year, month: month)). Older ones follow."
    }

    /// Said when a load found nothing at all, back to January of `oldestYear`.
    static func nothingFound(oldestYear: Int, jumpedTo: (year: Int, month: Int)? = nil, teamName: String? = nil) -> String {
        let subject = subject(teamName)
        guard let jumpedTo else { return "No \(subject) since January \(oldestYear)." }
        let label = monthLabel(year: jumpedTo.year, month: jumpedTo.month)
        if oldestYear == jumpedTo.year && jumpedTo.month == 1 { return "No \(subject) in \(label)." }
        return "No \(subject) from January \(oldestYear) to \(label)."
    }

    /// Said where ESPN had no answer for part of a year and the list went on without it.
    static func skippedText(year: Int, teamName: String? = nil) -> String {
        let text = "ESPN couldn't provide some of \(year)'s \(subject(teamName))"
        return text + (year > earliestYear ? ", so the list goes on with \(year - 1)." : ".")
    }

    /// Said when loading more found nothing, back to January of `oldestYear`.
    static func nothingOlder(oldestYear: Int, teamName: String? = nil) -> String {
        "No older \(subject(teamName)) found back to January \(oldestYear)."
    }

    /// Said at the bottom when there is nothing older to load.
    static func endText(teamName: String? = nil) -> String {
        "No older \(subject(teamName)). The list goes back to January \(earliestYear)."
    }
}
