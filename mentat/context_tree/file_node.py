import hashlib
from pathlib import Path
from typing import Optional

from mentat.errors import MentatError
from mentat.code_map import get_code_map
from mentat.diff_context import DiffAnnotation, annotate_file_message
from .node import ContextNode


def _compute_hash(data: str) -> str:
    """Compute SHA-256 checksum for given data."""
    sha256 = hashlib.sha256()
    sha256.update(data.encode('utf-8'))
    return sha256.hexdigest()


class FileNode(ContextNode):

    def __init__(self, path: Path, parent: Optional[ContextNode]=None):
        super().__init__(path, parent)
        self.refresh()

    _hash: str = ""
    def refresh(self):
        new_hash = _compute_hash(self.path.read_text())
        if new_hash != self._hash:
            self._hash = new_hash

    _diff_annotations: list[DiffAnnotation]
    def set_diff_annotations(self, diff_annotations: list[DiffAnnotation]) -> None:
        self._diff_annotations = diff_annotations

    def display_context(self, prefix: str=""):
        pass  # Handled by directory
    
    def get_code_message(self, recursive: bool=False) -> list[str]:
        message = list[str]()
        if self.node_settings.diff and not self._diff_annotations:
            raise MentatError(f"Diff annotations not set for file {self.path}.")

        # If user-specified, Include entire code body with diff annotations
        if self.node_settings.include:
            message += [f"{self.relative_path().as_posix()}"]
            code_message = self.path.read_text().splitlines()
            if self.node_settings.diff:
                code_message = annotate_file_message(code_message, self._diff_annotations)
            message += code_message
            return message
        
        # Else include diff and/or code_map
        if self.node_settings.diff:
            message += [f"{self.relative_path().as_posix()}"]
            for annotation in self._diff_annotations:
                message.append(f"{annotation.start}:{annotation.start + annotation.length}")
                message += annotation.message
        if self.node_settings.code_map:
            message += get_code_map(
                self.root().path, self.relative_path(), not self.node_settings.include_signature
            ).splitlines()
        return message
                
