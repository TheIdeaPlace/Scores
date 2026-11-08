//
//  ScoreboardDay.swift
//  SportsScores
//
//  Which day's scoreboard "today" means. Foundation only.
//

import Foundation

enum ScoreboardDay {
    /// Until 5 AM local it's still last night's scoreboard, which is what's on: a
    /// West Coast game runs well past midnight in the East, and ESPN files it under
    /// the day it started, so asking for the new date loses it. Same rule as
    /// `scoreboard_today` in game_labels.py.
    private static let rolloverHours = 5

    static func today(now: Date = Date()) -> Date {
        let earlier = now.addingTimeInterval(-Double(rolloverHours) * 3600)
        return Calendar.current.startOfDay(for: earlier)
    }

    static func isToday(_ date: Date, now: Date = Date()) -> Bool {
        Calendar.current.isDate(date, inSameDayAs: today(now: now))
    }

    static func isYesterday(_ date: Date, now: Date = Date()) -> Bool {
        isToday(Calendar.current.date(byAdding: .day, value: 1, to: date) ?? date, now: now)
    }

    /// Whether a game on this day's board belongs on the screen for `today`. The day
    /// runs on past midnight to the rollover, and a game being played always counts.
    static func belongsOnToday(_ game: Game, now: Date = Date()) -> Bool {
        game.status.isLive || startsOnToday(game.date, now: now)
    }

    /// Whether this starts on the board for `today`, whatever it says about itself. A game
    /// kept from before a league failed is judged by this alone: its "live" is only what it
    /// was the last time ESPN answered, perhaps last night.
    static func startsOnToday(_ date: Date, now: Date = Date()) -> Bool {
        let start = today(now: now)
        let end = (Calendar.current.date(byAdding: .day, value: 1, to: start) ?? start)
            .addingTimeInterval(Double(rolloverHours) * 3600)
        return date >= start && date < end
    }

    static func isTomorrow(_ date: Date, now: Date = Date()) -> Bool {
        isToday(Calendar.current.date(byAdding: .day, value: -1, to: date) ?? date, now: now)
    }

    /// Noon local on the date ESPN's UTC timestamp falls on. A game with
    /// `timeValid: false` has a placeholder time, so only its UTC date means
    /// anything, and converting it would land on the wrong day west of Greenwich.
    static func localNoon(onUTCDayOf date: Date, in localTimeZone: TimeZone = .current) -> Date {
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(secondsFromGMT: 0) ?? .current
        var day = utc.dateComponents([.year, .month, .day], from: date)
        day.hour = 12
        // Gregorian here too: the device's own calendar can be Buddhist or Hijri.
        var local = Calendar(identifier: .gregorian)
        local.timeZone = localTimeZone
        return local.date(from: day) ?? date
    }

    // MARK: - Today's scoreboard, for monitoring

    private static let eastern = TimeZone(identifier: "America/New_York") ?? .current

    private static func yearMonthDay(of date: Date, in timeZone: TimeZone) -> [Int] {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        let day = calendar.dateComponents([.year, .month, .day], from: date)
        return [day.year ?? 0, day.month ?? 0, day.day ?? 0]
    }

    /// The day whose scoreboard has this game, as year, month and day. ESPN files a game
    /// under its US Eastern date wherever you are, so a 7 PM Eastern kickoff is that day's
    /// even where it's already after midnight. A game whose time isn't set has `date` at
    /// noon local on its UTC date (`localNoon`), and that date is the true one. Same rule
    /// as `scoreboard_date` in game_labels.py.
    static func scoreboardDate(of date: Date, timeValid: Bool?,
                               localTimeZone: TimeZone = .current) -> [Int] {
        yearMonthDay(of: date, in: timeValid == false ? localTimeZone : eastern)
    }

    /// Whether a game is on the scoreboard Live Scores shows, `today`'s, which is last
    /// night's until 5 AM. Only those can be monitored. Same rule as
    /// `on_todays_scoreboard` in game_labels.py, held to tests/fixtures/scoreboard_date_grid.json.
    static func isOnTodaysScoreboard(_ date: Date, timeValid: Bool?, now: Date = Date(),
                                     localTimeZone: TimeZone = .current) -> Bool {
        let today = yearMonthDay(of: now.addingTimeInterval(-Double(rolloverHours) * 3600),
                                 in: localTimeZone)
        return scoreboardDate(of: date, timeValid: timeValid, localTimeZone: localTimeZone) == today
    }
}
