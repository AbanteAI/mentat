from typing import List
from dataclasses import dataclass
from mentat.config_manager import ConfigManager
from termcolor import cprint
from git import Repo, GitCommandError
from .git_handler import get_diff_for_file

from .errors import UserError


@dataclass
class DiffAnnotation:
    start: int
    message: List[str]

    @property
    def length(self):
        return sum(bool(line.startswith("+")) for line in self.message)


def _parse_diff(diff: str) -> List[DiffAnnotation]:
    """Parse diff into a list of annotations."""
    annotations = []
    active_annotation = None
    lines = diff.splitlines()
    for line in lines[4:]:  # Ignore header
        if line.startswith("@@"):
            if active_annotation:
                annotations.append(active_annotation)
            _new_index = line.split(" ")[2]
            if "," in _new_index:
                new_start = _new_index[1:].split(",")[0]
            else:
                new_start = _new_index[1:]
            active_annotation = DiffAnnotation(int(new_start), [])
        elif line.startswith(("+", "-")):
            if not active_annotation:
                raise UserError("Invalid diff")
            active_annotation.message.append(line)
    if active_annotation:
        annotations.append(active_annotation)
    annotations.sort(key=lambda a: a.start)
    return annotations


def _annotate_file_message(
    code_message: List[str], annotations: List[DiffAnnotation]
) -> List[str]:
    """Return the code_message with annotations inserted."""
    active_index = 0
    annotated_message = []
    for annotation in annotations:
        # Fill-in lines between annotations
        if active_index < annotation.start:
            unaffected_lines = code_message[active_index : annotation.start]
            annotated_message += unaffected_lines
        active_index = annotation.start
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
    config: ConfigManager
    repo: Repo
    target: str
    files: List[str] = []

    def __init__(self, config, history=0, commit=None, branch=None):
        if sum([bool(history), bool(commit), bool(branch)]) > 1:
            cprint("Only one of history, commit, or branch can be set", "light_yellow")
            exit()

        self.repo = Repo(config.git_root)
        if history:
            _commit = list(self.repo.iter_commits())[history]
            self.target = _commit.hexsha
            self.name = f"History depth={history}: Commit {self.target[:8]} {_commit.summary}"
        elif commit:
            _commit = self.repo.commit(commit)
            self.target = _commit.hexsha
            self.name = f"Commit {self.target[:8]} {_commit.summary}"
        elif branch:
            self.target = branch
            self.name = f"Branch {self.target}"
        else:
            self.target = "HEAD"
            self.name = "HEAD (last commit)"

        try:
            self.files = self.repo.git.diff(
                self.target, "--", name_only=True
            ).splitlines()
        except GitCommandError:
            cprint(f"Invalid target: {self.target}", "light_yellow")
            exit()

    def display_context(self) -> None:
        if not self.files:
            return
        cprint("Diff annotations:", "green")
        num_files = len(self.files)
        num_lines = 0
        for file in self.files:
            diff = get_diff_for_file(self.repo.working_tree_dir, self.target, file)
            diff_lines = diff.splitlines()
            num_lines += len(
                [line for line in diff_lines if line.startswith(("+ ", "- "))]
            )
        print(f" ─•─ {self.name} | {num_files} files | {num_lines} lines\n")

    def annotate_file_message(
        self, rel_path: str, file_message: List[str]
    ) -> List[str]:
        """Return file_message annotated with active diff."""
        if not self.files:
            return file_message

        diff = get_diff_for_file(self.repo.working_tree_dir, self.target, rel_path)
        annotations = _parse_diff(diff)
        return _annotate_file_message(file_message, annotations)
