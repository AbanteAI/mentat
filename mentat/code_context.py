import glob
import logging
import os
from pathlib import Path
from typing import Dict, Iterable

from .code_file import CodeFile
from .config_manager import ConfigManager
from .errors import UserError
from .git_handler import get_non_gitignored_files


def _is_file_text_encoded(file_path):
    try:
        # The ultimate filetype test
        with open(file_path) as f:
            f.read()
        return True
    except UnicodeDecodeError:
        return False


def _abs_files_from_list(paths: Iterable[str], check_for_text: bool = True):
    files_direct = set()
    file_paths_from_dirs = set()
    for path in paths:
        file = CodeFile(path)
        path = Path(file.path)
        if path.is_file():
            if check_for_text and not _is_file_text_encoded(path):
                logging.info(f"File path {path} is not text encoded.")
                raise UserError(f"File path {path} is not text encoded.")
            files_direct.add(file)
        elif path.is_dir():
            nonignored_files = set(
                map(
                    lambda f: os.path.realpath(path / f),
                    get_non_gitignored_files(path),
                )
            )

            file_paths_from_dirs.update(
                filter(
                    lambda f: (not check_for_text) or _is_file_text_encoded(f),
                    nonignored_files,
                )
            )

    files_from_dirs = [CodeFile(path) for path in file_paths_from_dirs]
    return files_direct, files_from_dirs


def _abs_file_paths_from_list(paths: Iterable[str], check_for_text: bool = True):
    files_direct, files_from_dirs = _abs_files_from_list(paths, check_for_text)
    return set(map(lambda f: f.path, files_direct)), set(
        map(lambda f: f.path, files_from_dirs)
    )


class CodeContext:
    def __init__(
        self,
        config: ConfigManager,
        paths: Iterable[str],
        exclude_paths: Iterable[str],
    ):
        self.config = config

        self.files: Dict[Path, CodeFile]

        self._set_file_paths(paths, exclude_paths)

    def _set_file_paths(
        self,
        paths: Iterable[str],
        exclude_paths: Iterable[str],
    ) -> None:
        excluded_files, excluded_files_from_dir = _abs_file_paths_from_list(
            exclude_paths, check_for_text=False
        )

        glob_excluded_files = set(
            os.path.join(self.config.git_root, file)
            for glob_path in self.config.file_exclude_glob_list()
            # If the user puts a / at the beginning, it will try to look in root directory
            for file in glob.glob(
                pathname=glob_path,
                root_dir=self.config.git_root,
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

        self.files = {}
        for file in files_direct:
            if file.path not in excluded_files | excluded_files_from_dir:
                self.files[file.path] = file
