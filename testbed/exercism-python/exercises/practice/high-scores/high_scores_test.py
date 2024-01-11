# These tests are auto-generated with test data from:
# https://github.com/exercism/problem-specifications/tree/main/exercises/high-scores/canonical-data.json
# File last updated on 2023-07-19

import unittest

from high_scores import (
    HighScores,
)


class HighScoresTest(unittest.TestCase):
    def test_list_of_scores(self):
        scores = [30, 50, 20, 70]
        expected = [30, 50, 20, 70]
        self.assertEqual(HighScores(scores).scores, expected)

    def test_latest_score(self):
        scores = [100, 0, 90, 30]
        expected = 30
        self.assertEqual(HighScores(scores).latest(), expected)

    def test_personal_best(self):
        scores = [40, 100, 70]
        expected = 100
        self.assertEqual(HighScores(scores).personal_best(), expected)

    def test_personal_top_three_from_a_list_of_scores(self):
        scores = [10, 30, 90, 30, 100, 20, 10, 0, 30, 40, 40, 70, 70]
        expected = [100, 90, 70]
        self.assertEqual(HighScores(scores).personal_top_three(), expected)

    def test_personal_top_highest_to_lowest(self):
        scores = [20, 10, 30]
        expected = [30, 20, 10]
        self.assertEqual(HighScores(scores).personal_top_three(), expected)

    def test_personal_top_when_there_is_a_tie(self):
        scores = [40, 20, 40, 30]
        expected = [40, 40, 30]
        self.assertEqual(HighScores(scores).personal_top_three(), expected)

    def test_personal_top_when_there_are_less_than_3(self):
        scores = [30, 70]
        expected = [70, 30]
        self.assertEqual(HighScores(scores).personal_top_three(), expected)

    def test_personal_top_when_there_is_only_one(self):
        scores = [40]
        expected = [40]
        self.assertEqual(HighScores(scores).personal_top_three(), expected)

    def test_latest_score_after_personal_top_scores(self):
        scores = [70, 50, 20, 30]
        expected = 30
        highscores = HighScores(scores)
        highscores.personal_top_three()
        self.assertEqual(highscores.latest(), expected)

    def test_scores_after_personal_top_scores(self):
        scores = [30, 50, 20, 70]
        expected = [30, 50, 20, 70]
        highscores = HighScores(scores)
        highscores.personal_top_three()
        self.assertEqual(highscores.scores, expected)

    def test_latest_score_after_personal_best(self):
        scores = [20, 70, 15, 25, 30]
        expected = 30
        highscores = HighScores(scores)
        highscores.personal_best()
        self.assertEqual(highscores.latest(), expected)

    def test_scores_after_personal_best(self):
        scores = [20, 70, 15, 25, 30]
        expected = [20, 70, 15, 25, 30]
        highscores = HighScores(scores)
        highscores.personal_best()
        self.assertEqual(highscores.scores, expected)
