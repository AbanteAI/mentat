import json
from typing import Optional, Tuple

import attr

from mentat.transcripts import Transcript


@attr.define
class BenchmarkResult:
    iterations: int = attr.ib(metadata={"aggregation": "histogram"})
    passed: bool = attr.ib(metadata={"aggregation": "percent"})
    name: str = attr.ib()
    cost: float = attr.ib(metadata={"aggregation": "sum"})
    tokens: int = attr.ib(metadata={"aggregation": "average"})
    transcript: Optional[Transcript] = attr.ib(default=None)
    instructions: Optional[str] = attr.ib(default=None)
    code: Optional[str] = attr.ib(default=None)
    test_output: Optional[str] = attr.ib(
        default=None, metadata={"formatted_name": "Test output"}
    )
    response: Optional[str] = attr.ib(
        default=None, metadata={"formatted_name": "Analysis"}
    )
    reason: Optional[str] = attr.ib(default=None, metadata={"aggregation": "histogram"})

    def to_json(self):
        return json.dumps(attr.asdict(self))

    @classmethod
    def from_json(cls, json_str):
        return cls(**json.loads(json_str))


class BenchmarkResultSummary:
    results: list[BenchmarkResult]
    results_map: dict[str, BenchmarkResult]
    summary: dict[str, Tuple[int | float | str, float]]

    def __init__(self, results: list[BenchmarkResult]):
        self.results = results
        self.results_map = {result.name: result for result in results}
        self.summary = self.aggregate_results()

    def aggregate_results(self) -> dict[str, Tuple[int | float | str, float]]:
        summary = {}
        for field in attr.fields(BenchmarkResult):
            if "aggregation" in field.metadata:
                name = field.name
                values = [
                    getattr(result, name)
                    for result in self.results
                    if getattr(result, name) is not None
                ]
                aggregation_type = field.metadata["aggregation"]
                if aggregation_type == "sum":
                    summary[name] = (sum(values), len(values))
                elif aggregation_type == "average":
                    summary[name] = (
                        (sum(values) / len(values), len(values)) if values else (0, 0)
                    )
                elif aggregation_type == "percent":
                    summary[name] = (
                        (sum(values) / len(values) * 100, len(values))
                        if values
                        else (0, 0)
                    )
                elif aggregation_type == "histogram":
                    histogram = {val: values.count(val) for val in set(values)}
                    summary[name] = (histogram, len(values))
                elif aggregation_type == "none":
                    summary[name] = (values, len(values))
        return summary

    def formatted_summary(self) -> dict[str, str]:
        formatted = {}
        for field in attr.fields(BenchmarkResult):
            if "aggregation" in field.metadata:
                name = field.name
                value, count = self.summary[name]
                formatted_value = ""
                aggregation_type = field.metadata["aggregation"]
                if aggregation_type == "average":
                    formatted_name = f"{name} (avg)"
                else:
                    formatted_name = name

                if isinstance(value, float):
                    formatted_value = f"{value:.2f}"
                elif isinstance(value, dict):
                    formatted_value = ", ".join(f"{k}: {v}" for k, v in value.items())
                else:
                    formatted_value = str(value)

                # Add units based on aggregation type
                if aggregation_type == "sum" and "cost" in formatted_name:
                    formatted[formatted_name] = f"${formatted_value}"
                elif aggregation_type == "percent":
                    formatted[formatted_name] = f"{formatted_value}%"
                else:
                    formatted[formatted_name] = formatted_value

        return formatted
