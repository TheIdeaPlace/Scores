//
//  NFLDraftViewModel.swift
//  SportsScores
//

import Foundation

@MainActor
class NFLDraftViewModel: ObservableObject {
    @Published var response: DraftResponse?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var selectedYear: Int
    @Published var selectedRound: Int = 1

    let availableYears: [Int]

    private var teamDict: [String: DraftTeam] = [:]
    private var positionDict: [String: String] = [:]
    private let apiService = ESPNAPIService.shared

    init() {
        let cal = Calendar.current
        let now = Date()
        let month = cal.component(.month, from: now)
        let year = cal.component(.year, from: now)
        // Default to current year during draft season (April+), else previous year
        let defaultYear = month >= 4 ? year : year - 1
        self.selectedYear = defaultYear
        // Cover all years back to the first NFL Draft (1936)
        self.availableYears = Array(stride(from: year, through: 1936, by: -1))
    }

    // MARK: - Computed

    var picksForSelectedRound: [DraftPick] {
        response?.picks.filter { $0.round == selectedRound } ?? []
    }

    var numberOfRounds: Int {
        max(response?.rounds ?? 7, 1)
    }

    // MARK: - Lookups

    func team(for pick: DraftPick) -> DraftTeam? {
        teamDict[pick.teamId]
    }

    func positionAbbr(for position: DraftAthletePosition) -> String? {
        positionDict[position.id] ?? Self.positionsLeftOut[position.id]
    }

    /// Ids athletes carry that an older draft's own list of positions doesn't have: 2001 to 2014
    /// list a center as 4 while they're 91, and 2018 its kickers as 80 while they're 22. Windows
    /// has these too: DRAFT_POSITIONS_LEFT_OUT in espn_api.py.
    nonisolated static let positionsLeftOut = ["91": "C", "22": "PK"]

    // MARK: - Data loading

    func fetchDraft() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            let draft = try await apiService.fetchDraft(year: selectedYear)
            response = draft
            teamDict = Dictionary(uniqueKeysWithValues: draft.teams.map { ($0.id, $0) })
            positionDict = Dictionary(uniqueKeysWithValues: draft.positions.map { ($0.id, $0.abbreviation) })
            selectedRound = detectActiveRound(picks: draft.picks)
        } catch {
            errorMessage = APIError.unavailable("the draft")
            response = nil
        }
    }

    // MARK: - Private helpers

    private func detectActiveRound(picks: [DraftPick]) -> Int {
        guard !picks.isEmpty else { return 1 }
        let onClockRounds = Set(picks.filter { $0.status == "ON_THE_CLOCK" }.map { $0.round })
        let madeRounds = Set(picks.filter { $0.status == "SELECTION_MADE" }.map { $0.round })
        // A round with both statuses is the in-progress round
        let transitioning = onClockRounds.intersection(madeRounds)
        if let active = transitioning.min() { return active }
        // All on the clock → draft hasn't started, show round 1
        if !onClockRounds.isEmpty { return onClockRounds.min() ?? 1 }
        // All made → draft complete, show round 1
        return 1
    }
}
