import asyncio
import json
import os
import sqlite3
from pathlib import Path

import numpy as np

from mentat.code_feature import CodeFeature, count_feature_tokens
from mentat.errors import MentatError
from mentat.llm_api_handler import (
    count_tokens,
    model_context_size,
    model_price_per_1000_tokens,
)
from mentat.session_context import SESSION_CONTEXT
from mentat.session_input import ask_yes_no
from mentat.utils import mentat_dir_path, sha256

MAX_SIMULTANEOUS_REQUESTS = 10


class EmbeddingsDatabase:
    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir or mentat_dir_path
        os.makedirs(self.output_dir, exist_ok=True)
        self.path = Path(self.output_dir) / "embeddings.sqlite3"
        self._connect()

    def _connect(self):
        self.conn = sqlite3.connect(self.path)
        with self.conn as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS embeddings "
                "(checksum TEXT PRIMARY KEY, vector BLOB)"
            )

    def set(self, items: dict[str, list[float]]):
        with self.conn as db:
            db.executemany(
                "INSERT OR REPLACE INTO embeddings (checksum, vector) VALUES (?, ?)",
                [
                    (key, sqlite3.Binary(json.dumps(value).encode("utf-8")))
                    for key, value in items.items()
                ],
            )

    def get(self, keys: list[str]) -> dict[str, list[float]]:
        with self.conn as db:
            cursor = db.execute(
                "SELECT checksum, vector FROM embeddings WHERE checksum IN"
                f" ({','.join(['?']*len(keys))})",
                keys,
            )
            return {row[0]: json.loads(row[1]) for row in cursor.fetchall()}

    def exists(self, key: str) -> bool:
        with self.conn as db:
            cursor = db.execute("SELECT 1 FROM embeddings WHERE checksum=?", (key,))
            return cursor.fetchone() is not None

    def __del__(self):
        self.conn.close()


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


embedding_api_semaphore = asyncio.Semaphore(MAX_SIMULTANEOUS_REQUESTS)


async def _fetch_embeddings(model: str, batch: list[str]):
    ctx = SESSION_CONTEXT.get()

    async with embedding_api_semaphore:
        response = await ctx.llm_api_handler.call_embedding_api(batch, model)
        return response


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Calculate the cosine similarity between two vectors."""
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    return dot_product / (norm_v1 * norm_v2)  # pyright: ignore


async def get_feature_similarity_scores(
    prompt: str,
    features: list[CodeFeature],
    loading_multiplier: float = 0.0,
) -> list[float]:
    """Return the similarity scores for a given prompt and list of features."""
    global database
    session_context = SESSION_CONTEXT.get()
    stream = session_context.stream
    embedding_model = session_context.config.embedding_model
    max_model_tokens = model_context_size(embedding_model)
    if max_model_tokens is None:
        raise MentatError(f"Missing model context size for {embedding_model}.")

    # Keep things in the same order
    checksums: list[str] = [f.get_checksum() for f in features]
    tokens: list[int] = await count_feature_tokens(features, embedding_model)

    # Make a checksum:content dict of all items that need to be embedded
    items_to_embed = dict[str, str]()
    items_to_embed_tokens = dict[str, int]()
    prompt_checksum = sha256(prompt)
    num_prompt_tokens = 0
    if not database.exists(prompt_checksum):
        items_to_embed[prompt_checksum] = prompt
        items_to_embed_tokens[prompt_checksum] = count_tokens(prompt, embedding_model)
    for feature, checksum, token in zip(features, checksums, tokens):
        if token > max_model_tokens:
            continue
        if not database.exists(checksum):
            feature_content = feature.get_code_message()
            # Remove line numbering
            items_to_embed[checksum] = "\n".join(feature_content)
            items_to_embed_tokens[checksum] = token
            num_prompt_tokens += token

    # If it costs more than $1, get confirmation from user.
    cost = model_price_per_1000_tokens(embedding_model)
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

    tasks = list[tuple[asyncio.Task[list[list[float]]], list[str]]]()
    for batch in batches:
        batch_content = [items_to_embed[k] for k in batch]
        task = asyncio.create_task(_fetch_embeddings(embedding_model, batch_content))
        tasks.append((task, batch))
    for i, (task, batch) in enumerate(tasks):
        if loading_multiplier:
            stream.send(
                f"Fetching embeddings, batch {i+1}/{len(tasks)}",
                channel="loading",
                progress=(100 / len(tasks)) * loading_multiplier,
            )
        response = await task
        database.set({k: v for k, v in zip(batch, response)})

    # Calculate similarity score for each feature
    prompt_embedding = database.get([prompt_checksum])[prompt_checksum]
    embeddings = database.get(checksums)
    scores = [_cosine_similarity(prompt_embedding, embeddings[k]) for k in checksums]

    return scores
