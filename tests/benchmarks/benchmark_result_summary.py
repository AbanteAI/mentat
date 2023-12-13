import os
import webbrowser
from typing import Tuple

import attr
from jinja2 import Environment, FileSystemLoader, select_autoescape

from tests.benchmarks.benchmark_result import BenchmarkResult


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
                elif aggregation_type == "percent" and "verify" in formatted_name:
                    formatted[formatted_name] = f"{formatted_value}% (verified)"
                else:
                    formatted[formatted_name] = formatted_value

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
            formatted[result.escaped_name] = formatted_result
        return formatted

    def render_results(self):
        env = Environment(
            loader=FileSystemLoader(
                os.path.join(
                    os.path.dirname(__file__), "../../mentat/resources/templates"
                )
            ),
            autoescape=select_autoescape(["html", "xml"]),
        )
        template = env.get_template("exercism_benchmark.jinja")
        rendered_html = template.render(summary=self)

        with open("results.html", "w") as f:
            f.write(rendered_html)
        webbrowser.open("file://" + os.path.realpath("results.html"))
