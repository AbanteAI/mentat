#!/usr/bin/env python
import argparse
import json
import os
from pathlib import Path

from spice.spice import get_model_from_name


def select_transcripts(
    file: str,
    model: str,
    count: int,
    skip_docs: bool,
    skip_config: bool,
    sort_by_complexity: bool,
):
    with open(file, "r") as f:
        commit_information = json.load(f)

    if sort_by_complexity:
        commit_information = sorted(
            commit_information,
            key=lambda info: info["complexity"],
            reverse=True,
        )

    transcripts = []
    for sha, info in commit_information.items():
        if len(transcripts) >= count:
            break
        if skip_docs and info["documentation"]:
            continue
        if skip_config and info["configuration"]:
            continue
        if count_tokens(json.dumps(info["mocked_conversation"]), model) > get_model_from_name(model).context_length:
            continue
        transcripts.append(info["mocked_conversation"])

    return transcripts


if __name__ == "__main__":
    # Run after git_log_to_transcripts.py
    parser = argparse.ArgumentParser(description="Make a jsonl for training for a direcotry with commit information")
    parser.add_argument(
        "--file",
        type=str,
        default="repos/mentat/commit_information.json",
        help="The commit information file to convert to transcripts",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-3.5-turbo-0613",
        help="The model to compute token counts with respect to",
    )
    parser.add_argument(
        "--skip-docs",
        action="store_true",
        help="Skip transcripts that are only documentation",
    )
    parser.add_argument(
        "--skip-config",
        action="store_true",
        help="Skip transcripts that are only configuration",
    )
    parser.add_argument(
        "--sort-by-complexity",
        action="store_true",
        help="Return the transcripts GPT judged to be most complicated",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="The number of commits to convert to transcripts",
    )
    args = parser.parse_args()
    transcripts = select_transcripts(
        args.file,
        args.model,
        args.count,
        args.skip_docs,
        args.skip_config,
        args.sort_by_complexity,
    )
    directory = Path(os.path.dirname(args.file))

    with open(directory / "transcripts.jsonl", "w") as f:
        for transcript in transcripts:
            f.write(json.dumps(transcript) + "\n")
