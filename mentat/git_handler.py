import hashlib
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional, Set

from git import Repo  # type: ignore

from mentat.errors import UserError
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import is_file_text_encoded


def get_untracked_files(root: Path, paths: list[Path] = []) -> list[str]:
    """Returns untracked files. --directory flag is used to show only directories
    and not files in the output. A significant performance improvement when things
    like node_modules are present."""
    command = [
        "git",
        "ls-files",
        "--exclude-standard",
        "--others",
        "--directory",
    ] + paths
    result = subprocess.run(command, cwd=root, stdout=subprocess.PIPE)
    untracked = result.stdout.decode("utf-8").strip()
    if untracked != "":
        return untracked.split("\n")
    else:
        return []


def get_non_gitignored_files(root: Path, visited: set[Path] = set()) -> Set[Path]:
    paths = set(
        # git returns / separated paths even on windows, convert so we can remove
        # glob_excluded_files, which have windows paths on windows
        Path(os.path.normpath(p))
        for p in filter(
            lambda p: p != "",
            subprocess.check_output(
                # -c shows cached (regular) files, -o shows other (untracked/new) files
                ["git", "ls-files", "-c", "-o", "--exclude-standard"],
                cwd=root,
                text=True,
                stderr=subprocess.DEVNULL,
            ).split("\n"),
        )
        # windows-safe check if p exists in path
        if Path(root / p).exists()
    )

    file_paths: Set[Path] = set()
    # We use visited to make sure we break out of any infinite loops symlinks might cause
    visited.add(root.resolve())
    for path in paths:
        # git ls-files returns directories if the directory is itself a git project;
        # so we recursively run this function on any directories it returns.
        if (root / path).is_dir():
            if (root / path).resolve() in visited:
                continue
            file_paths.update(root / path / inner_path for inner_path in get_non_gitignored_files(root / path, visited))
        else:
            file_paths.add(path)
    return file_paths


def get_git_root_for_path(path: Path, raise_error: bool = True) -> Optional[Path]:
    if os.path.isdir(path):
        dir_path = path
    else:
        dir_path = os.path.dirname(path)
    try:
        relative_path = (
            subprocess.check_output(
                [
                    "git",
                    "rev-parse",
                    "--show-prefix",
                ],
                cwd=os.path.realpath(dir_path),
                stderr=subprocess.DEVNULL,
            )
            .decode("utf-8")
            .strip()
        )
        # --show-toplevel doesn't work in some windows environment with posix paths,
        # like msys2, so we have to use --show-prefix instead
        git_root = os.path.abspath(os.path.join(dir_path, "../" * len(Path(relative_path).parts)))
        # call realpath to resolve symlinks, so all paths match
        return Path(os.path.realpath(git_root))
    except subprocess.CalledProcessError:
        if raise_error:
            logging.error(f"File {path} isn't part of a git project.")
            raise UserError()
        else:
            return


def get_shared_git_root_for_paths(paths: list[Path]) -> Path:
    git_roots = set[Path]()
    for path in paths:
        git_root = get_git_root_for_path(path)
        if git_root is None:
            logging.error(f"File {path} isn't part of a git project.")
            raise UserError()
        git_roots.add(git_root)
    if not paths:
        git_root = get_git_root_for_path(Path(os.getcwd()))
        git_roots.add(git_root)  # pyright: ignore

    if len(git_roots) > 1:
        logging.error("All paths must be part of the same git project! Projects provided:" f" {git_roots}")
        raise UserError()
    elif len(git_roots) == 0:
        logging.error("No git projects provided.")
        raise UserError()

    return git_roots.pop()


def commit(message: str) -> None:
    """
    Commit all unstaged and staged changes
    """
    subprocess.run(["git", "add", "."])
    subprocess.run(["git", "commit", "-m", message])


def get_diff_for_file(target: str, path: Path) -> str:
    """Return commit data & diff for target versus active code"""
    # TODO: Cache git diffs and check last modified time on file
    session_context = SESSION_CONTEXT.get()

    try:
        diff_content = subprocess.check_output(
            ["git", "diff", "-U0", f"{target}", "--", path],
            cwd=session_context.cwd,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return diff_content
    except subprocess.CalledProcessError:
        logging.error(f"Error obtaining diff for commit '{target}'.")
        raise UserError()


def get_treeish_metadata(git_root: Path, target: str) -> dict[str, str]:
    try:
        commit_info = subprocess.check_output(
            ["git", "log", target, "-n", "1", "--pretty=format:%H %s"],
            cwd=git_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()

        # Split the returned string into the hash and summary
        commit_hash, commit_summary = commit_info.split(" ", 1)
        return {"hexsha": commit_hash, "summary": commit_summary}
    except subprocess.CalledProcessError:
        logging.error(f"Error obtaining commit data for target '{target}'.")
        raise UserError()


def get_files_in_diff(target: str) -> list[Path]:
    """Return commit data & diff for target versus active code"""
    session_context = SESSION_CONTEXT.get()

    try:
        diff_content = subprocess.check_output(
            ["git", "diff", "--name-only", f"{target}", "--"],
            cwd=session_context.cwd,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if diff_content:
            return [Path(path) for path in diff_content.split("\n")]
        else:
            return []
    except subprocess.CalledProcessError:
        logging.error(f"Error obtaining diff for commit '{target}'.")
        raise UserError()


def check_head_exists() -> bool:
    session_context = SESSION_CONTEXT.get()

    try:
        subprocess.check_output(
            ["git", "rev-parse", "HEAD", "--"],
            cwd=session_context.cwd,
            stderr=subprocess.DEVNULL,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def get_default_branch() -> str:
    session_context = SESSION_CONTEXT.get()

    try:
        # Fetch the symbolic ref of HEAD which points to the default branch
        default_branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=session_context.cwd,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return default_branch
    except subprocess.CalledProcessError:
        # Handle error if needed or raise an exception
        raise Exception("Unable to determine the default branch.")


def get_git_diff(*args: str, cwd: Optional[Path] = None) -> str:
    """A wrapper on git diff that always includes new/untracked files."""
    if cwd is None:
        session_context = SESSION_CONTEXT.get()
        cwd = session_context.cwd

    repo = Repo(cwd)
    # Stage untracked files so they are included in the diff
    repo.git.add(all=True)
    diff = repo.git.diff(*args, unified=1)
    # Unstage changes again
    repo.git.reset()
    return diff + "\n" if diff else ""  # Required to form a valid .diff file


def get_hexsha_active() -> str:
    """Return the SHA-1 of the current commit."""
    session_context = SESSION_CONTEXT.get()
    cwd = session_context.cwd

    hexsha = ""
    all_files: set[Path] = get_non_gitignored_files(cwd)
    if all_files:
        hasher = hashlib.sha256()
        for file_path in sorted(all_files):
            if file_path.exists() and is_file_text_encoded(file_path):
                hasher.update(file_path.read_bytes())
        hexsha = hasher.hexdigest()
    return hexsha


# The following utilities give git information for the Mentat project itself. They are
# useful for benchmarks but shouldn't be used by the mentat module because it won't be a
# git repo when installed via pip.
def get_mentat_hexsha():
    try:
        hexsha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).parent.parent,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return hexsha
    except subprocess.CalledProcessError:
        return ""


def get_mentat_branch():
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=Path(__file__).parent.parent,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return branch
    except subprocess.CalledProcessError:
        return ""
