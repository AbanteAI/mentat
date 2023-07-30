import logging
import os
import subprocess
from pathlib import Path


def get_git_diff_for_path(git_root, path: str) -> str:
    return subprocess.check_output(["git", "diff", path], cwd=git_root).decode("utf-8")


def get_non_gitignored_files(path: str) -> set[str]:
    return set(
        # git returns / separated paths even on windows, convert so we can remove
        # glob_excluded_files, which have windows paths on windows
        os.path.normpath(p)
        for p in filter(
            lambda p: p != "",
            subprocess.check_output(
                # -c shows cached (regular) files, -o shows other (untracked/new) files
                ["git", "ls-files", "-c", "-o", "--exclude-standard"],
                cwd=path,
                text=True,
            ).split("\n"),
        )
    )


def get_paths_with_git_diffs(git_root) -> set[str]:
    changed = subprocess.check_output(
        ["git", "diff", "--name-only"], cwd=git_root, text=True
    ).split("\n")
    new = subprocess.check_output(
        ["git", "ls-files", "-o", "--exclude-standard"], cwd=git_root, text=True
    ).split("\n")
    return set(
        map(
            lambda path: os.path.realpath(os.path.join(git_root, Path(path))),
            changed + new,
        )
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


def get_shared_git_root_for_paths(paths) -> str:
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
