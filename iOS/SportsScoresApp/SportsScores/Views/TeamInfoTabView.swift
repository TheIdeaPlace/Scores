//
//  TeamInfoTabView.swift
//  SportsScores
//
//  Info tab for Team Hub — high-level team overview card.
//

import SwiftUI

struct TeamInfoTabView: View {
    @ObservedObject var viewModel: TeamHubViewModel
    let team: TransactionTeam
    let sport: Sport

    private static let dateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .medium
        f.timeStyle = .short
        return f
    }()

    var body: some View {
        Group {
            if viewModel.isLoadingInfo {
                ProgressView("Loading…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = viewModel.errorInfo, viewModel.teamInfo == nil {
                errorState(message: error)
            } else {
                content
            }
        }
    }

    // MARK: - Main content

    private var content: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                teamHeaderCard
                    .padding(.bottom, 16)

                if let info = viewModel.teamInfo {
                    recordSection(info: info)
                    standingSection(info: info)
                }

                scheduleSection
                venueCoachSection
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 24)
        }
    }

    // MARK: - Team header card (logo + name + colors)

    private var teamHeaderCard: some View {
        let accentColor = viewModel.teamInfo?.color.flatMap { Color(hex: $0) } ?? Color.accentColor

        return ZStack(alignment: .bottomLeading) {
            RoundedRectangle(cornerRadius: 16)
                .fill(accentColor.opacity(0.15))

            HStack(spacing: 16) {
                if let logoURL = team.primaryLogoURL {
                    AsyncImage(url: logoURL) { phase in
                        switch phase {
                        case .success(let img):
                            img.resizable()
                                .scaledToFit()
                                .frame(width: 80, height: 80)
                        default:
                            Image(systemName: "shield.fill")
                                .font(.system(size: 56))
                                .foregroundColor(accentColor)
                                .frame(width: 80, height: 80)
                        }
                    }
                    .accessibilityHidden(true)
                } else {
                    Image(systemName: "shield.fill")
                        .font(.system(size: 56))
                        .foregroundColor(accentColor)
                        .frame(width: 80, height: 80)
                        .accessibilityHidden(true)
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text(team.displayName)
                        .font(.title2).bold()
                    Text(sport.displayName)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                    if let record = viewModel.teamInfo?.overallRecord {
                        Text(record)
                            .font(.headline)
                            .foregroundColor(accentColor)
                            .accessibilityLabel("Record: \(record)")
                    }
                }
                Spacer()
            }
            .padding(16)
        }
        .padding(.top, 8)
    }

    // MARK: - Record section

    private func recordSection(info: TeamHubTeamInfo) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionHeader("Record")

            HStack(spacing: 0) {
                recordCell(label: "Overall", value: info.overallRecord ?? "–")
                Divider().frame(height: 44).accessibilityHidden(true)
                recordCell(label: "Home", value: info.homeRecord ?? "–")
                Divider().frame(height: 44).accessibilityHidden(true)
                recordCell(label: "Away", value: info.awayRecord ?? "–")
            }
            .background(Color.secondary.opacity(0.05))
            .cornerRadius(10)
        }
        .padding(.bottom, 16)
    }

    private func recordCell(label: String, value: String) -> some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.title3).bold()
            Text(label)
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 10)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(label) record: \(value)")
    }

    // MARK: - Standing section

    private func standingSection(info: TeamHubTeamInfo) -> some View {
        Group {
            if let standing = info.standingSummary {
                VStack(alignment: .leading, spacing: 8) {
                    sectionHeader("Standing")
                    infoRow(icon: "list.number", label: "Position", value: standing)
                }
                .padding(.bottom, 16)
            }
        }
    }

    // MARK: - Schedule section (prev/next game)

    private var scheduleSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionHeader("Games")

            if viewModel.isLoadingSchedule {
                HStack {
                    ProgressView()
                    Text("Loading games…")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding(.vertical, 8)
            } else {
                if let prev = viewModel.previousGame {
                    previousGameRow(game: prev)
                }
                if let next = viewModel.upcomingGame {
                    upcomingGameRow(game: next)
                } else if let nextGame = viewModel.teamInfo?.nextGame {
                    // Fall back to next event from team info if schedule not loaded yet
                    nextGameFromInfoRow(nextGame: nextGame)
                }
                if viewModel.previousGame == nil && viewModel.upcomingGame == nil && !viewModel.isLoadingSchedule {
                    Text("No recent or upcoming games")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .padding(.vertical, 4)
                }
            }
        }
        .padding(.bottom, 16)
    }

    private func previousGameRow(game: ScheduleGame) -> some View {
        let outcome = game.outcome(forTeamId: viewModel.teamId)
        let color: Color = outcome == .win ? .green : (outcome == .loss ? .red : .secondary)
        let opponentTeam = opponentOf(game: game)
        let scoreText: String = {
            guard let hs = game.homeTeam.score, let as_ = game.awayTeam.score else { return game.statusText }
            return "\(game.awayTeam.abbreviation) \(as_) – \(hs) \(game.homeTeam.abbreviation)"
        }()
        let outcomeWord = outcome == .win ? "Win" : (outcome == .loss ? "Loss" : (outcome == .tie ? "Tie" : "Final"))
        let labelSuffix = game.label.map { ". \($0)" } ?? ""

        return HStack(spacing: 12) {
            Circle()
                .fill(color)
                .frame(width: 8, height: 8)
            VStack(alignment: .leading, spacing: 2) {
                Text("vs \(opponentTeam.abbreviation)")
                    .font(.subheadline).bold()
                Text(scoreText)
                    .font(.caption)
                    .foregroundColor(.secondary)
                if let label = game.label {
                    Text(label)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            Spacer()
            Text(outcome == .win ? "W" : (outcome == .loss ? "L" : (outcome == .tie ? "T" : "–")))
                .font(.caption).bold()
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(color.opacity(0.15))
                .cornerRadius(6)
                .foregroundColor(color)
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Previous game: \(scoreText). \(outcomeWord)\(labelSuffix)")
    }

    private func upcomingGameRow(game: ScheduleGame) -> some View {
        let opponentTeam = opponentOf(game: game)
        let isHome = game.homeTeam.id == viewModel.teamId
        let locationText = isHome || game.isNeutralSite ? "vs" : "@"
        let dateText = game.timeIsKnown ? Self.dateFormatter.string(from: game.date)
            : DateFormatter.localizedString(from: game.date, dateStyle: .medium, timeStyle: .none) + ", time TBD"

        return HStack(spacing: 12) {
            Image(systemName: "calendar.circle")
                .font(.subheadline)
                .foregroundColor(.accentColor)
            VStack(alignment: .leading, spacing: 2) {
                Text("\(locationText) \(opponentTeam.displayName)")
                    .font(.subheadline).bold()
                Text(dateText)
                    .font(.caption)
                    .foregroundColor(.secondary)
                if let label = game.label {
                    Text(label)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            Spacer()
            Text("Next")
                .font(.caption).bold()
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.accentColor.opacity(0.12))
                .cornerRadius(6)
                .foregroundColor(.accentColor)
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Next game: \(locationText) \(opponentTeam.displayName) on \(dateText)\(game.label.map { ". \($0)" } ?? "")")
    }

    private func nextGameFromInfoRow(nextGame: TeamHubNextGame) -> some View {
        let locationText = nextGame.isHome || nextGame.isNeutralSite ? "vs" : "@"
        let dateText = nextGame.timeIsKnown ? Self.dateFormatter.string(from: nextGame.date)
            : DateFormatter.localizedString(from: nextGame.date, dateStyle: .medium, timeStyle: .none) + ", time TBD"

        return HStack(spacing: 12) {
            Image(systemName: "calendar.circle")
                .font(.subheadline)
                .foregroundColor(.accentColor)
            VStack(alignment: .leading, spacing: 2) {
                Text("\(locationText) \(nextGame.opponentDisplayName)")
                    .font(.subheadline).bold()
                Text(dateText)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            Spacer()
            Text("Next")
                .font(.caption).bold()
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.accentColor.opacity(0.12))
                .cornerRadius(6)
                .foregroundColor(.accentColor)
        }
        .padding(.vertical, 4)
    }

    // MARK: - Venue & coach section

    private var venueCoachSection: some View {
        Group {
            let showVenue = viewModel.teamInfo?.venueName != nil
            let showCoach = (viewModel.teamInfo?.coachName ?? viewModel.coachName) != nil
            if showVenue || showCoach {
                VStack(alignment: .leading, spacing: 8) {
                    sectionHeader("Details")
                    if let venue = viewModel.teamInfo?.venueName {
                        let city = viewModel.teamInfo?.venueCity
                        let venueLabel = city.map { "\(venue), \($0)" } ?? venue
                        infoRow(icon: "mappin.and.ellipse", label: "Venue", value: venueLabel)
                    }
                    let coach = viewModel.teamInfo?.coachName ?? viewModel.coachName
                    if let coach = coach {
                        infoRow(icon: "person.fill", label: "Manager / Coach", value: coach)
                    }
                }
            }
        }
    }

    // MARK: - Reusable helpers

    private func sectionHeader(_ title: String) -> some View {
        Text(title.uppercased())
            .font(.caption)
            .fontWeight(.semibold)
            .foregroundColor(.secondary)
            .padding(.top, 4)
            .accessibilityAddTraits(.isHeader)
    }

    private func infoRow(icon: String, label: String, value: String) -> some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.subheadline)
                .foregroundColor(.accentColor)
                .frame(width: 24)
            VStack(alignment: .leading, spacing: 1) {
                Text(label)
                    .font(.caption)
                    .foregroundColor(.secondary)
                Text(value)
                    .font(.subheadline)
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(label): \(value)")
    }

    // MARK: - Helpers

    private func opponentOf(game: ScheduleGame) -> ScheduleGame.ScheduleTeam {
        game.homeTeam.id == viewModel.teamId ? game.awayTeam : game.homeTeam
    }

    // MARK: - Error state

    private func errorState(message: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 40))
                .foregroundColor(.secondary)
            Text(message)
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
            Button("Retry") { Task { await viewModel.loadInfo() } }
                .buttonStyle(.borderedProminent)
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Color hex extension

private extension Color {
    init?(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        guard Scanner(string: hex).scanHexInt64(&int) else { return nil }
        let r, g, b: Double
        switch hex.count {
        case 6:
            r = Double((int >> 16) & 0xFF) / 255
            g = Double((int >> 8)  & 0xFF) / 255
            b = Double(int         & 0xFF) / 255
        default:
            return nil
        }
        self.init(red: r, green: g, blue: b)
    }
}
