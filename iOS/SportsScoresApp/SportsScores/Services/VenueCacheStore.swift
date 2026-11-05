//
//  VenueCacheStore.swift
//  SportsScores
//
//  A league's venues for as long as the app is running. They come from a month that can be
//  19 MB and rarely change. An actor for the same reason as `ScheduleCacheStore`.
//

import Foundation

actor VenueCacheStore {
    /// Keyed by league and query, because the coverage setting can change the query.
    private var venues: [String: [LeagueVenue]] = [:]

    func venues(forKey key: String) -> [LeagueVenue]? {
        venues[key]
    }

    func store(_ list: [LeagueVenue], forKey key: String) {
        venues[key] = list
    }
}
