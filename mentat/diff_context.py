import logging
from typing import Dict, Iterable, List
from enum import Enum
from dataclasses import dataclass
from termcolor import cprint
from git import Repo, GitCommandError

from .errors import UserError

def _get_files_in_diff(repo: Repo, base: str, target: str) -> List[str]:
    return repo.git.diff(target, base, name_only=True).splitlines()
    
def _get_diff_for_file(repo: Repo, base: str, target: str, file: str) -> List[str]:
    return repo.git.diff(target, base, '--unified=0', '--', file).splitlines()

@dataclass
class DiffAnnotation:
    start: int
    end: int
    message: List[str]


def _parse_diff(diff: List[str]) -> List[dict]:
    annotations = []
    active_annotation = None
    for line in diff[4:]:  # Ignore header
        if line.startswith('@@'):
            if active_annotation:
                annotations.append(active_annotation)
            _new_index = line.split(' ')[2]
            if ',' in _new_index:
                new_start, new_len = _new_index[1:].split(',')
            else:
                new_start, new_len = _new_index[1:], 1
            active_annotation = DiffAnnotation(int(new_start), int(new_start) + int(new_len), [])
        elif line.startswith(('+ ', '- ')):
            if not active_annotation:
                raise UserError("Invalid diff")
            active_annotation.message.append(line)
    annotations.sort(key=lambda a: a.start)
    return annotations


class DiffContext:
    
    repo: Repo
    base: str = ''
    target: str = ''
    files: List[str] = []

    def __init__(self, config, history=0, commit=None, branch=None, base='HEAD'):
        
        if sum([bool(history), bool(commit), bool(branch)]) > 1:
            cprint("Only one of history, commit, or branch can be set", 'light_yellow')
            exit()

        self.repo = Repo(config.git_root)
        self.base = '--'
        if history:
            _commit = list(self.repo.iter_commits())[history]
            self.target = _commit.hexsha
            self.name = f'commit ({self.target[:8]}) {_commit.summary}'
        elif commit:
            _commit = self.repo.commit(commit)
            self.target = _commit.hexsha
            self.name = f"commit ({self.target[:8]}) {_commit.summary}"
        elif branch:
            self.target = branch
            self.name = f"branch {self.target}"            
        else:
            self.target = 'HEAD'
            self.name = 'since last commit'
        
        try:
            self.files = _get_files_in_diff(self.repo, self.base, self.target)
        except GitCommandError as e:
            cprint(f'Invalid {self.target}', 'light_yellow')
            exit()
    
    def display_context(self) -> None:
        if not self.files:
            return
        cprint("Diffs included in context:", "green")
        cprint(f"   {self.name}", "light_blue")
        num_files = len(self.files) 
        num_lines = 0
        for file in self.files:
            diff_lines = _get_diff_for_file(self.repo, self.base, self.target, file)
            num_lines += len([line for line in diff_lines if line.startswith(('+ ', '- '))])
        print(f"      {num_files} files | {num_lines} lines\n")

    def annotate_file_message(self, rel_path: str, code_message: List[str]) -> List[str]:
        """Return diff for the given message as lines."""
        if not self.files:
            return code_message
        
        annotated_message = [
            code_message[0],  # POSIX path
        ]
        active_index = 1
        diff = _get_diff_for_file(self.repo, self.base, self.target, rel_path)
        annotations: List[DiffAnnotation] = _parse_diff(diff)
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