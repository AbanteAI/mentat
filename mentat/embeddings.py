import gzip
import json
import os
from pathlib import Path

import numpy as np

from .code_file import CodeFile, count_feature_tokens
from .config_manager import mentat_dir_path
from .llm_api import call_embedding_api, count_tokens
from .session_stream import SESSION_STREAM
from .utils import sha256

EMBEDDING_MODEL = "text-embedding-ada-002"
EMBEDDING_MAX_TOKENS = 8192


class EmbeddingsDatabase:
    # { sha256 : [ 1536 floats ] }
    _dict: dict[str, list[float]] = dict[str, list[float]]()

    def __init__(self, output_dir: Path | None = None):
        if output_dir is None:
            output_dir = mentat_dir_path
        os.makedirs(output_dir, exist_ok=True)
        self.path = Path(output_dir) / "embeddings.json.gz"
        if self.path.exists():
            with gzip.open(self.path, "rt") as f:
                self._dict = json.load(f)

    def save(self):
        with gzip.open(self.path, "wt") as f:
            json.dump(self._dict, f)

    def __getitem__(self, key: str) -> list[float]:
        return self._dict[key]

    def __setitem__(self, key: str, value: list[float]):
        self._dict[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._dict


database = EmbeddingsDatabase()


def _batch_ffd(data: dict[str, int], batch_size: int) -> list[list[str]]:
    """Batch files using the First Fit Decreasing algorithm."""
    # Sort the data by the length of the strings in descending order
    sorted_data = sorted(data.items(), key=lambda x: x[1], reverse=True)
    batches = list[list[str]]()
    for key, value in sorted_data:
        # Place each item in the first batch that it fits in
        placed = False
        for batch in batches:
            if sum(data[k] for k in batch) + value <= batch_size:
                batch.append(key)
                placed = True
                break
        if not placed:
            batches.append([key])
    return batches


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Calculate the cosine similarity between two vectors."""
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    return dot_product / (norm_v1 * norm_v2)


async def get_feature_similarity_scores(
    prompt: str, features: list[CodeFile]
) -> list[float]:
    """Return the similarity scores for a given prompt and list of features."""
    global database
    stream = SESSION_STREAM.get()

    # Keep things in the same order
    checksums: list[str] = [f.get_checksum() for f in features]
    tokens: list[int] = await count_feature_tokens(features, EMBEDDING_MODEL)

    # Make a checksum:content dict of all items that need to be embedded
    items_to_embed = dict[str, str]()
    items_to_embed_tokens = dict[str, int]()
    prompt_checksum = sha256(prompt)
    if prompt_checksum not in database:
        items_to_embed[prompt_checksum] = prompt
        items_to_embed_tokens[prompt_checksum] = count_tokens(prompt, EMBEDDING_MODEL)
    for feature, checksum, token in zip(features, checksums, tokens):
        if token > EMBEDDING_MAX_TOKENS:
            continue
        if checksum not in database:
            feature_content = await feature.get_code_message()
            # Remove line numbering
            items_to_embed[checksum] = "\n".join(feature_content)
            items_to_embed_tokens[checksum] = token

    # Fetch embeddings in batches
    batches = _batch_ffd(items_to_embed_tokens, EMBEDDING_MAX_TOKENS)
    for i, batch in enumerate(batches):
        batch_content = [items_to_embed[k] for k in batch]
        await stream.send(f"Embedding batch {i}/{len(batches)}...")
        response = call_embedding_api(batch_content, EMBEDDING_MODEL)
        for k, v in zip(batch, response):
            database[k] = v
    if len(batches) > 0:
        database.save()

    # Calculate similarity score for each feature
    prompt_embedding = database[prompt_checksum]
    scores = [0.0 for _ in checksums]
    for i, checksum in enumerate(checksums):
        if checksum not in database:
            continue
        feature_embedding = database[checksum]
        scores[i] = _cosine_similarity(prompt_embedding, feature_embedding)

    return scores
