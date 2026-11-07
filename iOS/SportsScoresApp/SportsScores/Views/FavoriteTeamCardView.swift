//
//  FavoriteTeamCardView.swift
//  SportsScores
//
//  A card in the Favorites section of Team Hub. Each piece of information is a
//  separate VoiceOver element so users can navigate between them individually:
//    1. Team name — heading + button (pushes to TeamHubDetailView)
//    2. Live or next game — navigates to GameDetailView
//    3. First news headline — opens article in Safari sheet
//    4. Second news headline — opens article in Safari sheet
//

import SwiftUI

struct FavoriteTeamCardView: View {

    let favorite: FavoriteTeam
    let schedule: [ScheduleGame]
    let news: [NewsItem]          // up to 2 items
    /// Full game details from the ESPN summary endpoint for any live game.
    /// Used for accurate live scores (header), inning/status detail, and the
    /// in-play situation (pitcher, batter, bases, count, outs via rosters lookup).
    let liveGameDetails: GameDetails?
    /// Called when the user activates the "Remove from Favorites" VoiceOver action.
    var onRemove: (() -> Void)? = nil
    /// Reorder callbacks — nil when the operation is not available (e.g., already at top).
    var onMoveUp: (() -> Void)? = nil
    var onMoveDown: (() -> Void)? = nil
    var onMoveToTop: (() -> Void)? = nil
    var onMoveToBottom: (() -> Void)? = nil

    @State private var showArticle1 = false
    @State private var showArticle2 = false

    // MARK: - Date formatter

    private static let gameDateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateStyle = .short
        f.timeStyle = .short
        return f
    }()

    // MARK: - Derived game data

    /// Live, last and next, by the rule Windows shares (FavoriteCardGames).
    private var cardGames: FavoriteCardGames {
        FavoriteCardGames(schedule: schedule, now: Date())
    }

    private var liveGame: ScheduleGame? { cardGames.live }

    private var lastGame: ScheduleGame? { cardGames.last }

    private var nextGame: ScheduleGame? { cardGames.next }

    private func gameLabel(for game: ScheduleGame, prefix: String) -> String {
        let isHome = game.homeTeam.id == favorite.id
        let opp = FavoriteCardGames.opponent(in: game, forTeamId: favorite.id)
        let loc = FavoriteCardGames.location(of: game, forTeamId: favorite.id)
        if game.isInProgress {
            // Build a scoreboard-style label: "Away name score @ Home name score, Status detail, Situation"
            // Uses live details from the summary endpoint for accurate scores, status, and
            // in-play situation (pitcher, batter, bases, count, outs).
            if let comp = liveGameDetails?.header?.competitions.first {
                let awayComp = comp.competitors.first(where: { $0.homeAway == "away" })
                let homeComp = comp.competitors.first(where: { $0.homeAway == "home" })
                let awayName = game.awayTeam.displayName
                let homeName = game.homeTeam.displayName
                let awaySc = awayComp?.score.map { " \($0)" } ?? ""
                let homeSc = homeComp?.score.map { " \($0)" } ?? ""
                var label = "\(prefix): \(awayName)\(awaySc) @ \(homeName)\(homeSc)"
                if let detail = comp.status?.type?.detail, !detail.isEmpty {
                    label += ", \(detail)"
                }
                if let sit = liveGameDetails?.situation,
                   let lookup = liveGameDetails.map({ $0.playerLookup }),
                   let situationText = sit.situationText(playerLookup: lookup),
                   !situationText.isEmpty {
                    label += ", \(situationText)"
                }
                return label
            }
            // Header not loaded yet — show what we have without a false 0-0.
            let myScore = isHome ? game.homeTeam.score : game.awayTeam.score
            let oppScore = isHome ? game.awayTeam.score : game.homeTeam.score
            if let my = myScore, let op = oppScore {
                return "\(prefix): \(loc) \(opp.abbreviation) \(my)-\(op)"
            }
            return "\(prefix): \(loc) \(opp.abbreviation)"
        }
        if game.isCompleted {
            return FavoriteCardGames.resultLine(for: game, teamId: favorite.id, prefix: prefix)
        }
        let gameLabel = game.label.map { ", \($0)" } ?? ""
        return "\(prefix): \(loc) \(opp.abbreviation), \((game.timeIsKnown ? Self.gameDateFormatter.string(from: game.date) : DateFormatter.localizedString(from: game.date, dateStyle: .short, timeStyle: .none)))\(gameLabel)"
    }

    // MARK: - Body

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {

            // 1. Team name — heading + button
            NavigationLink(destination: TeamHubDetailView(team: favorite.asTransactionTeam, sport: favorite.sport)) {
                HStack(spacing: 12) {
                    logoView
                    Text(favorite.displayName)
                        .font(.headline)
                        .foregroundColor(.primary)
                    Spacer()
                    Text(favorite.sport.displayName)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            .accessibilityLabel("\(favorite.displayName), \(favorite.sport.displayName)")
            .accessibilityAddTraits(.isButton)
            .accessibilityAction(named: "Remove from Favorites") { onRemove?() }
            .accessibilityActionIfPresent(named: "Move Up",         action: onMoveUp)
            .accessibilityActionIfPresent(named: "Move Down",       action: onMoveDown)
            .accessibilityActionIfPresent(named: "Move to Top",     action: onMoveToTop)
            .accessibilityActionIfPresent(named: "Move to Bottom",  action: onMoveToBottom)

            // 2. Live or last game — navigates to GameDetailView
            if let live = liveGame {
                NavigationLink(destination: GameDetailView(game: live.toGame(), sport: favorite.sport)) {
                    gameStatusView(label: gameLabel(for: live, prefix: "Live"), isLive: true)
                }
                .accessibilityLabel(gameLabel(for: live, prefix: "Live"))
                .accessibilityHint("Open game details.")
            } else if let last = lastGame {
                NavigationLink(destination: GameDetailView(game: last.toGame(), sport: favorite.sport)) {
                    gameStatusView(label: gameLabel(for: last, prefix: "Last"), isLive: false)
                }
                .accessibilityLabel(gameLabel(for: last, prefix: "Last"))
                .accessibilityHint("Open game details.")
            }

            // 3. Next game — navigates to GameDetailView
            if let next = nextGame {
                NavigationLink(destination: GameDetailView(game: next.toGame(), sport: favorite.sport)) {
                    gameStatusView(label: gameLabel(for: next, prefix: "Next"), isLive: false)
                }
                .accessibilityLabel(gameLabel(for: next, prefix: "Next"))
                .accessibilityHint("Open game details.")
            }

            // 4. First news headline — opens article in Safari
            if !news.isEmpty {
                if let url = news[0].articleURL {
                    Button { showArticle1 = true } label: {
                        Text(news[0].headline)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .lineLimit(2)
                            .padding(.leading, 48)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(news[0].headline)
                    .accessibilityHint("Double tap to open article.")
                    .sheet(isPresented: $showArticle1) {
                        SafariView(url: url).ignoresSafeArea()
                    }
                } else {
                    Text(news[0].headline)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                        .padding(.leading, 48)
                }
            }

            // 5. Second news headline — opens article in Safari
            if news.count > 1 {
                if let url = news[1].articleURL {
                    Button { showArticle2 = true } label: {
                        Text(news[1].headline)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .lineLimit(2)
                            .padding(.leading, 48)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(news[1].headline)
                    .accessibilityHint("Double tap to open article.")
                    .sheet(isPresented: $showArticle2) {
                        SafariView(url: url).ignoresSafeArea()
                    }
                } else {
                    Text(news[1].headline)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                        .padding(.leading, 48)
                }
            }
        }
        .padding(.vertical, 4)
        .contextMenu {
            if let action = onMoveUp {
                Button { action() } label: {
                    Label("Move Up", systemImage: "arrow.up")
                }
            }
            if let action = onMoveDown {
                Button { action() } label: {
                    Label("Move Down", systemImage: "arrow.down")
                }
            }
            if let action = onMoveToTop {
                Button { action() } label: {
                    Label("Move to Top", systemImage: "arrow.up.to.line")
                }
            }
            if let action = onMoveToBottom {
                Button { action() } label: {
                    Label("Move to Bottom", systemImage: "arrow.down.to.line")
                }
            }
        }
    }

    // MARK: - Sub-views

    private var logoView: some View {
        Group {
            if let url = favorite.logoURL {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let img):
                        img.resizable().scaledToFit()
                    default:
                        Image(systemName: "shield.fill")
                            .font(.title2)
                            .foregroundColor(.secondary)
                    }
                }
            } else {
                Image(systemName: "shield.fill")
                    .font(.title2)
                    .foregroundColor(.secondary)
            }
        }
        .frame(width: 36, height: 36)
        .accessibilityHidden(true)
    }

    private func gameStatusView(label: String, isLive: Bool) -> some View {
        HStack(spacing: 4) {
            if isLive {
                Circle()
                    .fill(Color.red)
                    .frame(width: 6, height: 6)
                    .accessibilityHidden(true)
            }
            Text(label)
                .font(.caption)
                .foregroundColor(isLive ? .red : .secondary)
        }
        .padding(.leading, 48)
    }
}

