import math
from pathlib import Path


class Interval:
    def __init__(
        self,
        start: int,
        end: int,
    ):
        self.start = start
        self.end = end

    def contains(self, k):
        return self.start <= k <= self.end


def parse_intervals(interval_string: str) -> list[Interval] | None:
    try:
        intervals = []
        for interval in interval_string.split(","):
            interval = interval.split("-", 1)
            if len(interval) == 1:
                intervals += [Interval(int(interval[0]), int(interval[0]))]
            else:
                intervals += [Interval(int(interval[0]), int(interval[1]))]
        return intervals
    except (ValueError, IndexError):
        return None


class CodeFile:
    """
    Represents a file along with the lines that should be in the prompt context. Can be
    iniitialized with a Path object or a string path with optional line information
    such as "path/to/file.py:1-5,7,12-40".

    Attributes:
        path: The path to the file.
        intervals: The lines in context.
    """

    def __init__(self, path: str | Path):
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

    def contains_line(self, line_number: int):
        return any([interval.contains(line_number) for interval in self.intervals])
