from pathlib import Path

from datasets import load_dataset, DatasetDict  # type: ignore

from mentat.sampler.sample import Sample


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
