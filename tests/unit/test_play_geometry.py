"""Checks the basketball/hockey play sonification mapping.

The coordinate spaces are undocumented, so the assertions here pin the facts
the mapping was derived from: where the basket is, where the goal lines are,
and which plays ESPN sends without a location.
"""

import math

import pytest

from play_geometry import (
    audio_params,
    basketball_location,
    has_coordinate,
    hockey_location,
    league_family,
    locate,
    PENTATONIC_HZ,
)


class TestLeagueFamily:
    @pytest.mark.parametrize("league", ["NBA", "nba", "WNBA", "NCAAM", "NCAAWB"])
    def test_basketball_leagues(self, league):
        assert league_family(league) == "basketball"

    @pytest.mark.parametrize("league", ["NHL", "nhl", "NCAAH", "NCAAWH"])
    def test_hockey_leagues(self, league):
        assert league_family(league) == "hockey"

    @pytest.mark.parametrize("league", ["NFL", "NCAAF", "MLB", "Soccer", "", None])
    def test_leagues_without_play_coordinates(self, league):
        assert league_family(league) is None

    def test_locate_returns_none_for_unsupported_league(self):
        assert locate("NFL", 10, 10) is None
        assert audio_params("MLB", 10, 10) is None


class TestHasCoordinate:
    def test_accepts_a_real_location(self):
        assert has_coordinate({"coordinate": {"x": 21, "y": 7}})

    def test_rejects_espn_sentinel(self):
        # What ESPN sends for substitutions, timeouts and free throws.
        assert not has_coordinate({"coordinate": {"x": -214748340, "y": -214748365}})

    def test_rejects_missing_or_malformed(self):
        assert not has_coordinate({})
        assert not has_coordinate({"coordinate": None})
        assert not has_coordinate({"coordinate": {}})
        assert not has_coordinate({"coordinate": {"x": 10}})
        assert not has_coordinate({"coordinate": {"x": "10", "y": "4"}})

    def test_accepts_zero_and_negative_coordinates(self):
        # Hockey runs negative, and basketball x reaches 0 on the sideline.
        assert has_coordinate({"coordinate": {"x": 0, "y": 0}})
        assert has_coordinate({"coordinate": {"x": -99, "y": -42}})


class TestBasketballGeometry:
    def test_basket_is_the_origin_of_distance(self):
        # Dunks and layups cluster here across real games.
        assert basketball_location(25, 3).distance_ft == pytest.approx(0.0)

    def test_corner_three_measures_about_twenty_two_feet(self):
        # The NBA corner line is 22 ft; this is what pins the basket at (25, 3).
        corner = basketball_location(3, 3)
        assert corner.distance_ft == pytest.approx(22.0, abs=0.5)

    def test_top_of_the_arc_measures_about_twenty_four_feet(self):
        # 23.75 ft at the top of the key.
        assert basketball_location(25, 27).distance_ft == pytest.approx(24.0, abs=0.5)

    def test_pan_follows_the_court_width(self):
        assert basketball_location(0, 10).pan == pytest.approx(-1.0)
        assert basketball_location(25, 10).pan == pytest.approx(0.0)
        assert basketball_location(50, 10).pan == pytest.approx(1.0)

    def test_basket_sits_where_the_venue_tour_puts_it(self):
        # BasketballCourtTourView places the attacking basket at field_y +43.
        assert basketball_location(25, 3).field_y == pytest.approx(43.0)

    def test_field_x_is_centred_on_the_court(self):
        assert basketball_location(25, 20).field_x == pytest.approx(0.0)
        assert basketball_location(10, 20).field_x == pytest.approx(-15.0)

    @pytest.mark.parametrize(
        "x,y,expected",
        [
            (25, 3, "at the rim"),
            (25, 9, "in the paint, middle"),
            (25, 18, "short mid-range, middle"),
            (3, 3, "from three, left side"),
            (47, 3, "from three, right side"),
        ],
    )
    def test_descriptions(self, x, y, expected):
        assert basketball_location(x, y).description == expected

    def test_a_heave_is_described_with_its_distance(self):
        description = basketball_location(25, 80).description
        assert description.startswith("deep,")
        assert "77 feet" in description


class TestHockeyGeometry:
    def test_goal_mouth_is_the_origin_of_distance(self):
        # Standard NHL goal line, 11 ft off the end boards.
        assert hockey_location(89, 0).distance_ft == pytest.approx(0.0)
        assert hockey_location(-89, 0).distance_ft == pytest.approx(0.0)

    def test_espn_axes_are_transposed_into_the_tour_frame(self):
        # ESPN x is the rink's length; the tour's field_y is the length.
        location = hockey_location(60, -20)
        assert location.field_y == pytest.approx(60.0)
        assert location.field_x == pytest.approx(-20.0)

    def test_goal_lines_sit_where_the_venue_tour_puts_them(self):
        # HockeyRinkTourView places the goal lines at field_y ±89.
        assert hockey_location(89, 0).field_y == pytest.approx(89.0)

    def test_pan_follows_the_rink_width(self):
        assert hockey_location(0, -42.5).pan == pytest.approx(-1.0)
        assert hockey_location(0, 0).pan == pytest.approx(0.0)
        assert hockey_location(0, 42.5).pan == pytest.approx(1.0)

    def test_both_ends_measure_the_same_distance(self):
        # Which end is in the spoken label, not the tone, so a shot from the
        # slot sounds the same at either end of the ice.
        near = hockey_location(-80, 5)
        far = hockey_location(80, 5)
        assert near.distance_ft == pytest.approx(far.distance_ft)

    def test_each_end_is_named(self):
        assert hockey_location(-80, 0).description.startswith("near end")
        assert hockey_location(80, 0).description.startswith("far end")

    @pytest.mark.parametrize(
        "x,y,expected",
        [
            (80, 0, "far end, in the slot"),
            (-80, 0, "near end, in the slot"),
            (0, 0, "neutral zone, centre"),
            (10, 30, "neutral zone, right side"),
            (60, -30, "far end, from the point, left side"),
        ],
    )
    def test_descriptions(self, x, y, expected):
        assert hockey_location(x, y).description == expected

    def test_left_and_right_are_mirrored_at_the_near_end(self):
        # The same ESPN y is on opposite sides once you face each end's goal.
        far = hockey_location(70, 20)
        near = hockey_location(-70, 20)
        assert far.description.endswith("right side")
        assert near.description.endswith("left side")
        assert far.pan == pytest.approx(-near.pan)

    def test_sides_do_not_swap_at_the_red_line(self):
        assert hockey_location(5, 30).pan == pytest.approx(hockey_location(-5, 30).pan)
        assert hockey_location(-5, 30).description == "neutral zone, right side"

    def test_mirroring_leaves_the_raw_position_alone(self):
        # The venue tour plots field_x directly, so only pan and words flip.
        assert hockey_location(-70, 20).field_x == pytest.approx(20.0)

    @pytest.mark.parametrize(
        "x,y,expected",
        [
            (95, 0, "far end, behind the net"),
            (-95, 10, "near end, behind the net"),
            (97, 35, "far end, in the right corner"),
            (97, -35, "far end, in the left corner"),
            (-97, 35, "near end, in the left corner"),
            # In front of the goal line and wide is still a band, not a corner.
            (70, 30, "far end, from the point, right side"),
        ],
    )
    def test_behind_the_net_and_corners(self, x, y, expected):
        assert hockey_location(x, y).description == expected

    def test_coordinates_beyond_the_boards_are_clamped(self):
        location = hockey_location(140, 60)
        assert location.field_y == pytest.approx(100.0)
        assert location.field_x == pytest.approx(42.5)
        assert -1.0 <= location.pan <= 1.0


class TestAudioParams:
    def test_closer_plays_get_a_higher_note(self):
        rim_freq, _, _, _ = audio_params("NBA", 25, 3)
        three_freq, _, _, _ = audio_params("NBA", 25, 27)
        assert rim_freq > three_freq

    def test_slot_gets_a_higher_note_than_the_point(self):
        slot_freq, _, _, _ = audio_params("NHL", 85, 0)
        point_freq, _, _, _ = audio_params("NHL", 45, 0)
        assert slot_freq > point_freq

    def test_farther_plays_ring_longer(self):
        _, rim_ms, _, _ = audio_params("NBA", 25, 3)
        _, three_ms, _, _ = audio_params("NBA", 25, 27)
        assert three_ms > rim_ms

    def test_balance_runs_left_to_right(self):
        _, _, left, _ = audio_params("NBA", 0, 10)
        _, _, centre, _ = audio_params("NBA", 25, 10)
        _, _, right, _ = audio_params("NBA", 50, 10)
        assert left == pytest.approx(0.0)
        assert centre == pytest.approx(0.5)
        assert right == pytest.approx(1.0)

    @pytest.mark.parametrize("league", ["NBA", "NHL"])
    def test_every_note_is_in_the_pentatonic_scale(self, league):
        # One key across the whole app, same scale the iOS pitch engine uses.
        for x in range(-100, 101, 7):
            for y in range(-42, 83, 5):
                params = audio_params(league, x, y)
                assert params[0] in PENTATONIC_HZ

    @pytest.mark.parametrize("league", ["NBA", "NHL"])
    def test_output_stays_in_range_across_the_whole_surface(self, league):
        for x in range(-110, 111, 3):
            for y in range(-50, 91, 3):
                frequency, duration_ms, balance, description = audio_params(league, x, y)
                assert 200 <= frequency <= 2000
                assert 200 <= duration_ms <= 420
                assert 0.0 <= balance <= 1.0
                assert description
                assert not math.isnan(frequency)
