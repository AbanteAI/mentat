#!/usr/bin/env python
import webbrowser
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from benchmarks.benchmark_run_summary import BenchmarkRunSummary
from benchmarks.plot_generator import generate_plot_html


def generate_list(path: Path, output: Path):
    summaries = []
    for file in path.iterdir():
        if file.is_file() and file.suffix == ".json":
            summary = BenchmarkRunSummary.load_file(file)
            summaries.append(summary)

    plot = generate_plot_html(summaries)
    env = Environment(
        loader=FileSystemLoader(
            [
                Path(__file__).parent / "resources/templates",
                Path(__file__).parent.parent / "mentat/resources/templates",
            ]
        ),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("benchmark_list.jinja")
    rendered_html = template.render(summary_list=summaries, plot=plot)

    with open(output, "w") as f:
        f.write(rendered_html)
    webbrowser.open(f"file://{output.resolve()}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path, help="Path to the benchmark result directory")
    parser.add_argument("output", type=Path, help="Path to the benchmark result directory")
    args = parser.parse_args()
    generate_list(args.path, args.output)
