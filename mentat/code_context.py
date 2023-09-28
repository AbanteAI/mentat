import glob
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from .code_file import CodeFile
from .code_map import CodeMap
from .config_manager import ConfigManager
from .diff_context import DiffContext, get_diff_context
from .errors import UserError
from .git_handler import get_non_gitignored_files, get_paths_with_git_diffs
from .session_stream import get_session_stream


def _is_file_text_encoded(file_path: Path):
    try:
        # The ultimate filetype test
        with open(file_path) as f:
            f.read()
        return True
    except UnicodeDecodeError:
        return False


def _abs_files_from_list(paths: list[Path], check_for_text: bool = True):
    files_direct = set[CodeFile]()
    file_paths_from_dirs = set[Path]()
    for path in paths:
        file = CodeFile(os.path.realpath(path))
        path = Path(file.path)
        if path.is_file():
            if check_for_text and not _is_file_text_encoded(path):
                logging.info(f"File path {path} is not text encoded.")
                raise UserError(f"File path {path} is not text encoded.")
            files_direct.add(file)
        elif path.is_dir():
            nonignored_files = set(
                map(
                    lambda f: Path(os.path.realpath(path / f)),
                    get_non_gitignored_files(path),
                )
            )

            file_paths_from_dirs.update(
                filter(
                    lambda f: (not check_for_text) or _is_file_text_encoded(f),
                    nonignored_files,
                )
            )

    files_from_dirs = [
        CodeFile(os.path.realpath(path)) for path in file_paths_from_dirs
    ]
    return files_direct, files_from_dirs


def _get_files(
    config: ConfigManager, paths: list[Path], exclude_paths: list[Path]
) -> Dict[Path, CodeFile]:
    excluded_files_direct, excluded_files_from_dirs = _abs_files_from_list(
        exclude_paths, check_for_text=False
    )
    excluded_files, excluded_files_from_dir = set(
        map(lambda f: f.path, excluded_files_direct)
    ), set(map(lambda f: f.path, excluded_files_from_dirs))

    glob_excluded_files = set(
        os.path.join(config.git_root, file)
        for glob_path in config.file_exclude_glob_list()
        # If the user puts a / at the beginning, it will try to look in root directory
        for file in glob.glob(
            pathname=glob_path,
            root_dir=config.git_root,
            recursive=True,
        )
    )
    files_direct, files_from_dirs = _abs_files_from_list(paths, check_for_text=True)

    # config glob excluded files only apply to files added from directories
    files_from_dirs = [
        file
        for file in files_from_dirs
        if str(file.path.resolve()) not in glob_excluded_files
    ]

    files_direct.update(files_from_dirs)

    files = dict[Path, CodeFile]()
    for file in files_direct:
        if file.path not in excluded_files | excluded_files_from_dir:
            files[Path(os.path.realpath(file.path))] = file

    return files


def _build_path_tree(files: list[CodeFile], git_root: Path):
    tree = dict[str, Any]()
    for file in files:
        path = os.path.relpath(file.path, git_root)
        parts = Path(path).parts
        current_level = tree
        for part in parts:
            if part not in current_level:
                current_level[part] = {}
            current_level = current_level[part]
    return tree


async def _print_path_tree(
    tree: dict[str, Any], changed_files: set[Path], cur_path: Path, prefix: str = ""
):
    stream = get_session_stream()

    keys = list(tree.keys())
    for i, key in enumerate(sorted(keys)):
        if i < len(keys) - 1:
            new_prefix = prefix + "│   "
            await stream.send(f"{prefix}├── ", end="")
        else:
            new_prefix = prefix + "    "
            await stream.send(f"{prefix}└── ", end="")

        cur = cur_path / key
        star = "* " if cur in changed_files else ""
        if tree[key]:
            color = "blue"
        elif star:
            color = "green"
        else:
            color = None
        await stream.send(f"{star}{key}", color=color)
        if tree[key]:
            await _print_path_tree(tree[key], changed_files, cur, new_prefix)


class CodeContext:
    def __init__(
        self,
        config: ConfigManager,
        files: Dict[Path, CodeFile],
        diff_context: DiffContext,
        code_map: CodeMap | None,
    ):
        self.config = config
        self.files = files
        self.diff_context = diff_context
        self.code_map = code_map

    @classmethod
    async def create(
        cls,
        config: ConfigManager,
        paths: list[Path],
        exclude_paths: list[Path],
        diff: Optional[str] = None,
        pr_diff: Optional[str] = None,
        no_code_map: bool = False,
    ):
        stream = get_session_stream()

        # Diff context
        try:
            diff_context = get_diff_context(config, diff, pr_diff)
            if not paths:
                paths = diff_context.files
        except UserError as e:
            await stream.send(str(e), color="light_yellow")
            exit()  # NOTE: should this be here?
        # User-specified Files
        files = _get_files(config, paths, exclude_paths)
        # Universal ctags
        code_map = None
        if not no_code_map:
            code_map = await CodeMap.create(config, token_limit=2048)

        self = CodeContext(config, files, diff_context, code_map)

        return self

    async def display_context(self):
        stream = get_session_stream()

        if self.files:
            await stream.send("Files included in context:", color="green")
        else:
            await stream.send("No files included in context.\n", color="red")
            await stream.send("Git project: ", color="green", end="")
        await stream.send(self.config.git_root.name, color="blue")
        await _print_path_tree(
            _build_path_tree(list(self.files.values()), self.config.git_root),
            get_paths_with_git_diffs(self.config.git_root),
            self.config.git_root,
        )
        self.diff_context.display_context()  # TODO: make async

    async def add_file(self, code_file: CodeFile):
        stream = get_session_stream()

        if not os.path.exists(code_file.path):
            await stream.send(f"File does not exist: {code_file.path}\n", color="red")
            return
        if code_file.path in self.files:
            await stream.send(
                f"File already in context: {code_file.path}\n", color="yellow"
            )
            return
        self.files[code_file.path] = code_file
        await stream.send(f"File added to context: {code_file.path}\n", color="green")

    async def remove_file(self, code_file: CodeFile):
        stream = get_session_stream()

        if not os.path.exists(code_file.path):
            await stream.send(f"File does not exist: {code_file.path}\n", color="red")
            return
        if code_file.path not in self.files:
            await stream.send(
                f"File not in context: {code_file.path}\n", color="yellow"
            )
            return
        del self.files[code_file.path]
        await stream.send(
            f"File removed from context: {code_file.path}\n", color="green"
        )
