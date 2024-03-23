import argparse
import json
import os
from pathlib import Path

import asyncio
from datasets import load_dataset, DatasetDict  # type: ignore

from benchmarks.run_sample import run_sample
from mentat.sampler.sample import Sample


SWE_BENCH_SAMPLES_DIR = Path(__file__).parent / "benchmarks" / "swe_bench_samples"


def download_swe_benchmarks(split: str = "dev") -> list[dict[str, str]]:
    """3 splits are available: dev (225), test (2.29k), and train (19k)."""
    dataset: DatasetDict = load_dataset("princeton-nlp/SWE-bench", split=split)  # type: ignore
    dataset: list[dict[str, str]] = [dict(benchmark) for benchmark in dataset]
    return dataset


def get_swe_samples(
    split: str = "dev", max_benchmarks: int | None = None
) -> list[Sample]:
    """Return a list of SWE-Bench samples. 
    
    If missing, download, convert to Samples and save locally.
    """
    split_dir = SWE_BENCH_SAMPLES_DIR / split
    saved_benchmarks = list(split_dir.glob("*.json"))
    if (
        not split_dir.exists() or
        max_benchmarks and len(saved_benchmarks) < max_benchmarks
    ):
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
    print(f"Selected {len(samples)} benchmarks from '{args.split}'")
    return samples


async def run_samples(samples: list[Sample], workers: int = 1) -> list[dict[str, str]]:
    """Run a list of samples and return the results."""
    results = list[dict[str, str]]()
    semaphore = asyncio.Semaphore(workers)
    run_from_dir = Path.cwd()
    for sample in samples:
        async with semaphore:
            try:
                print(80 * "-")
                print(f"SAMPLE ID: {sample.id}")
                print(sample.message_prompt)
                result = await run_sample(sample)
                print("RESULTS:")
                print(results)
                results.append(result)
            except Exception as e:
                print("ERROR:", e)
            finally:
                os.chdir(run_from_dir)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run SWE-Bench benchmarks.")
    parser.add_argument("--split", "-s", default="dev", type=str, help="The dataset split to use (dev, train, test).")
    parser.add_argument("--max-benchmarks", "-n", type=int, help="Number of samples to process.")
    args = parser.parse_args()

    samples = get_swe_samples(args.split, args.max_benchmarks)

    results = asyncio.run(run_samples(samples))
    with open(f"{args.split}_results.json", "w") as f:
        json.dump(results, f, indent=4)
