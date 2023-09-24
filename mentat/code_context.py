import glob
from pathlib import Path
from textwrap import dedent
from typing import Any, Optional

from termcolor import cprint

from .code_map import check_ctags_executable
from .config_manager import ConfigManager
from .context_tree import ContextNode, DirectoryNode, FileNode, get_node
from .diff_context import DiffContext, get_diff_context
from .errors import UserError


def _set_diff_annotations(root: ContextNode, diff_context: DiffContext) -> None:
    for file in diff_context.files:
        node = root[file]
        if isinstance(node, FileNode) and node.node_settings.include:
            node.set_diff_annotations(diff_context.get_diff_annotations(file))


def _set_code_map(
    root: ContextNode, model: str = "gpt-4", max_tokens: Optional[int] = None
) -> None:
    try:
        check_ctags_executable()
    except UserError as e:
        ctags_disabled_message = dedent(
            f"""
            There was an error with your universal ctags installation, disabling CodeMap.
            Reason: {e}
        """
        )
        cprint(ctags_disabled_message, color="yellow")
        return

    # Try to include everything
    root.update_settings({"code_map": True, "include_signature": True}, recursive=True)
    context_length = root.count_tokens(model, recursive=True)
    if not max_tokens or context_length <= max_tokens:
        return
    # Otherwise, find the level at which everything fits...
    root.update_settings({"include_signature": False}, recursive=True)
    context_length = root.count_tokens(model, recursive=True)
    if context_length < max_tokens:
        _update_feature = "include_signature"
    else:
        root.update_settings({"code_map": False}, recursive=True)
        context_length = root.count_tokens(model, recursive=True)
        _update_feature = "code_map"
    # ...then add features to files one-by-one till we run out of space
    token_budget = max_tokens - context_length
    for node in root.iter_nodes():
        baseline = node.count_tokens(model)
        node.update_settings({_update_feature: True}, recursive=False)
        adjusted = node.count_tokens(model)
        if adjusted - baseline > token_budget:
            node.update_settings({_update_feature: False}, recursive=False)
            break
        token_budget -= adjusted - baseline


class CodeContext:
    config: ConfigManager
    root: DirectoryNode
    diff_context: DiffContext
    context_settings: dict[str, Any]

    def __init__(
        self,
        config: ConfigManager,
        paths: list[Path],
        exclude_paths: list[Path],
        diff: Optional[str] = None,
        pr_diff: Optional[str] = None,
        no_code_map: bool = False,
    ):
        self.config = config
        self.context_settings = {
            "paths": paths,
            "exclude_paths": exclude_paths,
            "no_code_map": no_code_map,
            "diff": diff,
            "pr_diff": pr_diff,
        }
        # Generate file tree
        self.root = DirectoryNode(self.config.git_root)
        self.refresh()

    def refresh(
        self,
        max_tokens: Optional[int] = None,
    ) -> None:
        """Update file tree and display settings based on configuration"""

        # Check for new and changed files
        self.root.refresh()

        # Apply user settings
        try:
            self.diff_context = get_diff_context(
                self.config,
                self.context_settings["diff"],
                self.context_settings["pr_diff"],
            )
            if not self.context_settings["paths"]:
                self.context_settings["paths"] = self.diff_context.files
        except UserError as e:
            cprint(str(e), "light_yellow")
            exit()
        for path in self.context_settings["paths"]:
            self.add_path(path)
        for path in self.context_settings["exclude_paths"]:
            self.remove_path(path)
        glob_exclude_files = set(
            Path(file)
            for glob_path in self.config.file_exclude_glob_list()
            # If the user puts a / at the beginning, it will try to look in root directory
            for file in glob.glob(
                pathname=glob_path,
                root_dir=self.config.git_root,
                recursive=True,
            )
        )
        for path in glob_exclude_files:
            if path in self.context_settings["paths"]:
                continue
            self.remove_path(path)
        _set_diff_annotations(self.root, self.diff_context)

        # Validate length
        context_length = self.root.count_tokens(self.config.model(), recursive=True)
        if max_tokens and context_length > max_tokens:
            raise KeyboardInterrupt(
                f"Code context exceeds token limit ({context_length} /"
                f" {max_tokens}). Please try running again with a reduced"
                " number of files."
            )
        # Fill-in extra space with code_map, other files from diff..
        if not self.context_settings["no_code_map"]:
            _set_code_map(self.root, self.config.model(), max_tokens)

    @property
    def files(self) -> list[Path]:
        return [
            f.relative_path()
            for f in self.root.iter_nodes(include_dirs=False)
            if f.node_settings.include
        ]

    def display_context(self):
        included_files = [
            f
            for f in self.root.iter_nodes(include_dirs=False)
            if f.node_settings.include
        ]
        if len(included_files) > 0:
            cprint("Files included in context:", "green")
        else:
            cprint("No files included in context.\n", "red")
            cprint("Git project: ", "green", end="")
        cprint(self.root.path.name, "blue")
        self.root.display_context()
        print()
        self.diff_context.display_context()
        print()
        if self.root.node_settings.include_signature:
            code_map_level = "full syntax tree"
        elif self.root.node_settings.code_map:
            code_map_level = "partial syntax tree"
        else:
            return
        cprint(f"Including Code Map: {code_map_level}", "green")

    def get_code_message(self) -> str:
        code_message = ["Code Files:\n"]
        code_message += self.root.get_code_message(recursive=True)
        return "\n".join(code_message)

    def add_path(self, path: Path | str, verbose: bool = False):
        if isinstance(path, str):
            path = Path(path)
        if not path.exists():
            if verbose:
                cprint(f"File does not exist: {path}\n", "red")
            return
        try:
            node = self.root[path]
            if node.node_settings.include:
                if verbose:
                    cprint(
                        f"File already in context: {node.relative_path()}\n", "yellow"
                    )
            else:
                node.update_settings({"include": True}, recursive=True)
                if verbose:
                    cprint(f"File added to context: {node.relative_path()}\n", "green")
        except KeyError:
            # Add an ignored file/dir to context
            relative_path = path.resolve().relative_to(self.root.path)
            relative_paths = [Path(p) for p in Path(relative_path).parts]
            _cursor = self.root
            for part in relative_paths:
                if part not in _cursor.children:
                    node_path = _cursor.path / part
                    _cursor.children[part] = get_node(node_path, _cursor)
                    if verbose:
                        cprint(f"Added git-ignored path to context: {part}\n", "green")
                _cursor = _cursor.children[part]
            _cursor.update_settings({"include": True}, recursive=True)

    def remove_path(self, path: Path):
        try:
            node = self.root[path]
            if not node.node_settings.include:
                cprint(f"File already included: {node.relative_path()}\n", "yellow")
            else:
                node.update_settings({"include": False}, recursive=True)
                cprint(f"File excluded: {node.relative_path()}\n", "green")
        except KeyError:
            cprint(f"File not in context: {path}\n", "yellow")
