import json
import re
from typing import Optional

import attr

from mentat.transcripts import Transcript


@attr.define
class BenchmarkResult:
    passed: bool = attr.ib(metadata={"aggregation": "percent"})
    name: str = attr.ib()
    cost: float = attr.ib(metadata={"aggregation": "sum"})
    tokens: int = attr.ib(metadata={"aggregation": "average"})
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
    # New optional fields for benchmark results
    diff_grade: Optional[dict] = attr.ib(default=None, metadata={"display": "json"})
    response_grade: Optional[dict] = attr.ib(default=None, metadata={"display": "json"})
    comparison_grade: Optional[dict] = attr.ib(
        default=None, metadata={"display": "json"}
    )
    verify: Optional[bool] = attr.ib(default=None, metadata={"aggregation": "percent"})

    @property
    def escaped_name(self) -> str:
        """For use as html id"""
        return re.sub(r"[ '\"/\\-^]", "", self.name).replace(" ", "_")

    def to_json(self):
        return json.dumps(attr.asdict(self))

    @classmethod
    def from_json(cls, json_str):
        return cls(**json.loads(json_str))
