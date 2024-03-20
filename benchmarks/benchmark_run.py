import json
import os
import webbrowser
from pathlib import Path
from typing import Optional, Tuple

import attr
from jinja2 import Environment, FileSystemLoader, select_autoescape

from benchmarks.benchmark_result import BenchmarkResult
from benchmarks.benchmark_run_summary import BenchmarkRunSummary


class BenchmarkRun:
    def __init__(
        self,
        results: list[BenchmarkResult],
        metadata: Optional[dict] = None,
    ):
        self.results = results
        self.metadata = metadata or {}
        self.results_map = {result.name: result for result in results}
        self.result_groups = self.group_results()
        self.summary: BenchmarkRunSummary = self.aggregate_results()

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

    def aggregate_results(self) -> BenchmarkRunSummary:
        summary: dict[str, Tuple[int | float | str, float]] = {}
        for field in attr.fields(BenchmarkResult):
            if "aggregation" in field.metadata:
                name = field.name
                values = [getattr(result, name) for result in self.results if getattr(result, name) is not None]
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
        return BenchmarkRunSummary(summary, self.metadata)

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

    def make_html_report(self, output_path: Path = Path("results.html")):
        env = Environment(
            loader=FileSystemLoader(
                [
                    os.path.join(os.path.dirname(__file__), "../mentat/resources/templates"),
                    os.path.join(os.path.dirname(__file__), "resources/templates"),
                ]
            ),
            autoescape=select_autoescape(["html", "xml"]),
        )
        template = env.get_template("benchmark.jinja")
        rendered_html = template.render(benchmark_run=self)

        with open(output_path, "w") as f:
            f.write(rendered_html)

    def render_results(self):
        self.make_html_report()

        webbrowser.open("file://" + os.path.realpath("results.html"))

    def to_json(self) -> str:
        return json.dumps(
            {
                "results": [result.to_dict() for result in self.results],
                "metadata": self.metadata,
            },
            indent=4,
        )

    def save(
        self,
        folder: Path = Path("."),
        name: str = "results.json",
        summary_dir: str = "summary",
    ):
        folder.mkdir(parents=True, exist_ok=True)
        summary_dir = folder / summary_dir
        summary_dir.mkdir(parents=True, exist_ok=True)
        file_path = folder / name
        summary_path = summary_dir / name
        with open(file_path, "w") as f:
            f.write(self.to_json())
        with open(summary_path, "w") as f:
            f.write(self.summary.to_json())

    @classmethod
    def load_json(cls, json_str: str) -> "BenchmarkRun":
        data = json.loads(json_str)
        results = [BenchmarkResult.from_dict(result) for result in data["results"]]
        metadata = data.get("metadata")
        return cls(results, metadata=metadata)

    @classmethod
    def load_file(cls, file: Path) -> "BenchmarkRun":
        file_name = os.path.basename(file)
        with open(file, "r") as f:
            run = cls.load_json(f.read())
        run.metadata["file"] = file_name  # Used for links
        return run
