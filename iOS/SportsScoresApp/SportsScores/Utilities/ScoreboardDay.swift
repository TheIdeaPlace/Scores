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

    static func isTomorrow(_ date: Date, now: Date = Date()) -> Bool {
        isToday(Calendar.current.date(byAdding: .day, value: -1, to: date) ?? date, now: now)
    }

    /// Noon local on the date ESPN's UTC timestamp falls on. A game with
    /// `timeValid: false` has a placeholder time, so only its UTC date means
    /// anything, and converting it would land on the wrong day west of Greenwich.
    static func localNoon(onUTCDayOf date: Date) -> Date {
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(secondsFromGMT: 0) ?? .current
        var day = utc.dateComponents([.year, .month, .day], from: date)
        day.hour = 12
        return Calendar.current.date(from: day) ?? date
    }
}
