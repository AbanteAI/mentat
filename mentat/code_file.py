import math
import os
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from .code_map import get_code_map
from .config_manager import ConfigManager
from .diff_context import annotate_file_message, parse_diff
from .git_handler import get_diff_for_file
from .llm_api import count_tokens

if TYPE_CHECKING:
    from .code_file_manager import CodeFileManager


class Interval:
    def __init__(
        self,
        start: int | float,
        end: int | float,
    ):
        self.start = start
        self.end = end

    def contains(self, line_number: int):
        return self.start <= line_number <= self.end


def parse_intervals(interval_string: str) -> list[Interval]:
    try:
        intervals = list[Interval]()
        for interval in interval_string.split(","):
            interval = interval.split("-", 1)
            if len(interval) == 1:
                intervals += [Interval(int(interval[0]), int(interval[0]))]
            else:
                intervals += [Interval(int(interval[0]), int(interval[1]))]
        return intervals
    except (ValueError, IndexError):
        return []


class CodeMessageLevel(Enum):
    CODE = "code"
    INTERVAL = "interval"
    CMAP_FULL = "cmap_full"
    CMAP = "cmap"
    FILE_NAME = "file_name"


class CodeFile:
    """
    Represents a file along with the lines that should be in the prompt context. Can be
    iniitialized with a Path object or a string path with optional line information
    such as "path/to/file.py:1-5,7,12-40".

    Attributes:
        path: The absolute path to the file.
        intervals: The lines in context.
    """

    def __init__(
        self,
        path: str | Path,
        level: CodeMessageLevel = CodeMessageLevel.CODE,
        diff: str | None = None,
    ):
        if Path(path).exists():
            self.path = Path(path)
            self.intervals = [Interval(0, math.inf)]
        else:
            path = str(path)
            split = path.rsplit(":", 1)
            self.path = Path(split[0])
            if not self.path.exists():
                self.path = Path(path)
                self.intervals = [Interval(0, math.inf)]
            else:
                self.intervals = parse_intervals(split[1])
                level = CodeMessageLevel.INTERVAL
        self.level = level
        self.diff = diff

    def __repr__(self):
        return f"CodeFile(fname={self.path.name}, intervals={self.intervals}, level={self.level}, diff={self.diff})"

    def contains_line(self, line_number: int):
        return any([interval.contains(line_number) for interval in self.intervals])

    def _get_file_message(self, config: ConfigManager) -> list[str]:
        file_message: list[str] = []

        # We always want to give GPT posix paths
        abs_path = Path(config.git_root / self.path)
        rel_path = Path(os.path.relpath(abs_path, config.git_root))
        posix_rel_path = Path(rel_path).as_posix()
        file_message.append(posix_rel_path)

        if self.level == CodeMessageLevel.CODE:
            file_lines = abs_path.read_text().splitlines()
            for i, line in enumerate(file_lines, start=1):
                if self.contains_line(i):
                    file_message.append(f"{i}:{line}")
        elif self.level == CodeMessageLevel.INTERVAL:
            file_lines = abs_path.read_text().splitlines()
            for i, line in enumerate(file_lines, start=1):
                if self.contains_line(i):
                    file_message.append(f"{i}:{line}")
        elif self.level == CodeMessageLevel.CMAP_FULL:
            file_message += get_code_map(config.git_root, self.path)
        elif self.level == CodeMessageLevel.CMAP:
            file_message += get_code_map(
                config.git_root, self.path, exclude_signatures=True
            )
        elif not CodeMessageLevel.FILE_NAME:
            raise ValueError(f"Invalid code message level: {self.level}")
        file_message.append("")

        if self.diff is not None:
            diff: str = get_diff_for_file(config.git_root, self.diff, rel_path)
            diff_annotations = parse_diff(diff)
            if self.level == CodeMessageLevel.CODE:
                file_message = annotate_file_message(file_message, diff_annotations)
            else:
                for section in diff_annotations:
                    file_message += section.message
        return file_message

    _file_checksum: str | None = None
    _file_message: list[str] | None = None

    def get_code_message(
        self, config: ConfigManager, code_file_manager: "CodeFileManager"
    ) -> list[str]:
        abs_path = config.git_root / self.path
        file_checksum = code_file_manager.get_file_checksum(Path(abs_path))
        if file_checksum != self._file_checksum or self._file_message is None:
            self._file_checksum = file_checksum
            self._file_message = self._get_file_message(config)
        return self._file_message

    def count_tokens(
        self, config: ConfigManager, code_file_manager: "CodeFileManager", model: str
    ) -> int:
        code_message = "\n".join(self.get_code_message(config, code_file_manager))
        return count_tokens(code_message, model)
