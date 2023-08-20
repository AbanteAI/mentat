import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List

from ipdb import set_trace

from .llm_api import count_tokens


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


def _get_code_map(root: str, file_path: str, exclude_signatures: bool = False):
    # Create ctags from executable in a subprocess
    ctags_cmd_args = [
        "--extras=-F",
        "--input-encoding=utf-8",
        "--output-format=json",
        "--output-encoding=utf-8",
    ]
    if exclude_signatures:
        ctags_cmd_args.append("--fields=-s")
    else:
        ctags_cmd_args.append("--fields=+S")
    ctags_cmd = ["ctags", *ctags_cmd_args, str(Path(root).joinpath(file_path))]
    output = subprocess.check_output(ctags_cmd, stderr=subprocess.PIPE).decode("utf-8")
    output_lines = output.splitlines()

    # Extract subprocess stdout into python objects
    ctags = set()
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

        ctags.add(tuple(res))

    # Build LLM-readable string representation of ctag objects
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

    return output


def _get_file_map(file_paths: List[str]):
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

    file_map_tree = tree_to_string(tree)

    return file_map_tree


class CodeMap:
    def __init__(self, git_root: str, token_limit: int | None = None):
        self.git_root = git_root
        self.token_limit = token_limit

        self.ctags_disabled = True
        self.ctags_disabled_reason = ""

        self._check_ctags_executable()

    def _check_ctags_executable(self):
        try:
            cmd = ["ctags", "--version"]
            output = subprocess.check_output(cmd, stderr=subprocess.PIPE).decode(
                "utf-8"
            )
            output = output.lower()

            cmd = " ".join(cmd)
            if "universal ctags" not in output:
                self.ctags_disabled_reason = (
                    f"{cmd} does not claim to be universal ctags"
                )
                return
            if "+json" not in output:
                self.ctags_disabled_reason = f"{cmd} does not list +json support"
                return

            with tempfile.TemporaryDirectory() as tempdir:
                hello_py = os.path.join(tempdir, "hello.py")
                with open(hello_py, "w", encoding="utf-8") as f:
                    f.write("def hello():\n    print('Hello, world!')\n")
                _get_code_map(tempdir, hello_py)
        except FileNotFoundError:
            self.ctags_disabled_reason = f"ctags executable not found"
            return
        except Exception as e:
            self.ctags_disabled_reason = f"error running universal-ctags: {e}"
            return

        self.ctags_disabled = False

    def _get_code_map_message(
        self, root: str, file_paths: List[str], exclude_signatures: bool = False
    ) -> str | None:
        code_maps = []
        code_maps_token_count = 0
        for file_path in file_paths:
            code_map = _get_code_map(
                root, file_path, exclude_signatures=exclude_signatures
            )
            code_map_token_count = count_tokens(code_map)

            if self.token_limit is not None and code_map_token_count > self.token_limit:
                if exclude_signatures is True:
                    return
                return self._get_code_map_message(
                    root, file_paths, exclude_signatures=True
                )

            code_maps.append(code_map)
            code_maps_token_count += code_map_token_count

        message = f"""
            Below is a read-only code map of all files tracked by git in this project. 
            If you need to edit any of the files in this code map that aren't in the current context,
            don't try to edit them and instead give the user the filepaths of what they should add to this context.
        """
        message = message.strip()
        message = re.sub(r"[\n\s]+", " ", message)
        message += "\n\n" + "\n".join(code_maps)

        message_token_count = count_tokens(message)
        if self.token_limit is not None and message_token_count > self.token_limit:
            if exclude_signatures is True:
                return
            return self._get_code_map_message(root, file_paths, exclude_signatures=True)

        return message

    def _get_file_map_message(self, file_paths: List[str]) -> str | None:
        file_map_tree = _get_file_map(file_paths)

        message = f"""
            Below is a read-only code map of all files tracked by git in this project. 
            If you need to edit any of the files in this code map that aren't in the current context,
            don't try to edit them and instead give the user the filepaths of what they should add to this context.
        """
        message = message.strip()
        message = re.sub(r"[\n\s]+", " ", message)
        message += "\n\n" + file_map_tree

        message_token_count = count_tokens(message)
        if self.token_limit is not None and message_token_count > self.token_limit:
            return

        return message

    def get_message(self):
        git_file_paths = get_git_files(self.git_root)

        if not self.ctags_disabled:
            code_map_message = self._get_code_map_message(self.git_root, git_file_paths)
            if code_map_message is not None:
                return code_map_message

        file_map_message = self._get_file_map_message(git_file_paths)
        if file_map_message is not None:
            return file_map_message
