//
//  VenuesView.swift
//  SportsScores
//
//  A league's venues and their home teams, as Windows has them, and a venue's details on
//  selecting it. Everything the details show came with the list, so nothing waits on the
//  network there.
//

import SwiftUI
import UIKit

struct VenuesView: View {
    let sport: Sport
    @StateObject private var viewModel = VenuesViewModel()
    @State private var viewMode: ViewMode = .quickList
    @State private var viewModeInitialized = false
    /// The venue opened from a cell of Table View, which VoiceOver reaches through
    /// `AccessibleDataTable` rather than the row's link.
    @State private var openedFromTable: LeagueVenue?
    @EnvironmentObject private var appSettings: AppSettings

    var body: some View {
        // A view that stays put, so going from loading to an error isn't an appearance that
        // starts the task again.
        ZStack { content }
            // College football's list follows the coverage setting, which Settings can change
            // while this is on screen.
            .task(id: appSettings.ncaafCoverage) { await viewModel.fetchVenues(for: sport) }
            .refreshable { await viewModel.refresh(for: sport) }
            .toolbar {
                if !viewModel.venues.isEmpty {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        ViewModeMenuButton(currentMode: $viewMode)
                    }
                }
            }
            .navigationDestination(item: $openedFromTable) { venue in
                VenueDetailsView(venue: venue, sport: sport)
            }
            // Focus is still on the tab below, so nothing else would say it failed.
            .onChange(of: viewModel.errorMessage) { _, message in
                if let message { UIAccessibility.post(notification: .announcement, argument: message) }
            }
            .onChange(of: viewModel.refreshFailed) { _, failed in
                if failed { UIAccessibility.post(notification: .announcement, argument: Self.refreshFailedText) }
            }
            .onAppear {
                guard !viewModeInitialized else { return }
                viewMode = appSettings.defaultTableViewMode
                viewModeInitialized = true
            }
    }

    @ViewBuilder
    private var content: some View {
        if viewModel.isLoading {
            ProgressView("Loading venues…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let error = viewModel.errorMessage {
            ErrorStateView(message: error) {
                Task { await viewModel.retry(for: sport) }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if viewModel.venues.isEmpty {
            emptyState
        } else {
            VStack(spacing: 0) {
                if viewModel.refreshFailed {
                    refreshFailedNote
                }
                switch viewMode {
                case .table:
                    tableView
                case .quickList:
                    quickListView
                case .fullList:
                    fullListView
                }
            }
        }
    }

    private static let refreshFailedText = "Couldn't refresh the venues. These are the ones last loaded."

    /// Above the list rather than in place of it, so whoever is partway down keeps their place.
    private var refreshFailedNote: some View {
        HStack(spacing: 12) {
            Text(Self.refreshFailedText)
                .font(.caption)
                .foregroundColor(.secondary)
            Spacer()
            Button("Retry") {
                Task { await viewModel.refresh(for: sport) }
            }
            .font(.caption)
            .buttonStyle(.bordered)
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "building.2")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
                .accessibilityHidden(true)
            Text("No venue data available for \(sport.displayName).")
                .font(.headline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var countHeading: some View {
        let count = viewModel.venues.count
        return Text("\(sport.displayName) stadiums and venues, \(count) total")
            .font(.subheadline.bold())
            .foregroundColor(.secondary)
            .accessibilityAddTraits(.isHeader)
    }

    private func details(_ venue: LeagueVenue) -> VenueDetailsView {
        VenueDetailsView(venue: venue, sport: sport)
    }

    // MARK: - Table view mode

    private var tableView: some View {
        let venues = viewModel.venues
        return ScrollView {
            VStack(alignment: .leading, spacing: 6) {
                countHeading
                    .padding(.horizontal)
                tableGrid(venues)
                    .background(Color.secondary.opacity(0.04))
                    .cornerRadius(8)
                    .accessibilityHidden(true)
                    .overlay(
                        AccessibleDataTable(
                            headers: Self.tableHeaders,
                            rows: venues.map(\.tableRow),
                            onActivateRow: { index in
                                if venues.indices.contains(index) { openedFromTable = venues[index] }
                            },
                            activationHint: "Opens venue details"
                        )
                        .allowsHitTesting(false)
                    )
                    .padding(.horizontal)
            }
            .padding(.vertical, 8)
        }
    }

    private static let tableHeaders = ["Venue", "Location", "Type", "Home Teams"]

    private func tableGrid(_ venues: [LeagueVenue]) -> some View {
        VStack(spacing: 0) {
            HStack(spacing: 0) {
                ForEach(Self.tableHeaders, id: \.self) { header in
                    Text(header)
                        .font(.caption.bold())
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 6)
                        .background(Color.secondary.opacity(0.12))
                }
            }
            ForEach(Array(venues.enumerated()), id: \.element.id) { index, venue in
                tableGridRow(venue, shaded: index % 2 != 0)
                if index < venues.count - 1 { Divider() }
            }
        }
    }

    private func tableGridRow(_ venue: LeagueVenue, shaded: Bool) -> some View {
        NavigationLink(destination: details(venue)) {
            HStack(spacing: 0) {
                ForEach(Array(venue.tableRow.enumerated()), id: \.offset) { _, value in
                    Text(value)
                        .font(.caption)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                }
            }
            .background(shaded ? Color.secondary.opacity(0.04) : Color.clear)
        }
        .buttonStyle(.plain)
    }

    // MARK: - Quick List view mode

    private var quickListView: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 4) {
                countHeading
                ForEach(viewModel.venues) { venue in
                    NavigationLink(destination: details(venue)) {
                        Text(venue.summary)
                            .font(.subheadline)
                            .multilineTextAlignment(.leading)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(venue.quickAccessibilityLabel)
                    .accessibilityHint("Opens venue details")
                }
            }
            .padding()
        }
    }

    // MARK: - Full List view mode

    private var fullListView: some View {
        List {
            Section {
                ForEach(viewModel.venues) { venue in
                    NavigationLink(destination: details(venue)) {
                        VenueFullRow(venue: venue)
                    }
                    .accessibilityLabel(venue.fullAccessibilityLabel)
                    .accessibilityHint("Opens venue details")
                }
            } header: {
                countHeading
                    .textCase(nil)
            }
        }
        .listStyle(.insetGrouped)
    }
}

private struct VenueFullRow: View {
    let venue: LeagueVenue

    private var placeLine: String {
        [venue.location, venue.typeText].filter { !$0.isEmpty }.joined(separator: " · ")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(venue.name)
                .font(.headline)
            if !placeLine.isEmpty {
                Text(placeLine)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }
            Text(venue.homeTeams.map(\.name).joined(separator: ", "))
                .font(.subheadline)
        }
        .padding(.vertical, 2)
    }
}

// MARK: - A venue's details

struct VenueDetailsView: View {
    let venue: LeagueVenue
    let sport: Sport

    var body: some View {
        List {
            Text(venue.name)
                .font(.title2.bold())
                .accessibilityAddTraits(.isHeader)

            Section {
                if !venue.location.isEmpty {
                    Text("Location: \(venue.location)")
                }
                Text("League: \(sport.rawValue)")
            } header: {
                sectionHeading("Basic Information")
            }

            if let type = venue.typeDetailLine {
                Section {
                    Text(type)
                } header: {
                    sectionHeading("Stadium Characteristics")
                }
            }

            if !venue.homeTeams.isEmpty {
                Section {
                    ForEach(venue.homeTeams, id: \.id) { team in
                        Text(team.detailLine)
                    }
                } header: {
                    sectionHeading("Home Teams")
                }
            }

            Section {
                ForEach(venue.facts(in: sport), id: \.self) { fact in
                    Text(fact)
                }
            } header: {
                sectionHeading("Interesting Facts")
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle(venue.name)
        .navigationBarTitleDisplayMode(.inline)
    }

    private func sectionHeading(_ title: String) -> some View {
        Text(title)
            .textCase(nil)
            .accessibilityAddTraits(.isHeader)
    }
}
