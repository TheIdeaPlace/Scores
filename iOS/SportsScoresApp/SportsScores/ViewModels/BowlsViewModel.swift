//
//  BowlsViewModel.swift
//  SportsScores
//
//  College football's bowls and playoff, for the Bowls & Playoffs screen.
//

import Foundation

@MainActor
final class BowlsViewModel: ObservableObject {
    @Published private(set) var sections: [PostseasonSection] = []
    /// True from the start, so nothing can read as "no bowl games" before the first answer.
    @Published private(set) var isLoading = true
    @Published private(set) var errorMessage: String?
    /// A pull to refresh failed. The list stays, and this says it's the one last loaded.
    @Published private(set) var refreshFailed = false

    /// What was last asked for, whatever came of it. The view's task runs again on coming
    /// back from a game's details, and reloading then would take VoiceOver off the row it
    /// was on. It doesn't ask again after a failure either, which is for Retry.
    private var attemptedQuery: String?
    /// Which load is the current one, so that one it has replaced changes nothing.
    private var latestLoad = 0
    private let apiService: ESPNAPIService

    init(apiService: ESPNAPIService = .shared) {
        self.apiService = apiService
    }

    static let failure = APIError.unavailable("bowl games")

    func load(for sport: Sport, coverage: NCAAFCoverage) async {
        guard apiService.postseasonURLString(for: sport, ncaafCoverage: coverage) != attemptedQuery else { return }
        await retry(for: sport, coverage: coverage)
    }

    func retry(for sport: Sport, coverage: NCAAFCoverage) async {
        attemptedQuery = apiService.postseasonURLString(for: sport, ncaafCoverage: coverage)
        isLoading = true
        errorMessage = nil
        refreshFailed = false
        latestLoad += 1
        let load = latestLoad
        do {
            let games = try await apiService.fetchPostseasonGames(for: sport, ncaafCoverage: coverage)
            guard load == latestLoad else { return }
            sections = PostseasonList.sections(games)
            isLoading = false
        } catch is CancellationError {
            // Gone from the screen, so it's asked for again on coming back.
            guard load == latestLoad else { return }
            attemptedQuery = nil
        } catch let error as URLError where error.code == .cancelled {
            guard load == latestLoad else { return }
            attemptedQuery = nil
        } catch {
            guard load == latestLoad else { return }
            sections = []
            errorMessage = Self.failure
            isLoading = false
        }
    }

    /// Pull to refresh asks ESPN again; the list stays on screen while it does and if it fails.
    func refresh(for sport: Sport, coverage: NCAAFCoverage) async {
        refreshFailed = false
        latestLoad += 1
        let load = latestLoad
        do {
            let games = try await apiService.fetchPostseasonGames(for: sport, ncaafCoverage: coverage)
            guard load == latestLoad else { return }
            attemptedQuery = apiService.postseasonURLString(for: sport, ncaafCoverage: coverage)
            sections = PostseasonList.sections(games)
            errorMessage = nil
            isLoading = false
        } catch is CancellationError {
            return
        } catch let error as URLError where error.code == .cancelled {
            return
        } catch {
            guard load == latestLoad else { return }
            if sections.isEmpty {
                errorMessage = Self.failure
                isLoading = false
            } else {
                refreshFailed = true
            }
        }
    }
}
