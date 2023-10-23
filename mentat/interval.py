from __future__ import annotations


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

    def intersects(self, other: Interval) -> bool:
        return not (other.end < self.start or self.end < other.start)
