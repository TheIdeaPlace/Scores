//
//  SoccerHubViewModel.swift
//  SportsScores
//

import Foundation

@MainActor
final class SoccerHubViewModel: ObservableObject {
    @Published var gameCounts: [Sport: Int] = [:]
    @Published var isLoading = true
    @Published var selectedDate: Date

    private let api = ESPNAPIService.shared
    private var newDayObserver: Task<Void, Never>?

    init(initialDate: Date? = nil) {
        self.selectedDate = initialDate.map { Calendar.current.startOfDay(for: $0) } ?? ScoreboardDay.today()
        newDayObserver = Task { [weak self] in
            for await _ in NotificationCenter.default.notifications(named: .appReturnedToNewDay) {
                await self?.goToToday()
            }
        }
    }

    deinit { newDayObserver?.cancel() }

    func load() async {
        isLoading = true
        await withTaskGroup(of: (Sport, Int).self) { group in
            for league in Sport.soccerLeagues {
                group.addTask {
                    let count = (try? await self.api.fetchGames(for: league, date: self.selectedDate))
                        .map { $0.count } ?? 0
                    return (league, count)
                }
            }
            for await (league, count) in group {
                gameCounts[league] = count
            }
        }
        isLoading = false
    }

    // MARK: - Date navigation (±7 days from today)

    private var navStart: Date {
        Calendar.current.date(byAdding: .day, value: -7,
                              to: ScoreboardDay.today()) ?? Date()
    }
    private var navEnd: Date {
        Calendar.current.date(byAdding: .day, value: 7,
                              to: ScoreboardDay.today()) ?? Date()
    }

    var canNavigateBackward: Bool { selectedDate > navStart }
    var canNavigateForward: Bool  { selectedDate < navEnd }

    func goBack() async {
        let prev = Calendar.current.date(byAdding: .day, value: -1, to: selectedDate) ?? selectedDate
        selectedDate = max(prev, navStart)
        await load()
    }

    func goForward() async {
        let next = Calendar.current.date(byAdding: .day, value: 1, to: selectedDate) ?? selectedDate
        selectedDate = min(next, navEnd)
        await load()
    }

    func goToToday() async {
        selectedDate = ScoreboardDay.today()
        await load()
    }

    var headerText: String {
        ScoreboardDay.isToday(selectedDate) ? "Today's Games" : "\(dayOfWeek(selectedDate))'s Games"
    }

    var isOnToday: Bool { ScoreboardDay.isToday(selectedDate) }

    private func dayOfWeek(_ date: Date) -> String {
        let fmt = DateFormatter()
        fmt.dateFormat = "EEEE"
        return fmt.string(from: date)
    }

    func accessibilityLabel(for league: Sport) -> String {
        guard !isLoading else { return league.displayName }
        let count = gameCounts[league] ?? 0
        if count == 0 { return "\(league.displayName), no games today" }
        return "\(league.displayName), \(count) \(count == 1 ? "game" : "games") today"
    }
}
