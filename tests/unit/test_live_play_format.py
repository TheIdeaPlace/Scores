"""Tests for how a live game's current play is laid out in a scores list.

Both the All Scores view and a single league's list use live_play_format, so
a live game reads the same in each. What a screen reader user hears is the
point: no clock spoken twice, away team before home, plays cut at a word, and
team names that match the rest of the list.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import live_play_format as lpf  # noqa: E402

TEAMS = [
    {"name": "Cardinals", "score": "35", "home_away": "home"},
    {"name": "Seminoles", "score": "14", "home_away": "away"},
]

FOOTBALL = ("Florida State Seminoles 14 at Louisville Cardinals 35 | Timeout Louisville, clock 11:11"
            "\n11:11 Q4 | 4th & 7 | FSU: 4 plays")

BASEBALL = ("New York Yankees 3 at Boston Red Sox 2"
            "\nRunner on 1st | 1-2 count, 2 outs | At bat: Some Batter"
            "\nLast: Single to left")


class TestFootball:
    def test_clock_already_on_the_play_line_is_not_repeated(self):
        text = lpf.format_live_game("NCAAF", TEAMS, "11:11 - 4th", FOOTBALL, "")
        assert text == FOOTBALL
        assert text.count("11:11") == 2  # the play's own "clock 11:11" and the line-2 clock

    def test_status_without_a_clock_is_kept(self):
        text = lpf.format_live_game("NFL", TEAMS, "Halftime", FOOTBALL, "")
        assert text.endswith("FSU: 4 plays (Halftime)")

    def test_status_with_a_different_clock_is_kept(self):
        text = lpf.format_live_game("NFL", TEAMS, "10:40 - 4th", FOOTBALL, "")
        assert text.endswith("(10:40 - 4th)")

    def test_single_line_play_lists_away_team_first(self):
        text = lpf.format_live_game("NFL", TEAMS, "5:00 - 2nd", "Two-minute warning", "")
        assert text == "Seminoles 14 at Cardinals 35 (5:00 - 2nd) | Two-minute warning"


class TestBaseball:
    def test_three_lines_with_inning_after_the_teams(self):
        text = lpf.format_live_game("MLB", TEAMS, "Top 5th", BASEBALL, "")
        lines = text.split("\n")
        assert lines[0] == "New York Yankees 3 at Boston Red Sox 2 (Top 5th)"
        assert lines[1:] == BASEBALL.split("\n")[1:]

    def test_summary_fallback_line_lists_away_team_first(self):
        text = lpf.format_live_game("MLB", TEAMS, "Top 5th", "P: A Pitcher | AB: A Batter | Count: 0-0", "")
        assert text.startswith("Seminoles 14 at Cardinals 35 (Top 5th) | P: A Pitcher")

    def test_teams_without_home_away_keep_their_order(self):
        teams = [{"name": "One", "score": "1"}, {"name": "Two", "score": "2"}]
        assert lpf.score_line(teams) == "One 1 at Two 2"


class TestOtherLeagues:
    def test_play_follows_the_usual_game_text(self):
        text = lpf.format_live_game("NHL", TEAMS, "End of 2nd", "Goal by Someone", "Ducks 2 at Jets 0 [End of 2nd]")
        assert text == "Ducks 2 at Jets 0 [End of 2nd] | Goal by Someone"

    def test_long_play_is_cut_at_a_word_and_marked(self):
        play = "Golden State Valkyries Full timeout called with the shot clock running down " * 3
        text = lpf.format_live_game("WNBA", TEAMS, "", play, "Valkyries 8 at Aces 14")
        tail = text.split(" | ", 1)[1]
        assert tail.endswith("...")
        assert play.startswith(tail[:-3])
        assert len(tail) <= lpf.PLAY_LIMIT + 3
        assert not tail[:-3].endswith(" ")

    def test_short_play_untouched(self):
        assert lpf.short_play("Timeout") == "Timeout"

    def test_single_unbroken_word_is_cut_hard(self):
        assert lpf.short_play("x" * 80, limit=10) == "x" * 10 + "..."


class TestListTeamNames:
    GAME = {"competitions": [{"competitors": [
        {"team": {"displayName": "Boston Red Sox"}},
        {"team": {"displayName": "New York Yankees"}},
    ]}]}
    LIST_TEAMS = [{"name": "Red Sox"}, {"name": "Yankees"}]

    def test_play_text_uses_the_names_the_list_uses(self):
        names = lpf.list_team_names(self.GAME, self.LIST_TEAMS)
        text = lpf.use_list_team_names(BASEBALL, names)
        assert text.split("\n")[0] == "Yankees 3 at Red Sox 2"

    def test_only_the_first_line_is_renamed(self):
        names = {"Boston Red Sox": "Red Sox"}
        text = lpf.use_list_team_names("Boston Red Sox 1\nLast: Boston Red Sox pitching change", names)
        assert text == "Red Sox 1\nLast: Boston Red Sox pitching change"

    def test_college_names_already_match(self):
        game = {"competitions": [{"competitors": [{"team": {"displayName": "Louisville Cardinals"}}]}]}
        names = lpf.list_team_names(game, [{"name": "Louisville Cardinals"}])
        assert lpf.use_list_team_names(FOOTBALL, names) == FOOTBALL

    def test_longer_name_replaced_before_a_name_it_contains(self):
        names = {"Washington": "W", "Washington State Cougars": "Cougars"}
        assert lpf.use_list_team_names("Washington State Cougars 6 at Washington 0", names) == "Cougars 6 at W 0"

    def test_missing_competitions_give_no_names(self):
        assert lpf.list_team_names({}, self.LIST_TEAMS) == {}
        assert lpf.list_team_names({"competitions": []}, self.LIST_TEAMS) == {}


class TestClockMatch:
    def test_shorter_clock_inside_a_longer_one_is_not_a_repeat(self):
        play = "Team A 7 at Team B 3 | Pass\n11:11 Q4 | 1st & 10 | TB: 2 plays"
        assert lpf.format_football([], "1:11 - 4th", play).endswith("(1:11 - 4th)")

    def test_same_clock_is_a_repeat(self):
        play = "Team A 7 at Team B 3 | Pass\n1:11 Q4 | 1st & 10 | TB: 2 plays"
        assert "(1:11 - 4th)" not in lpf.format_football([], "1:11 - 4th", play)


class TestFootballScoreLineOnly:
    def test_status_gets_its_own_line(self):
        play = "Away Team 3 at Home Team 7 | Kickoff"
        assert lpf.format_football([], "Halftime", play) == f"{play}\nHalftime"


class TestRenameLeavesThePlay:
    def test_play_text_keeps_espns_names(self):
        names = {"Kansas City Chiefs": "Chiefs"}
        text = "Kansas City Chiefs 7 at X 3 | Kansas City Chiefs timeout\n5:00 Q2"
        assert lpf.use_list_team_names(text, names) == "Chiefs 7 at X 3 | Kansas City Chiefs timeout\n5:00 Q2"


class TestAwayThenHome:
    def test_home_listed_first_comes_out_away_first(self):
        # ESPN lists home first; "Colts at Commanders" must read 30-13, not 13-30.
        teams = [{"name": "Commanders", "score": "13", "home_away": "home"},
                 {"name": "Colts", "score": "30", "home_away": "away"}]
        assert [t["score"] for t in lpf.away_then_home(teams)] == ["30", "13"]

    def test_unknown_sides_keep_their_order(self):
        teams = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
        assert [t["name"] for t in lpf.away_then_home(teams)] == ["A", "B"]


def test_list_name_containing_the_full_name_is_not_doubled():
    names = {"Arizona Wildcats": "#5 Arizona Wildcats"}
    for text in ("Arizona Wildcats 56 vs UCLA 62 | play", "#5 Arizona Wildcats 56 vs UCLA 62 | play"):
        assert lpf.use_list_team_names(text, names) == "#5 Arizona Wildcats 56 vs UCLA 62 | play"
