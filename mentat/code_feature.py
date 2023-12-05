from __future__ import annotations

import asyncio
import logging
import math
from collections import OrderedDict, defaultdict
from enum import Enum
from pathlib import Path
from typing import Optional

from mentat.ctags import get_ctag_lines_and_names
from mentat.diff_context import annotate_file_message, parse_diff
from mentat.errors import MentatError
from mentat.git_handler import get_diff_for_file
from mentat.interval import Interval, parse_intervals
from mentat.llm_api_handler import count_tokens
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import get_relative_path, sha256

MIN_INTERVAL_LINES = 10


def split_file_into_intervals(
    feature: CodeFeature,
    min_lines: int | None = None,
    user_features: list[CodeFeature] = [],
) -> list[CodeFeature]:
    if feature.level != CodeMessageLevel.CODE:
        return [feature]

    min_lines = min_lines or MIN_INTERVAL_LINES
    session_context = SESSION_CONTEXT.get()
    code_file_manager = session_context.code_file_manager
    n_lines = len(code_file_manager.read_file(feature.path))

    lines_and_names = get_ctag_lines_and_names(
        session_context.cwd.joinpath(feature.path)
    )

    if len(lines_and_names) == 0:
        return [feature]

    lines, names = map(list, zip(*sorted(lines_and_names)))
    lines[0] = 1  # first interval covers from start of file
    draft_named_intervals = [
        (name, start, end)
        for name, start, end in zip(names, lines, lines[1:] + [n_lines])
    ]

    def length(interval: tuple[str, int, int]):
        return interval[2] - interval[1]

    def merge_intervals(int1: tuple[str, int, int], int2: tuple[str, int, int]):
        return (f"{int1[0]},{int2[0]}", int1[1], int2[2])

    named_intervals = [draft_named_intervals[0]]
    for next_interval in draft_named_intervals[1:]:
        last_interval = named_intervals[-1]
        if length(last_interval) < min_lines:
            named_intervals[-1] = merge_intervals(last_interval, next_interval)
        elif (
            length(next_interval) < min_lines
            and next_interval == draft_named_intervals[-1]
        ):
            # this is the last interval it's too short, so merge it with previous
            named_intervals[-1] = merge_intervals(last_interval, next_interval)
        else:
            named_intervals.append(next_interval)

    if len(named_intervals) <= 1:
        return [feature]

    # Create and return separate features for each interval
    _features = list[CodeFeature]()
    for name, start, end in named_intervals:
        _user_included = any(
            u.contains_line(i) for u in user_features for i in range(start, end + 1)
        )
        feature_string = f"{feature.path}:{start}-{end}"
        _feature = CodeFeature(
            feature_string,
            level=CodeMessageLevel.INTERVAL,
            diff=feature.diff,
            user_included=_user_included,
            name=name,
        )
        _features.append(_feature)
    return _features


class CodeMessageLevel(Enum):
    CODE = ("code", 1, "Full File")
    INTERVAL = ("interval", 2, "Specific range")
    FILE_NAME = ("file_name", 3, "Relative path/filename")

    def __init__(self, key: str, rank: int, description: str):
        self.key = key
        self.rank = rank
        self.description = description


class CodeFeature:
    """
    Represents a section of the code_message which is included with the prompt.
    Includes a section of code and an annotation method.

    Attributes:
        path: The absolute path to the file.
        interval: The lines in the file.
        level: The level of information to include.
        diff: The diff annotations to include.
    """

    def __init__(
        self,
        path: str | Path,
        level: CodeMessageLevel = CodeMessageLevel.CODE,
        diff: str | None = None,
        user_included: bool = False,
        name: Optional[str] = None,
    ):
        if Path(path).exists():
            self.path = Path(path)
            self.interval = Interval(0, math.inf)
        else:
            path = str(path)
            split = path.rsplit(":", 1)
            self.path = Path(split[0])
            if not self.path.exists():
                self.path = Path(path)
                self.interval = Interval(0, math.inf)
            else:
                interval = parse_intervals(split[1])
                if len(interval) > 1:
                    raise MentatError("CodeFeatures should only have on interval.")
                self.interval = interval[0]
                level = CodeMessageLevel.INTERVAL

        if not self.path.is_absolute():
            raise MentatError("CodeFeature path must be absolute.")

        self.level = level
        self.diff = diff
        self.user_included = user_included
        self.name = name

    def __repr__(self):
        return (
            f"CodeFeature(fname={self.path.name},"
            f" interval={self.interval.start}-{self.interval.end},"
            f" level={self.level.key}, diff={self.diff})"
        )

    def ref(self, cwd: Optional[Path] = None) -> str:
        if cwd is not None and self.path.is_relative_to(cwd):
            path_string = self.path.relative_to(cwd)
        else:
            path_string = str(self.path)

        if self.level == CodeMessageLevel.INTERVAL:
            interval_string = f":{self.interval.start}-{self.interval.end}"
        else:
            interval_string = ""

        return f"{path_string}{interval_string}"

    def contains_line(self, line_number: int):
        return self.interval.contains(line_number)

    def _get_code_message(self) -> list[str]:
        session_context = SESSION_CONTEXT.get()
        code_file_manager = session_context.code_file_manager
        parser = session_context.config.parser

        code_message: list[str] = []

        # We always want to give GPT posix paths
        code_message_path = get_relative_path(self.path, session_context.cwd)
        code_message.append(str(code_message_path.as_posix()))

        if self.level in {CodeMessageLevel.CODE, CodeMessageLevel.INTERVAL}:
            file_lines = code_file_manager.read_file(self.path)
            for i, line in enumerate(file_lines):
                if self.contains_line(i + 1):
                    if parser.provide_line_numbers():
                        code_message.append(
                            f"{i + parser.line_number_starting_index()}:{line}"
                        )
                    else:
                        code_message.append(f"{line}")
        code_message.append("")

        if self.diff is not None:
            diff: str = get_diff_for_file(self.diff, self.path)
            diff_annotations = parse_diff(diff)
            if self.level == CodeMessageLevel.CODE:
                code_message = annotate_file_message(code_message, diff_annotations)
            else:
                for section in diff_annotations:
                    code_message += section.message
        return code_message

    def get_checksum(self) -> str:
        session_context = SESSION_CONTEXT.get()
        code_file_manager = session_context.code_file_manager

        file_checksum = code_file_manager.get_file_checksum(self.path, self.interval)
        return sha256(f"{file_checksum}{self.level.key}{self.diff}")

    _feature_checksum: str | None = None
    _code_message: list[str] | None = None

    def get_code_message(self) -> list[str]:
        feature_checksum = self.get_checksum()
        if feature_checksum != self._feature_checksum or self._code_message is None:
            self._feature_checksum = feature_checksum
            self._code_message = self._get_code_message()
        return self._code_message

    def count_tokens(self, model: str) -> int:
        code_message = self.get_code_message()
        return count_tokens("\n".join(code_message), model, full_message=False)


async def count_feature_tokens(features: list[CodeFeature], model: str) -> list[int]:
    """Return the number of tokens in each feature."""
    sem = asyncio.Semaphore(10)

    async def _count_tokens(feature: CodeFeature) -> int:
        async with sem:
            return feature.count_tokens(model)

    tasks = [_count_tokens(f) for f in features]
    return await asyncio.gather(*tasks)


def get_code_message_from_intervals(features: list[CodeFeature]) -> list[str]:
    """Merge multiple features for the same file into a single code message"""
    features_sorted = sorted(features, key=lambda f: f.interval.start)
    posix_path = features_sorted[0].get_code_message()[0]
    code_message = [posix_path]
    next_line = 1
    for feature in features_sorted:
        starting_line = feature.interval.start
        if starting_line < next_line:
            logging.warning(f"Features overlap: {feature}")
            if feature.interval.end < next_line:
                continue
            feature.interval = Interval(next_line, feature.interval.end)
        elif starting_line > next_line:
            code_message += ["..."]
        code_message += feature.get_code_message()[1:-1]
        next_line = feature.interval.end
    return code_message + [""]


def get_code_message_from_features(features: list[CodeFeature]) -> list[str]:
    """Generate a code message from a list of features"""
    code_message = list[str]()
    features_by_path: dict[Path, list[CodeFeature]] = OrderedDict()
    for feature in features:
        if feature.path not in features_by_path:
            features_by_path[feature.path] = list[CodeFeature]()
        features_by_path[feature.path].append(feature)
    for path_features in features_by_path.values():
        if len(path_features) == 1:
            code_message += path_features[0].get_code_message()
        else:
            code_message += get_code_message_from_intervals(path_features)
    return code_message


def get_consolidated_feature_refs(features: list[CodeFeature]) -> list[str]:
    """Return a list of 'path:<interval>,<interval>' strings"""
    level_info_by_path = defaultdict[Path, list[Interval | None]](list)
    for f in features:
        if f.level == CodeMessageLevel.CODE:
            level_info_by_path[f.path].append(None)
        elif f.level == CodeMessageLevel.INTERVAL:
            level_info_by_path[f.path].append(f.interval)
        else:
            pass  # Skipping filename, code_maps

    consolidated_refs = list[str]()
    for path, level_info in level_info_by_path.items():
        ref_string = str(path)
        if not any(level is None for level in level_info):
            intervals = sorted(
                [level for level in level_info if isinstance(level, Interval)],
                key=lambda i: i.start,
            )
            ref_string += f":{intervals[0].start}-"
            last_end = intervals[0].end
            for i in intervals[1:]:
                if i.start > last_end + 1:
                    ref_string += f"{last_end},{i.start}-"
                last_end = i.end
            ref_string += str(last_end)
        consolidated_refs.append(ref_string)

    return consolidated_refs
