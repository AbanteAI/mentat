import glob
import logging
import os
from pathlib import Path
from typing import Dict, Iterable
from collections import defaultdict

from termcolor import cprint

from .code_file import CodeFile
from .config_manager import ConfigManager
from .errors import UserError
from .git_handler import get_non_gitignored_files, get_paths_with_git_diffs, \
                         get_commit_history, get_commit_diff, get_branch_diff


def _is_file_text_encoded(file_path):
    try:
        # The ultimate filetype test
        with open(file_path) as f:
            f.read()
        return True
    except UnicodeDecodeError:
        return False


def _abs_files_from_list(paths: Iterable[str], check_for_text: bool = True):
    files_direct = set()
    file_paths_from_dirs = set()
    for path in paths:
        file = CodeFile(path)
        path = Path(file.path)
        if path.is_file():
            if check_for_text and not _is_file_text_encoded(path):
                logging.info(f"File path {path} is not text encoded.")
                raise UserError(f"File path {path} is not text encoded.")
            files_direct.add(file)
        elif path.is_dir():
            nonignored_files = set(
                map(
                    lambda f: os.path.realpath(path / f),
                    get_non_gitignored_files(path),
                )
            )

            file_paths_from_dirs.update(
                filter(
                    lambda f: (not check_for_text) or _is_file_text_encoded(f),
                    nonignored_files,
                )
            )

    files_from_dirs = [CodeFile(path) for path in file_paths_from_dirs]
    return files_direct, files_from_dirs


def _parse_diff(diff_output: str) -> dict[str, str]:
    """
    Return a dict with paths as keys and diffs as values.
    """
    lines = diff_output.splitlines()
    files = {}
    current_file = None
    current_diff = []
    for line in lines:
        if line.startswith("diff --git"):  # New file
            if current_file:
                files[current_file] = '\n'.join(current_diff)
                current_diff = []
            current_file = line.split(" b/")[-1]  # Git's a/b/ notation
        else:
            current_diff.append(line)
    if current_file:
        files[current_file] = '\n'.join(current_diff)
    return files


def _get_diffs(
    config: ConfigManager, history: int, commits: Iterable[str], branches: Iterable[str]
) -> Dict[Path, str]:
    """Return a dict of {<abs_path>: [<diff>]} for all passed diffs."""
    commits = set(commits)
    if history:
        if history < 0:
            raise UserError("History must be a positive integer.")
        commits.update(get_commit_history(config.git_root, history))
    
    commit_diffs = {}
    invalid_commits = []
    for commit in commits:
        try:
            commit_diffs[commit] = get_commit_diff(config.git_root, commit)
        except UserError:
            invalid_commits.append(commit)
    if invalid_commits:
        cprint(
            "The following commits do not exist:",
            "light_yellow",
        )
        print("\n".join(invalid_commits))
        exit()

    branch_diffs = {}
    invalid_branches = []
    for branch in branches:
        try:
            branch_diffs[branch] = get_branch_diff(config.git_root, branch)
        except UserError:
            invalid_branches.append(branch)
    if invalid_branches:
        cprint(
            "The following branches do not exist:",
            "light_yellow",
        )
        print("\n".join(invalid_branches))
        exit()
    
    file_diffs = defaultdict(list)
    for commit_hash, commit in commit_diffs.items():
        diff_content = _parse_diff(commit)
        for file_path, diff in diff_content.items():
            diff = f"Commit: {commit_hash}\n{diff}"
            file_diffs[file_path].append(diff)

    for branch_name, branch in branch_diffs.items():
        diff_content = _parse_diff(branch)
        for file_path, diff in diff_content.items():
            diff = f"Branch: {branch_name}\n{diff}"
            file_diffs[file_path].append(diff)

    return dict(file_diffs)


def _build_diffs_list(diffs: Dict[Path, list]):
    """Return a lists of identifiers for commits and branches"""
    commits = set()
    branches = set()
    for file, file_diffs in diffs.items():
        for _diff in file_diffs:
            title_line = _diff.splitlines()[0]
            _type, _identifier = title_line.split(": ")
            if _type == "Commit":
                commits.add(_identifier)
            elif _type == "Branch":
                branches.add(_identifier)
            else:
                raise UserError(f"Unrecognized diff type {_type}")
    return list(commits), list(branches)


def _get_files(
    config: ConfigManager, paths: Iterable[str], exclude_paths: Iterable[str]
) -> Dict[Path, CodeFile]:
    excluded_files_direct, excluded_files_from_dirs = _abs_files_from_list(
        exclude_paths, check_for_text=False
    )
    excluded_files, excluded_files_from_dir = set(
        map(lambda f: f.path, excluded_files_direct)
    ), set(map(lambda f: f.path, excluded_files_from_dirs))

    glob_excluded_files = set(
        os.path.join(config.git_root, file)
        for glob_path in config.file_exclude_glob_list()
        # If the user puts a / at the beginning, it will try to look in root directory
        for file in glob.glob(
            pathname=glob_path,
            root_dir=config.git_root,
            recursive=True,
        )
    )
    files_direct, files_from_dirs = _abs_files_from_list(paths, check_for_text=True)

    # config glob excluded files only apply to files added from directories
    files_from_dirs = [
        file
        for file in files_from_dirs
        if str(file.path.resolve()) not in glob_excluded_files
    ]

    files_direct.update(files_from_dirs)

    files = {}
    for file in files_direct:
        if file.path not in excluded_files | excluded_files_from_dir:
            files[file.path] = file

    return files


def _build_path_tree(files: Iterable[CodeFile], git_root):
    tree = {}
    for file in files:
        path = os.path.relpath(file.path, git_root)
        parts = Path(path).parts
        current_level = tree
        for part in parts:
            if part not in current_level:
                current_level[part] = {}
            current_level = current_level[part]
    return tree


def _print_path_tree(tree, changed_files, cur_path, prefix=""):
    keys = list(tree.keys())
    for i, key in enumerate(sorted(keys)):
        if i < len(keys) - 1:
            new_prefix = prefix + "│   "
            print(f"{prefix}├── ", end="")
        else:
            new_prefix = prefix + "    "
            print(f"{prefix}└── ", end="")

        cur = cur_path / key
        star = "* " if cur in changed_files else ""
        if tree[key]:
            color = "blue"
        elif star:
            color = "green"
        else:
            color = None
        cprint(f"{star}{key}", color)
        if tree[key]:
            _print_path_tree(tree[key], changed_files, cur, new_prefix)


class CodeContext:
    def __init__(
        self,
        config: ConfigManager,
        paths: Iterable[str],
        exclude_paths: Iterable[str],
        history: int,
        commits: Iterable[str],
        branches: Iterable[str],
    ):
        self.config = config

        self.diffs = _get_diffs(self.config, history, commits, branches)
        if not paths:
            paths = self.diffs.keys()
        else:
            pass  # Leave the extra diffs, even though not included in message
        self.files = _get_files(self.config, paths, exclude_paths)

    def display_context(self):
        if self.diffs:
            commits, branches = _build_diffs_list(self.diffs)
            if commits:
                cprint("Commits included in context:", "green")
                print("\n".join(commits))
            if branches:
                cprint("Branches included in context:", "green")
                print("\n".join(branches))

        if self.files:
            cprint("Files included in context:", "green")
        else:
            cprint("No files included in context.\n", "red")
            cprint("Git project: ", "green", end="")
        cprint(self.config.git_root.name, "blue")
        _print_path_tree(
            _build_path_tree(self.files.values(), self.config.git_root),
            get_paths_with_git_diffs(self.config.git_root),
            self.config.git_root,
        )
        print()
