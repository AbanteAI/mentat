# Our code map implementation was inspired by Aider's repo map, which also uses ctags to create a map of a project.
# Aider: https://github.com/paul-gauthier/aider

import json
import logging
import subprocess
import tempfile
from functools import cache
from pathlib import Path
from typing import Any

CTAG = tuple[str | None, str, str, str | None, int]


def get_ctags(abs_file_path: Path, exclude_signatures: bool = False) -> set[CTAG]:
    # Create ctags from executable in a subprocess
    ctags_cmd_args = [
        "--extras=-F",
        "--input-encoding=utf-8",
        "--output-format=json",
        "--output-encoding=utf-8",
        "--fields=+n",
    ]
    if exclude_signatures:
        ctags_cmd_args.append("--fields=-s")
    else:
        ctags_cmd_args.append("--fields=+S")
    ctags_cmd = ["ctags", *ctags_cmd_args, str(abs_file_path)]
    output = subprocess.check_output(
        ctags_cmd, stderr=subprocess.DEVNULL, start_new_session=True, text=True
    ).strip()
    output_lines = output.splitlines()

    # Extract subprocess stdout into python objects
    ctags = set[CTAG]()
    for output_line in output_lines:
        try:
            tag = json.loads(output_line)
        except json.decoder.JSONDecodeError as err:
            logging.error(f"Error parsing ctags output: {err}\n{repr(output_line)}")
            continue

        scope: str | None = tag.get("scope")
        kind: str = tag.get("kind")
        name: str = tag.get("name")
        signature: str | None = tag.get("signature")
        line_number: int = tag.get("line")

        ctags.add((scope, kind, name, signature, line_number))
    return ctags
