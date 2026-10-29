"""Turns ESPN play coordinates into spatial audio parameters and spoken labels.

Baseball already had this: `simple_audio_mapper` maps a pitch's 0-255 strike-zone
coordinates to a frequency and a stereo balance. Basketball and hockey plays carry
coordinates too — ESPN puts an `x`/`y` on almost every play in the `summary` feed —
so the same treatment works for shots on a court and plays on a rink.

This module is deliberately free of PyQt and winsound so the mapping can be tested
on any platform; `play_audio_mapper` wraps it with the sound playback.

Coordinate systems, measured against real games rather than taken from ESPN docs
(there are none). See TheBench/ESPN_UNUSED_DATA.md for the survey.

Basketball (`basketball/nba`, `wnba`, both college leagues)
    x: 0-50, the court's width in feet.
    y: distance in feet from the baseline the attacking basket sits on. Every
       play is normalised to one end, so y runs 0 at that baseline up to ~82 for
       a full-court heave.
    The basket is at (25, 3). That is not a guess: across six NBA games, dunks
    and layups cluster at x=25, y=2, and measuring from (25, 3) puts the closest
    three-pointer at 21.9 ft with the 5th percentile at 22.4 ft, which is the
    22 ft corner line. Shifting the basket even to (25, 5.25) drags the closest
    three down to 19.8 ft, which no three-point line explains.

Hockey (`hockey/nhl`, both college leagues)
    x: -100 to +100, the rink's 200 ft length, origin at centre ice.
    y: -42 to +42, the rink's 85 ft width.
    Goal mouths sit at (±89, 0), the standard NHL goal line 11 ft off the end
    boards. Goals scored cluster at |x| median 79 — about ten feet out, which is
    where most goals come from — and reach |x| 94, behind the goal line.

Both are transposed into the convention the iOS venue tours already use
(`BasketballCourtTourView`, `HockeyRinkTourView`): `field_x` runs across the
surface and drives the stereo pan, `field_y` runs along it. Keeping that
convention means a shot sonified from the play-by-play lands in the same place
the finger tour puts it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ESPN sends this when a play has no meaningful location — a substitution, a
# timeout, a free throw, a face-off. It is int32 min scaled down, and it arrives
# as a real number rather than null, so it has to be filtered by magnitude.
_SENTINEL = 1_000_000

BASKETBALL_LEAGUES = frozenset({"NBA", "WNBA", "NCAAM", "NCAAWB", "NCAAW"})
HOCKEY_LEAGUES = frozenset({"NHL", "NCAAH", "NCAAWH"})

# Basketball, in feet.
_COURT_HALF_WIDTH = 25.0
_BASKET_ESPN = (25.0, 3.0)
# A corner three is 22 ft and the arc reaches 23.75 ft; 40 ft covers every
# ordinary shot and leaves headroom for a heave before the note bottoms out.
_COURT_MAX_DISTANCE = 40.0

# Hockey, in feet.
_RINK_HALF_WIDTH = 42.5
_RINK_HALF_LENGTH = 100.0
_GOAL_LINE = 89.0
# Centre ice to a goal mouth. A play behind the goal line measures slightly more
# than this, which the clamp absorbs.
_RINK_MAX_DISTANCE = 95.0


@dataclass(frozen=True)
class PlayLocation:
    """Where a play happened, in the terms the audio and the screen reader want.

    `field_x` and `field_y` are feet in the venue-tour frame: x across the
    surface (negative left), y along it. `distance_ft` is the distance to the
    basket or the nearer goal — the quantity that actually says something about
    the play, so it is what drives the note. `pan` is -1.0 (hard left) to
    +1.0 (hard right). `description` is the spoken label.
    """

    field_x: float
    field_y: float
    distance_ft: float
    pan: float
    description: str


def has_coordinate(play: dict) -> bool:
    """True when the play carries a usable location.

    About a third of basketball plays and six percent of hockey plays do not:
    substitutions, timeouts, free throws, period markers and most face-offs.
    """
    coord = play.get("coordinate")
    if not isinstance(coord, dict):
        return False
    x, y = coord.get("x"), coord.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return False
    return abs(x) < _SENTINEL and abs(y) < _SENTINEL


def league_family(league: str | None) -> str | None:
    """"basketball", "hockey", or None for a league with no play coordinates."""
    if not league:
        return None
    key = league.upper()
    if key in BASKETBALL_LEAGUES:
        return "basketball"
    if key in HOCKEY_LEAGUES:
        return "hockey"
    return None


def basketball_location(x: float, y: float) -> PlayLocation:
    """Locate a basketball play from its ESPN court coordinates."""
    field_x = _clamp(x - _COURT_HALF_WIDTH, -_COURT_HALF_WIDTH, _COURT_HALF_WIDTH)
    # The tour frame puts the attacking basket at field_y +43, so measure back
    # from the far baseline.
    field_y = 46.0 - y

    distance = math.hypot(x - _BASKET_ESPN[0], y - _BASKET_ESPN[1])
    pan = _clamp(field_x / _COURT_HALF_WIDTH, -1.0, 1.0)
    return PlayLocation(
        field_x=field_x,
        field_y=field_y,
        distance_ft=distance,
        pan=pan,
        description=_basketball_description(field_x, distance),
    )


def hockey_location(x: float, y: float) -> PlayLocation:
    """Locate a hockey play from its ESPN rink coordinates.

    ESPN's x is the rink's length and y its width, which is the transpose of the
    tour frame, so the two swap here.
    """
    field_x = _clamp(y, -_RINK_HALF_WIDTH, _RINK_HALF_WIDTH)
    field_y = _clamp(x, -_RINK_HALF_LENGTH, _RINK_HALF_LENGTH)

    # Distance to the goal at this end of the ice. Which end is in the spoken
    # label rather than the tone, so that a shot from the slot sounds like a
    # shot from the slot at either end.
    near_goal = _GOAL_LINE if field_y >= 0 else -_GOAL_LINE
    distance = math.hypot(field_x, field_y - near_goal)
    pan = _clamp(field_x / _RINK_HALF_WIDTH, -1.0, 1.0)
    return PlayLocation(
        field_x=field_x,
        field_y=field_y,
        distance_ft=distance,
        pan=pan,
        description=_hockey_description(field_x, field_y, distance),
    )


def locate(league: str | None, x: float, y: float) -> PlayLocation | None:
    """Locate a play for whichever of the two families `league` belongs to."""
    family = league_family(league)
    if family == "basketball":
        return basketball_location(x, y)
    if family == "hockey":
        return hockey_location(x, y)
    return None


def audio_params(league: str | None, x: float, y: float):
    """Map a play to (frequency Hz, duration ms, balance 0-1, description).

    `balance` matches the convention `stereo_audio_mapper` already uses: 0.0 is
    the left speaker, 0.5 centre, 1.0 the right. Frequency falls as the play
    moves away from the basket or the goal, so close in is a high note — the
    same direction baseball uses for a high pitch in the zone.
    """
    location = locate(league, x, y)
    if location is None:
        return None

    family = league_family(league)
    span = _COURT_MAX_DISTANCE if family == "basketball" else _RINK_MAX_DISTANCE
    distance_norm = _clamp(location.distance_ft / span, 0.0, 1.0)

    frequency = PENTATONIC_HZ[_note_index(1.0 - distance_norm)]
    # Close in is crisp, far out rings longer; a corner three should feel like it
    # travelled further than a layup.
    duration_ms = int(round(220 + 180 * distance_norm))
    balance = _clamp((location.pan + 1.0) / 2.0, 0.0, 1.0)
    return frequency, duration_ms, balance, location.description


# A-minor pentatonic over three octaves, the same scale the iOS pitch engine
# uses, so every tone the app plays belongs to one key.
PENTATONIC_HZ = (
    220.00, 261.63, 293.66, 329.63, 392.00,
    440.00, 523.25, 587.33, 659.25, 784.00,
    880.00, 1046.50, 1174.66, 1318.51, 1567.98,
)


def _note_index(norm: float) -> int:
    return int(_clamp(norm, 0.0, 1.0) * (len(PENTATONIC_HZ) - 1) + 0.5)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _side(field_x: float, width: float) -> str:
    """Name the lateral third, from the attacking team's point of view."""
    fraction = field_x / width
    if fraction <= -0.33:
        return "left"
    if fraction >= 0.33:
        return "right"
    return "middle"


def _basketball_description(field_x: float, distance: float) -> str:
    side = _side(field_x, _COURT_HALF_WIDTH)
    # Bands chosen to match how the game is actually described: at the rim, in
    # the paint, mid-range, then beyond the arc.
    if distance <= 4.0:
        return "at the rim"
    if distance <= 8.0:
        band = "in the paint"
    elif distance <= 16.0:
        band = "short mid-range"
    elif distance < 21.0:
        band = "mid-range"
    elif distance <= 27.0:
        # The corner line is 22 ft and the arc 23.75 ft, but ESPN rounds to the
        # foot, so real corner threes measure anywhere from 21.9 ft up. Cutting
        # at 21 ft keeps them out of "mid-range" at the cost of calling the
        # occasional long two a three — the same ambiguity the live feed has.
        band = "from three"
    else:
        return f"deep, {int(round(distance))} feet out"

    if side == "middle":
        return f"{band}, middle"
    return f"{band}, {side} side"


def _hockey_description(field_x: float, field_y: float, distance: float) -> str:
    side = _side(field_x, _RINK_HALF_WIDTH)
    zone = _hockey_zone(field_y)
    if zone == "neutral zone":
        if side == "middle":
            return "neutral zone, centre"
        return f"neutral zone, {side} side"

    if distance <= 12.0:
        band = "in the slot"
    elif distance <= 25.0:
        band = "from the hash marks"
    elif distance <= 45.0:
        band = "from the point"
    else:
        band = "from distance"

    if side == "middle":
        return f"{zone}, {band}"
    return f"{zone}, {band}, {side} side"


def _hockey_zone(field_y: float) -> str:
    """Which third of the ice, by the blue lines at ±25 ft."""
    if field_y > 25.0:
        return "far end"
    if field_y < -25.0:
        return "near end"
    return "neutral zone"
