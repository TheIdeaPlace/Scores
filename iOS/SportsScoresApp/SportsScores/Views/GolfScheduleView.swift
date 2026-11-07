//
//  GolfScheduleView.swift
//  SportsScores
//
//  Full-season tournament schedule list for a golf tour.
//  Grouped by month, shows past/current/upcoming tournaments, and each finished
//  tournament's winner and score (from scoreboard?dates=YEAR, as on Windows).
//  Tapping a row navigates to that tournament in GolfLeagueView.
//

import SwiftUI

struct GolfScheduleView: View {

    let calendar: [GolfCalendarEntry]
    /// This season's events by id, with their state and each finished one's winner.
    var seasonEvents: [String: GolfSeasonEvent] = [:]
    /// The winners couldn't be loaded; the schedule shows without them and says so.
    var seasonFailed = false
    let selectedIndex: Int?
    let onSelect: (Int) -> Void
    @State private var viewMode: ViewMode = .quickList

    static let winnersUnavailable = "Winners aren't available right now. Pull down to try again."

    private var groupedByMonth: [(String, [(Int, GolfCalendarEntry)])] {
        let fmt = DateFormatter()
        fmt.dateFormat = "MMMM yyyy"
        var groups: [(String, [(Int, GolfCalendarEntry)])] = []
        var currentMonth = ""
        var currentGroup: [(Int, GolfCalendarEntry)] = []

        for (idx, entry) in calendar.enumerated() {
            let month = fmt.string(from: entry.startDate)
            if month != currentMonth {
                if !currentGroup.isEmpty {
                    groups.append((currentMonth, currentGroup))
                }
                currentMonth = month
                currentGroup = []
            }
            currentGroup.append((idx, entry))
        }
        if !currentGroup.isEmpty {
            groups.append((currentMonth, currentGroup))
        }
        return groups
    }

    var body: some View {
        if calendar.isEmpty {
            VStack(spacing: 16) {
                Image(systemName: "calendar")
                    .font(.system(size: 48))
                    .foregroundColor(.secondary)
                Text("Schedule Not Available")
                    .font(.headline)
                    .foregroundColor(.secondary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            VStack(spacing: 0) {
                switch viewMode {
                case .table:
                    tournamentTableView
                case .quickList:
                    tournamentQuickListView
                case .fullList:
                    tournamentFullListView
                }
            }
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    ViewModeMenuButton(currentMode: $viewMode)
                }
            }
        }
    }

    /// Says the winners are missing, above the schedule in every view mode.
    @ViewBuilder
    private var winnersNote: some View {
        if seasonFailed {
            Text(Self.winnersUnavailable)
                .font(.footnote)
                .foregroundColor(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 16)
                .padding(.vertical, 6)
        }
    }

    // MARK: - Status and winner

    private enum Status { case active, past, upcoming }

    /// ESPN's state for the event when the season has loaded, else judged from the dates.
    private func status(_ entry: GolfCalendarEntry) -> Status {
        switch seasonEvents[entry.id]?.state {
        case "in":   return .active
        case "post": return .past
        case "pre":  return .upcoming
        default:
            let now = Date()
            if entry.startDate <= now && entry.endDate >= now { return .active }
            return entry.endDate < now ? .past : .upcoming
        }
    }

    private func winner(_ entry: GolfCalendarEntry) -> GolfWinner? {
        seasonEvents[entry.id]?.winner
    }

    /// A finished event with no winner in ESPN's own word, such as "Canceled", as on Windows.
    private func finishedWithoutWinner(_ entry: GolfCalendarEntry) -> String? {
        guard let event = seasonEvents[entry.id], event.state == "post", event.winner == nil,
              !event.statusDescription.isEmpty else { return nil }
        return event.statusDescription
    }

    private func tournamentStatusText(_ entry: GolfCalendarEntry) -> String {
        if let word = finishedWithoutWinner(entry) { return word }
        switch status(entry) {
        case .active:   return "Active"
        case .past:     return "Past"
        case .upcoming: return "Upcoming"
        }
    }

    /// The Winner cell: never blank, so VoiceOver has something to say on it.
    private func winnerCellText(_ entry: GolfCalendarEntry) -> String {
        if let won = winner(entry) { return won.text }
        return status(entry) == .past ? "None" : "Not yet"
    }

    // MARK: - Table view mode

    private var tournamentTableView: some View {
        let headers = ["Tournament", "Dates", "Status", "Winner"]
        let rows = calendar.map { tournamentTableRowData($0) }
        return ScrollView {
            winnersNote
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
                ForEach(Array(calendar.enumerated()), id: \.element.id) { idx, entry in
                    Button { onSelect(idx) } label: {
                        HStack(spacing: 0) {
                            ForEach(Array(tournamentTableRowData(entry).enumerated()), id: \.offset) { colIdx, val in
                                Text(val)
                                    .font(colIdx == 0 ? .subheadline : .caption)
                                    .frame(maxWidth: .infinity, alignment: colIdx == 0 ? .leading : .center)
                                    .padding(.vertical, 8)
                                    .padding(.horizontal, colIdx == 0 ? 8 : 4)
                            }
                        }
                        .background(idx % 2 == 0 ? Color.clear : Color.secondary.opacity(0.04))
                    }
                    .buttonStyle(.plain)
                    .accessibilityHidden(true)
                    if idx < calendar.count - 1 { Divider() }
                }
            }
            .background(Color.secondary.opacity(0.04))
            .cornerRadius(8)
            .accessibilityHidden(true)
            .overlay(
                AccessibleDataTable(headers: headers, rows: rows,
                                    onActivateRow: { onSelect($0) },
                                    activationHint: "Double tap to view leaderboard")
                    .allowsHitTesting(false)
            )
            .padding(.horizontal)
            .padding(.vertical, 8)
        }
    }

    private func tournamentTableRowData(_ entry: GolfCalendarEntry) -> [String] {
        [entry.name, entry.dateRangeText, tournamentStatusText(entry), winnerCellText(entry)]
    }

    // MARK: - Quick List view mode

    private var tournamentQuickListView: some View {
        ScrollView {
            winnersNote
            LazyVStack(alignment: .leading, spacing: 2) {
                ForEach(Array(calendar.enumerated()), id: \.element.id) { idx, entry in
                    Button { onSelect(idx) } label: {
                        Text(tournamentQuickText(entry))
                            .font(.subheadline)
                            .padding(.horizontal, 16)
                            .padding(.vertical, 6)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(idx % 2 == 0 ? Color.clear : Color.secondary.opacity(0.04))
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(tournamentQuickText(entry))
                    .accessibilityHint("Double tap to view leaderboard")
                }
            }
            .padding(.vertical, 8)
        }
    }

    private func tournamentQuickText(_ entry: GolfCalendarEntry) -> String {
        var text = "\(entry.name) — \(entry.dateRangeText) [\(tournamentStatusText(entry))]"
        if let won = winner(entry) { text += " — Winner: \(won.text)" }
        return text
    }

    // MARK: - Full List view mode

    private var tournamentFullListView: some View {
        List {
            if seasonFailed {
                Section { winnersNote }
            }
            ForEach(groupedByMonth, id: \.0) { month, entries in
                Section(header: Text(month).accessibilityAddTraits(.isHeader)) {
                    ForEach(entries, id: \.0) { idx, entry in
                        tournamentRow(entry: entry, index: idx)
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
    }

    private func tournamentRow(entry: GolfCalendarEntry, index: Int) -> some View {
        let isSelected = selectedIndex == index
        let entryStatus = status(entry)
        let isPast      = entryStatus == .past
        let isActive    = entryStatus == .active
        let entryWinner = winner(entry)

        return Button {
            onSelect(index)
        } label: {
            HStack(spacing: 12) {
                // Status indicator dot
                Circle()
                    .fill(dotColor(isPast: isPast, isActive: isActive))
                    .frame(width: 8, height: 8)

                VStack(alignment: .leading, spacing: 2) {
                    Text(entry.name)
                        .font(.subheadline)
                        .foregroundColor(isPast ? .secondary : .primary)
                        .lineLimit(2)
                    Text(entry.dateRangeText)
                        .font(.caption)
                        .foregroundColor(.secondary)
                    if let entryWinner {
                        Text("Winner: \(entryWinner.text)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }

                Spacer()

                if isSelected {
                    Image(systemName: "checkmark")
                        .font(.caption.bold())
                        .foregroundColor(.accentColor)
                }
            }
            .padding(.vertical, 2)
        }
        .buttonStyle(.plain)
        .listRowBackground(isSelected ? Color.accentColor.opacity(0.08) : Color.clear)
        .accessibilityLabel(accessibilityLabel(entry: entry, isPast: isPast, isActive: isActive,
                                               isSelected: isSelected, winner: entryWinner))
        .accessibilityHint("Double tap to view leaderboard")
    }

    private func dotColor(isPast: Bool, isActive: Bool) -> Color {
        if isActive { return .red }
        if isPast   { return Color.secondary.opacity(0.4) }
        return Color.secondary.opacity(0.2)
    }

    private func accessibilityLabel(entry: GolfCalendarEntry, isPast: Bool, isActive: Bool,
                                    isSelected: Bool, winner: GolfWinner?) -> String {
        let status = finishedWithoutWinner(entry) ?? (isActive ? "In progress" : (isPast ? "Completed" : "Upcoming"))
        let won = winner.map { ", won by \($0.text)" } ?? ""
        let selected = isSelected ? ", currently selected" : ""
        return "\(entry.name), \(entry.dateRangeText), \(status)\(won)\(selected)"
    }
}
