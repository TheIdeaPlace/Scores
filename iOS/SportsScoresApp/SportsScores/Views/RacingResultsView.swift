//
//  RacingResultsView.swift
//  SportsScores
//
//  Displays the current or most recent race for a series.
//  Supports three view modes (Quick List / Full List / Table) for the driver order list.
//
//  States:
//   - Scheduled: race info card, and the entry list (no positions) once ESPN has one
//   - In Progress / Final: driver finishing / running order in the selected view mode
//   - No event: off-season placeholder
//

import SwiftUI

struct RacingResultsView: View {
    let series: Sport
    let raceEvent: RaceEvent?
    let isLoading: Bool
    let viewMode: ViewMode

    // Table column definitions. An entry list, before the race, has no positions to show.
    private func tableHeaders(_ event: RaceEvent) -> [String] {
        event.kind == "Entry List" ? ["Driver", "Nat"] : ["Pos", "Driver", "Nat"]
    }
    private func tableRow(_ c: RaceCompetitor, kind: String) -> [String] {
        if kind == "Entry List" {
            return [c.driverName, c.nationality]
        }
        // A driver ESPN gives no order mid-race still gets a cell under Pos, as on Windows.
        return [c.position.map(String.init) ?? "-", c.driverName, c.nationality]
    }

    var body: some View {
        if isLoading && raceEvent == nil {
            ProgressView("Loading…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let event = raceEvent {
            raceContent(event)
        } else {
            emptyState
        }
    }

    // MARK: - Main content

    @ViewBuilder
    private func raceContent(_ event: RaceEvent) -> some View {
        ScrollView {
            VStack(spacing: 0) {
                raceHeaderCard(event)

                if !event.competitors.isEmpty {
                    switch viewMode {
                    case .table:     tableContent(event)
                    case .quickList: listContent(event, fullLabels: false)
                    case .fullList:  listContent(event, fullLabels: true)
                    }
                }
            }
        }
    }

    // MARK: - Race header card (same across all modes)

    private func raceHeaderCard(_ event: RaceEvent) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top) {
                Text(event.name)
                    .font(.headline)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer()
                if event.isInProgress {
                    Text("LIVE")
                        .font(.caption.bold())
                        .foregroundColor(.white)
                        .padding(.horizontal, 7).padding(.vertical, 3)
                        .background(Color.red, in: Capsule())
                        .accessibilityHidden(true)
                } else if event.isCompleted {
                    Text("FINAL")
                        .font(.caption.bold())
                        .foregroundColor(.secondary)
                        .accessibilityHidden(true)
                } else if event.isCanceled {
                    Text(event.statusDescription.uppercased())
                        .font(.caption.bold())
                        .foregroundColor(.secondary)
                        .accessibilityHidden(true)
                }
            }
            HStack(spacing: 16) {
                Label(
                    event.date.formatted(date: .abbreviated,
                                         time: event.isScheduled ? .shortened : .omitted),
                    systemImage: "calendar"
                )
                .font(.subheadline).foregroundColor(.secondary)
                if !event.broadcastText.isEmpty {
                    Label(event.broadcastText, systemImage: "tv")
                        .font(.subheadline).foregroundColor(.secondary)
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(headerAccessibilityLabel(event))
    }

    // MARK: - Table mode

    private func tableContent(_ event: RaceEvent) -> some View {
        VStack(spacing: 0) {
            // Section heading
            Text(event.kind)
                .font(.caption.bold())
                .foregroundColor(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 16)
                .padding(.top, 12)
                .padding(.bottom, 4)
                .accessibilityAddTraits(.isHeader)

            // Column header row
            HStack(spacing: 0) {
                if event.kind != "Entry List" {
                    Text("Pos")
                        .frame(width: 36, alignment: .trailing)
                }
                Text("Driver")
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.leading, 12)
                Text("Nat")
                    .frame(width: 44, alignment: .trailing)
            }
            .font(.caption.bold())
            .foregroundColor(.secondary)
            .padding(.vertical, 6)
            .padding(.horizontal, 16)
            .background(Color.secondary.opacity(0.10))

            Divider()

            // Data rows — hidden from VoiceOver; UIKit overlay handles navigation
            VStack(spacing: 0) {
                ForEach(Array(event.competitors.enumerated()), id: \.element.id) { idx, comp in
                    tableRow(comp, isWinner: event.isCompleted && comp.position == 1,
                             isEntryList: event.kind == "Entry List", idx: idx)
                    if idx < event.competitors.count - 1 {
                        Divider().padding(.leading, 16)
                    }
                }
            }
            .accessibilityHidden(true)
            .overlay(
                AccessibleDataTable(
                    headers: tableHeaders(event),
                    rows: event.competitors.map { tableRow($0, kind: event.kind) }
                )
                .allowsHitTesting(false)
            )
        }
    }

    private func tableRow(_ comp: RaceCompetitor, isWinner: Bool, isEntryList: Bool, idx: Int) -> some View {
        HStack(spacing: 0) {
            if !isEntryList {
                Text(comp.position.map(String.init) ?? "-")
                    .font(.system(.body, design: .monospaced).bold())
                    .foregroundColor(podiumColor(comp.position ?? 0))
                    .frame(width: 36, alignment: .trailing)
            }

            HStack(spacing: 4) {
                if isWinner {
                    Image(systemName: "trophy.fill")
                        .font(.caption).foregroundColor(.yellow)
                }
                Text(comp.driverName)
                    .font(.body)
                    .lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.leading, 12)

            Text(comp.nationality)
                .font(.caption)
                .foregroundColor(.secondary)
                .frame(width: 44, alignment: .trailing)
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 16)
        .background(idx % 2 == 0 ? Color.clear : Color.secondary.opacity(0.04))
    }

    // MARK: - Quick List / Full List (visually identical; only VoiceOver label differs)

    private func listContent(_ event: RaceEvent, fullLabels: Bool) -> some View {
        VStack(spacing: 0) {
            Text(event.kind)
                .font(.caption.bold())
                .foregroundColor(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 16)
                .padding(.top, 12)
                .padding(.bottom, 4)
                .accessibilityAddTraits(.isHeader)

            VStack(spacing: 0) {
                ForEach(event.competitors) { comp in
                    competitorListRow(
                        comp,
                        isWinner: event.isCompleted && comp.position == 1,
                        isEntryList: event.kind == "Entry List",
                        fullLabels: fullLabels
                    )
                    Divider().padding(.leading, 16)
                }
            }
        }
    }

    private func competitorListRow(_ comp: RaceCompetitor, isWinner: Bool, isEntryList: Bool,
                                   fullLabels: Bool) -> some View {
        HStack(spacing: 12) {
            if !isEntryList {
                Text(comp.position.map(String.init) ?? "-")
                    .font(.system(.subheadline, design: .monospaced).bold())
                    .foregroundColor(podiumColor(comp.position ?? 0))
                    .frame(width: 28, alignment: .trailing)
            }

            if isWinner {
                Image(systemName: "trophy.fill")
                    .font(.caption).foregroundColor(.yellow)
                    .frame(width: 16)
            } else {
                Color.clear.frame(width: 16, height: 1)
            }

            Text(comp.driverName)
                .font(.subheadline)
                .lineLimit(1)

            if !comp.nationality.isEmpty {
                Text(comp.nationality)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }

            Spacer()
        }
        .padding(.vertical, 9)
        .padding(.horizontal, 16)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(fullLabels
            ? fullListLabel(comp)
            : quickListLabel(comp))
    }

    // MARK: - Accessibility labels

    private func quickListLabel(_ comp: RaceCompetitor) -> String {
        // Terse: "P1 — Max Verstappen", or the name alone in an entry list
        var label = comp.position.map { "P\($0) — \(comp.driverName)" } ?? comp.driverName
        if !comp.nationality.isEmpty { label += " · \(comp.nationality)" }
        return label
    }

    private func fullListLabel(_ comp: RaceCompetitor) -> String {
        // Verbose: "Position: 1, Driver: Max Verstappen, Nationality: Dutch"
        var parts = comp.position.map { ["Position: \($0)"] } ?? []
        parts.append("Driver: \(comp.driverName)")
        if !comp.nationality.isEmpty { parts.append("Nationality: \(comp.nationality)") }
        return parts.joined(separator: ", ")
    }

    private func headerAccessibilityLabel(_ event: RaceEvent) -> String {
        var parts = [event.name]
        if event.isInProgress      { parts.append("Live") }
        else if event.isCompleted  { parts.append("Final") }
        else if event.isCanceled   { parts.append(event.statusDescription) }
        else { parts.append(event.date.formatted(date: .long, time: .shortened)) }
        if !event.broadcastText.isEmpty { parts.append("on \(event.broadcastText)") }
        return parts.joined(separator: ". ")
    }

    // MARK: - Empty state

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "flag.checkered")
                .font(.system(size: 48)).foregroundColor(.secondary)
            Text("No Race Scheduled")
                .font(.headline).foregroundColor(.secondary)
            Text("Check back during the racing season.")
                .font(.subheadline).foregroundColor(.secondary)
                .multilineTextAlignment(.center).padding(.horizontal)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Helpers

    private func podiumColor(_ position: Int) -> Color {
        switch position {
        case 1: return .yellow
        case 2: return Color(white: 0.6)
        case 3: return Color(red: 0.72, green: 0.45, blue: 0.20)
        default: return .secondary
        }
    }
}
