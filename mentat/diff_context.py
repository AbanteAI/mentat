import logging
import subprocess
from typing import Dict, Iterable, List
from enum import Enum
from dataclasses import dataclass
from mentat.config_manager import ConfigManager
from termcolor import cprint
from git import Repo, GitCommandError
from .git_handler import get_diff_for_file

from .errors import UserError

def _get_files_in_diff(repo: Repo, base: str, target: str) -> List[str]:
    return repo.git.diff(target, base, name_only=True).splitlines()
    

def get_diff_for_file(git_root: str, target: str, path: str) -> str:
    """Return commit data & diff for <commit> w/r/t HEAD"""
    try:
        diff_content = subprocess.check_output(
            ["git", "diff", "-U0", f"{target}", "--", path],
            cwd=git_root,
            text=True
        ).strip()
        return diff_content
    except subprocess.CalledProcessError:
        logging.error(f"Error obtaining for commit {target}.")
        raise UserError()
    

@dataclass
class DiffAnnotation:
    start: int
    message: List[str]

    @property
    def length(self):
        return sum(bool(line.startswith('+')) for line in self.message)


def _parse_diff(diff: List[str]) -> List[DiffAnnotation]:
    annotations = []
    active_annotation = None
    lines = diff.splitlines()
    for line in lines[4:]:  # Ignore header
        if line.startswith('@@'):
            if active_annotation:
                annotations.append(active_annotation)
            _new_index = line.split(' ')[2]
            if ',' in _new_index:
                new_start, new_len = _new_index[1:].split(',')
            else:
                new_start, new_len = _new_index[1:], 1
            active_annotation = DiffAnnotation(int(new_start), [])
        elif line.startswith(('+', '-')):
            if not active_annotation:
                raise UserError("Invalid diff")
            active_annotation.message.append(line)
    if active_annotation:
        annotations.append(active_annotation)
    annotations.sort(key=lambda a: a.start)
    return annotations

def _annotate_file_with_diff(
    code_message: List[str], 
    annotations: List[DiffAnnotation]
) -> List[str]:
    annotated_message = [
        code_message[0],  # POSIX path
    ]
    active_index = 1
    for annotation in annotations:
        if active_index < annotation.start:
            unaffected_lines = code_message[active_index:annotation.start]
            annotated_message += unaffected_lines
        active_index = annotation.start
        i_minus = 0
        for line in annotation.message:
            sign = line[0]
            if sign == '+':
                annotated_message.append(f"{active_index}:{line}")
                active_index += 1
            elif sign == '-':
                annotated_message.append(f"{annotation.start + i_minus}:{line}")
                i_minus += 1
    if active_index < len(code_message):
        annotated_message += code_message[active_index:]

    return annotated_message

def _annotate_file_message(
    code_message: List[str], 
    annotations: List[DiffAnnotation]
) -> List[str]:
    active_index = 0
    annotated_message = []
    for annotation in annotations:
        if active_index < annotation.start:
            unaffected_lines = code_message[active_index:annotation.start]
            annotated_message += unaffected_lines
        active_index = annotation.start
        i_minus = None
        for line in annotation.message:
            sign = line[0]
            if sign == '+':
                annotated_message.append(f"{active_index}:{line}")
                active_index += 1
                i_minus = None
            elif sign == '-':
                i_minus = 0 if i_minus is None else i_minus
                annotated_message.append(f"{annotation.start + i_minus}:{line}")
                i_minus += 1
    if active_index < len(code_message):
        annotated_message += code_message[active_index:]

    return annotated_message

def _annotate_file_message_duplicate(
    code_message: List[str],
    annotations: List[Dict]
) -> List[str]:
    annotated_message = []
    active_annotation = 0
    for line in code_message:
        if not line or not line[0].isdigit() or not ':' in line:
            annotated_message.append(line)
            continue
        _line_number = int(line.split(':')[0])
        if active_annotation < len(annotations):
            _annotation = annotations[active_annotation]
            _insert_at = _annotation.start + _annotation.length
            if _line_number >= _insert_at:
                annotated_message += _annotation.message
                active_annotation += 1
        annotated_message.append(line)
    return annotated_message
            


class DiffContext:
    
    config: ConfigManager
    repo: Repo
    target: str
    files: List[str] = []

    def __init__(self, config, history=0, commit=None, branch=None):
        
        if sum([bool(history), bool(commit), bool(branch)]) > 1:
            cprint("Only one of history, commit, or branch can be set", 'light_yellow')
            exit()

        self.config = config
        self.repo = Repo(config.git_root)
        if history:
            _commit = list(self.repo.iter_commits())[history]
            self.target = _commit.hexsha
            self.name = f'Commit ({self.target[:8]}) {_commit.summary}'
        elif commit:
            _commit = self.repo.commit(commit)
            self.target = _commit.hexsha
            self.name = f"Commit ({self.target[:8]}) {_commit.summary}"
        elif branch:
            self.target = branch
            self.name = f"Branch {self.target}"            
        else:
            self.target = 'HEAD'
            self.name = 'HEAD (last commit)'
        
        try:
            self.files = _get_files_in_diff(self.repo, '--', self.target)
        except GitCommandError as e:
            cprint(f'Invalid {self.target}', 'light_yellow')
            exit()
    
    def display_context(self) -> None:
        if not self.files:
            return
        cprint(f"Diff annotations:", "green")
        num_files = len(self.files) 
        num_lines = 0
        for file in self.files:
            diff = get_diff_for_file(self.config.git_root, self.target, file)
            diff_lines = diff.splitlines()
            num_lines += len([line for line in diff_lines if line.startswith(('+ ', '- '))])
        print(f" ── {self.name} | {num_files} files | {num_lines} lines")

    def annotate_file_message(self, rel_path: str, file_message: List[str]) -> List[str]:
        """Return diff for the given message as lines."""
        if not self.files:
            return file_message
        
        diff = get_diff_for_file(self.config.git_root, self.target, rel_path)
        append = False
        if append:
            return file_message + diff.splitlines()
        
        annotations = _parse_diff(diff)
        return _annotate_file_message(file_message, annotations)
    
