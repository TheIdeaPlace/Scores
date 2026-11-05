//
//  FavoritesHubViewModel.swift
//  SportsScores
//
//  Loads live/next game info and two news headlines for each favorite team.
//  Owned by TeamHubSportPickerView so data persists while the hub is in the nav stack.
//

import Foundation

@MainActor
final class FavoritesHubViewModel: ObservableObject {

    @Published var newsMap: [String: [NewsItem]] = [:]           // keyed by teamId, up to 2 items
    @Published var scheduleMap: [String: [ScheduleGame]] = [:]   // keyed by teamId
    /// Live game details for any in-progress game — scores come from the ESPN summary
    /// endpoint which always reflects the current state, unlike the schedule endpoint.
    @Published var liveDetailsMap: [String: GameDetails] = [:]   // keyed by teamId
    @Published var isLoading = false

    private let apiService = ESPNAPIService.shared

    func loadFavorites(_ favorites: [FavoriteTeam]) async {
        guard !favorites.isEmpty else {
            newsMap = [:]
            scheduleMap = [:]
            liveDetailsMap = [:]
            return
        }
        isLoading = true
        await withTaskGroup(of: Void.self) { group in
            for fav in favorites {
                group.addTask { await self.loadSingleFavorite(fav) }
            }
        }
        isLoading = false
    }

    private func loadSingleFavorite(_ fav: FavoriteTeam) async {
        async let newsFetch = fetchNews(fav)
        async let scheduleFetch = fetchSchedule(fav)
        let (news, sched) = await (newsFetch, scheduleFetch)
        if let news { newsMap[fav.id] = news }
        if let sched {
            scheduleMap[fav.id] = sched
            // If a game is currently in progress, fetch its summary so we have live scores.
            // The schedule endpoint returns nil scores for live games.
            if let liveGame = sched.first(where: { $0.isInProgress }),
               let details = try? await apiService.fetchGameDetails(for: liveGame.id, sport: fav.sport) {
                liveDetailsMap[fav.id] = details
            }
        }
    }

    private func fetchNews(_ fav: FavoriteTeam) async -> [NewsItem]? {
        try? await apiService.fetchTeamNews(teamId: fav.id, sport: fav.sport, limit: 2)
    }

    private func fetchSchedule(_ fav: FavoriteTeam) async -> [ScheduleGame]? {
        try? await apiService.fetchFavoriteCardSchedule(teamId: fav.id, sport: fav.sport)
    }
}
