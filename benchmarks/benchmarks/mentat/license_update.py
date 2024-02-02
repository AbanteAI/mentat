import importlib

from mentat.config import Config

title = "License Update"

description = """
This benchmark tests the ability of Mentat to add a license to the allowed license list.
"""

prompts = [
    # This one fails too by not putting HPND second. But it was the only prompt
    # I could make that consistently passes verify.
    'Add "HPND" second in the list of allowed licenses.',
    # This one generally fails with an off by one error. Putting HPND
    # outside of the list.
    'Add "HPND" to the list of allowed licenses.',
    # About half the time GPT spells out Historical Permission Notice and Disclaimer
    "Add HPND to the list of allowed licenses.",
]

repo = "https://github.com/AbanteAI/mentat"
commit = "b0848711c36e0c2fe9619ebb2b77dc6d27396ff2"
minimum_context = ["tests/license_check.py:11-22"]
paths = []

config = Config(
    auto_context_tokens=8000,
    maximum_context=8000,
)


def verify():
    try:
        import benchmark_repos.mentat.tests.license_check as license_check

        importlib.reload(license_check)
        return set(license_check.accepted_licenses) == set(
            [
                "BSD License",
                "Apache Software License",
                "MIT License",
                "MIT",
                "Mozilla Public License 2.0 (MPL 2.0)",
                "Python Software Foundation License",
                "Apache 2.0",
                "BSD 3-Clause",
                "ISC License (ISCL)",
                "HPND",
            ]
        )
    except IndentationError:
        return False
