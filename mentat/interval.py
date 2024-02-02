from __future__ import annotations

import math
import re
from pathlib import Path

import attr


def split_intervals_from_path(custom_path: str | Path) -> tuple[Path, str]:
    match = re.match(
        r"(.*?):((\d+-\d+|\d+)(,\d+(-\d+)?)*$)",  # One or more intervals/numbers
        str(custom_path),
    )
    if match:
        path, intervals = match.groups()[0], match.groups()[1]
        return Path(path), intervals
    else:
        return Path(custom_path), ""


def parse_intervals(interval_string: str) -> list[Interval]:
    try:
        intervals = list[Interval]()
        for interval in interval_string.split(","):
            interval = interval.split("-", 1)
            if len(interval) == 1:
                interval = Interval(int(interval[0]), int(interval[0]) + 1)
            else:
                interval = Interval(int(interval[0]), int(interval[1]))
            if interval.end <= interval.start:
                continue
            intervals.append(interval)
        return intervals
    except (ValueError, IndexError):
        return []


# Unfortunately there is no any way to set class properties with attrs so we can't make this part of Interval
INTERVAL_FILE_END = math.inf


@attr.define(order=True, frozen=True)
class Interval:
    """
    1-indexed interval of file lines, inclusive start, exclusive end
    """

    start: int | float = attr.field()
    end: int | float = attr.field()

    def contains(self, line_number: int) -> bool:
        return self.start <= line_number < self.end

    def intersects(self, other: Interval) -> bool:
        return self.start < other.end and other.start < self.end

    def whole_file(self) -> bool:
        return self.start == 1 and self.end == INTERVAL_FILE_END

    def __str__(self) -> str:
        if self.end == self.start + 1:
            return f"{self.start}"
        else:
            return f"{self.start}-{self.end}"
