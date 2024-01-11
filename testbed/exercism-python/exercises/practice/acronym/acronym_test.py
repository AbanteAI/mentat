# These tests are auto-generated with test data from:
# https://github.com/exercism/problem-specifications/tree/main/exercises/acronym/canonical-data.json
# File last updated on 2023-07-20

import unittest

from acronym import (
    abbreviate,
)


class AcronymTest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(abbreviate("Portable Network Graphics"), "PNG")

    def test_lowercase_words(self):
        self.assertEqual(abbreviate("Ruby on Rails"), "ROR")

    def test_punctuation(self):
        self.assertEqual(abbreviate("First In, First Out"), "FIFO")

    def test_all_caps_word(self):
        self.assertEqual(abbreviate("GNU Image Manipulation Program"), "GIMP")

    def test_punctuation_without_whitespace(self):
        self.assertEqual(abbreviate("Complementary metal-oxide semiconductor"), "CMOS")

    def test_very_long_abbreviation(self):
        self.assertEqual(
            abbreviate(
                "Rolling On The Floor Laughing So Hard That My Dogs Came Over And Licked Me"
            ),
            "ROTFLSHTMDCOALM",
        )

    def test_consecutive_delimiters(self):
        self.assertEqual(abbreviate("Something - I made up from thin air"), "SIMUFTA")

    def test_apostrophes(self):
        self.assertEqual(abbreviate("Halley's Comet"), "HC")

    def test_underscore_emphasis(self):
        self.assertEqual(abbreviate("The Road _Not_ Taken"), "TRNT")
