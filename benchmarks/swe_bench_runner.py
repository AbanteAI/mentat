from datasets import load_dataset  # type: ignore


def setup():
    # Fetch the benchmark data from huggingface
    dataset = load_dataset("princeton-nlp/SWE-bench")
    print("Loaded SWE-Bench datasets:")
    for split in {"dev", "train", "test"}:
        print(f" - {split}: {len(dataset[split])} samples")  # type: ignore
    
    # Validate as Samples

if __name__ == "__main__":
    setup()
