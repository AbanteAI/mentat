import json
import os
from collections import defaultdict

import fire
import pytest
from termcolor import cprint

benchmark_location = "tests/benchmark_test.py"
benchmark_log_location = "benchmark_results/benchmark.log"
benchmark_results_location = "benchmark_results/benchmark.results"


def main(run=False, threshold=0.75, count=1):
    os.makedirs("benchmark_results", exist_ok=True)

    if not os.path.isfile(benchmark_results_location):
        with open(benchmark_results_location, "w") as results_file:
            results = {}
            results_json = json.dumps(results)
            results_file.write(results_json)

    with open(benchmark_results_location, "r") as results_file:
        results = json.load(results_file)

    if run:
        for _ in range(count):
            os.environ["MENTAT_BENCHMARKS_RUNNING"] = "true"
            pytest.main(
                [
                    benchmark_location,
                    "--benchmark",
                    "--report-log",
                    benchmark_log_location,
                ]
            )
            os.environ["MENTAT_BENCHMARKS_RUNNING"] = "false"
            print()
            nodes = []
            with open(benchmark_log_location, "r") as result_file:
                for line in result_file:
                    nodes.append(json.loads(line))

            # pytest_reportlog makes multiple nodes per test
            test_names = defaultdict(lambda: True)
            for node in nodes:
                if "location" in node:
                    test_name = node["location"][2]
                    passed = node["outcome"] == "passed"
                    test_names[test_name] = test_names[test_name] and passed

            for test_name, success in test_names.items():
                if test_name not in results:
                    results[test_name] = [0, 0]
                results[test_name][1] += 1
                if success:
                    results[test_name][0] += 1
                    cprint(f"{test_name} passed", "green")
                else:
                    cprint(f"{test_name} failed", "red")
            print()

            with open(benchmark_results_location, "w") as results_file:
                results_json = json.dumps(results)
                results_file.write(results_json)

    for test_name in results.keys():
        passes, total = results[test_name]
        frac = passes / total
        cprint(
            f"{test_name}: {passes} / {total} {frac * 100}%",
            "red" if frac < threshold else "green",
        )


if __name__ == "__main__":
    fire.Fire(main)
