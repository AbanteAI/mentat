import json
import os
from pathlib import Path
from typing import Optional, Tuple

import attr

from benchmarks.benchmark_result import BenchmarkResult


class BenchmarkRunSummary:
    def __init__(
        self,
        summary: dict[str, Tuple[int | float | str, float]],
        metadata: Optional[dict] = None,
    ):
        self.summary = summary
        self.metadata = metadata
        self.display_string = self.display_string()

    def formatted_summary(self) -> dict[str, str]:
        formatted = {}
        total = self.summary["count"][0]
        for field in attr.fields(BenchmarkResult):
            if "aggregation" in field.metadata:
                name = field.name
                value, total_set = self.summary[name]
                if total_set == 0:
                    continue
                percent_set_display = ""
                if total_set < total:
                    percent_set_display = f" ({total_set}/{total})"
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
                    formatted[formatted_name] = f"${formatted_value} {percent_set_display}"
                elif aggregation_type == "percent":
                    formatted[formatted_name] = f"{formatted_value}% {percent_set_display}"
                else:
                    formatted[formatted_name] = f"{formatted_value} {percent_set_display}"

        return formatted

    def display_string(self) -> str:
        return ", ".join(f"{name}: {value}" for name, value in self.formatted_summary().items())

    def to_json(self) -> str:
        return json.dumps(
            {
                "summary": self.summary,
                "metadata": self.metadata,
            },
            indent=4,
        )

    @classmethod
    def load_json(cls, json_str: str) -> "BenchmarkRunSummary":
        data = json.loads(json_str)
        return cls(data["summary"], data["metadata"])

    @classmethod
    def load_file(cls, file: Path) -> "BenchmarkRunSummary":
        file_name = os.path.basename(file)
        with open(file, "r") as f:
            summary = cls.load_json(f.read())
        summary.metadata["file"] = file_name  # Used for links
        return summary
