import argparse
import asyncio
import json

from mentat.sampler.sample import Sample
from mentat.utils import mentat_dir_path

SAMPLES_DIR = mentat_dir_path / "samples"


def find_sample_files(sample_ids=None):
    if sample_ids:
        # Check the samples_dir for filenames containing each sample_id, and include matching filesnames.
        sample_files = []
        for sample_id in sample_ids:
            sample_files.extend(list(SAMPLES_DIR.glob(f"*{sample_id}*.json")))
        return sample_files
    else:
        return SAMPLES_DIR.glob("*.json")


async def evaluate_sample(sample_file):
    sample = Sample.load(sample_file)
    results = await sample.eval()
    return results


async def main():
    parser = argparse.ArgumentParser(description="Evaluate code samples.")
    parser.add_argument("sample_ids", nargs="*", help="Optional sample IDs to evaluate")
    args = parser.parse_args()
    sample_files = find_sample_files(args.sample_ids)
    if not sample_files:
        print(f"No {'matching' if args.sample_ids else ''} sample files found.")
        return
    for sample_file in sample_files:
        if sample_file.exists():
            results = await evaluate_sample(sample_file)
            print(f"Results for {sample_file.stem}: {json.dumps(results, indent=4)}")
        else:
            print(f"Sample file {sample_file} does not exist.")


if __name__ == "__main__":
    asyncio.run(main())
