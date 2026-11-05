//
//  TransactionViewModel.swift
//  SportsScores
//

import Foundation

@MainActor
class TransactionViewModel: ObservableObject {
    @Published var transactions: [TransactionItem] = []
    @Published var teams: [TransactionTeam] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    /// Current ESPN page (only meaningful when `filterTeam == nil`).
    @Published var currentPage = 1
    @Published var pageCount = 1
    @Published var selectedMonth: Int
    @Published var selectedYear: Int
    @Published var noDataForSport = false

    let sport: Sport
    let filterTeam: TransactionTeam?

    private let apiService = ESPNAPIService.shared

    // MARK: - Init

    init(sport: Sport, team: TransactionTeam? = nil) {
        self.sport = sport
        self.filterTeam = team
        let cal = Calendar.current
        let now = Date()
        self.selectedMonth = cal.component(.month, from: now)
        self.selectedYear = cal.component(.year, from: now)
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
            errorMessage = "Could not load teams."
        }
    }

    // MARK: - Transactions

    func loadTransactions() async {
        isLoading = true
        errorMessage = nil
        noDataForSport = false
        defer { isLoading = false }

        let range = dateRange(month: selectedMonth, year: selectedYear)

        do {
            if let team = filterTeam {
                // Fetch the full month at once (large limit) then filter client-side.
                let response = try await apiService.fetchTransactions(
                    sport: sport,
                    page: 1,
                    limit: 500,
                    dateRange: range
                )
                transactions = response.transactions.filter { $0.team.id == team.id }
                pageCount = 1
                currentPage = 1
                noDataForSport = response.count == 0
            } else {
                // Standard ESPN pagination.
                let response = try await apiService.fetchTransactions(
                    sport: sport,
                    page: currentPage,
                    limit: 25,
                    dateRange: range
                )
                pageCount = max(response.pageCount, 1)
                transactions = response.transactions
                noDataForSport = response.count == 0
            }
        } catch {
            errorMessage = APIError.unavailable("transactions")
            transactions = []
        }
    }

    func nextPage() async {
        guard currentPage < pageCount else { return }
        currentPage += 1
        await loadTransactions()
    }

    func previousPage() async {
        guard currentPage > 1 else { return }
        currentPage -= 1
        await loadTransactions()
    }

    func jumpToMonthYear(month: Int, year: Int) async {
        selectedMonth = month
        selectedYear = year
        currentPage = 1
        await loadTransactions()
    }

    // MARK: - Computed

    /// Whether page-navigation controls should be shown (not relevant for team-filtered views).
    var isPaginated: Bool { filterTeam == nil }

    /// Transactions grouped by calendar day (newest-first order preserved).
    var groupedTransactions: [(date: String, items: [TransactionItem])] {
        var groups: [(date: String, items: [TransactionItem])] = []
        for item in transactions {
            let day = formattedDay(item.dateString)
            if groups.last?.date == day {
                groups[groups.count - 1].items.append(item)
            } else {
                groups.append((day, [item]))
            }
        }
        return groups
    }

    /// Navigation title for the list view.
    var listTitle: String {
        filterTeam?.displayName ?? "All \(sport.displayName)"
    }

    /// Human-readable month/year label, e.g. "April 2026".
    var monthYearLabel: String {
        let df = DateFormatter()
        df.dateFormat = "MMMM yyyy"
        df.locale = Locale(identifier: "en_US_POSIX")
        let comps = DateComponents(year: selectedYear, month: selectedMonth, day: 1)
        if let date = Calendar.current.date(from: comps) {
            return df.string(from: date)
        }
        return "\(selectedMonth)/\(selectedYear)"
    }

    static let earliestYear = 2001

    // MARK: - Date helpers

    /// Returns `(startString, endString)` in `"yyyyMMdd"` format for the given month.
    func dateRange(month: Int, year: Int) -> (start: String, end: String) {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        let comps = DateComponents(year: year, month: month, day: 1)
        let firstDay = cal.date(from: comps) ?? Date()
        let daysInMonth = cal.range(of: .day, in: .month, for: firstDay)?.count ?? 30
        let lastComps = DateComponents(year: year, month: month, day: daysInMonth)
        let lastDay = cal.date(from: lastComps) ?? Date()

        let fmt = DateFormatter()
        fmt.dateFormat = "yyyyMMdd"
        fmt.locale = Locale(identifier: "en_US_POSIX")
        fmt.timeZone = TimeZone(identifier: "UTC")
        return (fmt.string(from: firstDay), fmt.string(from: lastDay))
    }

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
        for fmt in formats {
            df.dateFormat = fmt
            if let date = df.date(from: dateString) {
                let display = DateFormatter()
                display.dateStyle = .medium
                display.timeStyle = .none
                return display.string(from: date)
            }
        }
        return dateString
    }
}
