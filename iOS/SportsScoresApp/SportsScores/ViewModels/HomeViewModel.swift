//
//  HomeViewModel.swift
//  SportsScores
//

import Foundation

@MainActor
final class HomeViewModel: ObservableObject {
    @Published var gameCounts: [Sport: Int] = [:]
    @Published var soccerGameCount: Int = 0
    @Published var cflGameCount: Int = 0
    @Published var isLoading = true
    @Published var selectedDate: Date = ScoreboardDay.today()

    private let api = ESPNAPIService.shared
    private var newDayObserver: Task<Void, Never>?

    init() {
        newDayObserver = Task { [weak self] in
            for await _ in NotificationCenter.default.notifications(named: .appReturnedToNewDay) {
                await self?.goToToday()
            }
        }
    }

    deinit { newDayObserver?.cancel() }

    func load() async {
        isLoading = true

        // Load per-sport counts for the main sports list
        await withTaskGroup(of: (Sport, Int).self) { group in
            for sport in Sport.allCases {
                group.addTask {
                    let count = (try? await self.api.fetchGames(for: sport, date: self.selectedDate))
                        .map { $0.count } ?? 0
                    return (sport, count)
                }
            }
            for await (sport, count) in group {
                gameCounts[sport] = count
            }
        }

        // Load total soccer count (summed across all leagues) for the Soccer hub row
        var soccerTotal = 0
        await withTaskGroup(of: Int.self) { group in
            for league in Sport.soccerLeagues {
                group.addTask {
                    (try? await self.api.fetchGames(for: league, date: self.selectedDate))
                        .map { $0.count } ?? 0
                }
            }
            for await count in group { soccerTotal += count }
        }
        soccerGameCount = soccerTotal

        // CFL count (separate data source).
        cflGameCount = await CFLAPIService.shared.gameCount(on: selectedDate)

        isLoading = false
    }

    // Navigation window: today ± 7 days
    private var navigationWindowStart: Date {
        let today = ScoreboardDay.today()
        return Calendar.current.date(byAdding: .day, value: -7, to: today) ?? today
    }

    private var navigationWindowEnd: Date {
        let today = ScoreboardDay.today()
        return Calendar.current.date(byAdding: .day, value: 7, to: today) ?? today
    }

    var canNavigateBackward: Bool {
        selectedDate > navigationWindowStart
    }

    var canNavigateForward: Bool {
        selectedDate < navigationWindowEnd
    }

    func goBack() async {
        let prevDate = Calendar.current.date(byAdding: .day, value: -1, to: selectedDate) ?? selectedDate
        selectedDate = max(prevDate, navigationWindowStart)
        await load()
    }

    func goForward() async {
        let nextDate = Calendar.current.date(byAdding: .day, value: 1, to: selectedDate) ?? selectedDate
        selectedDate = min(nextDate, navigationWindowEnd)
        await load()
    }

    func goToToday() async {
        selectedDate = ScoreboardDay.today()
        await load()
    }
}
