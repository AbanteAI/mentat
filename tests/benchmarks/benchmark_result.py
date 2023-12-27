import json
from typing import Optional

import attr

from mentat.transcripts import Transcript


@attr.define
class BenchmarkResult:
    name: str = attr.ib()
    family: Optional[str] = attr.ib(default=None)
    cost: Optional[float] = attr.ib(default=None, metadata={"aggregation": "sum"})
    tokens: Optional[int] = attr.ib(default=None, metadata={"aggregation": "average"})
    iterations: Optional[int] = attr.ib(
        default=None, metadata={"aggregation": "histogram"}
    )
    transcript: Optional[Transcript] = attr.ib(
        default=None, metadata={"display": "transcript"}
    )
    instructions: Optional[str] = attr.ib(default=None, metadata={"display": "text"})
    code: Optional[str] = attr.ib(default=None, metadata={"display": "code"})
    test_output: Optional[str] = attr.ib(
        default=None, metadata={"formatted_name": "Test output", "display": "code"}
    )
    response: Optional[str] = attr.ib(
        default=None, metadata={"formatted_name": "Analysis", "display": "text"}
    )
    reason: Optional[str] = attr.ib(default=None, metadata={"aggregation": "histogram"})
    # For exercism benchmarks
    passed: Optional[bool] = attr.ib(default=None, metadata={"aggregation": "percent"})
    # New optional fields for benchmark results
    diff_grade: Optional[dict] = attr.ib(default=None, metadata={"display": "json"})
    response_grade: Optional[dict] = attr.ib(default=None, metadata={"display": "json"})
    comparison_grade: Optional[dict] = attr.ib(
        default=None, metadata={"display": "json"}
    )
    verify: Optional[bool] = attr.ib(default=None, metadata={"aggregation": "percent"})
    off_by_one: Optional[bool] = attr.ib(
        default=None, metadata={"aggregation": "percent"}
    )
    indentation_error: Optional[bool] = attr.ib(
        default=None, metadata={"aggregation": "percent"}
    )
    syntax_error: Optional[bool] = attr.ib(
        default=None, metadata={"aggregation": "percent"}
    )
    missing_functionality: Optional[bool] = attr.ib(
        default=None, metadata={"aggregation": "percent"}
    )
    extra_functionality: Optional[bool] = attr.ib(
        default=None, metadata={"aggregation": "percent"}
    )
    referenced_format: Optional[bool] = attr.ib(
        default=None, metadata={"aggregation": "percent"}
    )

    def display_color(self) -> str:
        if self.passed is None:
            if self.indentation_error or self.off_by_one or self.syntax_error:
                return "grey"
            if (
                self.missing_functionality
                or self.extra_functionality
                or self.referenced_format
            ):
                return "yellow"
            if self.verify is not None:
                if self.verify:
                    return "green"
                else:
                    return "red"
            return "green"
        elif self.passed:
            return "green"
        else:
            return "red"

    def to_dict(self):
        return attr.asdict(self)

    def to_json(self):
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str):
        return cls(**json.loads(json_str))
