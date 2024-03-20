import subprocess
from pathlib import Path
from typing import List, Literal, Optional

import attr

from mentat.errors import MentatError
from mentat.git_handler import (
    check_head_exists,
    get_diff_for_file,
    get_files_in_diff,
    get_git_root_for_path,
    get_treeish_metadata,
    get_untracked_files,
)
from mentat.interval import Interval
from mentat.session_context import SESSION_CONTEXT
from mentat.session_stream import SessionStream


@attr.define(frozen=True)
class DiffAnnotation(Interval):
    start: int | float = attr.field()
    message: List[str] = attr.field()
    end: int | float = attr.field(
        default=attr.Factory(
            lambda self: self.start + sum(bool(line.startswith("-")) for line in self.message),
            takes_self=True,
        )
    )


def parse_diff(diff: str) -> list[DiffAnnotation]:
    """Parse diff into a list of annotations."""
    annotations: list[DiffAnnotation] = []
    active_annotation: Optional[DiffAnnotation] = None
    lines = diff.splitlines()
    for line in lines:
        if line.startswith(("---", "+++", "//", "diff", "index")):
            continue
        elif line.startswith("@@"):
            if active_annotation:
                annotations.append(active_annotation)
            _new_index = line.split(" ")[2]
            if "," in _new_index:
                new_start = _new_index[1:].split(",")[0]
            else:
                new_start = _new_index[1:]
            active_annotation = DiffAnnotation(start=int(new_start), message=[])
        elif line.startswith(("+", "-")):
            if not active_annotation:
                raise MentatError("Invalid diff")
            active_annotation.message.append(line)
    if active_annotation:
        annotations.append(active_annotation)
    annotations.sort(key=lambda a: a.start)
    return annotations


def annotate_file_message(code_message: list[str], annotations: list[DiffAnnotation]) -> list[str]:
    """Return the code_message with annotations inserted."""
    active_index = 0
    annotated_message: list[str] = []
    for annotation in annotations:
        # Fill-in lines between annotations
        if active_index < annotation.start:
            unaffected_lines = code_message[active_index : annotation.start]
            annotated_message += unaffected_lines
        active_index = annotation.start
        if annotation.start == 0:
            # Make sure the PATH stays on line 1
            annotated_message.append(code_message[0])
            active_index += 1
        i_minus = None
        for line in annotation.message:
            sign = line[0]
            if sign == "+":
                # Add '+' lines in place of code_message lines
                annotated_message.append(f"{active_index}:{line}")
                active_index += 1
                i_minus = None
            elif sign == "-":
                # Insert '-' lines at the point they were removed
                i_minus = 0 if i_minus is None else i_minus
                annotated_message.append(f"{annotation.start + i_minus}:{line}")
                i_minus += 1
    if active_index < len(code_message):
        annotated_message += code_message[active_index:]

    return annotated_message


class DiffContext:
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
                "Cannot specify more than one type of diff. Disabling diff and" " pr-diff.",
                style="warning",
            )
            diff = None
            pr_diff = None

        target = diff or pr_diff
        if not target:
            self.target = "HEAD"
            self.name = "HEAD (last commit)"
            return

        name = ""
        treeish_type = _get_treeish_type(self.git_root, target)
        if treeish_type is None:
            stream.send(f"Invalid treeish: {target}", style="failure")
            stream.send("Disabling diff and pr-diff.", style="warning")
            self.target = "HEAD"
            self.name = "HEAD (last commit)"
            return

        if treeish_type == "branch":
            name += f"Branch {target}: "
        elif treeish_type == "relative":
            name += f"{target}: "

        if pr_diff:
            name = f"Merge-base {name}"
            target = _git_command(self.git_root, "merge-base", "HEAD", pr_diff)
            if not target:
                # TODO: Same as above todo
                stream.send(
                    f"Cannot identify merge base between HEAD and {pr_diff}. Disabling" " pr-diff.",
                    style="warning",
                )
                self.target = "HEAD"
                self.name = "HEAD (last commit)"
                return

        meta = get_treeish_metadata(self.git_root, target)
        name += f'{meta["hexsha"][:8]}: {meta["summary"]}'
        if target == "HEAD":
            name = "HEAD (last commit)"

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

    def get_annotations(self, rel_path: Path) -> list[DiffAnnotation]:
        if not self.git_root:
            return []
        diff = get_diff_for_file(self.target, rel_path)
        return parse_diff(diff)

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

    def annotate_file_message(self, rel_path: Path, file_message: list[str]) -> list[str]:
        """Return file_message annotated with active diff."""
        if not self.git_root:
            return []
        annotations = self.get_annotations(rel_path)
        return annotate_file_message(file_message, annotations)


TreeishType = Literal["commit", "branch", "relative"]


def _git_command(git_root: Path, *args: str) -> str | None:
    try:
        return subprocess.check_output(["git"] + list(args), cwd=git_root, stderr=subprocess.PIPE, text=True).strip()
    except subprocess.CalledProcessError:
        return None


def _get_treeish_type(git_root: Path, treeish: str) -> TreeishType | None:
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
