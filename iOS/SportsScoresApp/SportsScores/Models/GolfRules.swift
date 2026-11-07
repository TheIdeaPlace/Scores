//
//  GolfRules.swift
//  SportsScores
//
//  The rules both apps follow on ESPN's golf scoreboard: which event to show, what state an
//  event is in, and who won a finished one. The twin of golf.py in the Windows app; both
//  are held to tests/fixtures/golf_grid.json (GolfGridTests.swift here, test_golf_grid.py
//  there). Change both together.
//

import Foundation

/// A finished event's winner, as the schedule shows it.
struct GolfWinner: Equatable {
    let name: String
    let score: String

    /// "Chris Gotterup (-16)", or just the name when there's no score.
    var text: String { score.isEmpty ? name : "\(name) (\(score))" }
}

enum GolfRules {

    private static func nonBlank(_ text: String?) -> String? {
        guard let trimmed = text?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty else { return nil }
        return trimmed
    }

    /// "pre", "in" or "post", or "" when ESPN doesn't say. The event's own status comes
    /// first: between rounds ESPN calls the event in progress while its competition says
    /// play is complete for the day, and the tournament is still on. The competition's
    /// status is the fallback for an event that has none of its own.
    static func state(of event: GolfEventAPIResponse) -> String {
        nonBlank(event.status?.type?.state)
            ?? nonBlank(event.competitions.first?.status?.type?.state)
            ?? ""
    }

    /// The event to show from a scoreboard's events, or nil if there are none: the one
    /// asked for by id when it's there (a past week can list two events), else the first
    /// in progress, else the first.
    static func pickEvent(_ events: [GolfEventAPIResponse], id wanted: String? = nil) -> GolfEventAPIResponse? {
        if let wanted = nonBlank(wanted),
           let match = events.first(where: { nonBlank($0.id) == wanted }) {
            return match
        }
        return events.first(where: { state(of: $0) == "in" }) ?? events.first
    }

    /// By ESPN's `order`: one with no order goes last, and ties keep ESPN's listed order.
    static func byOrder(_ competitors: [GolfCompetitorAPIResponse]) -> [GolfCompetitorAPIResponse] {
        competitors.enumerated().sorted { a, b in
            switch (a.element.order, b.element.order) {
            case let (x?, y?) where x != y: return x < y
            case (.some, nil): return true
            case (nil, .some): return false
            default: return a.offset < b.offset
            }
        }.map(\.element)
    }

    /// A golfer's name, or a team's in a team event (the Zurich Classic, the Presidents Cup).
    static func competitorName(_ competitor: GolfCompetitorAPIResponse) -> String {
        nonBlank(competitor.athlete?.displayName)
            ?? nonBlank(competitor.athlete?.fullName)
            ?? nonBlank(competitor.team?.displayName)
            ?? nonBlank(competitor.team?.name)
            ?? ""
    }

    /// A finished event's winner, or nil. Only a finished event has one, and only if it has
    /// a field: a cancelled event is finished with nobody in it. The competitor ESPN marks
    /// `winner` comes first (the team cups do); else the lowest `order`, which is 1 for the
    /// winner of a playoff too. The score is ESPN's as it is ("-16"; a cup's points, "17").
    static func winner(of event: GolfEventAPIResponse) -> GolfWinner? {
        guard state(of: event) == "post" else { return nil }
        let ranked = byOrder(event.competitions.first?.competitors ?? [])
        guard let top = ranked.first(where: { $0.winner == true }) ?? ranked.first else { return nil }
        let name = competitorName(top)
        guard !name.isEmpty else { return nil }
        return GolfWinner(name: name, score: nonBlank(top.score) ?? "")
    }
}
