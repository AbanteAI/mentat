from __future__ import annotations

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
            intervals.append(interval)
        return intervals
    except (ValueError, IndexError):
        return []


@attr.define
class Interval:
    start: int | float = attr.field()
    end: int | float = attr.field()

    def contains(self, line_number: int):
        return self.start <= line_number < self.end

    def intersects(self, other: Interval) -> bool:
        return not (other.end < self.start or self.end < other.start)
