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


def _make_ctags_human_readable(ctags: set[CTAG]) -> list[str]:
    cleaned_tags = set[tuple[str, ...]]()
    for tag in ctags:
        (scope, kind, name, signature, _) = tag  # Line number currently unused

        last = name
        if signature:
            last += " " + signature

        res: list[Any] = []
        if scope:
            res.append(scope)
        res += [kind, last]

        cleaned_tags.add(tuple(res))

    sorted_tags = sorted(cleaned_tags)
    output = ""
    last = [None] * len(sorted_tags[0])
    tab = "\t"
    for tag in sorted_tags:
        tag = list(tag)

        num_common = 0
        for i in range(len(last) + 1):
            if i == len(last):
                break
            if last[i] != tag[i]:
                num_common = i
                break

        indent = tab * num_common
        rest = tag[num_common:]

        for item in rest:
            output += indent + str(item) + "\n"
            indent += tab
        last = tag
    return output.splitlines()


def get_code_map(abs_file_path: Path, exclude_signatures: bool = False) -> list[str]:
    ctags = get_ctags(abs_file_path, exclude_signatures)
    if not ctags:
        return []
    return _make_ctags_human_readable(ctags)


@cache
def check_ctags_disabled() -> str | None:
    try:
        cmd = ["ctags", "--version"]
        output = subprocess.check_output(cmd, stderr=subprocess.PIPE).decode("utf-8")
        output = output.lower()

        cmd = " ".join(cmd)
        if "universal ctags" not in output:
            return f"{cmd} does not claim to be universal ctags"
        if "+json" not in output:
            return f"{cmd} does not list +json support"

        with tempfile.TemporaryDirectory() as tempdir:
            hello_py = Path(tempdir) / "hello.py"
            with open(hello_py, "w", encoding="utf-8") as f:
                f.write("def hello():\n    print('Hello, world!')\n")
            get_code_map(hello_py)
        return
    except FileNotFoundError:
        return "ctags executable not found"
    except Exception as e:
        return f"error running universal-ctags: {e}"
