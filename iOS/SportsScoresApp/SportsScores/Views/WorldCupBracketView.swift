//
//  WorldCupBracketView.swift
//  SportsScores
//
//  Tournament bracket tab for the World Cup hub.
//
//  Phase picker across the top selects the tournament round.
//  - Group Stage → delegates to WorldCupGroupsView (re-uses groups data)
//  - Knockout rounds → fetches and shows a list of matches in 3 view modes
//
//  List-based design keeps it fully accessible to VoiceOver without requiring
//  a visual bracket tree.
//

import SwiftUI

struct WorldCupBracketView: View {

    @ObservedObject var viewModel: WorldCupViewModel
    let sport: Sport

    @State private var viewMode: ViewMode = .savedDefault()
    @EnvironmentObject private var appSettings: AppSettings

    var body: some View {
        VStack(spacing: 0) {
            pathToTheCupButton
                .padding(.horizontal)
                .padding(.top, 8)
                .padding(.bottom, 4)

            phasePicker
                .padding(.horizontal)
                .padding(.vertical, 8)
                .background(Color.secondary.opacity(0.05))
                .overlay(alignment: .bottom) { Divider() }

            phaseContent
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .toolbar {
            // Only show view-mode button on knockout phases (Group Stage uses its own toolbar button)
            if viewModel.selectedPhaseId != "1" {
                ToolbarItem(placement: .navigationBarTrailing) {
                    ViewModeMenuButton(currentMode: $viewMode)
                }
            }
        }
        .task {
            // Load the initial phase on first appear.
            if let phase = viewModel.selectedPhase, phase.id != "1" {
                await viewModel.loadBracket(for: phase)
            }
            // Load the full knockout bracket so placeholders ("Round of 32 N
            // Winner") can be resolved to real teams and Path to the Cup is ready.
            await viewModel.loadFullBracket()
        }
    }

    // MARK: - Path to the Cup

    private var pathToTheCupButton: some View {
        NavigationLink {
            WorldCupPathView(viewModel: viewModel, sport: sport)
        } label: {
            HStack(spacing: 8) {
                Image(systemName: "trophy.fill")
                    .accessibilityHidden(true)
                Text("Path to the Cup")
                    .font(.subheadline.bold())
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.caption.bold())
                    .foregroundColor(.secondary)
                    .accessibilityHidden(true)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .frame(maxWidth: .infinity)
            .background(Color.accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Path to the Cup")
        .accessibilityHint("Pick any team to see their road to the title, or where they were eliminated")
    }

    // MARK: - Phase picker

    private var phasePicker: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(viewModel.phases) { phase in
                    Button {
                        Task { await viewModel.loadBracket(for: phase) }
                    } label: {
                        Text(phase.label)
                            .font(.subheadline.bold())
                            .padding(.horizontal, 14)
                            .padding(.vertical, 7)
                            .background(
                                viewModel.selectedPhaseId == phase.id
                                    ? Color.accentColor
                                    : Color.secondary.opacity(0.15),
                                in: Capsule()
                            )
                            .foregroundColor(
                                viewModel.selectedPhaseId == phase.id ? .white : .primary
                            )
                    }
                    .accessibilityLabel(phase.label)
                    .accessibilityAddTraits(viewModel.selectedPhaseId == phase.id ? .isSelected : [])
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Tournament phases")
    }

    // MARK: - Content for selected phase

    @ViewBuilder
    private var phaseContent: some View {
        if viewModel.selectedPhaseId == "1" {
            // Group Stage — show the group standings view
            WorldCupGroupsView(
                groups: viewModel.groups,
                sport: sport,
                phases: viewModel.phases,
                isLoading: viewModel.isLoadingGroups,
                error: viewModel.groupsError,
                onRetry: { Task { await viewModel.loadGroups() } }
            )
        } else if viewModel.isLoadingBracket {
            ProgressView("Loading matches…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .accessibilityLabel("Loading \(viewModel.selectedPhase?.label ?? "bracket") matches")
        } else if let err = viewModel.bracketError {
            ErrorStateView(message: err) {
                Task {
                    if let phase = viewModel.selectedPhase {
                        await viewModel.loadBracket(for: phase)
                    }
                }
            }
        } else if viewModel.bracketGames.isEmpty {
            emptyBracket
        } else {
            matchList(games: viewModel.bracketGames)
        }
    }

    // MARK: - Match list (3 view modes)

    private func matchList(games: [Game]) -> some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                let live      = games.filter { $0.status.isLive || $0.status.isSuspended }
                let upcoming  = games.filter { !$0.status.isLive && !$0.status.isCompleted
                                                && !$0.status.isPostponed && !$0.status.isCancelled
                                                && !$0.status.isSuspended }
                let completed = games.filter { $0.status.isCompleted && !$0.status.isSuspended }
                let other     = games.filter { $0.status.isPostponed || $0.status.isCancelled }

                matchSection(title: "In Progress", games: live)
                matchSection(title: "Upcoming",    games: upcoming)
                matchSection(title: "Completed",   games: completed)
                matchSection(title: "Other",       games: other)
            }
            .padding(.vertical)
        }
    }

    @ViewBuilder
    private func matchSection(title: String, games: [Game]) -> some View {
        if !games.isEmpty {
            switch viewMode {
            case .table:    tableSection(title: title, games: games)
            case .quickList: quickSection(title: title, games: games)
            case .fullList:  fullSection(title: title, games: games)
            }
        }
    }

    // -- Table mode --

    private func tableSection(title: String, games: [Game]) -> some View {
        let headers = ["Away", "Home", "Status"]
        let rows = games.map { tableRow($0) }
        return VStack(alignment: .leading, spacing: 0) {
            sectionHeader(title)
            VStack(spacing: 0) {
                HStack(spacing: 0) {
                    ForEach(headers, id: \.self) { h in
                        Text(h)
                            .font(.caption.bold())
                            .foregroundColor(.secondary)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 6)
                            .background(Color.secondary.opacity(0.12))
                    }
                }
                .accessibilityHidden(true)
                ForEach(Array(games.enumerated()), id: \.element.id) { idx, game in
                    NavigationLink(destination: GameDetailView(game: game, sport: sport)) {
                        HStack(spacing: 0) {
                            ForEach(Array(tableRow(game).enumerated()), id: \.offset) { _, val in
                                Text(val)
                                    .font(.subheadline)
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 8)
                            }
                        }
                        .background(idx % 2 == 0 ? Color.clear : Color.secondary.opacity(0.04))
                    }
                    .buttonStyle(.plain)
                    .accessibilityHidden(true)
                    if idx < games.count - 1 { Divider() }
                }
            }
            .background(Color.secondary.opacity(0.04))
            .cornerRadius(8)
            .accessibilityHidden(true)
            .overlay(
                AccessibleDataTable(headers: headers, rows: rows)
                    .allowsHitTesting(false)
            )
            .padding(.horizontal)
        }
    }

    // -- Quick List mode --

    private func quickSection(title: String, games: [Game]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            sectionHeader(title)
            ForEach(games) { game in
                NavigationLink(destination: GameDetailView(game: game, sport: sport)) {
                    Text(quickText(game))
                        .font(.subheadline)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(quickAccessibilityText(game))
                .accessibilityHint("Opens match details")
            }
        }
    }

    // -- Full List mode --

    private func fullSection(title: String, games: [Game]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionHeader(title)
            ForEach(games) { game in
                NavigationLink(destination: GameDetailView(game: game, sport: sport)) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(fullHeadline(game))
                            .font(.headline)
                        Text(fullDetailText(game))
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.secondary.opacity(0.05))
                    .cornerRadius(8)
                    .padding(.horizontal, 12)
                }
                .buttonStyle(.plain)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(quickAccessibilityText(game))
                .accessibilityHint("Opens match details")
            }
        }
    }

    // MARK: - Row formatters

    /// Resolved side labels for a match. When the full bracket is loaded, ESPN's
    /// "Round of 32 N Winner" placeholders are replaced with the real teams that
    /// feed the match (capped so a reader never tracks more than four teams).
    private func labels(for game: Game) -> WorldCupBracket.SideLabels {
        let pref = appSettings.teamNamePreference
        if let bracket = viewModel.bracket {
            return bracket.inlineLabels(for: game, pref: pref)
        }
        return WorldCupBracket.SideLabels(
            awayVisual: game.awayTeam.abbreviation,
            homeVisual: game.homeTeam.abbreviation,
            awayVoice:  game.awayTeam.voiceOverName(for: pref),
            homeVoice:  game.homeTeam.voiceOverName(for: pref)
        )
    }

    private func scoreSuffix(_ score: Int?) -> String { score.map { " \($0)" } ?? "" }

    private func tableRow(_ game: Game) -> [String] {
        let l = labels(for: game)
        let away = l.awayVisual + scoreSuffix(game.awayTeam.score)
        let home = l.homeVisual + scoreSuffix(game.homeTeam.score)
        let status: String
        if game.status.isLive            { status = game.status.displayText }
        else if game.status.isPostponed  { status = "PPD" }
        else if game.status.isCancelled  { status = "Cxl" }
        else if game.status.isSuspended  { status = "Susp" }
        else if game.status.isCompleted  { status = "Final" }
        else                             { status = game.displayTime }
        return [away, home, status]
    }

    private func quickText(_ game: Game) -> String {
        let l = labels(for: game)
        let away = l.awayVisual + scoreSuffix(game.awayTeam.score)
        let home = l.homeVisual + scoreSuffix(game.homeTeam.score)
        let status = statusText(game, abbreviated: true)
        var line = "\(away) @ \(home) — \(status)"
        if let venue = game.venue, !venue.name.isEmpty { line += " · \(venue.fullName)" }
        return line
    }

    private func quickAccessibilityText(_ game: Game) -> String {
        let l = labels(for: game)
        let away = l.awayVoice + scoreSuffix(game.awayTeam.score)
        let home = l.homeVoice + scoreSuffix(game.homeTeam.score)
        var label = "\(away) at \(home), \(statusText(game, abbreviated: false))"
        // Venue: unlabeled (terse) but still spoken. Scheduled even before teams are known.
        if let venue = game.venue, !venue.name.isEmpty { label += ", \(venue.fullName)" }
        return label
    }

    /// Headline for the Full List card — uses the resolved, name-preference form.
    private func fullHeadline(_ game: Game) -> String {
        let l = labels(for: game)
        return "\(l.awayVoice) vs \(l.homeVoice)"
    }

    private func fullDetailText(_ game: Game) -> String {
        var parts: [String] = [statusText(game, abbreviated: false)]
        if let venue = game.venue?.fullName, !venue.isEmpty { parts.append(venue) }
        if game.shouldShowBroadcastInfo, let b = game.broadcasts.first, !b.isEmpty {
            parts.append("TV: \(b)")
        }
        return parts.joined(separator: " · ")
    }

    private func statusText(_ game: Game, abbreviated: Bool) -> String {
        if game.status.isLive           { return game.status.displayText }
        if game.status.isPostponed      { return abbreviated ? "PPD" : "Postponed" }
        if game.status.isCancelled      { return abbreviated ? "Cxl" : "Cancelled" }
        if game.status.isSuspended      { return abbreviated ? "Susp" : "Suspended" }
        if game.status.isCompleted      { return "Final" }
        return game.displayTime
    }

    // MARK: - Helpers

    private func sectionHeader(_ title: String) -> some View {
        Text(title)
            .font(.subheadline.bold())
            .foregroundColor(.secondary)
            .padding(.horizontal, 16)
            .padding(.bottom, 4)
            .accessibilityAddTraits(.isHeader)
    }

    private var emptyBracket: some View {
        VStack(spacing: 16) {
            Image(systemName: "bracket")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
                .accessibilityHidden(true)
            Text("Matches will appear here as the tournament progresses.")
                .font(.headline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
