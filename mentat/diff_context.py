import subprocess
from pathlib import Path
from typing import List, Literal, Optional

from mentat.git_handler import (
    check_head_exists,
    get_diff_for_file,
    get_files_in_diff,
    get_git_root_for_path,
    get_treeish_metadata,
    get_untracked_files,
)
from mentat.session_context import SESSION_CONTEXT
from mentat.session_stream import SessionStream


class DiffContext:
    target: str = ""
    name: str = "index (last commit)"

    def __init__(
        self,
        stream: SessionStream,
        cwd: Path,
        diff: Optional[str] = None,
        pr_diff: Optional[str] = None,
    ):
        self.git_root = get_git_root_for_path(cwd, raise_error=False)
        if not self.git_root:
            return

        if diff and pr_diff:
            # TODO: Once broadcast queue's unread messages and/or config is moved to client,
            # determine if this should quit or not
            stream.send(
                "Cannot specify more than one type of diff. Disabling diff and pr-diff.",
                style="warning",
            )
            diff = None
            pr_diff = None

        target = diff or pr_diff
        if not target:
            return

        name = ""
        treeish_type = _get_treeish_type(self.git_root, target)
        if treeish_type is None:
            stream.send(f"Invalid treeish: {target}", style="failure")
            stream.send("Disabling diff and pr-diff.", style="warning")
            return

        if treeish_type == "branch":
            name += f"Branch {target}: "
        elif treeish_type in {"relative"}:
            name += f"{target}: "

        if pr_diff:
            name = f"Merge-base {name}"
            target = _git_command(self.git_root, "merge-base", "HEAD", pr_diff)
            if not target:
                # TODO: Same as above todo
                stream.send(
                    f"Cannot identify merge base between HEAD and {pr_diff}. Disabling pr-diff.",
                    style="warning",
                )
                return

        def _get_treeish_metadata(git_root: Path, _target: str):
            meta = get_treeish_metadata(git_root, _target)
            return f'{meta["hexsha"][:8]}: {meta["summary"]}'

        if not target:
            return
        elif treeish_type == "compare":
            name += "Comparing " + ", ".join(_get_treeish_metadata(self.git_root, part) for part in target.split(" "))
        else:
            name += _get_treeish_metadata(self.git_root, target)
        self.target = target
        self.name = name

    _diff_files: List[Path] | None = None
    _untracked_files: List[Path] | None = None

    def diff_files(self) -> List[Path]:
        if not self.git_root:
            return []
        if self._diff_files is None:
            self.refresh()
        return self._diff_files  # pyright: ignore

    def untracked_files(self) -> List[Path]:
        if not self.git_root:
            return []
        if self._untracked_files is None:
            self.refresh()
        return self._untracked_files  # pyright: ignore

    def refresh(self):
        if not self.git_root:
            return
        ctx = SESSION_CONTEXT.get()

        if self.target == "HEAD" and not check_head_exists():
            self._diff_files = []  # A new repo without any commits
            self._untracked_files = []
        else:
            self._diff_files = [(ctx.cwd / f).resolve() for f in get_files_in_diff(self.target)]
            self._untracked_files = [(ctx.cwd / f).resolve() for f in get_untracked_files(ctx.cwd)]

    def get_display_context(self) -> Optional[str]:
        if not self.git_root:
            return None
        diff_files = self.diff_files()
        if not diff_files:
            return ""
        num_files = len(diff_files)
        num_lines = 0
        for file in diff_files:
            diff = get_diff_for_file(self.target, file)
            diff_lines = diff.splitlines()
            num_lines += len([line for line in diff_lines if line.startswith(("+ ", "- "))])
        return f" {self.name} | {num_files} files | {num_lines} lines"


TreeishType = Literal["commit", "branch", "relative", "compare"]


def _git_command(git_root: Path, *args: str) -> str | None:
    try:
        return subprocess.check_output(["git"] + list(args), cwd=git_root, stderr=subprocess.PIPE, text=True).strip()
    except subprocess.CalledProcessError:
        return None


def _get_treeish_type(git_root: Path, treeish: str) -> TreeishType | None:
    if " " in treeish:
        parts = treeish.split(" ")
        types = [_get_treeish_type(git_root, part) for part in parts]
        if not all(types):
            return None
        return "compare"

    object_type = _git_command(git_root, "cat-file", "-t", treeish)

    if not object_type:
        return None

    if object_type == "commit":
        if "~" in treeish or "^" in treeish:
            return "relative"

        if _git_command(git_root, "show-ref", "--heads", treeish):
            return "branch"
        else:
            return "commit"
    return None
