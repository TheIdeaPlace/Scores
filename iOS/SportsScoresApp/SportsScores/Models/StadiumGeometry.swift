//
//  StadiumGeometry.swift
//  SportsScores
//
//  Hardcoded geometry for all 30 MLB stadiums.
//
//  Coordinate model
//  ────────────────
//  Field coordinates are in feet, referenced from home plate as the origin.
//    +x = right field direction, −x = left field direction
//    +y = toward center field (away from batter), −y = backstop direction
//
//  The outfield wall is modelled with five control distances:
//    leftFieldLine, leftCenter, centerField, rightCenter, rightFieldLine
//  A wall arc is interpolated (piecewise linear) between these points at
//  the corresponding compass bearings from home (−45°, −22.5°, 0°, +22.5°, +45°).
//

import Foundation
import CoreGraphics

// MARK: - Terrain type

/// Sound character category for the field audio engine.
enum FieldTerrain {
    case fair           // grass — soft swish
    case warningTrack   // cinder / gravel — middle ground
    case foul           // hard surface / concrete — rough
    case silent         // outside field boundary
}

// MARK: - Model

struct StadiumGeometry: Identifiable, Equatable, Hashable {

    /// Unique ID — ESPN venue name abbreviation or team city.
    let id: String
    /// Official current stadium name.
    let parkName: String
    /// Primary team that plays there.
    let teamName: String
    /// Team abbreviation (used to look up venue from game data).
    let teamAbbreviation: String
    /// City, State
    let location: String
    /// Year the current park opened.
    let yearOpened: Int
    /// Feature notes shown during the tour (special walls, quirks, etc.)
    let notableFeatures: [String]

    // MARK: - Wall distances (feet from home plate)

    /// Distance to the left-field foul pole.
    let leftFieldLine: Double
    /// Distance to left-center ("power alley" left side).
    let leftCenter: Double
    /// Distance to straightaway center field.
    let centerField: Double
    /// Distance to right-center ("power alley" right side).
    let rightCenter: Double
    /// Distance to the right-field foul pole.
    let rightFieldLine: Double

    // MARK: - Wall height (feet)

    /// Left field wall height (default 8 ft; Fenway Green Monster = 37 ft).
    let leftWallHeight: Double
    /// Right field wall height.
    let rightWallHeight: Double

    // MARK: - Roof type

    enum RoofType: String {
        case open, retractable, fixed
    }
    let roof: RoofType

    // MARK: - Wall distance interpolation

    /// Returns the interpolated wall distance (feet) at the given bearing from home plate.
    ///
    /// `bearingDegrees` — signed degrees from the CF direction:
    ///   −45° = left field line, 0° = straightaway CF, +45° = right field line.
    func wallDistanceFeet(bearing bearingDegrees: Double) -> Double {
        let b = Swift.min(Swift.max(bearingDegrees, -45.0), 45.0)
        // Five anchor bearings: −45, −22.5, 0, +22.5, +45
        let anchors: [(bearing: Double, dist: Double)] = [
            (-45.0, leftFieldLine),
            (-22.5, leftCenter),
            (  0.0, centerField),
            ( 22.5, rightCenter),
            ( 45.0, rightFieldLine),
        ]
        // Find the two anchors that bracket b
        for i in 0..<anchors.count - 1 {
            let lo = anchors[i]
            let hi = anchors[i + 1]
            if b >= lo.bearing && b <= hi.bearing {
                let t = (b - lo.bearing) / (hi.bearing - lo.bearing)
                return lo.dist + t * (hi.dist - lo.dist)
            }
        }
        return centerField
    }

    /// Returns the wall position in field-coordinate feet (x, y) at the given bearing.
    func wallPoint(bearing bearingDegrees: Double) -> (x: Double, y: Double) {
        let dist = wallDistanceFeet(bearing: bearingDegrees)
        let rad = bearingDegrees * .pi / 180.0
        return (x: dist * sin(rad), y: dist * cos(rad))
    }

    /// 19 sample points along the wall arc (bearing −45° to +45°, step 5°).
    var wallArcPoints: [(x: Double, y: Double)] {
        stride(from: -45.0, through: 45.0, by: 5.0).map { wallPoint(bearing: $0) }
    }

    // MARK: - Zone detection

    struct FieldZoneResult {
        let name: String
        let distanceFeet: Int
        let terrain: FieldTerrain
        /// True for bases, mound, and home plate — triggers a chime in addition to the terrain sound.
        var isLandmark: Bool = false
    }

    func detectZone(fieldX: Double, fieldY: Double) -> FieldZoneResult {
        let dist = (fieldX * fieldX + fieldY * fieldY).squareRoot()
        let bearing = atan2(fieldX, max(fieldY, 0.001)) * 180.0 / .pi  // degrees, 0=CF

        // ── Behind home plate ────────────────────────────────────────────
        if fieldY < 0 {
            if abs(fieldX) < 30 {
                return FieldZoneResult(name: "Backstop area, behind home plate", distanceFeet: Int(dist), terrain: .foul)
            } else {
                let side = fieldX < 0 ? "left" : "right"
                return FieldZoneResult(name: "Foul territory, \(side) side behind home", distanceFeet: Int(dist), terrain: .foul)
            }
        }

        // ── Named bases & mound (within 13 ft) ──────────────────────────
        if dist < 13 {
            return FieldZoneResult(name: "Home plate", distanceFeet: 0, terrain: .fair, isLandmark: true)
        }
        let distToFirst = hypot(fieldX - 63.64, fieldY - 63.64)
        if distToFirst < 13 {
            return FieldZoneResult(name: "First base", distanceFeet: 90, terrain: .fair, isLandmark: true)
        }
        let distToSecond = hypot(fieldX, fieldY - 127.28)
        if distToSecond < 13 {
            return FieldZoneResult(name: "Second base", distanceFeet: 127, terrain: .fair, isLandmark: true)
        }
        let distToThird = hypot(fieldX + 63.64, fieldY - 63.64)
        if distToThird < 13 {
            return FieldZoneResult(name: "Third base", distanceFeet: 90, terrain: .fair, isLandmark: true)
        }
        let distToMound = hypot(fieldX, fieldY - 60.5)
        if distToMound < 11 {
            return FieldZoneResult(name: "Pitcher's mound", distanceFeet: 60, terrain: .fair, isLandmark: true)
        }

        // ── Foul territory (outside the 45-degree foul lines) ─────────────
        if bearing < -45 {
            return FieldZoneResult(name: "Foul territory beyond left field line, \(Int(dist)) feet from home", distanceFeet: Int(dist), terrain: .foul)
        }
        if bearing > 45 {
            return FieldZoneResult(name: "Foul territory beyond right field line, \(Int(dist)) feet from home", distanceFeet: Int(dist), terrain: .foul)
        }

        // ── Infield ──────────────────────────────────────────────────────
        if dist < 120 {
            let side: String
            if bearing < -10 { side = "third base side" }
            else if bearing > 10 { side = "first base side" }
            else { side = "up the middle" }
            return FieldZoneResult(name: "Infield, \(side), \(Int(dist)) feet from home", distanceFeet: Int(dist), terrain: .fair)
        }

        // ── Outfield: determine wall distance at this bearing ────────────
        let wallDist = wallDistanceFeet(bearing: bearing)
        let distToWall = wallDist - dist

        // Fine-grained directional label from home plate bearing.
        // −45° = LF line, 0° = straight-away center, +45° = RF line.
        let dirLabel: String
        switch bearing {
        case ..<(-33): dirLabel = "Left field, near foul line"
        case ..<(-15): dirLabel = "Left field"
        case ..<(-5):  dirLabel = "Left center"
        case ...(5):   dirLabel = "Center field"
        case ...(15):  dirLabel = "Right center"
        case ...(33):  dirLabel = "Right field"
        default:       dirLabel = "Right field, near foul line"
        }

        // Wall-height note used only on warning track
        let wallHeightNote: String
        if bearing < -15 && leftWallHeight > 12 {
            wallHeightNote = " — \(Int(leftWallHeight))-foot wall"
        } else if bearing > 15 && rightWallHeight > 12 {
            wallHeightNote = " — \(Int(rightWallHeight))-foot wall"
        } else {
            wallHeightNote = ""
        }

        if distToWall < 15 {
            let wallFt = Int(wallDist)
            return FieldZoneResult(
                name: "\(dirLabel) warning track, \(wallFt) feet from home\(wallHeightNote)",
                distanceFeet: wallFt,
                terrain: .warningTrack
            )
        }

        // Beyond the wall
        if distToWall < 0 {
            return FieldZoneResult(name: "\(dirLabel) stands", distanceFeet: Int(dist), terrain: .silent)
        }

        return FieldZoneResult(
            name: "\(dirLabel), \(Int(dist)) feet from home",
            distanceFeet: Int(dist),
            terrain: .fair
        )
    }
}

// MARK: - All 30 MLB Stadiums

extension StadiumGeometry {

    // Looks up a stadium by team abbreviation (case-insensitive).
    static func stadium(forTeam abbreviation: String) -> StadiumGeometry? {
        all.first { $0.teamAbbreviation.lowercased() == abbreviation.lowercased() }
    }

    // Looks up by venue name fragment (case-insensitive search).
    static func stadium(venueContaining fragment: String) -> StadiumGeometry? {
        guard !fragment.isEmpty else { return nil }
        let lower = fragment.lowercased()
        return all.first { $0.parkName.lowercased().contains(lower) }
    }

    static let all: [StadiumGeometry] = [

        // ── American League East ──────────────────────────────────────────

        StadiumGeometry(
            id: "bal", parkName: "Oriole Park at Camden Yards",
            teamName: "Baltimore Orioles", teamAbbreviation: "BAL",
            location: "Baltimore, MD", yearOpened: 1992,
            notableFeatures: [
                "B&O Warehouse looms beyond the right-field corner — 460 ft from home plate.",
                "Irregularly shaped outfield with 25-foot right-field fence segment.",
                "One of the first modern retro ballparks, setting the template for future parks.",
            ],
            leftFieldLine: 333, leftCenter: 364, centerField: 400,
            rightCenter: 373, rightFieldLine: 318,
            leftWallHeight: 7, rightWallHeight: 25, roof: .open
        ),

        StadiumGeometry(
            id: "bos", parkName: "Fenway Park",
            teamName: "Boston Red Sox", teamAbbreviation: "BOS",
            location: "Boston, MA", yearOpened: 1912,
            notableFeatures: [
                "The Green Monster — a 37-foot-2-inch left field wall, the tallest in MLB.",
                "Pesky's Pole at right-field foul line is only 302 feet from home plate.",
                "The oldest active ballpark in Major League Baseball, opened April 20, 1912.",
                "Manual scoreboard is still operated by hand inside the Green Monster.",
            ],
            leftFieldLine: 310, leftCenter: 379, centerField: 420,
            rightCenter: 380, rightFieldLine: 302,
            leftWallHeight: 37, rightWallHeight: 3, roof: .open
        ),

        StadiumGeometry(
            id: "nyy", parkName: "Yankee Stadium",
            teamName: "New York Yankees", teamAbbreviation: "NYY",
            location: "Bronx, NY", yearOpened: 2009,
            notableFeatures: [
                "Short right-field porch (314 ft) rewards pull hitters — a Yankee Stadium tradition.",
                "Monument Park in center field honors retired Yankees legends.",
                "Black batter's eye wall in deep center creates a clean backdrop for hitters.",
            ],
            leftFieldLine: 318, leftCenter: 399, centerField: 408,
            rightCenter: 385, rightFieldLine: 314,
            leftWallHeight: 8, rightWallHeight: 8, roof: .open
        ),

        StadiumGeometry(
            id: "tb", parkName: "Tropicana Field",
            teamName: "Tampa Bay Rays", teamAbbreviation: "TB",
            location: "St. Petersburg, FL", yearOpened: 1990,
            notableFeatures: [
                "Fixed dome — all games played indoors regardless of Florida weather.",
                "Catwalk rings hang just 105 ft above the field and are in play.",
                "Artificial turf playing surface.",
                "D-ring catwalk at 190 ft — a ball hitting it is ruled a ground rule double.",
            ],
            leftFieldLine: 315, leftCenter: 370, centerField: 404,
            rightCenter: 370, rightFieldLine: 322,
            leftWallHeight: 8, rightWallHeight: 8, roof: .fixed
        ),

        StadiumGeometry(
            id: "tor", parkName: "Rogers Centre",
            teamName: "Toronto Blue Jays", teamAbbreviation: "TOR",
            location: "Toronto, ON", yearOpened: 1989,
            notableFeatures: [
                "Fixed dome with a retractable-style roof that is essentially always closed for baseball.",
                "Artificial turf surface.",
                "CN Tower — visible from the upper decks.",
                "Only MLB stadium located outside the United States.",
            ],
            leftFieldLine: 328, leftCenter: 375, centerField: 400,
            rightCenter: 375, rightFieldLine: 328,
            leftWallHeight: 8, rightWallHeight: 8, roof: .fixed
        ),

        // ── American League Central ───────────────────────────────────────

        StadiumGeometry(
            id: "cws", parkName: "Guaranteed Rate Field",
            teamName: "Chicago White Sox", teamAbbreviation: "CWS",
            location: "Chicago, IL", yearOpened: 1991,
            notableFeatures: [
                "Exploding scoreboard in right-center field — a nod to the original Comiskey Park.",
                "Deep center field at 400 feet provides a true test for power hitters.",
            ],
            leftFieldLine: 330, leftCenter: 377, centerField: 400,
            rightCenter: 372, rightFieldLine: 335,
            leftWallHeight: 8, rightWallHeight: 8, roof: .open
        ),

        StadiumGeometry(
            id: "cle", parkName: "Progressive Field",
            teamName: "Cleveland Guardians", teamAbbreviation: "CLE",
            location: "Cleveland, OH", yearOpened: 1994,
            notableFeatures: [
                "Intimate design keeps fans close to the action — smallest foul territory in the AL.",
                "Manual out-of-town scoreboard maintained by the grounds crew.",
                "Left field bleachers nicknamed the 'Corner' — a popular standing-room section.",
            ],
            leftFieldLine: 325, leftCenter: 370, centerField: 404,
            rightCenter: 375, rightFieldLine: 325,
            leftWallHeight: 19, rightWallHeight: 8, roof: .open
        ),

        StadiumGeometry(
            id: "det", parkName: "Comerica Park",
            teamName: "Detroit Tigers", teamAbbreviation: "DET",
            location: "Detroit, MI", yearOpened: 2000,
            notableFeatures: [
                "One of the deepest center fields at 420 feet — historically pitcher-friendly.",
                "Tiger statues and a Ferris wheel make it one of the most distinctive parks.",
                "Left-center power alley at 395 feet is among the deepest in baseball.",
            ],
            leftFieldLine: 345, leftCenter: 395, centerField: 420,
            rightCenter: 365, rightFieldLine: 330,
            leftWallHeight: 8, rightWallHeight: 8, roof: .open
        ),

        StadiumGeometry(
            id: "kc", parkName: "Kauffman Stadium",
            teamName: "Kansas City Royals", teamAbbreviation: "KC",
            location: "Kansas City, MO", yearOpened: 1973,
            notableFeatures: [
                "Crown scoreboard and massive waterfall beyond the outfield wall are iconic.",
                "Spacious symmetrical outfield rewards gap hitters.",
                "One of three stadiums that opened in 1973 alongside Riverfront and Veterans.",
            ],
            leftFieldLine: 330, leftCenter: 387, centerField: 410,
            rightCenter: 387, rightFieldLine: 330,
            leftWallHeight: 9, rightWallHeight: 9, roof: .open
        ),

        StadiumGeometry(
            id: "min", parkName: "Target Field",
            teamName: "Minnesota Twins", teamAbbreviation: "MIN",
            location: "Minneapolis, MN", yearOpened: 2010,
            notableFeatures: [
                "Open-air park in a cold-weather city — retractable roof was considered but not built.",
                "Sweeping limestone concourse reflects Minnesota's geology.",
                "Short-corner right field wall (328 ft) with a 23-foot high fence.",
            ],
            leftFieldLine: 339, leftCenter: 377, centerField: 411,
            rightCenter: 365, rightFieldLine: 328,
            leftWallHeight: 8, rightWallHeight: 23, roof: .open
        ),

        // ── American League West ─────────────────────────────────────────

        StadiumGeometry(
            id: "hou", parkName: "Daikin Park",
            teamName: "Houston Astros", teamAbbreviation: "HOU",
            location: "Houston, TX", yearOpened: 2000,
            notableFeatures: [
                "Tal's Hill — a 30-degree incline in center field (removed after 2016).",
                "The deepest center field at 436 feet when originally built.",
                "Retractable roof opens in about 12 minutes.",
                "Left field corner flags a 315-foot foul pole with a 19-foot Crawford Boxes wall.",
            ],
            leftFieldLine: 315, leftCenter: 362, centerField: 436,
            rightCenter: 373, rightFieldLine: 326,
            leftWallHeight: 19, rightWallHeight: 7, roof: .retractable
        ),

        StadiumGeometry(
            id: "laa", parkName: "Angel Stadium of Anaheim",
            teamName: "Los Angeles Angels", teamAbbreviation: "LAA",
            location: "Anaheim, CA", yearOpened: 1966,
            notableFeatures: [
                "Rock formation with cascading waterfall beyond the left-center outfield wall.",
                "One of four multi-purpose stadiums still hosting MLB baseball (originally built for football too).",
                "The Big A — a 230-foot structure outside the ballpark has stood since 1966.",
            ],
            leftFieldLine: 340, leftCenter: 385, centerField: 396,
            rightCenter: 365, rightFieldLine: 350,
            leftWallHeight: 8, rightWallHeight: 8, roof: .open
        ),

        StadiumGeometry(
            id: "oak", parkName: "Oakland Coliseum",
            teamName: "Oakland Athletics", teamAbbreviation: "OAK",
            location: "Oakland, CA", yearOpened: 1968,
            notableFeatures: [
                "Mount Davis — an upper deck in center field built to obscure the view of the A's games.",
                "Enormous foul territory — one of the largest in MLB, favoring pitchers.",
                "Last of the circular multi-purpose stadiums still hosting MLB baseball.",
            ],
            leftFieldLine: 330, leftCenter: 388, centerField: 400,
            rightCenter: 388, rightFieldLine: 330,
            leftWallHeight: 8, rightWallHeight: 8, roof: .open
        ),

        StadiumGeometry(
            id: "sea", parkName: "T-Mobile Park",
            teamName: "Seattle Mariners", teamAbbreviation: "SEA",
            location: "Seattle, WA", yearOpened: 1999,
            notableFeatures: [
                "Retractable roof designed to drain rainwater rather than enclose the space fully.",
                "Edgar's Cantina & Gifts — named after Edgar Martinez, the DH-era icon.",
                "The Hit It Here Café — diners sit above right field, within home-run reach.",
            ],
            leftFieldLine: 331, leftCenter: 378, centerField: 401,
            rightCenter: 381, rightFieldLine: 326,
            leftWallHeight: 8, rightWallHeight: 8, roof: .retractable
        ),

        StadiumGeometry(
            id: "tex", parkName: "Globe Life Field",
            teamName: "Texas Rangers", teamAbbreviation: "TEX",
            location: "Arlington, TX", yearOpened: 2020,
            notableFeatures: [
                "Fixed roof allows year-round stadium-controlled climate — crucial for Texas summers.",
                "Opened in 2020, the newest MLB park currently in use.",
                "Natural grass playing surface under artificial lighting.",
            ],
            leftFieldLine: 332, leftCenter: 372, centerField: 407,
            rightCenter: 374, rightFieldLine: 326,
            leftWallHeight: 8, rightWallHeight: 8, roof: .retractable
        ),

        // ── National League East ─────────────────────────────────────────

        StadiumGeometry(
            id: "atl", parkName: "Truist Park",
            teamName: "Atlanta Braves", teamAbbreviation: "ATL",
            location: "Cumberland, GA", yearOpened: 2017,
            notableFeatures: [
                "First MLB park built entirely in the suburbs — part of a mixed-use development.",
                "The Battery Atlanta surrounds the park with shops, restaurants, and offices.",
                "Left-field Chop House restaurant features the Tomahawk Chop tradition.",
            ],
            leftFieldLine: 335, leftCenter: 380, centerField: 400,
            rightCenter: 375, rightFieldLine: 325,
            leftWallHeight: 8, rightWallHeight: 8, roof: .open
        ),

        StadiumGeometry(
            id: "mia", parkName: "loanDepot park",
            teamName: "Miami Marlins", teamAbbreviation: "MIA",
            location: "Miami, FL", yearOpened: 2012,
            notableFeatures: [
                "Retractable roof and climate control essential in South Florida's heat and humidity.",
                "Home Run Sculpture in left-center — a towering kinetic art installation that activates on home runs.",
                "Sits on the former Orange Bowl site.",
            ],
            leftFieldLine: 344, leftCenter: 386, centerField: 400,
            rightCenter: 392, rightFieldLine: 335,
            leftWallHeight: 8, rightWallHeight: 8, roof: .retractable
        ),

        StadiumGeometry(
            id: "nym", parkName: "Citi Field",
            teamName: "New York Mets", teamAbbreviation: "NYM",
            location: "Flushing, NY", yearOpened: 2009,
            notableFeatures: [
                "Jackie Robinson Rotunda at the main entrance — a tribute to #42.",
                "Inspired by Ebbets Field, the historic Brooklyn Dodgers home.",
                "Apple in center-field stands rises after every Mets home run.",
            ],
            leftFieldLine: 335, leftCenter: 379, centerField: 408,
            rightCenter: 383, rightFieldLine: 330,
            leftWallHeight: 8, rightWallHeight: 8, roof: .open
        ),

        StadiumGeometry(
            id: "phi", parkName: "Citizens Bank Park",
            teamName: "Philadelphia Phillies", teamAbbreviation: "PHI",
            location: "Philadelphia, PA", yearOpened: 2004,
            notableFeatures: [
                "Ashburn Alley — a pedestrian concourse in center field named after Richie Ashburn.",
                "Liberty Bell replica rings after every Phillies home run.",
                "One of the more homer-friendly parks in the NL.",
            ],
            leftFieldLine: 329, leftCenter: 374, centerField: 401,
            rightCenter: 369, rightFieldLine: 330,
            leftWallHeight: 8, rightWallHeight: 8, roof: .open
        ),

        StadiumGeometry(
            id: "wsh", parkName: "Nationals Park",
            teamName: "Washington Nationals", teamAbbreviation: "WSH",
            location: "Washington, DC", yearOpened: 2008,
            notableFeatures: [
                "Racing Presidents mascot race is a beloved between-inning tradition.",
                "The Park sits on the Anacostia River waterfront.",
                "First LEED-certified MLB stadium.",
            ],
            leftFieldLine: 336, leftCenter: 377, centerField: 402,
            rightCenter: 370, rightFieldLine: 335,
            leftWallHeight: 8, rightWallHeight: 8, roof: .open
        ),

        // ── National League Central ───────────────────────────────────────

        StadiumGeometry(
            id: "chc", parkName: "Wrigley Field",
            teamName: "Chicago Cubs", teamAbbreviation: "CHC",
            location: "Chicago, IL", yearOpened: 1914,
            notableFeatures: [
                "Ivy-covered brick outfield walls — balls lost in the ivy are ground rule doubles.",
                "Hand-operated scoreboard in center field — unchanged since 1937.",
                "Wrigley rooftops across Waveland and Sheffield Avenues frame the park.",
                "Second-oldest MLB ballpark, opened as Weeghman Park on April 23, 1914.",
            ],
            leftFieldLine: 355, leftCenter: 368, centerField: 400,
            rightCenter: 368, rightFieldLine: 353,
            leftWallHeight: 11, rightWallHeight: 11, roof: .open
        ),

        StadiumGeometry(
            id: "cin", parkName: "Great American Ball Park",
            teamName: "Cincinnati Reds", teamAbbreviation: "CIN",
            location: "Cincinnati, OH", yearOpened: 2003,
            notableFeatures: [
                "The Gap — a short right-field power alley created by the riverfront location.",
                "Marge Schott/Riverfront Stadium once stood on this same Ohio River site.",
                "Coliseum seating section beyond left center — the original 'Reds Hall of Fame'.",
            ],
            leftFieldLine: 328, leftCenter: 370, centerField: 404,
            rightCenter: 370, rightFieldLine: 325,
            leftWallHeight: 12, rightWallHeight: 8, roof: .open
        ),

        StadiumGeometry(
            id: "mil", parkName: "American Family Field",
            teamName: "Milwaukee Brewers", teamAbbreviation: "MIL",
            location: "Milwaukee, WI", yearOpened: 2001,
            notableFeatures: [
                "Retractable roof — opens in 10 minutes; closed on about 20 games per year.",
                "Sausage Race between innings is a Wisconsin staple.",
                "Bernie Brewer's slide in left-center field activates after home runs.",
            ],
            leftFieldLine: 344, leftCenter: 370, centerField: 400,
            rightCenter: 374, rightFieldLine: 345,
            leftWallHeight: 8, rightWallHeight: 8, roof: .retractable
        ),

        StadiumGeometry(
            id: "pit", parkName: "PNC Park",
            teamName: "Pittsburgh Pirates", teamAbbreviation: "PIT",
            location: "Pittsburgh, PA", yearOpened: 2001,
            notableFeatures: [
                "Roberto Clemente Bridge — pedestrian-only on game days — connects downtown to the park.",
                "View of Pittsburgh's downtown skyline beyond the right-center field wall.",
                "The Allegheny River flows just beyond the right-field stands.",
            ],
            leftFieldLine: 325, leftCenter: 383, centerField: 399,
            rightCenter: 375, rightFieldLine: 320,
            leftWallHeight: 6, rightWallHeight: 21, roof: .open
        ),

        StadiumGeometry(
            id: "stl", parkName: "Busch Stadium",
            teamName: "St. Louis Cardinals", teamAbbreviation: "STL",
            location: "St. Louis, MO", yearOpened: 2006,
            notableFeatures: [
                "Gateway Arch visible beyond the outfield wall — one of the great MLB backdrops.",
                "Third Busch Stadium on this site; first opened in 1966.",
                "Sold out 5,000+ consecutive games at one point — record for a single city.",
            ],
            leftFieldLine: 336, leftCenter: 375, centerField: 400,
            rightCenter: 375, rightFieldLine: 335,
            leftWallHeight: 8, rightWallHeight: 8, roof: .open
        ),

        // ── National League West ─────────────────────────────────────────

        StadiumGeometry(
            id: "ari", parkName: "Chase Field",
            teamName: "Arizona Diamondbacks", teamAbbreviation: "ARI",
            location: "Phoenix, AZ", yearOpened: 1998,
            notableFeatures: [
                "Retractable roof and air conditioning — essential for Phoenix summers (110°F game days).",
                "Swimming pool in right-center field beyond the home-run wall.",
                "First retractable-roof MLB stadium to have a natural grass playing surface.",
            ],
            leftFieldLine: 330, leftCenter: 374, centerField: 407,
            rightCenter: 374, rightFieldLine: 334,
            leftWallHeight: 8, rightWallHeight: 8, roof: .retractable
        ),

        StadiumGeometry(
            id: "col", parkName: "Coors Field",
            teamName: "Colorado Rockies", teamAbbreviation: "COL",
            location: "Denver, CO", yearOpened: 1995,
            notableFeatures: [
                "Mile High altitude (5,280 ft above sea level) — baseballs travel 9% farther than at sea level.",
                "The Rockpile — bleachers in center field, cheapest seats in MLB.",
                "Purple row of seats in the upper deck marks exactly one mile above sea level.",
                "Humidor stores baseballs at 50% humidity to counteract the thin air.",
            ],
            leftFieldLine: 347, leftCenter: 390, centerField: 415,
            rightCenter: 375, rightFieldLine: 350,
            leftWallHeight: 8, rightWallHeight: 8, roof: .open
        ),

        StadiumGeometry(
            id: "lad", parkName: "Dodger Stadium",
            teamName: "Los Angeles Dodgers", teamAbbreviation: "LAD",
            location: "Los Angeles, CA", yearOpened: 1962,
            notableFeatures: [
                "Third-oldest MLB ballpark, opened April 10, 1962.",
                "Surrounded by Chavez Ravine's palm trees and the San Gabriel Mountains backdrop.",
                "Largest seating capacity in MLB — 56,000.",
                "Famous for its Dodger Dogs and casual Hollywood crowd.",
            ],
            leftFieldLine: 330, leftCenter: 375, centerField: 395,
            rightCenter: 375, rightFieldLine: 330,
            leftWallHeight: 4, rightWallHeight: 4, roof: .open
        ),

        StadiumGeometry(
            id: "sd", parkName: "Petco Park",
            teamName: "San Diego Padres", teamAbbreviation: "SD",
            location: "San Diego, CA", yearOpened: 2004,
            notableFeatures: [
                "Western Metal Supply building in the left-field corner is built into the park structure.",
                "The Park at the Park — a grassy knoll beyond center where fans watch for free.",
                "Comfortable year-round climate — San Diego averages 73°F on game days.",
            ],
            leftFieldLine: 336, leftCenter: 367, centerField: 396,
            rightCenter: 382, rightFieldLine: 322,
            leftWallHeight: 8, rightWallHeight: 8, roof: .open
        ),

        StadiumGeometry(
            id: "sf", parkName: "Oracle Park",
            teamName: "San Francisco Giants", teamAbbreviation: "SF",
            location: "San Francisco, CA", yearOpened: 2000,
            notableFeatures: [
                "McCovey Cove beyond the right-field wall — kayakers and boats collect splash home runs.",
                "Narrowest right-field foul pole in MLB at only 309 feet.",
                "Notorious wind and fog off San Francisco Bay suppresses offense.",
                "Splash hits — home runs landing directly in the Cove — are individually tracked.",
            ],
            leftFieldLine: 339, leftCenter: 382, centerField: 399,
            rightCenter: 364, rightFieldLine: 309,
            leftWallHeight: 8, rightWallHeight: 25, roof: .open
        ),
    ]
}
