from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from mentat.errors import MentatError
from mentat.llm_api import count_tokens


@dataclass
class ContextNodeSettings:
    # Code body
    include: bool = False
    diff: bool = False
    # Code map
    include_signature: bool = False
    code_map: bool = False
    file_name: bool = False

class ContextNode:
    path: Path  # Absolute
    parent: Optional['ContextNode']
    children: dict[Path, 'ContextNode']  # Indexed by path relative to self.path
    node_settings: ContextNodeSettings  # Control message generation

    def __init__(self, path: Path, parent: Optional['ContextNode']=None):
        try:
            self.path = path.resolve()
        except FileNotFoundError:
            raise MentatError(f"Path {path} does not exist.")
        self.parent = parent
        self.children = {}
        self.node_settings = ContextNodeSettings()

    def refresh(self) -> None:
        """Refresh node and subtree."""
        raise NotImplementedError

    #  --------------- NAVIGATION ---------------
    
    def root(self) -> 'ContextNode':
        return self.parent.root() if self.parent else self
    
    def relative_path(self) -> Path:
        """Return path relative to the root ContextNode (git_root)"""
        return self.path.relative_to(self.root().path)

    def __getitem__(self, path: Path|str) -> 'ContextNode':
        """Return the ContextNode at the given relative or absolute path."""
        if isinstance(path, str):
            path = Path(path)
        if path.is_absolute():
            path = path.relative_to(self.path)
        if len(path.parts) == 0:
            return self
        first, *rest = path.parts
        first = Path(first)
        if first in self.children:
            if rest:
                rest = Path(*rest)
                return self.children[first][rest]
            else:
                return self.children[first]
        else:
            raise KeyError(f"Path {path} not found in {self.path}")
        
    def iter_nodes(self, include_dirs: bool=True, include_files: bool=True) -> Iterable['ContextNode']:
        """Yield all nodes in subtree depth-first."""
        if include_dirs and self.path.is_dir():
            yield self
        if include_files and self.path.is_file():
            yield self
        for child in self.children.values():
            yield from child.iter_nodes(include_dirs, include_files)
        
    #  --------------- MESSAGE GENERATION ---------------

    def update_settings(self, updates: dict[str, bool], recursive: bool=False):
        for key, value in updates.items():
            setattr(self.node_settings, key, value)
        if recursive:
            for child in self.children.values():
                child.update_settings(updates, recursive)

    def display_context(self, prefix: str="") -> None:
        """Print a summary of current context to interface."""
        raise NotImplementedError
    
    def get_code_message(self, recursive: bool=False) -> list[str]:
        """Return the code message for prompt."""
        raise NotImplementedError
    
    def count_tokens(self, model: str='gpt-4', recursive: bool=False) -> int:
        """Return the number of tokens in this node's code message."""
        code_message = self.get_code_message()
        count = count_tokens("\n".join(code_message), model)
        if recursive:
            for child in self.children.values():
                count += child.count_tokens(model, True)
        return count
