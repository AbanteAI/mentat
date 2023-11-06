from __future__ import annotations

import attr


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


@attr.define
class Interval:
    start: int | float = attr.field()
    end: int | float = attr.field()

    def contains(self, line_number: int):
        return self.start <= line_number <= self.end

    def intersects(self, other: Interval) -> bool:
        return not (other.end < self.start or self.end < other.start)
