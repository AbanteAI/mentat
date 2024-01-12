import json
import os
import webbrowser
from typing import Tuple

import attr
from jinja2 import Environment, FileSystemLoader, select_autoescape

from benchmarks.benchmark_result import BenchmarkResult


class BenchmarkResultSummary:
    def __init__(self, results: list[BenchmarkResult]):
        self.results = results
        self.results_map = {result.name: result for result in results}
        self.result_groups = self.group_results()
        self.summary: dict[str, Tuple[int | float | str, float]] = (
            self.aggregate_results()
        )

    def group_results(self) -> dict[str, list[BenchmarkResult]]:
        groups = {}
        for result in self.results:
            if result.family is None:
                groups[result.name] = [result]
            else:
                if result.family not in groups:
                    groups[result.family] = []
                groups[result.family].append(result)
        return groups

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
                if len(values) == 0:
                    summary[name] = (0, 0)
                else:
                    total_set = len(values)
                    aggregation_type = field.metadata["aggregation"]
                    if aggregation_type == "sum":
                        summary[name] = (sum(values), total_set)
                    elif aggregation_type == "average":
                        summary[name] = (sum(values) / len(values), total_set)
                    elif aggregation_type == "percent":
                        summary[name] = (sum(values) / len(values) * 100, total_set)
                    elif aggregation_type == "histogram":
                        histogram = {val: values.count(val) for val in set(values)}
                        summary[name] = (histogram, len(values))
                    elif aggregation_type == "none":
                        summary[name] = (values, len(values))
        return summary

    def formatted_summary(self) -> dict[str, str]:
        formatted = {}
        total = len(self.results)
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
                    formatted[formatted_name] = (
                        f"${formatted_value} {percent_set_display}"
                    )
                elif aggregation_type == "percent":
                    formatted[formatted_name] = (
                        f"{formatted_value}% {percent_set_display}"
                    )
                else:
                    formatted[formatted_name] = (
                        f"{formatted_value} {percent_set_display}"
                    )

        return formatted

    def formatted_results(self) -> list[dict[str, str]]:
        formatted = {}
        for result in self.results:
            formatted_result = {}
            for field in attr.fields(BenchmarkResult):
                if "display" in field.metadata:
                    name = field.name
                    value = getattr(result, name)
                    if value is not None:
                        display_name = field.metadata.get("display_name", name)
                        formatted_result[display_name] = {
                            "content": value,
                            "type": field.metadata["display"],
                        }
            formatted[result.name] = formatted_result
        return formatted

    def summary_string(self) -> str:
        return ", ".join(
            f"{name}: {value}" for name, value in self.formatted_summary().items()
        )

    def render_results(self):
        env = Environment(
            loader=FileSystemLoader(
                os.path.join(os.path.dirname(__file__), "../mentat/resources/templates")
            ),
            autoescape=select_autoescape(["html", "xml"]),
        )
        template = env.get_template("benchmark.jinja")
        rendered_html = template.render(summary=self)

        with open("results.html", "w") as f:
            f.write(rendered_html)
        webbrowser.open("file://" + os.path.realpath("results.html"))

    def to_json(self) -> str:
        return json.dumps(
            {
                "results": [result.to_dict() for result in self.results],
                "summary": self.formatted_summary(),
                "summary_string": self.summary_string(),
            },
            indent=4,
        )
