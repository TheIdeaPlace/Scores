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

    /// Asked for only when the schedule above has no home game in it.
    @Published var regularSeason: [ScheduleGame] = []
    @Published var isLoadingHomeVenue = false

    private let apiService: ESPNAPIService
    private let fetchRegularSeason: (String, Sport) async throws -> [ScheduleGame]
    /// True once the schedule has an answer of any kind. False after a cancelled request,
    /// which isn't one, so `loadInfo` knows to ask again.
    private var scheduleAnswered = false

    // MARK: - Init

    init(teamId: String, sport: Sport, apiService: ESPNAPIService = .shared,
         fetchRegularSeason: @escaping (String, Sport) async throws -> [ScheduleGame] = { id, sport in
             try await ESPNAPIService.shared.fetchRegularSeasonSchedule(teamId: id, sport: sport)
         }) {
        self.teamId = teamId
        self.sport = sport
        self.apiService = apiService
        self.fetchRegularSeason = fetchRegularSeason
    }

    // MARK: - Load functions

    /// Loads team info and concurrently starts loading the schedule
    /// (needed for previous/next game in the Info tab).
    func loadInfo() async {
        guard teamInfo == nil, !isLoadingInfo else {
            // Pushing a screen while the schedule loads cancels it, with the team info already
            // in. Info would read "No recent or upcoming games", and the venue would settle
            // on ESPN's franchise name, with nothing to ever ask again.
            if !isLoadingInfo, !isLoadingSchedule, !scheduleAnswered {
                await loadSchedule()
                await loadHomeVenue()
            }
            return
        }
        isLoadingInfo = true
        isLoadingHomeVenue = true
        errorInfo = nil
        async let scheduleTask: Void = loadSchedule()
        do {
            if sport.usesCFLSource {
                teamInfo = try await CFLAPIService.shared.fetchTeamInfo(teamId: teamId)
            } else {
                teamInfo = try await apiService.fetchTeamHubInfo(teamId: teamId, sport: sport)
            }
        } catch let error where error.isCancellation {
            // With no team info, the next call starts over.
        } catch {
            errorInfo = "Could not load team info."
        }
        isLoadingInfo = false
        await scheduleTask
        await loadHomeVenue()
    }

    /// `fetchTeamHubSchedule` can come back with no home game on it, or none at all. If so,
    /// ask for the regular season ESPN does have before settling for the franchise venue.
    /// A World Cup team has no home, and the CFL has no ESPN schedule.
    func loadHomeVenue() async {
        isLoadingHomeVenue = true
        defer { isLoadingHomeVenue = false }
        guard !sport.isWorldCup, !sport.usesCFLSource,
              schedule.mostUsedHomeVenue(teamId: teamId) == nil else { return }
        regularSeason = (try? await fetchRegularSeason(teamId, sport)) ?? []
    }

    private var newsAnswered = false

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
        // A team with no news has answered: asking on every visit only shows "Loading news".
        guard news.isEmpty, !newsAnswered, !isLoadingNews else { return }
        isLoadingNews = true
        errorNews = nil
        do {
            news = try await apiService.fetchTeamNews(teamId: teamId, sport: sport, limit: 25)
            newsAnswered = true
        } catch let error where error.isCancellation {
            // Switching tabs mid-load. Nothing is known, and coming back asks again.
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
            scheduleAnswered = true
        } catch let error where error.isCancellation {
            // Switching tabs or pushing a screen mid-load. Nothing is known, and coming back
            // to either tab asks again: this one's own .task, and `loadInfo` for Info.
        } catch let error where error.isNothingThere && !sport.usesCFLSource {
            // ESPN says it has nothing there, which isn't a failure to report.
            scheduleAnswered = true
        } catch {
            errorSchedule = "Could not load schedule."
            scheduleAnswered = true
        }
        isLoadingSchedule = false
    }

    // MARK: - Derived schedule data

    /// Where the team plays, from the home games on the schedule `loadInfo` already loads.
    /// ESPN's franchise venue is the fallback, once there's no schedule to be had: showing
    /// it while the schedules load would put up an old name and then change it. A World Cup
    /// team's "home" games are tournament draws, so Brazil would read MetLife Stadium.
    var teamVenue: (name: String, city: String?)? {
        if !sport.isWorldCup {
            if let venue = schedule.mostUsedHomeVenue(teamId: teamId) { return venue }
            if let venue = regularSeason.mostUsedHomeVenue(teamId: teamId) { return venue }
        }
        guard !isLoadingSchedule, !isLoadingHomeVenue, let name = teamInfo?.venueName else { return nil }
        return (name, teamInfo?.venueCity)
    }

    /// The most recently completed game.
    var previousGame: ScheduleGame? {
        schedule.filter { $0.isCompleted }.last
    }

    /// The next unplayed game (date must be in the future to skip postponed/old games).
    var upcomingGame: ScheduleGame? {
        schedule.nextToPlay(after: Date())
    }

    /// Last 5 completed games (for the Schedule tab "Recent" section).
    var recentGames: [ScheduleGame] {
        Array(schedule.filter { $0.isCompleted }.suffix(5))
    }

    /// Next 10 upcoming games (for the Schedule tab "Upcoming" section). A game called off
    /// with its date still ahead stays, reading "Postponed" or "Canceled": someone planning
    /// around that date wants to know, and would otherwise see it just vanish.
    var upcomingGames: [ScheduleGame] {
        let now = Date()
        return Array(schedule.filter { !$0.isCompleted && !$0.isInProgress && $0.isAhead(of: now) }.prefix(10))
    }
}
