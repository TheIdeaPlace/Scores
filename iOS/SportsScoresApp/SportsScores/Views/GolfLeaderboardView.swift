//
//  GolfLeaderboardView.swift
//  SportsScores
//
//  Three-view accessible leaderboard for golf tournaments.
//  Mirrors the StandingsTableView pattern: visual grid hidden from VoiceOver,
//  AccessibleDataTable UIKit overlay provides proper row/column navigation.
//
//  View modes:
//    • Table   — grid: Pos | Player | Score | R1 | R2 | R3 | R4
//    • Quick List — compact: "1. Cameron Young (USA)  -12  67 / 69 / 68 / 71"
//    • Full List  — player cards with all round detail
//

import SwiftUI

struct GolfLeaderboardView: View {

    let tournament: GolfTournament
    @State private var viewMode: ViewMode = .savedDefault()

    // MARK: - Column definitions

    private let headers = ["Pos", "Player", "Today", "Thru", "Score", "R1", "R2", "R3", "R4", "Tot"]

    private func rowData(for competitor: GolfCompetitor) -> [String] {
        [
            competitor.positionDisplay,
            competitor.shortName,
            competitor.currentRoundDisplayScore,
            competitor.thruDisplay(tournamentInProgress: tournament.isInProgress),
            competitor.overallScore,
            competitor.roundScore(for: 1),
            competitor.roundScore(for: 2),
            competitor.roundScore(for: 3),
            competitor.roundScore(for: 4),
            competitor.totalStrokesDisplay
        ]
    }

    /// Full names for the AccessibleDataTable overlay (VoiceOver reads full name as row header).
    private func accessibleRowData(for competitor: GolfCompetitor) -> [String] {
        var cols = rowData(for: competitor)
        if cols.count > 1 { cols[1] = competitor.playerName }
        return cols
    }

    var body: some View {
        VStack(spacing: 0) {

            // Status banner
            if !tournament.isScheduled {
                tournamentStatusBanner
            }

            ScrollView {
                switch viewMode {
                case .table:
                    leaderboardTable
                case .quickList:
                    quickListContent
                case .fullList:
                    fullListContent
                }
            }
        }
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                ViewModeMenuButton(currentMode: $viewMode)
            }
        }
    }

    // MARK: - Status Banner

    private var tournamentStatusBanner: some View {
        VStack(spacing: 2) {
            HStack {
                if tournament.isInProgress {
                    Circle()
                        .fill(Color.red)
                        .frame(width: 8, height: 8)
                }
                Text(tournament.roundStatusText)
                    .font(.caption.bold())
                    .foregroundColor(tournament.isInProgress ? .red : .secondary)
                Spacer()
                if !tournament.broadcastText.isEmpty {
                    Text(tournament.broadcastText)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 6)
        .background(Color.secondary.opacity(0.07))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(tournament.roundStatusText)\(tournament.broadcastText.isEmpty ? "" : ". Broadcast: \(tournament.broadcastText)")")
    }

    // MARK: - Empty / Scheduled state

    private var scheduledPlaceholder: some View {
        VStack(spacing: 16) {
            Image(systemName: "calendar.badge.clock")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
            Text("Leaderboard Not Yet Available")
                .font(.headline)
                .foregroundColor(.secondary)
            Text("The field has not been announced yet.\nCheck back closer to the tournament start date.")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(.top, 48)
        .padding(.horizontal, 24)
    }

    // MARK: - Table mode

    private var leaderboardTable: some View {
        Group {
            if tournament.competitors.isEmpty {
                scheduledPlaceholder
            } else {
                tableGrid
            }
        }
    }

    private var tableGrid: some View {
        VStack(spacing: 0) {
            // Header row
            HStack(spacing: 0) {
                Text("Pos").font(.caption.bold()).frame(width: 28)
                Text("Player").font(.caption.bold()).frame(maxWidth: .infinity, alignment: .leading).padding(.leading, 8)
                Text("Today").font(.caption.bold()).frame(width: 36)
                Text("Thru").font(.caption.bold()).frame(width: 30)
                Text("Score").font(.caption.bold()).frame(width: 38)
                ForEach(1...4, id: \.self) { round in
                    Text("R\(round)").font(.caption.bold()).frame(width: 28)
                }
                Text("Tot").font(.caption.bold()).frame(width: 36)
            }
            .padding(.vertical, 6)
            .padding(.horizontal, 8)
            .background(Color.secondary.opacity(0.15))

            Divider()

            let activeCompetitors = tournament.competitors.filter(\.isActive)
            let cutCompetitors    = tournament.competitors.filter { $0.isCut || $0.isWithdrawn }

            VStack(spacing: 0) {
                ForEach(Array(activeCompetitors.enumerated()), id: \.element.id) { idx, comp in
                    competitorRow(comp, at: idx)
                    if idx < activeCompetitors.count - 1 {
                        Divider().padding(.leading, 8)
                    }
                }

                if !cutCompetitors.isEmpty {
                    // Cut / WD divider
                    HStack {
                        Divider()
                        Text("– CUT / WD –")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 8)
                        Divider()
                    }
                    .padding(.vertical, 4)
                    .accessibilityLabel("Cut line")

                    ForEach(Array(cutCompetitors.enumerated()), id: \.element.id) { idx, comp in
                        competitorRow(comp, at: activeCompetitors.count + idx)
                        if idx < cutCompetitors.count - 1 {
                            Divider().padding(.leading, 8)
                        }
                    }
                }
            }
            .accessibilityHidden(true) // UIKit overlay handles VoiceOver
        }
        .accessibilityHidden(true)
        .overlay(
            AccessibleDataTable(
                headers: headers,
                rows: tournament.competitors.map { accessibleRowData(for: $0) }
            )
            .allowsHitTesting(false)
        )
        .padding(.bottom, 16)
    }

    private func competitorRow(_ comp: GolfCompetitor, at idx: Int) -> some View {
        HStack(spacing: 0) {
            // Position
            Text(comp.positionDisplay)
                .font(.caption.monospacedDigit())
                .frame(width: 28)
                .foregroundColor(positionColor(comp.position))

            // Player name
            Text(comp.shortName)
                .font(.subheadline)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.leading, 8)
                .lineLimit(1)
                .foregroundColor(comp.isActive ? .primary : .secondary)

            // Today (current round score to par)
            Text(comp.currentRoundDisplayScore)
                .font(.caption.monospacedDigit().bold())
                .frame(width: 36)
                .foregroundColor(scoreColor(comp.currentRoundDisplayScore))

            // Thru (holes completed in current round)
            Text(comp.thruDisplay(tournamentInProgress: tournament.isInProgress))
                .font(.caption.monospacedDigit())
                .frame(width: 30)
                .foregroundColor(.secondary)

            // Overall score to par
            Text(comp.overallScore)
                .font(.subheadline.monospacedDigit().bold())
                .frame(width: 38)
                .foregroundColor(scoreColor(comp.overallScore))

            // Round stroke totals
            ForEach(1...4, id: \.self) { round in
                Text(comp.roundScore(for: round))
                    .font(.caption.monospacedDigit())
                    .frame(width: 28)
                    .foregroundColor(.secondary)
            }

            // Overall stroke total (completed rounds only)
            Text(comp.totalStrokesDisplay)
                .font(.caption.monospacedDigit())
                .frame(width: 36)
                .foregroundColor(.secondary)
        }
        .padding(.vertical, 7)
        .padding(.horizontal, 8)
        .background(idx % 2 == 0 ? Color.clear : Color.secondary.opacity(0.04))
    }

    // MARK: - Quick List mode

    private var quickListContent: some View {
        Group {
            if tournament.competitors.isEmpty {
                scheduledPlaceholder
            } else {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(tournament.competitors) { comp in
                        let values = rowData(for: comp).joined(separator: "  ")
                        Text(values)
                            .font(.subheadline.monospacedDigit())
                            .padding(.horizontal, 16)
                            .padding(.vertical, 6)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .accessibilityLabel(
                                zip(headers, accessibleRowData(for: comp))
                                    .map { "\($0): \($1)" }
                                    .joined(separator: ". ")
                            )
                    }
                }
                .padding(.vertical, 8)
            }
        }
    }

    // MARK: - Full List mode

    private var fullListContent: some View {
        Group {
            if tournament.competitors.isEmpty {
                scheduledPlaceholder
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(tournament.competitors) { comp in
                        let pairs = Array(zip(headers, rowData(for: comp)))
                        VStack(alignment: .leading, spacing: 3) {
                            ForEach(pairs, id: \.0) { header, value in
                                HStack(spacing: 6) {
                                    Text("\(header):")
                                        .font(.caption.bold())
                                        .foregroundColor(.secondary)
                                        .frame(width: 44, alignment: .leading)
                                    Text(value)
                                        .font(.subheadline.monospacedDigit())
                                }
                            }
                        }
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.secondary.opacity(0.05))
                        .cornerRadius(8)
                        .padding(.horizontal, 12)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(
                            zip(headers, accessibleRowData(for: comp))
                                .map { "\($0): \($1)" }
                                .joined(separator: ". ")
                        )
                    }
                }
                .padding(.vertical, 8)
            }
        }
    }

    // MARK: - Color helpers

    private func positionColor(_ position: Int) -> Color {
        switch position {
        case 1:  return .yellow
        case 2, 3: return Color(red: 0.75, green: 0.75, blue: 0.75)
        default: return .secondary
        }
    }

    private func scoreColor(_ score: String) -> Color {
        if score.hasPrefix("-") { return .red }
        if score.hasPrefix("+") { return .blue }
        if score == "E"         { return .primary }
        return .secondary
    }
}
