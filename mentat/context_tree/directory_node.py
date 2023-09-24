import subprocess
from pathlib import Path
from typing import Optional

from termcolor import cprint
from .node import ContextNode
from .file_node import FileNode


def is_file_text_encoded(file_path: Path):
    try:
        # The ultimate filetype test
        with open(file_path) as f:
            f.read()
        return True
    except UnicodeDecodeError:
        return False


def _has_child_with_setting(node: ContextNode, setting: str) -> bool:
    for child in node.children.values():
        if isinstance(child, DirectoryNode):
            if _has_child_with_setting(child, setting):
                return True
        elif child.node_settings.__dict__[setting]:
            return True
    return False


def get_node(path: Path, parent: Optional[ContextNode]=None) -> ContextNode:
    """Return the ContextNode at the given path."""
    if path.is_dir():
        return DirectoryNode(path, parent)
    else:
        return FileNode(path, parent)
    
        
class DirectoryNode(ContextNode):
    def __init__(self, path: Path, parent: Optional[ContextNode]=None):
        super().__init__(path, parent)
        self.refresh()
        

    def refresh(self):
        # Get non-ignored git children at this level
        _tracked: list[str] = subprocess.check_output(
            ["git", "ls-files"], 
            cwd=self.path, 
            universal_newlines=True
        ).splitlines()
        _tracked = list({Path(child).parts[0] for child in _tracked})
        
        # Get children not tracked by git at this level
        _untracked: list[str] = subprocess.check_output(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=self.path,
            universal_newlines=True
        ).splitlines()
        _untracked = list({Path(child).parts[0] for child in _untracked})

        previous_paths = set(self.children.keys())
        active_paths = set(Path(c) for c in _tracked + _untracked)
        paths_added = sorted(active_paths - previous_paths)
        paths_removed = previous_paths - active_paths
        for child in paths_added:
            child_abs = Path(self.path, child)
            if not child_abs.is_dir() and not is_file_text_encoded(child_abs):
                continue
            child_path = Path(self.path, child)
            child_node = get_node(child_path, self)
            self.children[Path(child_node.path.name)] = child_node
        for child in paths_removed:
            if not self.children[child].node_settings.include:
                del self.children[child]


    def display_context(self, prefix: str=""):
        """Print directory if node_settings.text is True for any child"""
        if not self.node_settings.include and not _has_child_with_setting(self, "include"):
            return
        
        include_children = list[ContextNode]()
        for child in self.children.values():
            if child.node_settings.include:
                include_children.append(child)
            elif isinstance(child, DirectoryNode):
                if _has_child_with_setting(child, "include"):
                    include_children.append(child)
                    
        for i, child in enumerate(include_children):
            if i < len(include_children) - 1:
                new_prefix = prefix + "│   "
                print(f"{prefix}├── ", end="")
            else:
                new_prefix = prefix + "    "
                print(f"{prefix}└── ", end="")
            
            star = "* " if self.node_settings.diff else ""
            if child.path.is_dir():
                color = "blue"
            elif star:
                color = "green"
            else:
                color = None
            cprint(f"{star}{child.path.name}", color)
            if child.path.is_dir():
                child.display_context(new_prefix)

    def get_code_message(self, recursive: bool=False) -> list[str]:
        message = list[str]()
        if _has_child_with_setting(self, "include"):
            message += [f"{self.relative_path().as_posix()}/"]
        if recursive:
            for child in self.children.values():
                message += child.get_code_message(recursive)
        return message
