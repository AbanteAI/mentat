from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Optional

import attr
from ragdaemon.utils import get_document

from mentat.errors import MentatError
from mentat.interval import INTERVAL_FILE_END, Interval
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import get_relative_path

MIN_INTERVAL_LINES = 10


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


def count_feature_tokens(feature: CodeFeature, model: str) -> int:
    ctx = SESSION_CONTEXT.get()

    cwd = ctx.cwd
    ref = feature.__str__(cwd)
    document = get_document(ref, cwd)
    return ctx.llm_api_handler.spice.count_tokens(document, model, is_message=False)


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
