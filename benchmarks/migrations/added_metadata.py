#!/usr/bin/env python
import argparse
from datetime import datetime
from pathlib import Path

from benchmarks.benchmark_run import BenchmarkRun


def migration(path: Path):
    full_result_path = path / "result"
    html_path = full_result_path
    full_result_path.mkdir(exist_ok=True)
    html_path.mkdir(exist_ok=True)
    for file in path.iterdir():
        if file.is_file() and file.suffix == ".json":
            benchmark_run = BenchmarkRun.load_file(file)
            try:
                timestr = file.stem.split("-")[-1].split(".")[0]
                date = datetime.strptime(timestr, "%Y%m%d%H%M%S")
                benchmark_run.metadata["date"] = date.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
            if "branch" not in benchmark_run.metadata:
                benchmark_run.metadata["branch"] = "main"

            if "type" not in benchmark_run.metadata:
                benchmark_run.metadata["type"] = file.stem.split("-")[0]
                if benchmark_run.metadata["type"] == "exercism":
                    benchmark_run.metadata["language"] = file.stem.split("-")[1]

            if "file" not in benchmark_run.metadata:
                benchmark_run.metadata["file"] = file.name

            benchmark_run.save(folder=full_result_path, name=file.name)
            benchmark_run.make_html_report(html_path / file.name.replace(".json", ".html"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path, help="Path to the benchmark result directory")
    args = parser.parse_args()
    migration(args.path)
