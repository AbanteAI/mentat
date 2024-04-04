"""
NOTE: Not all of the Samples are valid with our current implementation. The list of 
valid samples is saved in the `summoning-the-shoggoth` repo for now. Running this file
directly from the command line will run the full validation script and overwrite the
results there (takes a few hours).
"""
import argparse
import json
import os
from pathlib import Path
from typing import Any

from datasets import DatasetDict, load_dataset  # type: ignore

from benchmarks.run_sample import validate_test_fields
from mentat.sampler.sample import Sample

SWE_BENCH_SAMPLES_DIR = Path(__file__).parent / "benchmarks" / "swe_bench_samples"
SWE_VALIDATION_RESULTS_PATH = (
    Path(__file__).parent.parent.parent
    / "summoning-the-shoggoth"
    / "swe_bench"
    / "swe_bench_validation_results_2024-03-29.json"
)


def download_swe_benchmarks(split: str = "dev") -> list[dict[str, str]]:
    """Get raw SWE-Bench json samples from huggingface

    3 splits are available: dev (225), test (2.29k), and train (19k).
    """
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

    # Check that samples are valid
    valid_samples = list[Sample]()
    if not SWE_VALIDATION_RESULTS_PATH.exists():
        print(f"Sample validation results not found at {SWE_VALIDATION_RESULTS_PATH}.")
        print("Validating SWE samples...")
        print("\033[93m" + "Warning: This will take a couple hours." + "\033[0m")
        # This takes a couple hours.
        validate_swe_samples()
    with open(SWE_VALIDATION_RESULTS_PATH, "r") as f:
        swe_validation_results = json.load(f)
    for sample in samples:
        results = swe_validation_results.get(sample.title)
        pass_to_pass = (
            "PASS_TO_PASS" in results and results["PASS_TO_PASS"]["passed"] == results["PASS_TO_PASS"]["total"]
        )
        fail_to_pass_post = (
            "FAIL_TO_PASS_POST" in results
            and results["FAIL_TO_PASS_POST"]["passed"] == results["FAIL_TO_PASS_POST"]["total"]
        )
        if pass_to_pass and fail_to_pass_post:
            valid_samples.append(sample)
    samples = valid_samples

    if max_benchmarks:
        samples = samples[:max_benchmarks]
    print(f"Selected {len(samples)} benchmarks from '{split}'")
    return samples


def validate_swe_samples(targets: list[str] | None = None, refresh: bool = True) -> None:
    """Setup each sample and run its validation tests."""
    cwd = Path.cwd()
    samples = get_swe_samples()

    if SWE_VALIDATION_RESULTS_PATH.exists():
        with open(SWE_VALIDATION_RESULTS_PATH, "r") as f:
            results = json.load(f)
        print(f"Loaded {len(results)} previous validation results.")
    else:
        SWE_VALIDATION_RESULTS_PATH.mkdir(parents=True, exist_ok=True)
        SWE_VALIDATION_RESULTS_PATH.touch()
        results = dict[str, Any]()
    for sample in samples:
        os.chdir(cwd)

        if targets and not any(b in sample.title for b in targets):
            continue
        if not refresh and sample.title in results:
            continue
        try:
            print(80 * "*" + f"\nValidating {sample.id}...")
            test_results = validate_test_fields(sample)
            percentages = dict[str, float]()
            for category, result in test_results.items():
                _passed, _total = result.get("passed", 0), result.get("total", 0)
                percentage = 0 if _total == 0 else _passed / _total * 100
                percentages[category] = percentage
            for category, percent in percentages.items():
                expected = 0 if "_PRE" in category else 100
                print(f"{category}: {percent:.2f}% (expected {expected}%)")
            results[sample.title] = test_results
        except Exception as e:
            print(f"Error: {e}")
            results[sample.title] = {"error": str(e)}
        finally:
            with open(SWE_VALIDATION_RESULTS_PATH, "w") as f:
                json.dump(results, f, indent=4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("targets", nargs="*")
    parser.add_argument("--refresh", "-r", action="store_true")
    parsed_args = parser.parse_args()

    validate_swe_samples(targets=[str(arg) for arg in parsed_args.targets], refresh=parsed_args.refresh)
