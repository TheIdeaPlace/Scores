//
//  FantasyCheatsheetView.swift
//  SportsScores
//
//  NFL fantasy draft cheatsheet. A "good starting point" board backed by ESPN's
//  fantasy feed: players + team defenses ranked by ESPN's consensus rank, with
//  ADP, auction $ values, and season projections. Filterable by position, with a
//  taken/available toggle for live drafts and a scoring-format picker.
//
//  Three view modes (Quick List / Full List / Table) per DESIGN_PRINCIPLES.md.
//  Table mode uses AccessibleDataTable for VoiceOver row/column navigation.
//

import SwiftUI

struct FantasyCheatsheetView: View {
    @StateObject private var viewModel = FantasyCheatsheetViewModel()
    @State private var viewMode: ViewMode = .savedDefault()
    @State private var showingSettings = false
    @State private var selectedPlayer: CheatsheetPlayer?

    var body: some View {
        Group {
            if viewModel.isLoading {
                ProgressView("Loading draft board…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = viewModel.errorMessage {
                ErrorStateView(message: error) { Task { await viewModel.loadAll() } }
            } else {
                content
            }
        }
        .navigationTitle("Fantasy Cheatsheet")
        .navigationBarTitleDisplayMode(.inline)
        .searchable(text: $viewModel.searchQuery, prompt: "Search player or team")
        .task { if viewModel.players.isEmpty { await viewModel.loadAll() } }
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                teamMenu
            }
            ToolbarItemGroup(placement: .navigationBarTrailing) {
                optionsMenu
                Button {
                    showingSettings = true
                } label: {
                    Image(systemName: "slider.horizontal.3")
                }
                .accessibilityLabel("Cheatsheet settings")

                ViewModeMenuButton(currentMode: $viewMode)
            }
        }
        .sheet(isPresented: $showingSettings) {
            NavigationStack {
                ScoringSettingsView(viewModel: viewModel)
            }
        }
        .navigationDestination(item: $selectedPlayer) { player in
            CheatsheetPlayerDetailView(player: player, viewModel: viewModel)
        }
    }

    // MARK: - Options menu (sort + format)

    private var optionsMenu: some View {
        Menu {
            Picker("Sort by", selection: $viewModel.selectedSort) {
                ForEach(CheatsheetSort.allCases) { sort in
                    Text(sort.rawValue).tag(sort)
                }
            }
            Picker("Scoring format", selection: $viewModel.preset) {
                ForEach(ScoringPreset.allCases) { preset in
                    Text(preset.rawValue).tag(preset)
                }
            }
        } label: {
            Label("Sort and format", systemImage: "arrow.up.arrow.down")
        }
    }

    // MARK: - Team filter menu

    /// A popup team picker. Collapsed to a filter icon (with the team code when
    /// active) so the 32-team list stays hidden until the user opens it.
    private var teamMenu: some View {
        Menu {
            Picker("Team", selection: $viewModel.selectedTeam) {
                Text("All Teams").tag(String?.none)
                ForEach(viewModel.availableTeams, id: \.self) { team in
                    Text(team).tag(String?.some(team))
                }
            }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: viewModel.selectedTeam == nil
                      ? "line.3.horizontal.decrease.circle"
                      : "line.3.horizontal.decrease.circle.fill")
                if let team = viewModel.selectedTeam {
                    Text(team).font(.subheadline.bold())
                }
            }
        }
        .accessibilityLabel("Filter by team")
        .accessibilityValue(viewModel.selectedTeam ?? "All teams")
        .accessibilityHint("Shows only players from the chosen NFL team")
    }

    // MARK: - Content

    private var content: some View {
        VStack(spacing: 0) {
            positionFilterBar
            infoBanner
            Divider()
            if viewModel.displayedPlayers.isEmpty {
                emptyState
            } else {
                cheatsheetBody
            }
        }
    }

    // MARK: - Position filter chips

    private var positionFilterBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(FantasyPosition.allCases) { pos in
                    positionChip(pos)
                }
                Divider().frame(height: 18).padding(.horizontal, 4)
                Button {
                    viewModel.selectAllPositions()
                } label: {
                    Text("All")
                        .font(.caption.bold())
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Capsule().fill(Color.accentColor.opacity(0.12)))
                }
                .accessibilityLabel("Select all positions")
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
        }
    }

    private func positionChip(_ pos: FantasyPosition) -> some View {
        let selected = viewModel.selectedPositions.contains(pos)
        return Button {
            viewModel.togglePosition(pos)
        } label: {
            Text(pos.displayName)
                .font(.caption.bold())
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(
                    Capsule().fill(selected ? Color.accentColor.opacity(0.18) : Color.secondary.opacity(0.10))
                )
                .foregroundColor(selected ? .accentColor : .primary)
        }
        .accessibilityLabel("\(pos.displayName) filter")
        .accessibilityValue(selected ? "on" : "off")
    }

    // MARK: - Info banner

    private var infoBanner: some View {
        HStack {
            Image(systemName: "info.circle")
                .foregroundColor(.secondary)
                .accessibilityHidden(true)
            Text("\(String(viewModel.season)) rankings · \(viewModel.preset.rawValue) · ESPN ADP & projections")
                .font(.caption)
                .foregroundColor(.secondary)
            Spacer()
            Toggle("Hide taken", isOn: $viewModel.hideTaken)
                .toggleStyle(.switch)
                .labelsHidden()
                .accessibilityLabel("Hide drafted players")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 6)
    }

    // MARK: - Body (view-mode switch)

    @ViewBuilder
    private var cheatsheetBody: some View {
        switch viewMode {
        case .table:     tableView
        case .quickList: listView(fullLabels: false)
        case .fullList:  listView(fullLabels: true)
        }
    }

    // MARK: - List modes (Quick / Full)

    private func listView(fullLabels: Bool) -> some View {
        List {
            ForEach(viewModel.displayedPlayers) { player in
                // Marking taken is exposed to VoiceOver as a single explicit
                // rotor action. We intentionally do NOT use .swipeActions here:
                // on a row that is itself a button with its own accessibility
                // element, SwiftUI double-exposed the swipe action to VoiceOver
                // (two identical "Mark Taken" entries). One accessibilityAction is
                // unambiguous. Sighted quick-marking is available inside the
                // player detail screen.
                listRow(player, fullLabels: fullLabels)
                    .accessibilityAction(named: viewModel.isTaken(player) ? "Mark Available" : "Mark Taken") {
                        viewModel.toggleTaken(player)
                    }
            }
        }
        .listStyle(.plain)
    }

    private func listRow(_ player: CheatsheetPlayer, fullLabels: Bool) -> some View {
        Button {
            selectedPlayer = player
        } label: {
            HStack(spacing: 12) {
                Image(systemName: viewModel.isTaken(player) ? "checkmark.circle.fill" : "circle")
                    .foregroundColor(viewModel.isTaken(player) ? .green : .secondary)
                    .accessibilityHidden(true)

                Text(rankText(player))
                    .font(.system(.subheadline, design: .monospaced))
                    .foregroundColor(.secondary)
                    .frame(minWidth: 34, alignment: .trailing)
                    .accessibilityHidden(true)

                VStack(alignment: .leading, spacing: 2) {
                    Text(player.displayName)
                        .font(.subheadline.weight(.medium))
                        .strikethrough(viewModel.isTaken(player), color: .secondary)
                    HStack(spacing: 4) {
                        Text("\(player.position.displayName) · \(player.teamAbbreviation)")
                        if let injury = player.injuryStatus {
                            Text("· \(injury)").foregroundColor(.orange)
                        }
                    }
                    .font(.caption)
                    .foregroundColor(.secondary)
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 2) {
                    Text(player.projectedPointsString(for: viewModel.preset))
                        .font(.system(.subheadline, design: .monospaced).bold())
                        .foregroundColor(.accentColor)
                    Text("ADP \(player.adpString) · \(player.auctionString)")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                .accessibilityHidden(true)
            }
            .padding(.vertical, 4)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(listVoiceOverLabel(player, fullLabels: fullLabels))
    }

    /// Leading rank index for the current format ("—" when unranked).
    private func rankText(_ player: CheatsheetPlayer) -> String {
        guard let rank = player.rank(for: viewModel.preset) else { return "—" }
        return "#\(rank)"
    }

    private func listVoiceOverLabel(_ player: CheatsheetPlayer, fullLabels: Bool) -> String {
        let taken = viewModel.isTaken(player) ? ", taken" : ""
        let rank = player.rank(for: viewModel.preset).map(String.init) ?? "unranked"
        let name = player.displayName
        let pos = player.position.displayName
        let team = player.teamAbbreviation
        let proj = player.projectedPointsString(for: viewModel.preset)
        let adp = player.adpString
        let auction = player.auctionString
        let injury = player.injuryStatus.map { ", \($0)" } ?? ""

        if fullLabels {
            let adpPhrase = adp == "—" ? "no ADP" : "ADP \(adp)"
            let auctionPhrase = auction == "—" ? "no auction value" : "auction \(auction)"
            let projPhrase = proj == "—" ? "no projection" : "projected \(proj) points"
            return "Rank \(rank), Player: \(name), Position: \(pos), Team: \(team)\(injury), \(adpPhrase), \(auctionPhrase), \(projPhrase)\(taken)"
        } else {
            return "#\(rank) \(name) \(pos) \(team)\(injury) — \(proj) projected, ADP \(adp), \(auction)\(taken)"
        }
    }

    // MARK: - Table mode

    private var tableView: some View {
        let rows = viewModel.displayedPlayers
        let headers = ["Rank", "Player", "Pos", "Team", "ADP", "$", "Proj"]

        return ScrollView {
            VStack(spacing: 0) {
                HStack(spacing: 0) {
                    Text("Rank").frame(width: 46, alignment: .trailing)
                    Text("Player").frame(maxWidth: .infinity, alignment: .leading).padding(.leading, 10)
                    Text("Pos").frame(width: 40, alignment: .center)
                    Text("Tm").frame(width: 40, alignment: .leading)
                    Text("ADP").frame(width: 46, alignment: .trailing)
                    Text("$").frame(width: 40, alignment: .trailing)
                    Text("Proj").frame(width: 52, alignment: .trailing)
                }
                .font(.caption.bold())
                .foregroundColor(.secondary)
                .padding(.vertical, 6)
                .padding(.horizontal, 12)
                .background(Color.secondary.opacity(0.10))

                Divider()

                VStack(spacing: 0) {
                    ForEach(Array(rows.enumerated()), id: \.element.id) { idx, player in
                        Button {
                            selectedPlayer = player
                        } label: {
                            tableEntryRow(player)
                        }
                        .buttonStyle(.plain)
                        if idx < rows.count - 1 {
                            Divider().padding(.leading, 12)
                        }
                    }
                }
                .accessibilityHidden(true)
                .overlay(
                    AccessibleDataTable(
                        headers: headers,
                        rows: rows.map { p in
                            [rankText(p),
                             p.displayName,
                             p.position.displayName,
                             p.teamAbbreviation,
                             p.adpString,
                             p.auctionString,
                             p.projectedPointsString(for: viewModel.preset)]
                        }
                    )
                    .allowsHitTesting(false)
                )
            }
        }
    }

    private func tableEntryRow(_ player: CheatsheetPlayer) -> some View {
        HStack(spacing: 0) {
            Text(rankText(player))
                .font(.system(.body, design: .monospaced))
                .frame(width: 46, alignment: .trailing)

            Text(player.displayName)
                .font(.body)
                .lineLimit(1)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.leading, 10)
                .strikethrough(viewModel.isTaken(player), color: .secondary)

            Text(player.position.displayName)
                .font(.caption)
                .frame(width: 40, alignment: .center)
                .foregroundColor(.secondary)

            Text(player.teamAbbreviation)
                .font(.caption)
                .frame(width: 40, alignment: .leading)
                .foregroundColor(.secondary)

            Text(player.adpString)
                .font(.system(.caption, design: .monospaced))
                .frame(width: 46, alignment: .trailing)
                .foregroundColor(.secondary)

            Text(player.auctionString)
                .font(.system(.caption, design: .monospaced))
                .frame(width: 40, alignment: .trailing)
                .foregroundColor(.secondary)

            Text(player.projectedPointsString(for: viewModel.preset))
                .font(.system(.body, design: .monospaced).bold())
                .frame(width: 52, alignment: .trailing)
                .foregroundColor(.accentColor)
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 12)
        .accessibilityHidden(true)   // exposed via AccessibleDataTable overlay
    }

    // MARK: - Empty state

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "american.football")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
            Text("No players match the current filters")
                .font(.headline)
                .foregroundColor(.secondary)
            if viewModel.totalPlayerCount > 0 {
                Text("\(viewModel.totalPlayerCount) players loaded · \(viewModel.displayedCount) shown")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

#Preview {
    NavigationStack { FantasyCheatsheetView() }
}
