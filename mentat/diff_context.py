import logging
from collections import defaultdict
from typing import Dict, Iterable, List

from .errors import UserError
from .git_handler import get_commit_history, get_commit_diff, get_branch_diff


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

class Diff:
    def __init__(self, name: str, diff: str):
        self.name = name
        self.file_diffs = _parse_diff(diff)

class CommitDiff(Diff):
    def __init__(self, git_root, commit_hash: str, commit_message: str):
        try:
            diff = get_commit_diff(git_root, commit_hash)
        except UserError:
            logging.error(f"Commit hash {commit_hash} does not exist.")
        name = f"Commit: {commit_hash[:8]}|{commit_message}"
        super().__init__(name, diff)

class BranchDiff(Diff):
    def __init__(self, git_root, branch_name: str):
        diff = get_branch_diff(git_root, branch_name)
        source_str = f"Branch: {branch_name}"
        super().__init__(source_str, diff)

        

class DiffContext:
    
    _file_diffs: Dict[str, List[str]]
    def __init__(self, config, history=0, commits=[], branches=[]):
        commits = set(commits)
        if history:
            if history < 0:
                raise UserError("History must be a positive integer.")
            commits.update(get_commit_history(config.git_root, history))

        diffs = []
        for commit in commits:
            diffs.append(CommitDiff(config.git_root, commit))
        for branch in branches:
            diffs.append(BranchDiff(config.git_root, branch))

        file_diffs = defaultdict(list)
        for diff in diffs:
            for file_path, file_diff in diff.file_diffs.items():
                file_diffs[file_path].append(file_diff)
        self.file_diffs = dict(file_diffs)

    @property
    def commits(self) -> list[CommitDiff]:
        return [diff for diff in self.diffs if isinstance(diff, CommitDiff)]
    
    @property
    def branches(self) -> list[BranchDiff]:
        return [diff for diff in self.diffs if isinstance(diff, BranchDiff)]
    
    @property
    def files(self) -> list[str]:
        return list(self.file_diffs.keys())
    
    def get_diffs_for_file(self, file: str) -> list[str]:
        # Handle a variety of paths
        self.file_diffs[file]
