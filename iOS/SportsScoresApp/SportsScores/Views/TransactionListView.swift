//
//  TransactionListView.swift
//  SportsScores
//
//  One running list of transactions, newest first and grouped by day, that loads older
//  ones as you scroll, with a month/year picker that starts the list at the end of any
//  month back to January 2001 and keeps going older from there.
//

import SwiftUI

struct TransactionListView: View {
    @StateObject private var viewModel: TransactionViewModel
    @State private var showingDatePicker = false
    @State private var pickerMonth: Int
    @State private var pickerYear: Int
    let hideTeamLabel: Bool

    init(sport: Sport, team: TransactionTeam?, hideTeamLabel: Bool = false) {
        _viewModel = StateObject(wrappedValue: TransactionViewModel(sport: sport, team: team))
        let today = TransactionViewModel.today()
        _pickerMonth = State(initialValue: today.month)
        _pickerYear  = State(initialValue: today.year)
        self.hideTeamLabel = hideTeamLabel
    }

    var body: some View {
        VStack(spacing: 0) {
            positionBar

            Group {
                if viewModel.isLoading {
                    loadingView
                } else if let error = viewModel.errorMessage {
                    errorView(error)
                } else if let empty = viewModel.emptyMessage {
                    emptyView(empty)
                } else {
                    transactionList
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .navigationTitle(viewModel.listTitle)
        .navigationBarTitleDisplayMode(.inline)
        .task { await viewModel.startIfNeeded() }
        .sheet(isPresented: $showingDatePicker) {
            datePickerSheet
        }
    }

    // MARK: - Where the list starts

    private var positionBar: some View {
        HStack {
            Button {
                let today = TransactionViewModel.today()
                pickerMonth = viewModel.jump?.month ?? today.month
                pickerYear  = viewModel.jump?.year ?? today.year
                showingDatePicker = true
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "calendar")
                        .font(.subheadline)
                    Text("Jump to Month")
                        .font(.subheadline.weight(.semibold))
                }
            }
            .accessibilityLabel("Jump to month")
            .accessibilityValue(viewModel.positionLabel)
            .accessibilityHint("Starts the list at the end of a month and keeps going older from there.")

            Spacer()

            Text(viewModel.positionLabel)
                .font(.subheadline)
                .foregroundColor(.secondary)
                .accessibilityHidden(true)  // the button's value says it

            if viewModel.jump != nil {
                Button("Newest") {
                    Task { await viewModel.start() }
                }
                .font(.subheadline.weight(.semibold))
                .padding(.leading, 8)
                .accessibilityLabel("Back to the newest")
            }
        }
        .padding(.vertical, 10)
        .padding(.horizontal)
        .background(Color(.systemGroupedBackground))
    }

    // MARK: - Transaction list

    private var transactionList: some View {
        List {
            ForEach(viewModel.sections) { section in
                if let title = section.title {
                    Section(title) { rows(section) }
                } else {
                    Section { rows(section) }
                }
            }
            Section { footer }
        }
        .listStyle(.insetGrouped)
    }

    @ViewBuilder
    private func rows(_ section: TransactionViewModel.DaySection) -> some View {
        ForEach(section.entries) { entry in
            Group {
                switch entry {
                case .item(let item, _):
                    transactionRow(item)
                case .notice(let notice):
                    Text(notice.text)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .onAppear {
                // Reaching the end of the list loads older ones.
                if entry.id == viewModel.lastEntryID {
                    Task { await viewModel.loadMore() }
                }
            }
        }
    }

    /// Under the list: loading, a failure to try again, a button for older ones (it loads
    /// them as it appears, too), or the end.
    @ViewBuilder
    private var footer: some View {
        if viewModel.isLoadingMore {
            HStack {
                Spacer()
                ProgressView("Loading older transactions…")
                Spacer()
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Loading older transactions")
        } else if let error = viewModel.loadMoreError {
            VStack(alignment: .leading, spacing: 8) {
                Text(error)
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Button("Try Again") {
                    Task { await viewModel.loadMore() }
                }
            }
        } else if viewModel.hasMore {
            Button("Load Older Transactions") {
                Task { await viewModel.loadMore() }
            }
            .onAppear {
                Task { await viewModel.loadMore() }
            }
        } else if !viewModel.entries.isEmpty {
            Text(viewModel.endText)
                .font(.subheadline)
                .foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: - Transaction row

    @ViewBuilder
    private func transactionRow(_ item: TransactionItem) -> some View {
        let showTeam = !hideTeamLabel && !item.team.abbreviation.isEmpty
        HStack(alignment: .top, spacing: 10) {
            // Team abbreviation badge — hidden when viewing a single team
            if showTeam {
                Text(item.team.abbreviation)
                    .font(.caption.weight(.bold))
                    .foregroundColor(.white)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 3)
                    .background(colorFromHex(item.team.color))
                    .cornerRadius(4)
                    .fixedSize()
            }

            Text(item.description)
                .font(.body)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(showTeam ? "\(item.team.displayName): \(item.description)" : item.description)
    }

    // MARK: - State views

    private var loadingView: some View {
        VStack {
            Spacer()
            ProgressView("Loading transactions…")
            Spacer()
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Loading transactions")
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 12) {
            Spacer()
            Image(systemName: "exclamationmark.triangle")
                .font(.largeTitle)
                .foregroundColor(.secondary)
                .accessibilityHidden(true)
            Text(message)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding()
            Button("Try Again") {
                Task { await viewModel.start(at: viewModel.jump) }
            }
            Spacer()
        }
    }

    private func emptyView(_ message: String) -> some View {
        VStack(spacing: 12) {
            Spacer()
            Text(message)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding()
            if viewModel.isLoadingMore {
                ProgressView("Looking further back…")
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("Looking further back")
            } else if let error = viewModel.loadMoreError {
                Text(error)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                Button("Try Again") {
                    Task { await viewModel.loadMore() }
                }
            } else if viewModel.hasMore {
                Button("Look Further Back") {
                    Task { await viewModel.loadMore() }
                }
            }
            Spacer()
        }
    }

    // MARK: - Month/Year picker sheet

    private var datePickerSheet: some View {
        NavigationStack {
            Form {
                Picker("Month", selection: $pickerMonth) {
                    ForEach(1...12, id: \.self) { month in
                        Text(TransactionPaging.monthNames[month - 1]).tag(month)
                    }
                }

                Picker("Year", selection: $pickerYear) {
                    ForEach(Array(stride(from: TransactionViewModel.today().year,
                                         through: TransactionPaging.earliestYear, by: -1)), id: \.self) { year in
                        Text(String(year)).tag(year)
                    }
                }

                Section {
                    Text("Shows that month's transactions, newest first, then older ones. This month, or a later one, goes back to the newest.")
                        .font(.footnote)
                        .foregroundColor(.secondary)
                }
            }
            .navigationTitle("Jump to Month")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Go") {
                        showingDatePicker = false
                        Task { await viewModel.start(at: (pickerYear, pickerMonth)) }
                    }
                }
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { showingDatePicker = false }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    // MARK: - Helpers

    private func colorFromHex(_ hex: String?) -> Color {
        guard let hex = hex, hex.count == 6,
              let value = UInt64(hex, radix: 16) else {
            return Color.secondary
        }
        let r = Double((value >> 16) & 0xFF) / 255
        let g = Double((value >> 8)  & 0xFF) / 255
        let b = Double( value        & 0xFF) / 255
        return Color(red: r, green: g, blue: b)
    }
}

#Preview {
    NavigationStack { TransactionListView(sport: .mlb, team: nil) }
}
