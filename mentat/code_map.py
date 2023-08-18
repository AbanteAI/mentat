import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Set, Tuple

from ipdb import set_trace


def get_git_root():
    try:
        git_root = (
            subprocess.check_output(["git", "rev-parse", "--show-toplevel"])
            .strip()
            .decode("utf-8")
        )
    except subprocess.CalledProcessError:
        git_root = None

    return git_root


def get_git_files():
    git_files = (
        subprocess.check_output(["git", "ls-files"]).decode("utf-8").splitlines()
    )

    return git_files


def _build_ctags():
    ctags: DefaultDict[str, Set[Tuple[str, ...]]] = defaultdict(set)

    git_root = get_git_root()
    if git_root is None:
        return
    git_file_paths = get_git_files()

    for file_path in git_file_paths:
        ctags_cmd = [
            "ctags",
            "--fields=+S",
            "--extras=-F",
            "--input-encoding=utf-8",
            "--output-format=json",
            "--output-encoding=utf-8",
            str(Path(git_root).joinpath(file_path)),
        ]
        output = subprocess.check_output(ctags_cmd, stderr=subprocess.PIPE).decode(
            "utf-8"
        )
        output_lines = output.splitlines()

        for output_line in output_lines:
            try:
                tag = json.loads(output_line)
            except json.decoder.JSONDecodeError as err:
                print(f"Error parsing ctags output: {err}")
                print(repr(output_line))
                continue

            scope = tag.get("scope")
            kind = tag.get("kind")
            name = tag.get("name")
            signature = tag.get("signature")

            last = name
            if signature:
                last += " " + signature

            res = [file_path]
            if scope:
                res.append(scope)
            res += [kind, last]

            ctags[file_path].add(tuple(res))

    return ctags


def _get_message(ctags: DefaultDict[str, Set[Tuple[str, ...]]]):
    file_maps = []
    for ctags in ctags.values():
        sorted_tags = sorted(ctags)

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
                output += indent + item + "\n"
                indent += tab
            last = tag

        file_maps.append(output)

    message = f"""
        Below is a map of all files tracked by git in this project. Let the user know 
        if you think they should add the complete source code of any files to this 
        chat.
    """
    message = message.strip()
    message = re.sub(r"[\n\s]+", " ", message)
    message += "\n\n" + "\n".join(file_maps)

    return message


def get_code_map_message():
    is_git_repo = True if get_git_root() is not None else False
    if not is_git_repo:
        return
    ctags = _build_ctags()
    if ctags is None:
        return
    message = _get_message(ctags)

    return message
