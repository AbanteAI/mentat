import glob
import logging
import math
import mimetypes
import os
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from termcolor import cprint

from .change_conflict_resolution import (
    resolve_insertion_conflicts,
    resolve_non_insertion_conflicts,
)
from .code_change import CodeChange, CodeChangeAction
from .config_manager import ConfigManager
from .user_input_manager import UserInputManager

# mimetypes is OS dependent, so it's best to add as many extensions as we can
# fmt: off
default_filetype_include_list = [
    ".py",      # Python
    ".java",    # Java
    ".scala",   # Scala
    ".kt",      # Kotlin
    ".php",     # PHP
    ".html",    # HTML
    ".css",     # CSS
    ".less",    # Less
    ".scss",    # SCSS
    ".js",      # Javascript
    ".ts",      # Typescript
    ".c",       # C
    ".cpp",     # C++
    ".h",       # C Header
    ".cs",      # C#
    ".go",      # Go
    ".rs",      # Rust
    ".rb",      # Ruby
    ".swift",   # Swift
    ".lua",     # Lua
    ".pl",      # Perl
    ".sql",     # SQL
    ".r",       # R
    ".m",       # objective-c
    ".sh",      # shell scripts
    ".f",       # fortran
    ".jsx",     # javascript react
    ".tsx",     # typescript react
]
default_filetype_exclude_list = []
# fmt: on


def _get_git_diff_for_path(git_root, path: str) -> str:
    return subprocess.check_output(["git", "diff", path], cwd=git_root).decode("utf-8")


def _get_paths_with_git_diffs(git_root) -> set[str]:
    changed = subprocess.check_output(
        ["git", "diff", "--name-only"], cwd=git_root, text=True
    ).split("\n")
    return set(
        map(lambda path: os.path.realpath(os.path.join(git_root, Path(path))), changed)
    )


def _get_git_root_for_path(path) -> str:
    if os.path.isdir(path):
        dir_path = path
    else:
        dir_path = os.path.dirname(path)
    try:
        git_root = (
            subprocess.check_output(
                [
                    "git",
                    "rev-parse",
                    "--show-toplevel",
                ],
                cwd=os.path.realpath(dir_path),
                stderr=subprocess.DEVNULL,
            )
            .decode("utf-8")
            .strip()
        )
        # call realpath to resolve symlinks, so all paths match
        return os.path.realpath(git_root)
    except subprocess.CalledProcessError:
        logging.error(f"File {path} isn't part of a git project.")
        exit()


def _get_shared_git_root_for_paths(paths) -> str:
    git_roots = set()
    for path in paths:
        git_root = _get_git_root_for_path(path)
        git_roots.add(git_root)
    if not paths:
        git_root = _get_git_root_for_path(os.getcwd())
        git_roots.add(git_root)

    if len(git_roots) > 1:
        logging.error(
            "All paths must be part of the same git project! Projects provided:"
            f" {git_roots}"
        )
        exit()
    elif len(git_roots) == 0:
        logging.error("No git projects provided.")
        exit()

    return git_roots.pop()


def _build_path_tree(file_paths, git_root):
    tree = {}
    for path in file_paths:
        path = os.path.relpath(path, git_root)
        parts = Path(path).parts
        current_level = tree
        for part in parts:
            if part not in current_level:
                current_level[part] = {}
            current_level = current_level[part]
    return tree


def _print_path_tree(tree, non_text_files, changed_files, cur_path, prefix=""):
    keys = list(tree.keys())
    for i, key in enumerate(sorted(keys)):
        if i < len(keys) - 1:
            new_prefix = prefix + "│   "
            print(f"{prefix}├── ", end="")
        else:
            new_prefix = prefix + "    "
            print(f"{prefix}└── ", end="")

        cur = os.path.join(cur_path, key)
        star = "* " if cur in changed_files else ""
        if tree[key]:
            color = "blue"
        elif cur in non_text_files:
            color = "yellow"
        elif star:
            color = "green"
        else:
            color = None
        cprint(f"{star}{key}", color)
        if tree[key]:
            _print_path_tree(tree[key], non_text_files, changed_files, cur, new_prefix)


def _is_file_text(file_name):
    file_type, encoding = mimetypes.guess_type(file_name)
    return file_type and file_type.split("/")[0] == "text"


class CodeFileManager:
    def __init__(
        self,
        paths: Iterable[str],
        user_input_manager: UserInputManager,
        config: ConfigManager,
    ):
        # Make sure to apply user config last
        for file_type in default_filetype_include_list:
            mimetypes.add_type("text/default-include-list", file_type)
        for file_type in default_filetype_exclude_list:
            mimetypes.types_map.pop(file_type, None)

        for file_type in config.filetype_include_list():
            mimetypes.add_type("text/user-include-list", file_type)
        for file_type in config.filetype_exclude_list():
            mimetypes.types_map.pop(file_type, None)

        self.config = config
        self.git_root = _get_shared_git_root_for_paths(paths)
        self._set_file_paths(paths)
        self.user_input_manager = user_input_manager

        if self.file_paths:
            cprint("Files included in context:", "green")
        else:
            cprint("No files included in context.\n", "red")
            cprint("Git project: ", "green", end="")
        cprint(os.path.split(self.git_root)[1], "blue")
        _print_path_tree(
            _build_path_tree(self.file_paths + self.non_text_file_paths, self.git_root),
            self.non_text_file_paths,
            _get_paths_with_git_diffs(self.git_root),
            self.git_root,
        )

    def _set_file_paths(self, paths: Iterable[str] = None) -> None:
        invalid_paths = []
        for path in paths:
            if not os.path.exists(path):
                invalid_paths.append(path)
        if invalid_paths:
            cprint("Error:", "red", end=" ")
            cprint("The following paths do not exist:")
            print("\n".join(invalid_paths))
            print("Exiting...")
            exit()

        path_set = set()
        self.non_text_file_paths = []
        self.file_paths = []

        for path in paths:
            path = Path(path)
            if path.is_file():
                path_set.add(os.path.realpath(path))
            elif path.is_dir():
                non_git_ignored_files = set(
                    # git returns / seperated paths even on windows, convert so we can remove
                    # glob_excluded_files, which have windows paths on windows
                    os.path.normpath(path)
                    for path in filter(
                        lambda p: p != "",
                        subprocess.check_output(
                            # -c shows cached (regular) files, -o shows other (untracked/ new) files
                            ["git", "ls-files", "-c", "-o", "--exclude-standard"],
                            cwd=path,
                            text=True,
                        ).split("\n"),
                    )
                )
                glob_excluded_files = set(
                    file
                    for glob_path in self.config.file_exclude_glob_list()
                    # If the user puts a / at the beginning, it will try to look in root directory
                    for file in glob.glob(
                        pathname=glob_path.lstrip("/"),
                        root_dir=path,
                        recursive=True,
                    )
                )
                nonignored_files = non_git_ignored_files - glob_excluded_files

                non_text_files = filter(
                    lambda f: not _is_file_text(
                        os.path.realpath(os.path.join(path, f))
                    ),
                    nonignored_files,
                )
                self.non_text_file_paths.extend(
                    map(
                        lambda f: os.path.realpath(os.path.join(path, f)),
                        non_text_files,
                    )
                )
                text_files = filter(
                    _is_file_text,
                    map(
                        lambda f: os.path.realpath(os.path.join(path, f)),
                        nonignored_files,
                    ),
                )
                path_set.update(text_files)
        self.file_paths = list(path_set)

    def _read_file(self, abs_path) -> Iterable[str]:
        with open(abs_path, "r") as f:
            lines = f.read().split("\n")
        return lines

    def _read_all_file_lines(self) -> None:
        self.file_lines = dict()
        for abs_path in self.file_paths:
            self.file_lines[abs_path] = self._read_file(abs_path)

    def get_code_message(self):
        self._read_all_file_lines()
        code_message = ["Code Files:\n"]
        for abs_path in self.file_paths:
            rel_path = os.path.relpath(abs_path, self.git_root)
            code_message.append(rel_path)
            for i, line in enumerate(self.file_lines[abs_path], start=1):
                code_message.append(f"{i}:{line}")
            code_message.append("")
            git_diff_output = _get_git_diff_for_path(self.git_root, rel_path)
            if git_diff_output:
                code_message.append("Current git diff for this file:")
                code_message.append(f"{git_diff_output}")
        if self.non_text_file_paths:
            code_message.append("\nOther files:\n")
            code_message.extend(
                os.path.relpath(path, self.git_root)
                for path in self.non_text_file_paths
            )
        return "\n".join(code_message)

    def _handle_delete(self, delete_change):
        file_path = os.path.join(self.git_root, delete_change.file)
        if not os.path.exists(file_path):
            logging.error(f"Path {file_path} non-existent on delete")
            return

        cprint(f"Are you sure you want to delete {delete_change.file}?", "red")
        if self.user_input_manager.ask_yes_no(default_yes=False):
            logging.info(f"Deleting file {file_path}")
            cprint(f"Deleting {delete_change.file}...")
            self.file_paths.remove(file_path)
            os.remove(file_path)
        else:
            cprint(f"Not deleting {delete_change.file}")

    def _get_new_code_lines(self, changes) -> Iterable[str]:
        if len(set(map(lambda change: change.file, changes))) > 1:
            raise Exception("All changes passed in must be for the same file")

        changes = sorted(changes, reverse=True)

        # We resolve insertion conflicts twice because non-insertion conflicts
        # might move insert blocks outside of replace/delete blocks and cause
        # them to conflict again
        changes = resolve_insertion_conflicts(changes, self.user_input_manager, self)
        changes = resolve_non_insertion_conflicts(changes, self.user_input_manager)
        changes = resolve_insertion_conflicts(changes, self.user_input_manager, self)
        if not changes:
            return []

        rel_path = changes[0].file
        abs_path = os.path.join(self.git_root, rel_path)
        new_code_lines = self.file_lines[abs_path].copy()
        if new_code_lines != self._read_file(abs_path):
            logging.info(f"File '{rel_path}' changed while generating changes")
            cprint(
                (
                    f"File '{rel_path}' changed while generating; current file changes"
                    " will be erased. Continue?"
                ),
                color="light_yellow",
            )
            if not self.user_input_manager.ask_yes_no(default_yes=False):
                cprint(f"Not applying changes to file {rel_path}.")
                return None

        # Necessary in case the model needs to insert past the end of the file
        last_line = len(new_code_lines) + 1
        largest_changed_line = math.ceil(changes[0].last_changed_line)
        if largest_changed_line > last_line:
            new_code_lines += [""] * (largest_changed_line - last_line)

        min_changed_line = largest_changed_line + 1
        for i, change in enumerate(changes):
            if change.last_changed_line >= min_changed_line:
                raise ValueError(f"Change line number overlap in file {change.file}")
            min_changed_line = change.first_changed_line
            new_code_lines = change.apply(new_code_lines)
        return new_code_lines

    def write_changes_to_files(self, code_changes: list[CodeChange]) -> None:
        files_to_write = dict()
        file_changes = defaultdict(list)
        for code_change in code_changes:
            rel_path = code_change.file
            if code_change.action == CodeChangeAction.CreateFile:
                cprint(f"Creating new file {rel_path}", color="light_green")
                files_to_write[rel_path] = code_change.code_lines
            elif code_change.action == CodeChangeAction.DeleteFile:
                self._handle_delete(code_change)
            else:
                file_changes[rel_path].append(code_change)

        for file_path, changes in file_changes.items():
            new_code_lines = self._get_new_code_lines(changes)
            if new_code_lines:
                files_to_write[file_path] = new_code_lines

        for rel_path, code_lines in files_to_write.items():
            file_path = os.path.join(self.git_root, rel_path)
            # if changes created a new file and we are now writing to it, add it to context
            if file_path not in self.file_paths:
                logging.info(f"Adding new file {file_path} to context")
                self.file_paths.append(file_path)
            with open(file_path, "w") as f:
                f.write("\n".join(code_lines))
