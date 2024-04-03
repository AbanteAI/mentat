from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict, defaultdict
from pathlib import Path
from typing import Optional

import attr

from mentat.ctags import get_ctag_lines_and_names
from mentat.diff_context import annotate_file_message, parse_diff
from mentat.errors import MentatError
from mentat.git_handler import get_diff_for_file
from mentat.interval import INTERVAL_FILE_END, Interval
from mentat.llm_api_handler import count_tokens
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import get_relative_path

MIN_INTERVAL_LINES = 10


def split_file_into_intervals(
    feature: CodeFeature,
    min_lines: int | None = None,
) -> list[CodeFeature]:
    min_lines = min_lines or MIN_INTERVAL_LINES
    session_context = SESSION_CONTEXT.get()
    code_file_manager = session_context.code_file_manager
    n_lines = len(code_file_manager.read_file(feature.path))

    lines_and_names = get_ctag_lines_and_names(session_context.cwd.joinpath(feature.path))

    if len(lines_and_names) == 0:
        return [feature]

    lines, names = map(list, zip(*sorted(lines_and_names)))
    lines[0] = 1  # first interval covers from start of file
    draft_named_intervals = [(name, start, end) for name, start, end in zip(names, lines, lines[1:] + [n_lines])]

    def length(interval: tuple[str, int, int]):
        return interval[2] - interval[1]

    def merge_intervals(int1: tuple[str, int, int], int2: tuple[str, int, int]):
        return (f"{int1[0]},{int2[0]}", int1[1], int2[2])

    named_intervals = [draft_named_intervals[0]]
    for next_interval in draft_named_intervals[1:]:
        last_interval = named_intervals[-1]
        if length(last_interval) < min_lines:
            named_intervals[-1] = merge_intervals(last_interval, next_interval)
        elif length(next_interval) < min_lines and next_interval == draft_named_intervals[-1]:
            # this is the last interval it's too short, so merge it with previous
            named_intervals[-1] = merge_intervals(last_interval, next_interval)
        else:
            named_intervals.append(next_interval)

    if len(named_intervals) <= 1:
        return [feature]

    # Create and return separate features for each interval
    _features = list[CodeFeature]()
    for name, start, end in named_intervals:
        _feature = CodeFeature(
            feature.path,
            interval=Interval(start, end),
            name=name,
        )
        _features.append(_feature)
    return _features


@attr.define(frozen=True)
class CodeFeature:
    """
    Represents a section of the code_message which is included with the prompt.
    Includes a section of code and an annotation method.

    Attributes:
        path: The absolute path to the file.
        interval: The lines in the file.
        name: The names of the features/functions in this CodeFeature
    """

    path: Path = attr.field()
    interval: Interval = attr.field(factory=lambda: Interval(1, INTERVAL_FILE_END))
    # eq is set to false so that we can compare duplicate features without names getting in the way
    name: Optional[str] = attr.field(default=None, eq=False)

    def __attrs_post_init__(self):
        if not self.path.is_absolute():
            raise MentatError("CodeFeature path must be absolute.")

    def __repr__(self):
        return (
            f"CodeFeature(path={self.path}," f" interval={self.interval.start}-{self.interval.end}, name={self.name})"
        )

    def rel_path(self, cwd: Optional[Path] = None) -> str:
        if cwd is not None:
            path_string = str(get_relative_path(self.path, cwd))
        else:
            path_string = str(self.path)
        return path_string

    def interval_string(self) -> str:
        if not self.interval.whole_file():
            interval_string = f":{self.interval.start}-{self.interval.end}"
        else:
            interval_string = ""
        return interval_string

    def __str__(self, cwd: Optional[Path] = None) -> str:
        return self.rel_path(cwd) + self.interval_string()

    def get_code_message(self, standalone: bool = True) -> list[str]:
        """
        Gets this code features code message.
        If standalone is true, will include the filename at top and extra newline at the end.
        If feature contains entire file, will add inline diff annotations; otherwise, will append them to the end.
        """
        if not self.path.exists() or self.path.is_dir():
            return []

        session_context = SESSION_CONTEXT.get()
        code_file_manager = session_context.code_file_manager
        parser = session_context.config.parser
        code_context = session_context.code_context

        code_message: list[str] = []

        if standalone:
            # We always want to give GPT posix paths
            code_message_path = get_relative_path(self.path, session_context.cwd)
            code_message.append(str(code_message_path.as_posix()))

        # Get file lines
        file_lines = code_file_manager.read_file(self.path)
        for i, line in enumerate(file_lines):
            if self.interval.contains(i + 1):
                if parser.provide_line_numbers():
                    code_message.append(f"{i + parser.line_number_starting_index()}:{line}")
                else:
                    code_message.append(f"{line}")

        if standalone:
            code_message.append("")

        if self.path in code_context.diff_context.diff_files():
            diff = get_diff_for_file(code_context.diff_context.target, self.path)
            diff_annotations = parse_diff(diff)
            if self.interval.whole_file():
                code_message = annotate_file_message(code_message, diff_annotations)
            else:
                for section in diff_annotations:
                    # TODO: Place diff_annotations inside interval where they belong
                    if section.start >= self.interval.start and section.start < self.interval.end:
                        code_message += section.message
        return code_message

    def get_checksum(self) -> str:
        # TODO: Only update checksum if last modified time of file updates to conserve file system reads
        session_context = SESSION_CONTEXT.get()
        code_file_manager = session_context.code_file_manager

        return code_file_manager.get_file_checksum(self.path, self.interval)

    def count_tokens(self, model: str) -> int:
        code_message = self.get_code_message()
        return count_tokens("\n".join(code_message), model, full_message=False)


async def count_feature_tokens(features: list[CodeFeature], model: str) -> list[int]:
    """Return the number of tokens in each feature."""
    sem = asyncio.Semaphore(10)

    feature_tokens = list[int]()
    for feature in features:
        async with sem:
            tokens = feature.count_tokens(model)
            feature_tokens.append(tokens)
    return feature_tokens


def _get_code_message_from_intervals(features: list[CodeFeature]) -> list[str]:
    """
    Merge multiple features for the same file into a single code message.
    """
    features_sorted = sorted(features, key=lambda f: f.interval)
    posix_path = features_sorted[0].get_code_message()[0]
    code_message = [posix_path]
    next_line = 1
    for feature in features_sorted:
        starting_line = feature.interval.start
        if starting_line < next_line:
            logging.info(f"Features overlap: {feature}")
            if feature.interval.end <= next_line:
                continue
            feature = CodeFeature(
                feature.path,
                interval=Interval(next_line, feature.interval.end),
                name=feature.name,
            )
        elif starting_line > next_line:
            code_message += ["..."]
        code_message += feature.get_code_message(standalone=False)
        next_line = feature.interval.end
    return code_message + [""]


def get_code_message_from_features(features: list[CodeFeature]) -> list[str]:
    """
    Generate a code message from a list of features.
    Will automatically handle overlapping intervals.
    """
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
            code_message += _get_code_message_from_intervals(path_features)
    return code_message


def get_consolidated_feature_refs(features: list[CodeFeature]) -> list[str]:
    """
    Return a list of 'path:<interval>,<interval>' strings, merging code features with the same path
    """
    level_info_by_path = defaultdict[Path, list[Interval | None]](list)
    for f in features:
        if f.interval.whole_file():
            level_info_by_path[f.path].append(None)
        else:
            level_info_by_path[f.path].append(f.interval)

    consolidated_refs = list[str]()
    for path, level_info in level_info_by_path.items():
        ref_string = str(path)
        intervals = sorted([level for level in level_info if level is not None])
        if intervals and None not in level_info:
            ref_string += ":" + ",".join(str(interval) for interval in intervals)
        consolidated_refs.append(ref_string)

    return consolidated_refs
