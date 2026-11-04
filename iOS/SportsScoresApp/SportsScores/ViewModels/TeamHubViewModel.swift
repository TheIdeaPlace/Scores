//
//  TeamHubViewModel.swift
//  SportsScores
//
//  Manages data loading for all Team Hub tabs.
//  Each tab lazily loads its data on first access.
//

import Foundation

@MainActor
class TeamHubViewModel: ObservableObject {
    let teamId: String
    let sport: Sport

    // MARK: - Published state

    @Published var teamInfo: TeamHubTeamInfo?
    @Published var coachName: String?

    @Published var roster: [RosterPlayer] = []
    @Published var news: [NewsItem] = []
    @Published var schedule: [ScheduleGame] = []

    @Published var isLoadingInfo = false
    @Published var isLoadingRoster = false
    @Published var isLoadingNews = false
    @Published var isLoadingSchedule = false

    @Published var errorInfo: String?
    @Published var errorRoster: String?
    @Published var errorNews: String?
    @Published var errorSchedule: String?

    private let apiService: ESPNAPIService

    // MARK: - Init

    init(teamId: String, sport: Sport, apiService: ESPNAPIService = .shared) {
        self.teamId = teamId
        self.sport = sport
        self.apiService = apiService
    }

    // MARK: - Load functions

    /// Loads team info and concurrently starts loading the schedule
    /// (needed for previous/next game in the Info tab).
    func loadInfo() async {
        guard teamInfo == nil, !isLoadingInfo else { return }
        isLoadingInfo = true
        errorInfo = nil
        async let scheduleTask: Void = loadSchedule()
        do {
            if sport.usesCFLSource {
                teamInfo = try await CFLAPIService.shared.fetchTeamInfo(teamId: teamId)
            } else {
                teamInfo = try await apiService.fetchTeamHubInfo(teamId: teamId, sport: sport)
            }
        } catch {
            errorInfo = "Could not load team info."
        }
        isLoadingInfo = false
        await scheduleTask
    }

    func loadRoster() async {
        // No roster feed for CFL — leave empty so the tab shows "No roster available".
        guard !sport.usesCFLSource else { return }
        guard roster.isEmpty, !isLoadingRoster else { return }
        isLoadingRoster = true
        errorRoster = nil
        do {
            let result = try await apiService.fetchTeamRoster(teamId: teamId, sport: sport)
            roster = result.players
            // Backfill coach name if not yet set
            if coachName == nil { coachName = result.coachName }
        } catch {
            errorRoster = "Could not load roster."
        }
        isLoadingRoster = false
    }

    func loadNews() async {
        // No team news feed for CFL — leave empty so the tab shows "No news available".
        guard !sport.usesCFLSource else { return }
        guard news.isEmpty, !isLoadingNews else { return }
        isLoadingNews = true
        errorNews = nil
        do {
            news = try await apiService.fetchTeamNews(teamId: teamId, sport: sport, limit: 25)
        } catch {
            errorNews = "Could not load news."
        }
        isLoadingNews = false
    }

    func loadSchedule() async {
        guard schedule.isEmpty, !isLoadingSchedule else { return }
        isLoadingSchedule = true
        errorSchedule = nil
        do {
            if sport.usesCFLSource {
                schedule = try await CFLAPIService.shared.fetchSchedule(teamId: teamId)
            } else {
                schedule = try await apiService.fetchTeamHubSchedule(teamId: teamId, sport: sport)
            }
        } catch let error where error.isCancellation {
            // Switching tabs mid-load. Nothing is known, and coming back asks again.
        } catch {
            errorSchedule = "Could not load schedule."
        }
        isLoadingSchedule = false
    }

    // MARK: - Derived schedule data

    /// The most recently completed game.
    var previousGame: ScheduleGame? {
        schedule.filter { $0.isCompleted }.last
    }

    /// The next unplayed game (date must be in the future to skip postponed/old games).
    var upcomingGame: ScheduleGame? {
        let now = Date()
        return schedule.first { !$0.isCompleted && !$0.isInProgress && !$0.isCalledOff && $0.isAhead(of: now) }
    }

    /// Last 5 completed games (for the Schedule tab "Recent" section).
    var recentGames: [ScheduleGame] {
        Array(schedule.filter { $0.isCompleted }.suffix(5))
    }

    /// Next 10 upcoming games (for the Schedule tab "Upcoming" section).
    var upcomingGames: [ScheduleGame] {
        let now = Date()
        return Array(schedule.filter { !$0.isCompleted && !$0.isInProgress && $0.isAhead(of: now) }.prefix(10))
    }
}
