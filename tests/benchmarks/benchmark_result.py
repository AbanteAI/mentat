import json
from typing import Optional

import attr

from mentat.transcripts import Transcript


@attr.define
class BenchmarkResult:
    iterations: int
    passed: bool
    name: str
    cost: float
    tokens: int
    transcript: Optional[Transcript] = attr.ib(default=None)
    instructions: Optional[str] = attr.ib(default=None)
    code: Optional[str] = attr.ib(default=None)
    test_output: Optional[str] = attr.ib(default=None)
    response: Optional[str] = attr.ib(default=None)
    reason: Optional[str] = attr.ib(default=None)
    success: Optional[bool] = attr.ib(default=None)

    def to_json(self):
        return json.dumps(attr.asdict(self))

    @classmethod
    def from_json(cls, json_str):
        return cls(**json.loads(json_str))
