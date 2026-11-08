//
//  TransactionViewModel.swift
//  SportsScores
//
//  One running list of a league's (or a team's) transactions, newest first, that loads older
//  ones as you scroll, and a jump to the end of any month back to January 2001 that keeps
//  going older from there. The paging rule is TransactionPaging, the one Windows shares.
//

import Foundation
import UIKit

/// A line in the list that isn't a transaction: where the month jumped to has none, or where
/// ESPN couldn't give part of a year.
struct TransactionNotice: Identifiable, Equatable {
    let id = UUID()
    let text: String
}

/// What the list shows, in order.
enum TransactionEntry: Identifiable {
    case item(TransactionItem, index: Int)
    case notice(TransactionNotice)

    var id: String {
        switch self {
        case .item(let item, let index): return "\(index)-\(item.id)"
        case .notice(let notice): return notice.id.uuidString
        }
    }
}

@MainActor
class TransactionViewModel: ObservableObject {
    @Published var entries: [TransactionEntry] = []
    @Published var teams: [TransactionTeam] = []
    /// The first load of the list is under way.
    @Published var isLoading = false
    /// Loading older ones is under way.
    @Published var isLoadingMore = false
    /// The first load failed: the list has nothing to show but this.
    @Published var errorMessage: String?
    /// Loading older ones failed: what's there stays.
    @Published var loadMoreError: String?
    /// The first load found nothing at all; said plainly in place of the list.
    @Published var emptyMessage: String?
    /// The month the list starts at, or nil for the newest.
    @Published private(set) var jump: (year: Int, month: Int)?
    /// Where the next load starts; nil when there is nothing older.
    @Published private(set) var cursor: TransactionPaging.Cursor?

    let sport: Sport
    let filterTeam: TransactionTeam?

    private let apiService = ESPNAPIService.shared
    private var generation = 0
    private var itemCount = 0

    init(sport: Sport, team: TransactionTeam? = nil) {
        self.sport = sport
        self.filterTeam = team
    }

    // MARK: - Teams (used by team picker)

    func loadTeams() async {
        guard teams.isEmpty else { return }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let fetched = try await apiService.fetchTeamsForSport(sport: sport)
            teams = fetched.sorted { $0.displayName < $1.displayName }
        } catch {
            errorMessage = APIError.unavailable("the teams")
        }
    }

    // MARK: - Where the list is

    static func today() -> (year: Int, month: Int) {
        let now = Date()
        let calendar = Calendar.current
        return (calendar.component(.year, from: now), calendar.component(.month, from: now))
    }

    private var teamName: String? { filterTeam?.displayName }

    var hasMore: Bool { cursor != nil }

    /// "Newest first" or "From March 2003, newest first".
    var positionLabel: String {
        guard let jump else { return "Newest first" }
        return "From \(TransactionPaging.monthLabel(year: jump.year, month: jump.month)), newest first"
    }

    /// Navigation title for the list view.
    var listTitle: String {
        filterTeam?.displayName ?? "All \(sport.displayName)"
    }

    var endText: String { TransactionPaging.endText(teamName: teamName) }

    // MARK: - Loading

    /// The first time the list appears. Coming back to it (a Team Hub tab) keeps its place.
    func startIfNeeded() async {
        guard generation == 0 else { return }
        await start()
    }

    /// Start again at the month given, or the newest when it's nil, this month or later.
    func start(at month: (year: Int, month: Int)? = nil) async {
        generation += 1
        let today = Self.today()
        let first = TransactionPaging.startCursor(todayYear: today.year, todayMonth: today.month,
                                                  year: month?.year, month: month?.month)
        jump = first.month == nil ? nil : (first.year, first.month!)
        cursor = first
        entries = []
        itemCount = 0
        errorMessage = nil
        loadMoreError = nil
        emptyMessage = nil
        isLoadingMore = false
        await load(first: true)
    }

    /// Load older ones, from the end of the list or its button.
    func loadMore() async {
        guard cursor != nil, !isLoading, !isLoadingMore else { return }
        await load(first: false)
    }

    private struct Load {
        var items: [TransactionItem] = []
        var skipped: [(year: Int, below: Bool)] = []
        var following: TransactionPaging.Cursor?
        var oldestYear: Int
    }

    private func fetchLoad(from start: TransactionPaging.Cursor) async throws -> Load {
        var cursor = start
        var load = Load(oldestYear: start.year)
        var requests = 0
        while true {
            let answer = try await apiService.fetchTransactions(sport: sport, cursor: cursor, teamID: filterTeam?.id)
            requests += 1
            load.oldestYear = cursor.year
            if let answer {
                load.items += answer.transactions.filter { TransactionPaging.keeps(cursor, dateText: $0.dateString) }
                load.following = TransactionPaging.nextCursor(cursor, hasMore: cursor.page < answer.pageCount)
            } else {
                load.skipped.append((cursor.year, !load.items.isEmpty))
                load.following = TransactionPaging.afterNoAnswer(cursor)
            }
            guard TransactionPaging.loadContinues(found: load.items.count, requests: requests, cursor: cursor,
                                                  following: load.following, leaguePath: sport.apiPath),
                  let next = load.following else { break }
            cursor = next
        }
        let order = TransactionPaging.newestFirst(load.items.map(\.dateString))
        load.items = order.map { load.items[$0].withTeam(filterTeam) }
        return load
    }

    private func load(first: Bool) async {
        guard let from = cursor else { return }
        let mine = generation
        if first { isLoading = true } else { isLoadingMore = true }
        loadMoreError = nil
        defer {
            if mine == generation {
                if first { isLoading = false } else { isLoadingMore = false }
            }
        }
        do {
            let load = try await fetchLoad(from: from)
            guard mine == generation else { return }  // the month or team changed meanwhile
            cursor = load.following
            show(load, first: first)
        } catch {
            guard mine == generation else { return }
            if Task.isCancelled {
                // The view went away before the answer came. That isn't a failure: the list
                // starts again when it's back, or loads more when it's reached again.
                if first {
                    generation = 0
                    isLoading = false
                }
                return
            }
            let message = APIError.unavailable("transactions")
            if first {
                errorMessage = message
            } else {
                loadMoreError = message
                Self.announce(message)
            }
        }
    }

    private func show(_ load: Load, first: Bool) {
        var added: [TransactionEntry] = []
        let above = load.skipped.filter { !$0.below }.map { TransactionPaging.skippedText(year: $0.year, teamName: teamName) }
        let below = load.skipped.filter { $0.below }.map { TransactionPaging.skippedText(year: $0.year, teamName: teamName) }
        if first, let jump, !load.items.isEmpty,
           !load.skipped.contains(where: { !$0.below && $0.year == jump.year }),
           let notice = TransactionPaging.jumpNotice(year: jump.year, month: jump.month,
                                                     dates: load.items.map(\.dateString), teamName: teamName) {
            added.append(.notice(TransactionNotice(text: notice)))
        }
        added += above.map { .notice(TransactionNotice(text: $0)) }
        for item in load.items {
            added.append(.item(item, index: itemCount))
            itemCount += 1
        }
        added += below.map { .notice(TransactionNotice(text: $0)) }
        entries += added

        if entries.isEmpty {
            // Nothing at all yet, from the first load or from looking further back.
            emptyMessage = TransactionPaging.nothingFound(oldestYear: load.oldestYear, jumpedTo: jump, teamName: teamName)
            if !first {
                Self.announce(emptyMessage!)
            }
            return
        }
        emptyMessage = nil
        if !first {
            if load.items.isEmpty {
                Self.announce((above + below).joined(separator: " ").isEmpty
                              ? TransactionPaging.nothingOlder(oldestYear: load.oldestYear, teamName: teamName)
                              : (above + below).joined(separator: " "))
            } else {
                Self.announce("\(load.items.count) more transactions loaded.")
            }
        }
    }

    private static func announce(_ text: String) {
        UIAccessibility.post(notification: .announcement, argument: text)
    }

    // MARK: - Display

    struct DaySection: Identifiable {
        let id: String
        /// "Nov 7, 2026"; nil for a notice, which stands in a section of its own.
        let title: String?
        var entries: [TransactionEntry]
    }

    /// The list grouped by day, newest first, with each notice in its own untitled section.
    var sections: [DaySection] {
        var sections: [DaySection] = []
        for entry in entries {
            switch entry {
            case .notice:
                sections.append(DaySection(id: entry.id, title: nil, entries: [entry]))
            case .item(let item, _):
                let day = formattedDay(item.dateString)
                if let last = sections.last, last.title == day {
                    sections[sections.count - 1].entries.append(entry)
                } else {
                    sections.append(DaySection(id: "\(entry.id)-\(day)", title: day, entries: [entry]))
                }
            }
        }
        return sections
    }

    /// The last transaction in the list, whose appearing loads older ones.
    var lastEntryID: String? { entries.last?.id }

    /// Parses an ESPN date string and formats it as "MMM d, yyyy".
    func formattedDay(_ dateString: String) -> String {
        let formats = [
            "yyyy-MM-dd'T'HH:mm:ssZ",
            "yyyy-MM-dd'T'HH:mm'Z'",
            "yyyy-MM-dd'T'HH:mmZ",
            "yyyy-MM-dd"
        ]
        let df = DateFormatter()
        df.locale = Locale(identifier: "en_US_POSIX")
        df.timeZone = TimeZone(identifier: "UTC")
        for fmt in formats {
            df.dateFormat = fmt
            if let date = df.date(from: dateString) {
                let display = DateFormatter()
                display.dateStyle = .medium
                display.timeStyle = .none
                display.timeZone = TimeZone(identifier: "UTC")
                return display.string(from: date)
            }
        }
        return dateString
    }
}

