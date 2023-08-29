import glob
import logging
import os
from pathlib import Path
from typing import Iterable, Set

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


def _abs_file_paths_from_list(paths: Iterable[str], check_for_text: bool = True):
    file_paths_direct = set()
    file_paths_from_dirs = set()
    for path in paths:
        path = Path(path)
        if path.is_file():
            if check_for_text and not _is_file_text_encoded(path):
                logging.info(f"File path {path} is not text encoded.")
                raise UserError(f"File path {path} is not text encoded.")
            file_paths_direct.add(os.path.realpath(path))
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
    return file_paths_direct, file_paths_from_dirs


class CodeFileIndex:
    def __init__(
        self,
        config: ConfigManager,
        paths: Iterable[str],
        exclude_paths: Iterable[str],
    ):
        self.config = config
        self.file_paths: Set[str] = set()

        self._init_file_paths(paths, exclude_paths)

    def _init_file_paths(
        self, paths: Iterable[str], exclude_paths: Iterable[str]
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
        file_paths_direct, file_paths_from_dirs = _abs_file_paths_from_list(
            paths, check_for_text=True
        )

        # config glob excluded files only apply to files added from directories
        file_paths_from_dirs -= glob_excluded_files

        self.file_paths = set(
            (file_paths_direct | file_paths_from_dirs)
            - (excluded_files | excluded_files_from_dir)
        )
