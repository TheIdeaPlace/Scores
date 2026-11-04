//
//  TeamStatsStore.swift
//  SportsScores
//
//  Caches ESPN's league team-statistics payload and the stat glossary derived
//  from it.
//
//  This is an actor rather than a plain dictionary on ESPNAPIService because
//  every visible stat heading asks for its definition as it appears — a
//  screenful of sections hits this from many tasks at once, and unsynchronised
//  dictionary writes corrupt memory rather than merely losing a cache entry.
//  Concurrent callers for the same sport also share one download instead of
//  starting a request each.
//

import Foundation

actor TeamStatsStore {
    private let session: URLSession
    /// ESPN web API root, e.g. "https://site.web.api.espn.com/apis/common/v3/sports"
    private let baseURL: String
    private let ttl: TimeInterval = 15 * 60

    private struct CachedPayload {
        let response: TeamStatsByTeamResponse
        let fetchedAt: Date
    }

    private var payloads: [Sport: CachedPayload] = [:]
    private var payloadTasks: [Sport: Task<TeamStatsByTeamResponse, Error>] = [:]
    private var glossaries: [Sport: [String: String]] = [:]
    private var glossaryTasks: [Sport: Task<[String: String], Never>] = [:]

    init(session: URLSession, baseURL: String) {
        self.session = session
        self.baseURL = baseURL
    }

    // MARK: - Full payload

    /// Every team's full stat line for the latest regular season ESPN has, this year's or last's.
    ///
    /// The season is always asked for. With no `seasontype`, ESPN answers with the postseason from
    /// the end of a season until the next one: the WNBA's 8 playoff teams, not its 15. A season
    /// that hasn't started is an empty document or a 500, depending on the league.
    func payload(for sport: Sport) async throws -> TeamStatsByTeamResponse {
        if let cached = payloads[sport], Date().timeIntervalSince(cached.fetchedAt) < ttl {
            return cached.response
        }
        if let inFlight = payloadTasks[sport] {
            return try await inFlight.value
        }

        let task = Task<TeamStatsByTeamResponse, Error> { [session, baseURL] in
            try await Self.fetchLatestRegularSeason(sport: sport, session: session, baseURL: baseURL)
        }
        payloadTasks[sport] = task
        defer { payloadTasks[sport] = nil }

        let decoded = try await task.value
        payloads[sport] = CachedPayload(response: decoded, fetchedAt: Date())
        return decoded
    }

    // MARK: - Stat glossary

    /// Stat key → ESPN's plain-English definition. Kept for the session;
    /// glossary text does not change mid-season.
    func glossary(for sport: Sport) async -> [String: String] {
        if let cached = glossaries[sport] { return cached }
        if let inFlight = glossaryTasks[sport] { return await inFlight.value }

        // Reuse the full payload when it is already in hand; otherwise ask for a
        // single team. The glossary lives in the payload's top-level category
        // metadata, so one team's worth of data (~3 KB) carries every definition
        // instead of the whole league (350 KB for college basketball).
        let cachedResponse = payloads[sport].map(\.response)
        let task = Task<[String: String], Never> { [session, baseURL] in
            let categories: [TeamStatsByTeamResponse.CategoryMetadata]
            if let cachedResponse {
                categories = cachedResponse.categories ?? []
            } else {
                let light = try? await Self.fetch(sport: sport, limit: 1, session: session, baseURL: baseURL)
                categories = light?.categories ?? []
            }

            var definitions: [String: String] = [:]
            for category in categories {
                guard let names = category.names, let descriptions = category.descriptions else { continue }
                for (index, name) in names.enumerated() {
                    guard let text = descriptions[safe: index], !text.isEmpty,
                          definitions[name] == nil else { continue }
                    definitions[name] = text
                }
            }
            return definitions
        }
        glossaryTasks[sport] = task

        let definitions = await task.value
        glossaryTasks[sport] = nil
        // Don't cache a failed lookup — a definition missed while offline should
        // be retried, not remembered as "this sport has none".
        if !definitions.isEmpty { glossaries[sport] = definitions }
        return definitions
    }

    // MARK: - Networking

    /// Football collapses to 25 teams at 1000. ESPN's list isn't in rank order, so a small limit
    /// would drop the real leaders.
    private static let wholeLeagueLimit = 500

    private static func fetchLatestRegularSeason(
        sport: Sport,
        session: URLSession,
        baseURL: String
    ) async throws -> TeamStatsByTeamResponse {
        let year = sport.currentSeasonYear
        var failure: Error?
        for season in [year, year - 1] {
            let response: TeamStatsByTeamResponse
            do {
                response = try await fetch(sport: sport, limit: wholeLeagueLimit, season: season,
                                           session: session, baseURL: baseURL)
            } catch let error as URLError {
                // Another season won't get through a stalled network either.
                throw error
            } catch {
                failure = error
                continue
            }
            let isPreseason = response.requestedSeason?.type?.type == 1
            if !(response.teams ?? []).isEmpty, !isPreseason {
                return try await withEveryTeam(response, sport: sport, season: season,
                                               session: session, baseURL: baseURL)
            }
            failure = nil
        }
        if let failure { throw failure }
        return TeamStatsByTeamResponse(teams: [], categories: nil, pagination: nil, requestedSeason: nil)
    }

    /// ESPN sends 400 teams at most, and page 2 is empty or a 500. Late in a college basketball
    /// season it has 722, half of them schools that played one Division I game, so the list is
    /// asked for again sorted each way by a column every team has: 400 from each end cover them
    /// all, up to 800. A list with some cut would still look whole, with every rank after the gap
    /// wrong, so a failure here fails the lot.
    private static func withEveryTeam(
        _ response: TeamStatsByTeamResponse,
        sport: Sport,
        season: Int,
        session: URLSession,
        baseURL: String
    ) async throws -> TeamStatsByTeamResponse {
        var teams = response.teams ?? []
        guard let count = response.pagination?.count, count > teams.count,
              let column = TeamStatCatalog.sortColumn(for: sport) else { return response }

        var seen = Set(teams.compactMap(\.team.id))
        for direction in ["desc", "asc"] {
            let more = try await fetch(sport: sport, limit: wholeLeagueLimit, season: season,
                                       sort: "\(column):\(direction)", session: session, baseURL: baseURL)
            for team in more.teams ?? [] where team.team.id.map({ seen.insert($0).inserted }) ?? true {
                teams.append(team)
            }
        }
        return TeamStatsByTeamResponse(teams: teams, categories: response.categories,
                                       pagination: response.pagination, requestedSeason: response.requestedSeason)
    }

    /// With no `season`, whatever ESPN answers by default, which is enough for the glossary.
    private static func fetch(
        sport: Sport,
        limit: Int,
        season: Int? = nil,
        sort: String? = nil,
        session: URLSession,
        baseURL: String
    ) async throws -> TeamStatsByTeamResponse {
        var urlString = "\(baseURL)/\(sport.apiPath)/statistics/byteam?region=us&lang=en&limit=\(limit)"
        if let season { urlString += "&season=\(season)&seasontype=2" }
        if let sort { urlString += "&sort=\(sort)" }
        guard let url = URL(string: urlString) else { throw APIError.invalidURL }

        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw APIError.invalidResponse
        }
        return try JSONDecoder().decode(TeamStatsByTeamResponse.self, from: data)
    }
}
