from __future__ import annotations

import glob
import logging
import os
from contextvars import ContextVar
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, Optional

import attr

from .code_file import CodeFile
from .code_map import CodeMap
from .config_manager import CONFIG_MANAGER, ConfigManager
from .diff_context import DiffContext
from .errors import MentatError, UserError
from .git_handler import GIT_ROOT, get_non_gitignored_files, get_paths_with_git_diffs
from .llm_api import count_tokens, model_context_size
from .session_stream import SESSION_STREAM


def _is_file_text_encoded(file_path: Path):
    try:
        # The ultimate filetype test
        with open(file_path, "r") as f:
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
    config: ConfigManager, git_root: Path, paths: list[Path], exclude_paths: list[Path]
) -> Dict[Path, CodeFile]:
    excluded_files_direct, excluded_files_from_dirs = _abs_files_from_list(
        exclude_paths, check_for_text=False
    )
    excluded_files, excluded_files_from_dir = set(
        map(lambda f: f.path, excluded_files_direct)
    ), set(map(lambda f: f.path, excluded_files_from_dirs))

    glob_excluded_files = set(
        os.path.join(git_root, file)
        for glob_path in config.file_exclude_glob_list()
        # If the user puts a / at the beginning, it will try to look in root directory
        for file in glob.glob(
            pathname=glob_path,
            root_dir=git_root,
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
    stream = SESSION_STREAM.get()
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


@attr.define
class CodeContextSettings:
    paths: list[Path] = []
    exclude_paths: list[Path] = []
    diff: Optional[str] = None
    pr_diff: Optional[str] = None
    no_code_map: bool = False

    def asdict(self):
        return attr.asdict(self)


CODE_CONTEXT: ContextVar[CodeContext] = ContextVar("mentat:code_context")


class CodeContext:
    settings: CodeContextSettings
    files: dict[Path, CodeFile]  # included path -> CodeFile
    file_lines: dict[Path, list[str]]  # included path -> cached lines

    def __init__(self, settings: CodeContextSettings):
        self.settings = settings

    @classmethod
    async def create(cls, settings: CodeContextSettings):
        self = cls(settings)
        await self.refresh(replace_paths=True)

        return self

    async def refresh(self, replace_paths: bool = False):
        stream = SESSION_STREAM.get()
        config = CONFIG_MANAGER.get()
        git_root = GIT_ROOT.get()

        # Diff context
        try:
            self.diff_context = DiffContext.create(
                self.settings.diff, self.settings.pr_diff
            )
            if replace_paths and not self.settings.paths:
                self.settings.paths = self.diff_context.files
        except UserError as e:
            await stream.send(str(e), color="light_yellow")
            raise MentatError("Failed to create diff context.")
        # User-specified Files
        self.files = _get_files(
            config, git_root, self.settings.paths, self.settings.exclude_paths
        )
        # Universal ctags
        self.code_map = (
            await CodeMap.create(token_limit=2048)
            if not self.settings.no_code_map
            else None
        )
        if self.code_map is not None and self.code_map.ctags_disabled:
            ctags_disabled_message = f"""
                There was an error with your universal ctags installation, disabling CodeMap.
                Reason: {self.code_map.ctags_disabled_reason}
            """
            ctags_disabled_message = dedent(ctags_disabled_message)
            await stream.send(ctags_disabled_message, color="yellow")

    async def display_context(self):
        stream = SESSION_STREAM.get()
        git_root = GIT_ROOT.get()

        if self.files:
            await stream.send("Files included in context:", color="green")
        else:
            await stream.send("No files included in context.\n", color="red")
            await stream.send("Git project: ", color="green", end="")
        await stream.send(git_root.name, color="blue")
        await _print_path_tree(
            _build_path_tree(list(self.files.values()), git_root),
            get_paths_with_git_diffs(),
            git_root,
        )
        await self.diff_context.display_context()

    async def get_code_message(
        self,
        all_file_lines: dict[Path, list[str]],
        model: str,
        provide_line_numbers: bool,
    ) -> str:
        stream = SESSION_STREAM.get()
        git_root = GIT_ROOT.get()

        code_message: list[str] = []
        if self.diff_context.files:
            code_message += [
                "Diff References:",
                f' "-" = {self.diff_context.name}',
                ' "+" = Active Changes',
                "",
            ]

        code_message += ["Code Files:\n"]
        for file in self.files.values():
            file_message: list[str] = []
            abs_path = file.path
            rel_path = Path(os.path.relpath(abs_path, git_root))

            # We always want to give GPT posix paths
            posix_rel_path = Path(rel_path).as_posix()
            file_message.append(posix_rel_path)

            file_lines = all_file_lines[rel_path]
            for i, line in enumerate(file_lines, start=1):
                if file.contains_line(i):
                    if provide_line_numbers:
                        file_message.append(f"{i}:{line}")
                    else:
                        file_message.append(f"{line}")
            file_message.append("")

            if rel_path in self.diff_context.files:
                file_message = self.diff_context.annotate_file_message(
                    rel_path, file_message
                )

            code_message += file_message

        if self.code_map is not None:
            code_message_tokens = count_tokens("\n".join(code_message), model)
            context_size = model_context_size(model)
            if context_size:
                max_tokens_for_code_map = context_size - code_message_tokens
                if self.code_map.token_limit:
                    code_map_message_token_limit = min(
                        self.code_map.token_limit, max_tokens_for_code_map
                    )
                else:
                    code_map_message_token_limit = max_tokens_for_code_map
            else:
                code_map_message_token_limit = self.code_map.token_limit

            code_map_message = await self.code_map.get_message(
                token_limit=code_map_message_token_limit
            )
            if code_map_message:
                match (code_map_message.level):
                    case "signatures":
                        level_message = "full syntax tree"
                    case "no_signatures":
                        level_message = "partial syntax tree"
                    case "filenames":
                        level_message = "filepaths only"

                message = f"\nIncluding CodeMap ({level_message})"
                await stream.send(message, color="green")
                code_message += [f"\n{code_map_message.content}"]
            else:
                message = [
                    "\nExcluding CodeMap from system message.",
                    "Reason: not enough tokens available in model context.",
                ]
                message = "\n".join(message)
                await stream.send(message, color="yellow")

        return "\n".join(code_message)

    async def add_file(self, code_file: CodeFile):
        stream = SESSION_STREAM.get()

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
        stream = SESSION_STREAM.get()

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
