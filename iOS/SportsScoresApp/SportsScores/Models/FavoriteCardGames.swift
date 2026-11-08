//
//  FavoriteCardGames.swift
//  SportsScores
//
//  Which of a favorite team's games its card shows: the game being played or else the last
//  one finished, then the next one to play. Apart from the view so it can be tested.
//
//  Windows has the same rule in favorite_card.py. Both are held to
//  tests/fixtures/favorite_card_grid.json: which game is live, last and next, and the line
//  the last game reads as. Change both in the same commit.
//

import Foundation

struct FavoriteCardGames {
    let live: ScheduleGame?
    let last: ScheduleGame?
    let next: ScheduleGame?

    /// `schedule` in date order, as ESPNAPIService.fetchFavoriteCardSchedule gives it. A game
    /// called off is none of the three, whatever its date says.
    init(schedule: [ScheduleGame], now: Date) {
        live = schedule.first(where: { $0.isInProgress })
        last = schedule.last(where: { $0.isCompleted })
        next = schedule.nextToPlay(after: now)
    }

    /// "vs" at home or at a neutral site, "@" away.
    static func location(of game: ScheduleGame, forTeamId teamId: String) -> String {
        game.homeTeam.id == teamId || game.isNeutralSite ? "vs" : "@"
    }

    /// The other team.
    static func opponent(in game: ScheduleGame, forTeamId teamId: String) -> ScheduleGame.ScheduleTeam {
        game.homeTeam.id == teamId ? game.awayTeam : game.homeTeam
    }

    /// "Last: W vs LAD 2-1, Doubleheader - Game 2". This team's score comes first.
    static func resultLine(for game: ScheduleGame, teamId: String, prefix: String = "Last") -> String {
        let isHome = game.homeTeam.id == teamId
        let my = (isHome ? game.homeTeam.score : game.awayTeam.score) ?? 0
        let op = (isHome ? game.awayTeam.score : game.homeTeam.score) ?? 0
        let result = my > op ? "W" : my < op ? "L" : "T"
        let label = game.label.map { ", \($0)" } ?? ""
        return "\(prefix): \(result) \(location(of: game, forTeamId: teamId)) "
            + "\(opponent(in: game, forTeamId: teamId).abbreviation) \(my)-\(op)\(label)"
    }
}
