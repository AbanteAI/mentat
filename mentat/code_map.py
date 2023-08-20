import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, List, Set, Tuple

from ipdb import set_trace

from .llm_api import count_tokens


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


def get_git_files(git_root: str, absolute_paths: bool = False) -> List[str]:
    git_files_ = (
        subprocess.check_output(["git", "ls-files"], cwd=git_root)
        .decode("utf-8")
        .splitlines()
    )
    if absolute_paths:
        git_files = [str(Path(git_root).joinpath(f)) for f in git_files_]
    else:
        git_files = git_files_

    return git_files


def _build_ctags(root: str, file_paths: List[str]):
    ctags: DefaultDict[str, Set[Tuple[str, ...]]] = defaultdict(set)

    for file_path in file_paths:
        ctags_cmd = [
            "ctags",
            "--fields=+S",
            "--extras=-F",
            "--input-encoding=utf-8",
            "--output-format=json",
            "--output-encoding=utf-8",
            str(Path(root).joinpath(file_path)),
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


def _get_code_map_message(ctags: DefaultDict[str, Set[Tuple[str, ...]]]):
    file_maps = []
    for ctags_ in ctags.values():
        sorted_tags = sorted(ctags_)

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
        Below is a read-only code map of all files tracked by git in this project. 
        If you need to edit any of the files in this code map that aren't in the current context,
        don't try to edit them and instead give the user the filepaths of what they should add to this context.
    """
    message = message.strip()
    message = re.sub(r"[\n\s]+", " ", message)
    message += "\n\n" + "\n".join(file_maps)

    return message


def _get_file_map_message(file_paths: List[str]):
    tree = {}
    for file_path in file_paths:
        parts = file_path.split("/")
        node = tree
        for part in parts:
            if part not in node:
                node[part] = {}
            node = node[part]

    def tree_to_string(tree, indent=0):
        s = ""
        sorted_keys = sorted(tree.keys())
        for key in sorted_keys:
            s += "\t" * indent + key + "\n"
            s += tree_to_string(tree[key], indent + 1)
        return s

    return tree_to_string(tree)


def get_code_map_message(token_limit: int | None = None):
    git_root = get_git_root()
    if not git_root:
        return
    git_file_paths = get_git_files(git_root)
    ctags = _build_ctags(git_root, git_file_paths)

    code_map_message = _get_code_map_message(ctags)
    code_map_message_token_count = count_tokens(code_map_message)
    if token_limit is None or code_map_message_token_count <= token_limit:
        return code_map_message

    file_map_message = _get_file_map_message(git_file_paths)
    file_map_message_token_count = count_tokens(file_map_message)
    if file_map_message_token_count <= token_limit:
        return file_map_message
