//
//  PlayAudioGeometry.swift
//  SportsScores
//
//  Turns ESPN play coordinates into spatial audio parameters and spoken labels,
//  for the sports that have them beyond baseball.
//
//  Baseball already had this: PitchAudioEngine maps a pitch's 0-255 strike-zone
//  coordinates to a note and a stereo pan. Basketball and hockey plays carry
//  coordinates in the same summary feed, so a shot or a scoring chance can be
//  heard the same way.
//
//  This is the Swift half of a mapping the Windows app also ships, as
//  play_geometry.py. Keep the two in step: the bands, the landmarks and the
//  spoken wording are all meant to match, so a listener who uses both apps
//  hears the same thing. play_geometry.py has the test suite that pins the
//  numbers; TheBench/ESPN_UNUSED_DATA.md has the survey behind them.
//
//  Coordinate systems, measured against real games rather than taken from
//  ESPN docs, of which there are none.
//
//  Basketball (NBA, WNBA, both college leagues)
//    x: 0-50, the court's width in feet.
//    y: feet from the baseline the attacking basket sits on. Every play is
//       normalised to one end, so y runs 0 at that baseline up to ~82 for a
//       full-court heave.
//    The basket is at (25, 3). Across six NBA games, dunks and layups cluster
//    at x=25, y=2, and measuring from (25, 3) puts the closest three-pointer at
//    21.9 ft, which is the 22 ft corner line.
//
//  Hockey (NHL, both college leagues)
//    x: -100 to +100, the rink's 200 ft length, origin at centre ice.
//    y: -42 to +42, the rink's 85 ft width.
//    Goal mouths sit at (±89, 0), the standard goal line 11 ft off the end
//    boards. Goals scored cluster about ten feet out from there.
//
//  Both are transposed into the frame the venue tours already use
//  (BasketballCourtTourView, HockeyRinkTourView): fieldX runs across the
//  surface and drives the pan, fieldY runs along it. A shot sonified from the
//  play-by-play therefore lands where the finger tour puts it.
//

import Foundation

/// Where a play happened, in the terms the audio and VoiceOver want.
struct PlayLocation {
    /// Feet across the surface in the venue-tour frame; negative is left.
    let fieldX: Double
    /// Feet along the surface in the venue-tour frame.
    let fieldY: Double
    /// Distance to the basket, or to the nearer goal. This is the quantity that
    /// says something about the play, so it is what drives the note.
    let distanceFeet: Double
    /// -1.0 hard left to +1.0 hard right.
    let pan: Float
    /// The spoken label.
    let description: String
}

enum PlayAudioGeometry {

    /// The two families of sport whose plays carry coordinates.
    enum Family {
        case basketball
        case hockey
    }

    // Basketball, in feet.
    private static let courtHalfWidth = 25.0
    private static let basketESPN = (x: 25.0, y: 3.0)
    /// A corner three is 22 ft and the arc reaches 23.75 ft. 40 ft covers every
    /// ordinary shot and leaves headroom for a heave before the note bottoms out.
    private static let courtMaxDistance = 40.0

    // Hockey, in feet.
    private static let rinkHalfWidth = 42.5
    private static let rinkHalfLength = 100.0
    private static let goalLine = 89.0
    // Behind the net is past the goal line within this many feet of centre; the
    // corners are deeper than cornerDepth and wider than that.
    private static let creaseSpan = 20.0
    private static let cornerDepth = 75.0
    /// Centre ice to a goal mouth. A play behind the goal line measures a little
    /// more, which the clamp absorbs.
    private static let rinkMaxDistance = 95.0

    /// A-minor pentatonic over three octaves — the same scale PitchAudioEngine
    /// uses for pitches, so every tone the app plays belongs to one key.
    static let pentatonicHz: [Double] = [
        220.00, 261.63, 293.66, 329.63, 392.00,
        440.00, 523.25, 587.33, 659.25, 784.00,
        880.00, 1046.50, 1174.66, 1318.51, 1567.98,
    ]

    /// Which family a sport belongs to, or nil when its plays have no coordinates.
    static func family(for sport: Sport) -> Family? {
        switch sport {
        case .nba, .wnba, .ncaam, .ncaawb:
            return .basketball
        case .nhl, .ncaah, .ncaawh:
            return .hockey
        default:
            return nil
        }
    }

    /// True when this sport's plays can be sonified at all.
    static func supports(_ sport: Sport) -> Bool {
        family(for: sport) != nil
    }

    // MARK: - Locating a play

    /// Locate a basketball play from its ESPN court coordinates.
    static func basketballLocation(x: Double, y: Double) -> PlayLocation {
        let fieldX = clamp(x - courtHalfWidth, -courtHalfWidth, courtHalfWidth)
        // The tour frame puts the attacking basket at fieldY +43, so measure
        // back from the far baseline.
        let fieldY = 46.0 - y

        let distance = (pow(x - basketESPN.x, 2) + pow(y - basketESPN.y, 2)).squareRoot()
        let pan = Float(clamp(fieldX / courtHalfWidth, -1.0, 1.0))
        return PlayLocation(
            fieldX: fieldX,
            fieldY: fieldY,
            distanceFeet: distance,
            pan: pan,
            description: basketballDescription(fieldX: fieldX, distance: distance)
        )
    }

    /// Locate a hockey play from its ESPN rink coordinates.
    ///
    /// ESPN's x is the rink's length and y its width, the transpose of the tour
    /// frame, so the two swap here.
    static func hockeyLocation(x: Double, y: Double) -> PlayLocation {
        let fieldX = clamp(y, -rinkHalfWidth, rinkHalfWidth)
        let fieldY = clamp(x, -rinkHalfLength, rinkHalfLength)

        // Distance to the goal at this end. Which end is in the spoken label
        // rather than the tone, so a shot from the slot sounds like a shot from
        // the slot at either end of the ice.
        let nearGoal = fieldY >= 0 ? goalLine : -goalLine
        let distance = (pow(fieldX, 2) + pow(fieldY - nearGoal, 2)).squareRoot()
        // Left and right as seen facing the goal at this end. The two ends face
        // opposite ways, so the same y is the right side at one end and the left
        // at the other; without the flip, mirror-image shots would sound alike.
        let facingX = fieldY >= 0 ? fieldX : -fieldX
        let pan = Float(clamp(facingX / rinkHalfWidth, -1.0, 1.0))
        return PlayLocation(
            fieldX: fieldX,
            fieldY: fieldY,
            distanceFeet: distance,
            pan: pan,
            description: hockeyDescription(fieldX: facingX, fieldY: fieldY, distance: distance)
        )
    }

    /// Locate a play for whichever family `sport` belongs to.
    static func location(for sport: Sport, x: Double, y: Double) -> PlayLocation? {
        switch family(for: sport) {
        case .basketball: return basketballLocation(x: x, y: y)
        case .hockey:     return hockeyLocation(x: x, y: y)
        case nil:         return nil
        }
    }

    /// Locate a play straight from the feed, skipping the ones ESPN sends with
    /// no real location.
    static func location(for sport: Sport, play: GameDetails.Play) -> PlayLocation? {
        guard let coordinate = play.coordinate, coordinate.isUsable else { return nil }
        return location(for: sport, x: coordinate.x, y: coordinate.y)
    }

    // MARK: - Audio parameters

    /// What to play for a located play: a note, a stereo pan, how long it rings,
    /// and what VoiceOver should say.
    ///
    /// The note falls as the play moves away from the basket or the goal, so
    /// close in is a high note — the same direction a high pitch in the strike
    /// zone goes.
    static func audioParameters(for sport: Sport, x: Double, y: Double)
        -> (frequency: Double, pan: Float, duration: Double, description: String)?
    {
        guard let family = family(for: sport),
              let location = location(for: sport, x: x, y: y) else { return nil }

        let span = family == .basketball ? courtMaxDistance : rinkMaxDistance
        let distanceNorm = clamp(location.distanceFeet / span, 0.0, 1.0)

        let frequency = pentatonicHz[noteIndex(1.0 - distanceNorm)]
        // Close in is crisp, far out rings longer; a corner three should feel
        // like it travelled further than a layup.
        let duration = 0.22 + 0.18 * distanceNorm
        return (frequency, location.pan, duration, location.description)
    }

    static func audioParameters(for sport: Sport, play: GameDetails.Play)
        -> (frequency: Double, pan: Float, duration: Double, description: String)?
    {
        guard let coordinate = play.coordinate, coordinate.isUsable else { return nil }
        return audioParameters(for: sport, x: coordinate.x, y: coordinate.y)
    }

    // MARK: - Spoken labels

    private static func noteIndex(_ norm: Double) -> Int {
        let scaled = clamp(norm, 0.0, 1.0) * Double(pentatonicHz.count - 1)
        return min(pentatonicHz.count - 1, max(0, Int((scaled).rounded())))
    }

    private static func clamp(_ value: Double, _ low: Double, _ high: Double) -> Double {
        min(high, max(low, value))
    }

    /// Name the lateral third, from the attacking team's point of view.
    private static func side(_ fieldX: Double, width: Double) -> String {
        let fraction = fieldX / width
        if fraction <= -0.33 { return "left" }
        if fraction >= 0.33 { return "right" }
        return "middle"
    }

    private static func basketballDescription(fieldX: Double, distance: Double) -> String {
        let side = side(fieldX, width: courtHalfWidth)
        // Bands chosen to match how the game is actually described: at the rim,
        // in the paint, mid-range, then beyond the arc.
        if distance <= 4.0 { return "at the rim" }

        let band: String
        if distance <= 8.0 {
            band = "in the paint"
        } else if distance <= 16.0 {
            band = "short mid-range"
        } else if distance < 21.0 {
            band = "mid-range"
        } else if distance <= 27.0 {
            // The corner line is 22 ft and the arc 23.75 ft, but ESPN rounds to
            // the foot, so real corner threes measure anywhere from 21.9 ft up.
            // Cutting at 21 ft keeps them out of "mid-range" at the cost of
            // calling the occasional long two a three — the same ambiguity the
            // live feed has.
            band = "from three"
        } else {
            return "deep, \(Int(distance.rounded())) feet out"
        }

        return side == "middle" ? "\(band), middle" : "\(band), \(side) side"
    }

    private static func hockeyDescription(fieldX: Double, fieldY: Double, distance: Double) -> String {
        let side = side(fieldX, width: rinkHalfWidth)
        let zone = hockeyZone(fieldY)

        if zone == "neutral zone" {
            return side == "middle" ? "neutral zone, centre" : "neutral zone, \(side) side"
        }

        // Past the goal line and in the corners first: both are close to the
        // goal by distance, but nobody would call a battle behind the net "in
        // the slot".
        if abs(fieldY) > goalLine && abs(fieldX) <= creaseSpan {
            return "\(zone), behind the net"
        }
        if abs(fieldY) > cornerDepth && abs(fieldX) > creaseSpan {
            return "\(zone), in the \(side) corner"
        }

        let band: String
        if distance <= 12.0 {
            band = "in the slot"
        } else if distance <= 25.0 {
            band = "from the hash marks"
        } else if distance <= 45.0 {
            band = "from the point"
        } else {
            band = "from distance"
        }

        return side == "middle" ? "\(zone), \(band)" : "\(zone), \(band), \(side) side"
    }

    /// Which third of the ice, by the blue lines at ±25 ft.
    private static func hockeyZone(_ fieldY: Double) -> String {
        if fieldY > 25.0 { return "far end" }
        if fieldY < -25.0 { return "near end" }
        return "neutral zone"
    }
}
