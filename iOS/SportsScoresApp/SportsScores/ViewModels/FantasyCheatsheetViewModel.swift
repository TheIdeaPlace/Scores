//
//  FantasyCheatsheetViewModel.swift
//  SportsScores
//
//  Owns the cheatsheet state: the draft board (players + D/ST), the taken set,
//  the scoring preset, and sort/filter/search. Everything the board needs —
//  ranks, ADP, auction values, projections — arrives in a single service call,
//  so changing the preset or sort just re-derives locally (no refetch).
//

import Foundation
import Combine

@MainActor
final class FantasyCheatsheetViewModel: ObservableObject {

    // MARK: - Published state

    @Published private(set) var players: [CheatsheetPlayer] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    @Published var preset: ScoringPreset { didSet { persistPreset() } }
    @Published var draftState: DraftState { didSet { persistDraftState() } }
    @Published var selectedSort: CheatsheetSort = .rank
    @Published var selectedPositions: Set<FantasyPosition> = Set(FantasyPosition.allCases)
    @Published var searchQuery: String = ""
    @Published var hideTaken: Bool = false
    /// Team abbreviation to filter by; nil shows all teams.
    @Published var selectedTeam: String? = nil
    @Published private(set) var season: Int

    // MARK: - Private

    private let service = FantasyCheatsheetService.shared
    private let presetKey = "fantasyScoringPreset"
    private let draftStateKey = "fantasyDraftTaken"

    // MARK: - Init

    init() {
        if let raw = UserDefaults.standard.string(forKey: "fantasyScoringPreset"),
           let saved = ScoringPreset(rawValue: raw) {
            self.preset = saved
        } else {
            self.preset = .ppr   // PPR is the most common league format.
        }

        if let data = UserDefaults.standard.data(forKey: "fantasyDraftTaken"),
           let saved = try? JSONDecoder().decode(DraftState.self, from: data) {
            self.draftState = saved
        } else {
            self.draftState = DraftState()
        }

        self.season = service.upcomingSeason()
    }

    // MARK: - Derived output

    /// Filtered + sorted rows the view renders.
    var displayedPlayers: [CheatsheetPlayer] {
        players.filter(matches).sorted(by: sortComparator)
    }

    var totalPlayerCount: Int { players.count }
    var displayedCount: Int { displayedPlayers.count }

    /// Team abbreviations present in the pool, sorted, for the team filter menu.
    /// Team abbreviations present in the pool, for the team filter menu.
    ///
    /// "FA" is listed last rather than dropped. Unsigned players are a real slice
    /// of the board — Tyreek Hill and Keenan Allen are both free agents here —
    /// and excluding the entry left them reachable only by search.
    var availableTeams: [String] {
        let all = Set(players.map(\.teamAbbreviation)).subtracting([""])
        let named = all.subtracting(["FA"]).sorted()
        return all.contains("FA") ? named + ["FA"] : named
    }

    // MARK: - Filtering

    private func matches(_ p: CheatsheetPlayer) -> Bool {
        if !selectedPositions.contains(p.position) { return false }
        if let team = selectedTeam, p.teamAbbreviation != team { return false }
        if hideTaken && draftState.isTaken(p.id) { return false }
        if !searchQuery.isEmpty {
            let q = searchQuery.lowercased()
            if !p.fullName.lowercased().contains(q)
                && !p.teamAbbreviation.lowercased().contains(q) {
                return false
            }
        }
        return true
    }

    // MARK: - Sorting

    /// Ordering for the chosen sort, with rank breaking every tie.
    ///
    /// Two details matter here. Values are compared at the precision the row
    /// actually displays, because comparing at full precision orders rows that
    /// look identical by digits nobody can see. And ties fall back to rank rather
    /// than being left equal: `sorted(by:)` is not a stable sort in Swift, so
    /// equal elements may come back in a different order on each rebuild, which
    /// for a VoiceOver user re-reading the board is genuinely disorienting.
    private func sortComparator(_ a: CheatsheetPlayer, _ b: CheatsheetPlayer) -> Bool {
        let rankA = a.rank(for: preset) ?? .max
        let rankB = b.rank(for: preset) ?? .max

        switch selectedSort {
        case .rank:
            return rankA < rankB
        case .adp:
            let x = sortableADP(a), y = sortableADP(b)
            return x == y ? rankA < rankB : x < y
        case .auctionValue:
            // Higher dollar value first; rounded to the whole dollars shown.
            let x = (a.auctionValue ?? 0).rounded(), y = (b.auctionValue ?? 0).rounded()
            return x == y ? rankA < rankB : x > y
        case .projectedPoints:
            let x = sortableProjection(a), y = sortableProjection(b)
            return x == y ? rankA < rankB : x > y
        }
    }

    /// ADP for sorting, at the one decimal the row shows. Players nobody is
    /// drafting have no ADP at all and sort to the bottom.
    private func sortableADP(_ p: CheatsheetPlayer) -> Double {
        guard let a = p.adp, a > 0 else { return .greatestFiniteMagnitude }
        return (a * 10).rounded() / 10
    }

    /// Projected points for sorting, at the one decimal the row shows. Kickers
    /// and defenses carry no projection and sort last.
    private func sortableProjection(_ p: CheatsheetPlayer) -> Double {
        guard let v = p.projectedPoints(for: preset) else { return -.greatestFiniteMagnitude }
        return (v * 10).rounded() / 10
    }

    // MARK: - Draft actions

    func toggleTaken(_ player: CheatsheetPlayer) { draftState.toggleTaken(player.id) }
    func isTaken(_ player: CheatsheetPlayer) -> Bool { draftState.isTaken(player.id) }
    func clearDraft() { draftState = DraftState() }

    // MARK: - Filters

    func togglePosition(_ pos: FantasyPosition) {
        if selectedPositions.contains(pos) { selectedPositions.remove(pos) }
        else { selectedPositions.insert(pos) }
    }

    func selectAllPositions() { selectedPositions = Set(FantasyPosition.allCases) }

    func setPreset(_ preset: ScoringPreset) { self.preset = preset }

    // MARK: - Load

    func loadAll() async {
        guard !isLoading else { return }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let rows = try await service.fetchCheatsheet(season: season)
            players = rows
            if rows.isEmpty {
                errorMessage = "No fantasy draft data is available yet for the \(season) season."
            }
        } catch {
            errorMessage = APIError.unavailable("the draft board")
        }
    }

    // MARK: - Persistence

    private func persistPreset() {
        UserDefaults.standard.set(preset.rawValue, forKey: presetKey)
    }

    private func persistDraftState() {
        if let data = try? JSONEncoder().encode(draftState) {
            UserDefaults.standard.set(data, forKey: draftStateKey)
        }
    }
}
