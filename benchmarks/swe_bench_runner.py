import argparse
import json
import os
from pathlib import Path
from typing import Any

from datasets import load_dataset, DatasetDict  # type: ignore

from mentat.sampler.sample import Sample
from benchmarks.run_sample import validate_test_fields


SWE_BENCH_SAMPLES_DIR = Path(__file__).parent / "benchmarks" / "swe_bench_samples"


def download_swe_benchmarks(split: str = "dev") -> list[dict[str, str]]:
    """3 splits are available: dev (225), test (2.29k), and train (19k)."""
    dataset: DatasetDict = load_dataset("princeton-nlp/SWE-bench", split=split)  # type: ignore
    dataset: list[dict[str, str]] = [dict(benchmark) for benchmark in dataset]
    return dataset


def get_swe_samples(split: str = "dev", max_benchmarks: int | None = None) -> list[Sample]:
    """Return a list of SWE-Bench samples.

    If missing, download, convert to Samples and save locally.
    """
    split_dir = SWE_BENCH_SAMPLES_DIR / split
    saved_benchmarks = list(split_dir.glob("*.json"))
    if not split_dir.exists() or max_benchmarks and len(saved_benchmarks) < max_benchmarks:
        print(f"Downloading {split} split from SWE-Bench...")
        split_dir.mkdir(parents=True, exist_ok=True)
        dataset = download_swe_benchmarks(split)
        samples = [Sample.from_swe_bench(benchmark) for benchmark in dataset]
        for sample in samples:
            sample.save(split_dir / f"{sample.id}.json")
    else:
        samples = [Sample.load(fname) for fname in saved_benchmarks]

    if max_benchmarks:
        samples = samples[:max_benchmarks]
    print(f"Selected {len(samples)} benchmarks from '{split}'")
    return samples


def validate_swe_samples(targets: list[str] | None = None) -> None:
    cwd = Path.cwd()
    samples = get_swe_samples()

    results_path = cwd / "swe_bench_validation_results.json"
    if results_path.exists():
        with open(results_path, "r") as f:
            results = json.load(f)
        print(f"Loaded {len(results)} previous validation results.")
    else:
        results_path.touch()
        results = dict[str, Any]()
    for sample in samples:
        os.chdir(cwd)

        if targets and not any(b in sample.title for b in targets):
            continue
        # if sample.title in results:
        #     continue
        try:
            print(80 * "*" + f"\nValidating {sample.id}...")
            test_results = validate_test_fields(sample)
            percentages = _results_to_percentages(test_results)
            for category, percent in percentages.items():
                expected = 0 if "_PRE" in category else 100
                print(f"{category}: {percent:.2f}% (expected {expected}%)")
            results[sample.title] = test_results
        except Exception as e:
            print(f"Error: {e}")
            results[sample.title] = {"error": str(e)}
        finally:
            with open(results_path, "w") as f:
                json.dump(results, f, indent=4)


def _results_to_percentages(test_results: dict[str, Any]) -> dict[str, float]:
    percentages = dict[str, float]()
    for category, result in test_results.items():
        _passed, _total = result.get("passed", 0), result.get("total", 0)
        percentage = 0 if _total == 0 else _passed / _total * 100
        percentages[category] = percentage
    return percentages


if __name__ == "__main__":

    # anything added after 'python3 swe_bench_runner.py here or here' should go to
    # a list of strings, ["here", "or", "here"].
    parser = argparse.ArgumentParser()
    parser.add_argument("targets", nargs="*")
    parsed_args = parser.parse_args()
    targets = [str(arg) for arg in parsed_args.targets]

    validate_swe_samples(targets)
