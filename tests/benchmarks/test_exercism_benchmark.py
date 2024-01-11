
import json
from unittest.mock import MagicMock, patch
import webbrowser
import pytest
import os
from benchmarks.exercism_practice import run_exercism_benchmark
from textwrap import dedent


@pytest.fixture
def mock_webbrowser():
    with patch("webbrowser.open") as mock:
        yield mock

def test_run_exercism_benchmark(mock_webbrowser, mock_call_llm_api):
    os.chdir("exercism-python")
    mock_call_llm_api.set_streamed_values([dedent("""\
            @@start
            {
                "file": "exercises/practice/accumulate/accumulate.py",
                "action": "replace",
                "start-line": 1,
                "end-line": 2
            }
            @@code
            def accumulate(collection, operation):
                result = []
                for item in collection:
                    result.append(operation(item))
                return result
            @@end"""),
            dedent("""\
            test

            @@start
            {
                "file": "exercises/practice/acronym/acronym.py",
                "action": "replace",
                "start-line": 1,
                "end-line": 2
            }
            @@code
            import re

            def abbreviate(words):
                # Remove all punctuation except hyphens
                words_cleaned = re.sub(r'[^\\w\\s-]', '', words)
                # Replace hyphens with spaces to separate words
                words_cleaned = words_cleaned.replace('-', ' ')
                # Split the words and take the first letter of each, then join and convert to uppercase
                return ''.join(word[0].upper() for word in words_cleaned.split())
            @@end"""),
            dedent("""\
            @@start
            {
                "file": "exercises/practice/acronym/acronym.py",
                "action": "replace",
                "start-line": 4,
                "end-line": 9
            }
            @@code
            def abbreviate(words):
                # Remove all punctuation except hyphens and underscores
                words_cleaned = re.sub(r'[^\\w\\s-]|_', '', words)
                # Replace hyphens with spaces to separate words
                words_cleaned = words_cleaned.replace('-', ' ')
                # Split the words and take the first letter of each, then join and convert to uppercase
                return ''.join(word[0].upper() for word in words_cleaned.split())
            @@end"""),
            dedent("""\
            @@start
            {
                "file": "exercises/practice/high-scores/high_scores.py",
                "action": "replace",
                "start-line": 2,
                "end-line": 3
            }
            @@code
                def __init__(self, scores):
                    self.scores = scores

                def highest_score(self):
                    return max(self.scores)

                def latest_score(self):
                    return self.scores[-1]

                def top_three_scores(self):
                    return sorted(self.scores, reverse=True)[:3]
            @@end"""),
            dedent("""\
            @@start
            {
                "file": "exercises/practice/high-scores/high_scores.py",
                "action": "replace",
                "start-line": 5,
                "end-line": 6
            }
            @@code
                def personal_best(self):
                    return max(self.scores)
            @@end

            @@start
            {
                "file": "exercises/practice/high-scores/high_scores.py",
                "action": "replace",
                "start-line": 8,
                "end-line": 9
            }
            @@code
                def latest(self):
                    return self.scores[-1]
            @@end

            @@start
            {
                "file": "exercises/practice/high-scores/high_scores.py",
                "action": "replace",
                "start-line": 11,
                "end-line": 12
            }
            @@code
                def personal_top_three(self):
                    return sorted(self.scores, reverse=True)[:3]
            @@end""")])
    run_exercism_benchmark(
            ["accumulate", "acronym", "high-scores"],
            1,
            2,
            1,
            "python",
            )
    with open("results.json") as f:
        results = json.load(f)
    print(results)
