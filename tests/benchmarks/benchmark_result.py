import json
from typing import Optional

import attr

from mentat.transcripts import Transcript


@attr.define
class BenchmarkResult:
    iterations: int = attr.ib(metadata={"aggregation": "histogram"})
    passed: bool = attr.ib(metadata={"aggregation": "percent"})
    name: str = attr.ib()
    cost: float = attr.ib(metadata={"aggregation": "sum"})
    tokens: int = attr.ib(metadata={"aggregation": "average"})
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

    def to_json(self):
        return json.dumps(attr.asdict(self))

    @classmethod
    def from_json(cls, json_str):
        return cls(**json.loads(json_str))
