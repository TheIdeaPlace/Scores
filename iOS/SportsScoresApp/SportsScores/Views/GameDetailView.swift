//
//  GameDetailView.swift
//  SportsScores
//
//  Created on 1/4/26.
//

import SwiftUI
import Charts
import SafariServices

struct GameDetailView: View {
    let game: Game
    let sport: Sport
    @StateObject private var viewModel: GameDetailViewModel
    @State private var selectedSection = 0
    @State private var showZoneExplorer = false
    @State private var showFieldTour = false
    @EnvironmentObject private var appSettings: AppSettings

    init(game: Game, sport: Sport) {
        self.game = game
        self.sport = sport
        _viewModel = StateObject(wrappedValue: GameDetailViewModel(game: game, sport: sport))
    }

    // Audio engine shared across the plays view
    @StateObject private var pitchAudio = PitchAudioEngine()

    var body: some View {
        VStack(spacing: 0) {
            gameHeader
                .padding()
                .background(Color.secondary.opacity(0.1))

            Divider()

            if viewModel.isLoading {
                Spacer()
                ProgressView("Loading details...")
                Spacer()
            } else if let error = viewModel.errorMessage {
                Spacer()
                ErrorStateView(message: error) { Task { await viewModel.loadDetails() } }
                Spacer()
            } else if let details = viewModel.gameDetails {
                TabView(selection: $selectedSection) {
                    boxScoreTab(details: details).tag(0)
                    playsTab(details: details).tag(1)
                    gameInfoTab(details: details).tag(2)
                    if sport == .mlb {
                        moreTab(details: details).tag(3)
                    }
                }
                .tabViewStyle(.page(indexDisplayMode: .never))
            }

            if viewModel.gameDetails != nil {
                Divider()
                Picker("Section", selection: $selectedSection) {
                    Text("Box Score").tag(0)
                    Text(sport.isFootball ? "Drives" : "Plays").tag(1)
                    Text("Info").tag(2)
                    if sport == .mlb {
                        Text("More").tag(3)
                    }
                }
                .pickerStyle(.segmented)
                .padding()
            }
        }
        .navigationTitle("Game Details")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if game.status.isCompleted {
                ToolbarItem(placement: .navigationBarTrailing) {
                    ShareLink(item: gameSummaryText) {
                        Image(systemName: "square.and.arrow.up")
                    }
                    .accessibilityLabel("Share game summary")
                }
            }
        }
        .sheet(isPresented: $showZoneExplorer) {
            if let details = viewModel.gameDetails {
                NavigationStack {
                    PitchZoneExplorerView(plays: details.plays ?? [])
                        .navigationTitle("Zone Explorer")
                        .navigationBarTitleDisplayMode(.inline)
                        .toolbar {
                            ToolbarItem(placement: .confirmationAction) {
                                Button("Done") { showZoneExplorer = false }
                            }
                        }
                }
            }
        }
        .sheet(isPresented: $showFieldTour) {
            NavigationStack {
                BaseballFieldTourView(
                    preselectedStadium: StadiumGeometry.stadium(
                        venueContaining: game.venue?.name ?? ""
                    )
                )
                .navigationTitle("Field Tour")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Done") { showFieldTour = false }
                    }
                }
            }
        }
        .task { await viewModel.loadDetails() }
    }

    // MARK: - Game Header

    private var gameHeader: some View {
        VStack(spacing: 12) {
            if game.status.isLive {
                Label(game.status.displayText, systemImage: "circle.fill")
                    .foregroundColor(.red).font(.headline)
            } else if game.status.isPostponed {
                Text("Postponed").font(.headline).foregroundColor(.orange)
            } else if game.status.isCancelled {
                Text(game.status.detail.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Cancelled" : game.status.detail)
                    .font(.headline).foregroundColor(.orange)
            } else if game.status.isSuspended {
                Text(game.status.detail.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Suspended" : game.status.detail)
                    .font(.headline).foregroundColor(.orange)
            } else if game.status.isCompleted {
                Text("Final").font(.headline).foregroundColor(.secondary)
            } else {
                Text(game.displayTime).font(.headline).foregroundColor(.secondary)
            }
            HStack(spacing: 40) {
                teamColumn(game.awayTeam, isHome: false)
                Text("@").font(.title3).foregroundColor(.secondary)
                teamColumn(game.homeTeam, isHome: true)
            }

            // Venue information
            if let venue = game.venue {
                HStack(spacing: 4) {
                    Image(systemName: "mappin.circle")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text(venue.fullName)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                    // MLB-only: Field Tour button next to venue name
                    if sport == .mlb {
                        Button {
                            showFieldTour = true
                        } label: {
                            Image(systemName: "figure.walk")
                                .font(.caption)
                                .foregroundColor(.green)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Field tour for \(venue.fullName)")
                    }
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("Venue: \(venue.fullName)")
            }

            // Broadcast networks
            let activeBroadcasts = game.broadcasts.filter { !$0.isEmpty }
            if game.shouldShowBroadcastInfo && !activeBroadcasts.isEmpty {
                HStack(spacing: 4) {
                    Image(systemName: "tv")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text(activeBroadcasts.joined(separator: ", "))
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("TV: \(activeBroadcasts.joined(separator: ", "))")
            }

            // Odds (when available from summary API)
            if let odds = viewModel.gameDetails?.odds?.first {
                HStack(spacing: 12) {
                    if let spread = odds.details, !spread.isEmpty {
                        Text("Line: \(spread)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    if let ou = odds.overUnder {
                        Text("O/U: \(String(format: "%.1f", ou))")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel({
                    var parts: [String] = []
                    if let s = odds.details { parts.append("Line: \(s)") }
                    if let o = odds.overUnder { parts.append("Over/under: \(o)") }
                    return parts.joined(separator: ". ")
                }())
            }
        }
    }

    private func teamColumn(_ team: Game.Team, isHome: Bool) -> some View {
        // Prefer the live score from the summary header; fall back to the game object.
        // The game object may have nil/stale scores when navigated from schedule data.
        let displayScore: Int? = {
            if let comp = viewModel.gameDetails?.header?.competitions.first,
               let competitor = comp.competitors.first(where: { ($0.homeAway == "home") == isHome }) {
                return competitor.score
            }
            return team.score
        }()
        let hubTeam = TransactionTeam(
            id: team.id,
            location: nil,
            name: team.name,
            abbreviation: team.abbreviation,
            displayName: team.displayName,
            color: nil,
            logos: team.logo.flatMap { url in
                [TransactionTeamLogo(href: url, width: nil, height: nil, rel: ["default"])]
            }
        )
        return NavigationLink(destination: TeamHubDetailView(team: hubTeam, sport: sport, initialTab: .schedule)) {
            VStack {
                Text(team.abbreviation).font(.title2).fontWeight(.bold)
                if let score = displayScore {
                    Text("\(score)")
                        .font(.system(size: 48, weight: .bold, design: .rounded))
                        .monospacedDigit()
                }
                if let record = team.record {
                    Text("(\(record))").font(.caption).foregroundColor(.secondary)
                }
            }
            .foregroundColor(.primary)
        }
        .accessibilityLabel(teamAccessibilityLabel(team, isHome: isHome, score: displayScore))
        .accessibilityHint("Opens team hub")
    }

    private func teamAccessibilityLabel(_ team: Game.Team, isHome: Bool, score: Int?) -> String {
        let preferredName = team.voiceOverName(for: appSettings.teamNamePreference)
        if let score = score {
            return "\(preferredName), \(score)"
        }
        return preferredName
    }

    // MARK: - Box Score tab

    private func boxScoreTab(details: GameDetails) -> some View {
        Group {
            if let bs = details.boxscore {
                BoxScoreView(boxscore: bs, sport: sport)
            } else {
                Text("Box score not available")
                    .foregroundColor(.secondary).padding()
            }
        }
    }

    // MARK: - Plays / Drives tab

    @ViewBuilder
    private func playsTab(details: GameDetails) -> some View {
        // Football: prefer drives view; fall back to flat plays if no drives data.
        if sport.isFootball {
            let allDrives = details.drives?.all ?? []
            if !allDrives.isEmpty {
                NFLDrivesView(
                    drives: allDrives,
                    awayAbbr: game.awayTeam.abbreviation,
                    homeAbbr: game.homeTeam.abbreviation
                )
            } else {
                let plays = details.plays ?? []
                if plays.isEmpty {
                    Text("Drives not available")
                        .foregroundColor(.secondary).padding()
                } else {
                    GenericPlaysView(
                        plays: plays,
                        awayAbbr: game.awayTeam.abbreviation,
                        homeAbbr: game.homeTeam.abbreviation
                    )
                }
            }
        } else {
            let plays = details.plays ?? []
            if plays.isEmpty {
                Text("Play-by-play not available")
                    .foregroundColor(.secondary).padding()
            } else if sport == .mlb {
                VStack(spacing: 0) {
                    if plays.contains(where: { $0.isPitch }) {
                        HStack(spacing: 8) {
                            Spacer()
                            Button {
                                showZoneExplorer = true
                            } label: {
                                Label("Explore Zone", systemImage: "hand.tap")
                                    .font(.caption)
                            }
                            .buttonStyle(.bordered)
                            .tint(.green)
                        }
                        .padding(.horizontal)
                        .padding(.vertical, 4)
                        .background(Color.secondary.opacity(0.06))
                    }
                    MLBPlaysView(
                        plays: plays,
                        awayAbbr: game.awayTeam.abbreviation,
                        homeAbbr: game.homeTeam.abbreviation,
                        awayPreferredName: game.awayTeam.voiceOverName(for: appSettings.teamNamePreference),
                        homePreferredName: game.homeTeam.voiceOverName(for: appSettings.teamNamePreference),
                        audio: pitchAudio
                    )
                }
            } else {
                // Basketball and hockey plays carry court/rink coordinates, so
                // they get the audio actions; PlayAudioGeometry.supports gates
                // it, and every other sport falls through with sport nil.
                GenericPlaysView(
                    plays: plays,
                    awayAbbr: game.awayTeam.abbreviation,
                    homeAbbr: game.homeTeam.abbreviation,
                    sport: PlayAudioGeometry.supports(sport) ? sport : nil,
                    audio: PlayAudioGeometry.supports(sport) ? pitchAudio : nil
                )
            }
        }
    }

    // MARK: - Leaders tab

    // MARK: - Game Info tab (News + Leaders + Injuries + Officials)

    private func gameInfoTab(details: GameDetails) -> some View {
        ScrollView {
            VStack(spacing: 20) {
                // Game-specific news — shown first so it's easy to find
                if let articles = details.news?.articles, !articles.isEmpty {
                    gameNewsSection(articles: articles)
                }

                leadersSection(details: details)

                if let injuries = details.injuries, !injuries.isEmpty {
                    injuriesSection(injuries)
                }

                if let officials = details.gameInfo?.officials, !officials.isEmpty {
                    officialsSection(officials)
                }
            }
            .padding()
        }
    }

    // MARK: - Leaders section

    private func leadersSection(details: GameDetails) -> some View {
        let sections: [(String, [(String, String)])] = {
            guard let raw = details.leaders, !raw.isEmpty else { return [] }
            var result: [(String, [(String, String)])] = []

            for entry in raw {
                if let catName = entry.displayName ?? entry.name {
                    // Direct category (MLB/NFL/NHL)
                    let players: [(String, String)] = (entry.leaders ?? []).compactMap { pl in
                        guard let name = pl.athlete?.displayName, let val = pl.displayValue else { return nil }
                        return (name, val)
                    }
                    if !players.isEmpty { result.append((catName, players)) }
                } else {
                    // NBA: team-wrapper, inner leaders are categories
                    for inner in entry.leaders ?? [] {
                        let catName = inner.displayName ?? inner.name ?? "Leaders"
                        let players: [(String, String)] = (inner.leaders ?? []).compactMap { pl in
                            guard let name = pl.athlete?.displayName, let val = pl.displayValue else { return nil }
                            return (name, val)
                        }
                        if !players.isEmpty { result.append((catName, players)) }
                    }
                }
            }
            return result
        }()

        return Group {
            if !sections.isEmpty {
                sectionCard(title: "Leaders") {
                    ForEach(sections, id: \.0) { catName, players in
                        Text(catName)
                            .font(.subheadline.bold())
                            .foregroundColor(.secondary)
                            .padding(.top, 4)
                        ForEach(players, id: \.0) { playerName, value in
                            HStack {
                                Text(playerName)
                                    .font(.subheadline)
                                Spacer()
                                Text(value)
                                    .font(.subheadline.bold())
                            }
                            .padding(.vertical, 2)
                            .accessibilityElement(children: .ignore)
                            .accessibilityLabel("\(catName): \(playerName), \(value)")
                        }
                    }
                }
            }
        }
    }

    // MARK: - Injuries section

    private func injuriesSection(_ teams: [GameDetails.InjuryTeam]) -> some View {
        sectionCard(title: "Injuries") {
            ForEach(Array(teams.enumerated()), id: \.offset) { _, team in
                if let injuries = team.injuries, !injuries.isEmpty {
                    Text(team.team?.displayName ?? "")
                        .font(.subheadline.bold())
                        .foregroundColor(.secondary)
                        .padding(.top, 4)
                    ForEach(Array(injuries.enumerated()), id: \.offset) { _, injury in
                        HStack(spacing: 8) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(injury.athlete?.displayName ?? "")
                                    .font(.subheadline)
                                Text(injury.athlete?.position?.abbreviation ?? "")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            Spacer()
                            Text(injury.status ?? "")
                                .font(.caption.bold())
                                .padding(.horizontal, 7)
                                .padding(.vertical, 3)
                                .background(injuryColor(for: injury.status ?? "").opacity(0.15))
                                .foregroundColor(injuryColor(for: injury.status ?? ""))
                                .cornerRadius(6)
                        }
                        .padding(.vertical, 3)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(
                            "\(injury.athlete?.displayName ?? ""), \(injury.athlete?.position?.abbreviation ?? ""), status: \(injury.status ?? "")"
                        )
                    }
                }
            }
        }
    }

    private func injuryColor(for status: String) -> Color {
        switch status.lowercased() {
        case "out":  return .red
        case "questionable": return .orange
        case "doubtful": return .orange
        case "injured reserve", "ir": return .red
        default: return .secondary
        }
    }

    // MARK: - Officials section

    private func officialsSection(_ officials: [GameDetails.GameInfo.Official]) -> some View {
        sectionCard(title: "Officials") {
            ForEach(Array(officials.enumerated()), id: \.offset) { _, official in
                HStack {
                    Text(official.fullName ?? "")
                        .font(.subheadline)
                    Spacer()
                    Text(official.position?.displayName ?? "")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding(.vertical, 3)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("\(official.fullName ?? ""), \(official.position?.displayName ?? "")")
            }
        }
    }

    // MARK: - More tab (MLB KitchenSink: Win Probability + Season Series)

    private func moreTab(details: GameDetails) -> some View {
        ScrollView {
            VStack(spacing: 20) {
                // Win probability chart
                if let wp = details.winprobability, !wp.isEmpty {
                    winProbChart(
                        entries: wp,
                        awayAbbr: game.awayTeam.abbreviation,
                        homeAbbr: game.homeTeam.abbreviation
                    )
                }

                // Season series
                if let series = details.seasonseries, !series.isEmpty {
                    let sorted = series.sorted { $0.displayOrder < $1.displayOrder }
                    sectionCard(title: "Season Series") {
                        ForEach(Array(sorted.enumerated()), id: \.offset) { _, s in
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(s.title ?? "Series")
                                        .font(.subheadline.bold())
                                    if let summary = s.summary {
                                        Text(summary)
                                            .font(.caption)
                                            .foregroundColor(.secondary)
                                    }
                                }
                                Spacer()
                                if let total = s.totalCompetitions {
                                    Text("\(total) games")
                                        .font(.caption2)
                                        .foregroundColor(.secondary)
                                }
                            }
                            .padding(.vertical, 3)
                            .accessibilityElement(children: .ignore)
                            .accessibilityLabel("\(s.title ?? "Series"): \(s.summary ?? "")")
                        }
                    }
                }
            }
            .padding()
        }
    }

    @ViewBuilder
    private func winProbChart(entries: [GameDetails.WinProbEntry], awayAbbr: String, homeAbbr: String) -> some View {
        // Build (index, homeWinPct) data points
        let data = entries.enumerated().map { (i, e) in (i, e.homeWinPercentage) }

        sectionCard(title: "Win Probability — \(homeAbbr)") {
            Chart {
                // Away 50% reference line
                RuleMark(y: .value("50%", 0.5))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [4, 4]))
                    .foregroundStyle(.secondary.opacity(0.4))

                ForEach(data, id: \.0) { idx, pct in
                    LineMark(
                        x: .value("Play", idx),
                        y: .value("\(homeAbbr) Win %", pct)
                    )
                    .foregroundStyle(Color.accentColor)
                    .interpolationMethod(.catmullRom)
                }

                // Shade above 50% in home color, below 50% in away color
                ForEach(data, id: \.0) { idx, pct in
                    AreaMark(
                        x: .value("Play", idx),
                        yStart: .value("base", 0.5),
                        yEnd: .value("\(homeAbbr) Win %", pct)
                    )
                    .foregroundStyle(
                        pct >= 0.5
                            ? Color.accentColor.opacity(0.15)
                            : Color.secondary.opacity(0.12)
                    )
                    .interpolationMethod(.catmullRom)
                }
            }
            .chartYScale(domain: 0...1)
            .chartYAxis {
                AxisMarks(values: [0, 0.25, 0.5, 0.75, 1.0]) { val in
                    AxisGridLine()
                    AxisValueLabel {
                        if let d = val.as(Double.self) {
                            Text("\(Int(d * 100))%")
                                .font(.caption2)
                        }
                    }
                }
            }
            .chartXAxis(.hidden)
            .frame(height: 160)
            .accessibilityLabel(winProbAccessibilityLabel(entries: entries, homeAbbr: homeAbbr, awayAbbr: awayAbbr))
            .accessibilityHidden(false)
        }
    }

    private func winProbAccessibilityLabel(entries: [GameDetails.WinProbEntry], homeAbbr: String, awayAbbr: String) -> String {
        guard let last = entries.last else { return "Win probability chart" }
        let homePct = Int(last.homeWinPercentage * 100)
        let awayPct = 100 - homePct
        return "Win probability chart. Final: \(homeAbbr) \(homePct)%, \(awayAbbr) \(awayPct)%."
    }

    // MARK: - Game News section

    private func gameNewsSection(articles: [GameDetails.GameNewsContainer.GameArticle]) -> some View {
        sectionCard(title: "Related News") {
            ForEach(Array(articles.enumerated()), id: \.offset) { _, article in
                GameArticleRow(article: article)
                    .padding(.vertical, 3)
            }
        }
    }

    // MARK: - Shared card container

    private func sectionCard<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.headline)
                .accessibilityAddTraits(.isHeader)
            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(Color.secondary.opacity(0.07))
        .cornerRadius(12)
    }

    // MARK: - Share Summary

    private var gameSummaryText: String {
        var lines: [String] = []
        lines.append("\(game.awayTeam.displayName) @ \(game.homeTeam.displayName)")
        if let away = game.awayTeam.score, let home = game.homeTeam.score {
            lines.append("Final: \(game.awayTeam.abbreviation) \(away) – \(home) \(game.homeTeam.abbreviation)")
        }
        if let venue = game.venue {
            lines.append(venue.fullName)
        }
        if let odds = viewModel.gameDetails?.odds?.first {
            var parts: [String] = []
            if let s = odds.details { parts.append("Line: \(s)") }
            if let o = odds.overUnder { parts.append("O/U: \(String(format: "%.1f", o))") }
            if !parts.isEmpty { lines.append(parts.joined(separator: "  ")) }
        }
        // Top leaders
        if let raw = viewModel.gameDetails?.leaders, !raw.isEmpty {
            lines.append("")
            lines.append("Leaders:")
            for entry in raw.prefix(4) {
                if let catName = entry.displayName ?? entry.name,
                   let top = entry.leaders?.first,
                   let name = top.athlete?.displayName,
                   let val = top.displayValue {
                    lines.append("  \(catName): \(name) \(val)")
                }
            }
        }
        lines.append("")
        lines.append("via Sports Scores")
        lines.append("https://testflight.apple.com/join/128FeTqx")
        return lines.joined(separator: "\n")
    }
}

// MARK: - Game Article Row

struct GameArticleRow: View {
    let article: GameDetails.GameNewsContainer.GameArticle
    @State private var showSafari = false

    var body: some View {
        Button {
            if article.webURL != nil { showSafari = true }
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                Text(article.headline ?? "")
                    .font(.subheadline.bold())
                    .foregroundColor(.primary)
                    .multilineTextAlignment(.leading)
                    .lineLimit(3)
                if let desc = article.description, !desc.isEmpty {
                    Text(desc)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(article.headline ?? "")
        .accessibilityHint(article.webURL != nil ? "Double tap to open article." : "")
        .sheet(isPresented: $showSafari) {
            if let url = article.webURL {
                SafariView(url: url)
                    .ignoresSafeArea()
            }
        }
    }
}

#Preview {
    NavigationStack {
        GameDetailView(
            game: Game(
                id: "1",
                name: "Sample Game",
                shortName: "LAD @ SD",
                date: Date(),
                status: Game.GameStatus(state: "post", detail: "Final", period: nil, clock: nil, name: nil),
                homeTeam: Game.Team(id: "1", name: "Padres", abbreviation: "SD",
                                    displayName: "San Diego Padres", score: 5, record: "82-80", logo: nil),
                awayTeam: Game.Team(id: "2", name: "Dodgers", abbreviation: "LAD",
                                    displayName: "Los Angeles Dodgers", score: 3, record: "95-67", logo: nil),
                venue: nil, broadcasts: ["ESPN"], situation: nil, seasonType: 2
            ),
            sport: .mlb
        )
    }
}
