//
//  GolfScheduleView.swift
//  SportsScores
//
//  Full-season tournament schedule list for a golf tour.
//  Grouped by month, shows past/current/upcoming tournaments.
//  Tapping a row navigates to that tournament in GolfLeagueView.
//

import SwiftUI

struct GolfScheduleView: View {

    let calendar: [GolfCalendarEntry]
    let selectedIndex: Int?
    let onSelect: (Int) -> Void
    @State private var viewMode: ViewMode = .savedDefault()

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

    // MARK: - Table view mode

    private var tournamentTableView: some View {
        let headers = ["Tournament", "Dates", "Status"]
        let rows = calendar.map { tournamentTableRowData($0) }
        return ScrollView {
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
                AccessibleDataTable(headers: headers, rows: rows)
                    .allowsHitTesting(false)
            )
            .padding(.horizontal)
            .padding(.vertical, 8)
        }
    }

    private func tournamentStatusText(_ entry: GolfCalendarEntry) -> String {
        let isActive = entry.startDate <= Date() && entry.endDate >= Date()
        let isPast = entry.endDate < Date()
        return isActive ? "Active" : (isPast ? "Past" : "Upcoming")
    }

    private func tournamentTableRowData(_ entry: GolfCalendarEntry) -> [String] {
        [entry.name, entry.dateRangeText, tournamentStatusText(entry)]
    }

    // MARK: - Quick List view mode

    private var tournamentQuickListView: some View {
        ScrollView {
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
        "\(entry.name) — \(entry.dateRangeText) [\(tournamentStatusText(entry))]"
    }

    // MARK: - Full List view mode

    private var tournamentFullListView: some View {
        List {
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
        let isPast     = entry.endDate < Date()
        let isActive   = entry.startDate <= Date() && entry.endDate >= Date()

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
        .accessibilityLabel(accessibilityLabel(entry: entry, isPast: isPast, isActive: isActive, isSelected: isSelected))
        .accessibilityHint("Double tap to view leaderboard")
    }

    private func dotColor(isPast: Bool, isActive: Bool) -> Color {
        if isActive { return .red }
        if isPast   { return Color.secondary.opacity(0.4) }
        return Color.secondary.opacity(0.2)
    }

    private func accessibilityLabel(entry: GolfCalendarEntry, isPast: Bool, isActive: Bool, isSelected: Bool) -> String {
        let status = isActive ? "In progress" : (isPast ? "Completed" : "Upcoming")
        let selected = isSelected ? ", currently selected" : ""
        return "\(entry.name), \(entry.dateRangeText), \(status)\(selected)"
    }
}
