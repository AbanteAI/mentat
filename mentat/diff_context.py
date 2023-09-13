from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from termcolor import cprint

from .config_manager import ConfigManager
from .errors import UserError
from .git_handler import get_commit_metadata, get_diff_for_file, get_files_in_diff


@dataclass
class DiffAnnotation:
    start: int
    message: list[str]

    @property
    def length(self):
        return sum(bool(line.startswith("+")) for line in self.message)


def _parse_diff(diff: str) -> list[DiffAnnotation]:
    """Parse diff into a list of annotations."""
    annotations: list[DiffAnnotation] = []
    active_annotation: Optional[DiffAnnotation] = None
    lines = diff.splitlines()
    for line in lines[4:]:  # Ignore header
        if line.startswith(("---", "+++", "//")):
            continue
        elif line.startswith("@@"):
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
    code_message: list[str], annotations: list[DiffAnnotation]
) -> list[str]:
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
    config: ConfigManager
    target: str = "HEAD"
    name: str = "HEAD (last commit)"

    def __init__(self, config: ConfigManager):
        self.config = config

    @property
    def files(self) -> list[Path]:
        return get_files_in_diff(self.config.git_root, self.target)

    def display_context(self) -> None:
        if not self.files:
            return
        cprint("Diff annotations:", "green")
        num_files = len(self.files)
        num_lines = 0
        for file in self.files:
            diff = get_diff_for_file(self.config.git_root, self.target, file)
            diff_lines = diff.splitlines()
            num_lines += len(
                [line for line in diff_lines if line.startswith(("+ ", "- "))]
            )
        print(f" ─•─ {self.name} | {num_files} files | {num_lines} lines\n")

    def annotate_file_message(
        self, rel_path: Path, file_message: list[str]
    ) -> list[str]:
        """Return file_message annotated with active diff."""
        if not self.files:
            return file_message

        diff = get_diff_for_file(self.config.git_root, self.target, rel_path)
        annotations = _parse_diff(diff)
        return _annotate_file_message(file_message, annotations)


class HistoryDiffContext(DiffContext):
    def __init__(self, config: ConfigManager, history: int):
        super().__init__(config)
        self.target = f"HEAD~{history}"
        try:
            meta = get_commit_metadata(self.config.git_root, self.target)
        except UserError:
            cprint(f"Cannot get history to depth {history}.", "light_yellow")
            exit()
        self.name = f'{self.target}: {meta["summary"]}'


class CommitDiffContext(DiffContext):
    def __init__(self, config: ConfigManager, commit: str):
        super().__init__(config)
        self.target = commit
        try:
            meta = get_commit_metadata(self.config.git_root, commit)
        except UserError:
            cprint(f"Invalid commit hash {commit}.", "light_yellow")
            exit()
        self.name = f'{self.target[:8]}: {meta["summary"]}'


class BranchDiffContext(DiffContext):
    def __init__(self, config: ConfigManager, branch: str):
        super().__init__(config)
        self.target = branch
        self.name = f"Branch: {self.target}"
        try:  # Validate branch b/c metadata wasn't tried
            _ = self.files
        except UserError:
            cprint(f"Invalid branch {branch}.", "light_yellow")
            exit()


def get_diff_context(
    config: ConfigManager,
    history: Optional[int] = None,
    commit: Optional[str] = None,
    branch: Optional[str] = None,
):
    num_args = sum([bool(history), bool(commit), bool(branch)])
    if num_args > 1:
        cprint("Cannot specify more than one type of diff.", "light_yellow")
        exit()

    if history:
        return HistoryDiffContext(config, history)
    elif commit:
        return CommitDiffContext(config, commit)
    elif branch:
        return BranchDiffContext(config, branch)
    else:
        return DiffContext(config)
