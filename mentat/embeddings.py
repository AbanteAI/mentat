import gzip
import json
import logging
import os
from pathlib import Path
from timeit import default_timer

import numpy as np

from mentat.code_feature import CodeFeature, count_feature_tokens
from mentat.errors import MentatError
from mentat.llm_api import (
    call_embedding_api,
    count_tokens,
    model_context_size,
    model_price_per_1000_tokens,
)
from mentat.session_context import SESSION_CONTEXT
from mentat.session_input import ask_yes_no
from mentat.utils import mentat_dir_path, sha256

EMBEDDING_MODEL = "text-embedding-ada-002"
EMBEDDING_DIM = 1536


class EmbeddingsDatabase:
    # { sha256 : [ EMBEDDING_DIM floats ] }
    _dict: dict[str, list[float]] = dict[str, list[float]]()

    def __init__(self, output_dir: Path | None = None):
        if output_dir is None:
            output_dir = mentat_dir_path
        os.makedirs(output_dir, exist_ok=True)
        self.path = Path(output_dir) / "embeddings.json.gz"
        if self.path.exists():
            try:
                with gzip.open(self.path, "rt") as f:
                    self._dict = json.load(f)
            except gzip.BadGzipFile:
                logging.warning(f"Could not load embeddings from {self.path}.")

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
    prompt: str, features: list[CodeFeature]
) -> list[float]:
    """Return the similarity scores for a given prompt and list of features."""
    global database
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream
    cost_tracker = session_context.cost_tracker
    max_model_tokens = model_context_size(EMBEDDING_MODEL)
    if max_model_tokens is None:
        raise MentatError(f"Missing model context size for {EMBEDDING_MODEL}.")

    # Keep things in the same order
    t1 = default_timer()
    checksums: list[str] = [f.get_checksum() for f in features]
    t2 = default_timer()
    print('Got checksums in', t2 - t1)
    tokens: list[int] = await count_feature_tokens(features, EMBEDDING_MODEL)
    t3 = default_timer()
    print('Got tokens in', t3 - t2)

    # Make a checksum:content dict of all items that need to be embedded
    items_to_embed = dict[str, str]()
    items_to_embed_tokens = dict[str, int]()
    prompt_checksum = sha256(prompt)
    num_prompt_tokens = 0
    if prompt_checksum not in database:
        items_to_embed[prompt_checksum] = prompt
        items_to_embed_tokens[prompt_checksum] = count_tokens(prompt, EMBEDDING_MODEL)
    for feature, checksum, token in zip(features, checksums, tokens):
        if token > max_model_tokens:
            continue
        if checksum not in database:
            feature_content = feature.get_code_message()
            # Remove line numbering
            items_to_embed[checksum] = "\n".join(feature_content)
            items_to_embed_tokens[checksum] = token
            num_prompt_tokens += token
    t4 = default_timer()
    print('Got items to embed in', t4 - t3)

    # If it costs more than $1, get confirmation from user.
    cost = model_price_per_1000_tokens(EMBEDDING_MODEL)
    if cost is None:
        stream.send(
            "Warning: Could not determine cost of embeddings. Continuing anyway.",
            color="light_yellow",
        )
    else:
        expected_cost = (num_prompt_tokens / 1000) * cost[0]
        if expected_cost > 1.0:
            stream.send(
                f"Embedding {num_prompt_tokens} tokens will cost ${cost[0]:.2f}."
                " Continue anyway?"
            )
            if not await ask_yes_no(default_yes=True):
                stream.send("Ignoring embeddings for now.")
                return [0.0 for _ in checksums]

    # Fetch embeddings in batches
    batches = _batch_ffd(items_to_embed_tokens, max_model_tokens)
    t5 = default_timer()
    print('Got batches in', t5 - t4)

    _start_time = default_timer()
    _embed_time = 0.
    _add_to_db_time = 0.
    for i, batch in enumerate(batches):
        batch_content = [items_to_embed[k] for k in batch]
        stream.send(f"Embedding batch {i + 1}/{len(batches)}...")
        t1a = default_timer()
        response = await call_embedding_api(batch_content, EMBEDDING_MODEL)
        t1b = default_timer()
        print('Got response in', t1b - t1a)
        _embed_time += t1b - t1a
        for k, v in zip(batch, response):
            database[k] = v
        t1c = default_timer()
        _add_to_db_time += t1c - t1b
    if len(batches) > 0:
        t2a = default_timer()
        database.save()
        print('Saved to database in', default_timer() - t2a)
        cost_tracker.display_api_call_stats(
            num_prompt_tokens,
            0,
            EMBEDDING_MODEL,
            default_timer() - _start_time,
            decimal_places=4,
        )
    print(f'Total time to embed {len(batches)} batches:', _embed_time)
    print('Total time to add to db:', _add_to_db_time)

    # Calculate similarity score for each feature
    prompt_embedding = database[prompt_checksum]
    scores = [0.0 for _ in checksums]
    _check_in_db = 0.
    _get_from_db = 0.
    _cosine_times = 0.
    for i, checksum in enumerate(checksums):
        t1 = default_timer()
        if checksum not in database:
            _check_in_db += default_timer() - t1
            continue
        t2 = default_timer()
        _check_in_db += t2 - t1
        feature_embedding = database[checksum]
        t3 = default_timer()
        _get_from_db += t3 - t2
        scores[i] = _cosine_similarity(prompt_embedding, feature_embedding)
        t4 = default_timer()
        _cosine_times += t4 - t3
    print(f'Total time to check for {len(checksums)} checksums in db:', _check_in_db)
    print('Total time to get from db:', _get_from_db)
    print('Total time to cosine:', _cosine_times)

    return scores
