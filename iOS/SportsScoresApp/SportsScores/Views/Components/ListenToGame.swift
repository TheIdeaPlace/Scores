//
//  ListenToGame.swift
//  SportsScores
//
//  "Listen to the Game": a VoiceOver action and a context menu item on a game, and a
//  list of places for a game or team screen. Each place opens in Safari, or in its
//  own app when that app claims the link; the person signs in there if asked.
//

import SwiftUI

/// Adds "Listen to the Game" to a row: a VoiceOver custom action that offers the places
/// to listen, and the same places in the row's context menu. Adds nothing when there
/// is nowhere to listen.
struct ListenToGameModifier: ViewModifier {
    let title: String
    let options: [ListenOption]
    @State private var choosing = false
    @Environment(\.openURL) private var openURL

    func body(content: Content) -> some View {
        if options.isEmpty {
            content
        } else {
            content
                .accessibilityAction(named: "Listen to the Game") { listen() }
                .contextMenu {
                    Menu {
                        ForEach(options) { option in
                            Button(option.label) { openURL(option.url) }
                        }
                    } label: {
                        Label("Listen to the Game", systemImage: "radio")
                    }
                }
                .confirmationDialog(title, isPresented: $choosing, titleVisibility: .visible) {
                    ForEach(options) { option in
                        Button(option.label) { openURL(option.url) }
                    }
                    Button("Cancel", role: .cancel) {}
                }
        }
    }

    private func listen() {
        if options.count == 1, let only = options.first {
            openURL(only.url)
        } else {
            choosing = true
        }
    }
}

extension View {
    func listenToGame(_ game: Game, sport: Sport) -> some View {
        modifier(ListenToGameModifier(
            title: "Listen to \(game.awayTeam.displayName) \(game.matchupWord) \(game.homeTeam.displayName)",
            options: game.listenOptions(league: sport.rawValue)))
    }
}

/// The places to listen, as a list section of links, for a game or team screen.
struct ListenSection: View {
    let header: String
    let options: [ListenOption]
    var footer: String = "Opens in Safari or the service's app. Sign in there if it asks."

    var body: some View {
        if !options.isEmpty {
            Section {
                ForEach(options) { option in
                    Link(destination: option.url) {
                        Label(option.label, systemImage: "radio")
                    }
                    .accessibilityHint("Opens outside the app")
                }
            } header: {
                Text(header)
            } footer: {
                Text(footer)
            }
        }
    }
}
