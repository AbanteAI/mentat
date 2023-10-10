import math
import os
from enum import Enum
from pathlib import Path

from .code_file_manager import CODE_FILE_MANAGER
from .code_map import get_code_map
from .diff_context import annotate_file_message, parse_diff
from .git_handler import GIT_ROOT, get_diff_for_file
from .llm_api import count_tokens
from .parsers.parser import PARSER


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
    CODE = ("code", 1, "Complete code")
    INTERVAL = ("interval", 2, "Specific range(s)")
    CMAP_FULL = ("cmap_full", 3, "Function/Class names and signatures")
    CMAP = ("cmap", 4, "Function/Class names")
    FILE_NAME = ("file_name", 5, "Relative path/filename")

    def __init__(self, key: str, rank: int, description: str):
        self.key = key
        self.rank = rank
        self.description = description


class CodeFile:
    """
    Represents a section of the code_message which is included with the prompt.
    Includes a section of code and an annotation method.

    Attributes:
        path: The absolute path to the file.
        intervals: The lines in the file.
        level: The level of information to include.
        diff: The diff annotations to include.
    """

    def __init__(
        self,
        path: str | Path,
        level: CodeMessageLevel = CodeMessageLevel.CODE,
        diff: str | None = None,
        user_included: bool = False,
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
        self.user_included = user_included

    def __repr__(self):
        return (
            f"CodeFile(fname={self.path.name}, intervals={self.intervals},"
            f" level={self.level}, diff={self.diff})"
        )

    def contains_line(self, line_number: int):
        return any([interval.contains(line_number) for interval in self.intervals])

    async def _get_code_message(self) -> list[str]:
        git_root = GIT_ROOT.get()
        code_file_manager = CODE_FILE_MANAGER.get()
        parser = PARSER.get()

        code_message: list[str] = []

        # We always want to give GPT posix paths
        abs_path = Path(git_root / self.path)
        rel_path = Path(os.path.relpath(abs_path, git_root))
        posix_rel_path = Path(rel_path).as_posix()
        if self.user_included:
            filename = f"USER INCLUDED: {posix_rel_path}"
        else:
            filename = f"{posix_rel_path}"
        code_message.append(filename)

        if self.level in {CodeMessageLevel.CODE, CodeMessageLevel.INTERVAL}:
            file_lines = code_file_manager.read_file(abs_path)
            for i, line in enumerate(file_lines, start=1):
                if self.contains_line(i):
                    if parser.provide_line_numbers():
                        code_message.append(f"{i}:{line}")
                    else:
                        code_message.append(f"{line}")
        elif self.level == CodeMessageLevel.CMAP_FULL:
            cmap = await get_code_map(git_root, self.path)
            code_message += cmap
        elif self.level == CodeMessageLevel.CMAP:
            cmap = await get_code_map(git_root, self.path, exclude_signatures=True)
            code_message += cmap
        code_message.append("")

        if self.diff is not None:
            diff: str = get_diff_for_file(self.diff, rel_path)
            diff_annotations = parse_diff(diff)
            if self.level == CodeMessageLevel.CODE:
                code_message = annotate_file_message(code_message, diff_annotations)
            else:
                for section in diff_annotations:
                    code_message += section.message
        return code_message

    _file_checksum: str | None = None
    _code_message: list[str] | None = None

    async def get_code_message(self) -> list[str]:
        git_root = GIT_ROOT.get()
        code_file_manager = CODE_FILE_MANAGER.get()
        abs_path = git_root / self.path
        file_checksum = code_file_manager.get_file_checksum(Path(abs_path))
        if file_checksum != self._file_checksum or self._code_message is None:
            self._file_checksum = file_checksum
            self._code_message = await self._get_code_message()
        return self._code_message

    async def count_tokens(self, model: str) -> int:
        code_message = await self.get_code_message()
        return count_tokens("\n".join(code_message), model)
