import argparse


def common_benchmark_parser():
    parser = argparse.ArgumentParser(description="Run exercism benchmarks")
    parser.add_argument(
        "--refresh_repo",
        action="store_true",
        default=False,
        help="When set local changes will be discarded.",
    )
    parser.add_argument(
        "--language",
        default="python",
        type=str,
        help="Which exercism language to do exercises for",
    )
    parser.add_argument(
        "--benchmarks",
        nargs="*",
        default=[],
        help=("Which benchmarks to run. max_benchmarks ignored when set. Exact meaning" " depends on benchmark."),
    )
    parser.add_argument(
        "--directory",
        "-d",
        default="benchmarks/benchmarks",
        type=str,
        help="Directory from which to load benchmarks and/or samples",
    )
    parser.add_argument(
        "--max_benchmarks",
        default=1,
        type=int,
        help="The maximum number of exercises to run",
    )
    parser.add_argument(
        "--max_iterations",
        default=1,
        type=int,
        help="Number of times to rerun mentat with error messages",
    )
    parser.add_argument(
        "--max_workers",
        default=1,
        type=int,
        help="Number of workers to use for multiprocessing",
    )
    parser.add_argument(
        "--retries",
        action="store",
        default=1,
        type=int,
        help="Number of times to retry a benchmark",
    )
    parser.add_argument(
        "--repo",
        action="store",
        default="mentat",
        help="For benchmarks that are evaluated against a repo",
    )
    parser.add_argument(
        "--evaluate_baseline",
        action="store_true",
        help="Evaluate the baseline for the benchmark",
    )
    parser.add_argument(
        "--swe_bench",
        nargs="?",
        const="dev",
        default=None,
        type=str,
        help="Fetch or load SWE-bench examples from split: dev (default), train or test.",
    )
    parser.add_argument(
        "--auto_context_tokens",
        default=0,
        type=int,
        help="Include auto-selected tokens in benchmark runs and evaluate precision/recall",
    )

    return parser
