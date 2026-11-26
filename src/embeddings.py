
from __future__ import annotations

import os

from functools import lru_cache
from threading import Lock

import numpy as np
from sentence_transformers import SentenceTransformer


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384

BATCH_SIZE = max(
    1,
    int(os.getenv("EMBEDDING_BATCH_SIZE", "8"))
)

EMBEDDING_LOCK = Lock()


# Load the model once and reuse it.
@lru_cache(maxsize=1)
def get_model():

    return SentenceTransformer(
        MODEL_NAME,
        device="cpu",
    )


def prepare_entry_text(entry):

    if not isinstance(entry, dict):
        raise ValueError("Entry must be a dictionary.")

    prompt = str(
        entry.get("prompt") or ""
    ).strip()

    answer = str(
        entry.get("answer") or ""
    ).strip()

    if not answer:
        raise ValueError(
            "Cannot embed an entry without an answer."
        )

    return (
        f"Question: {prompt}\n"
        f"Answer: {answer}"
    )


def is_eligible_entry(entry):

    if not isinstance(entry, dict):
        return False

    category = str(
        entry.get("category") or ""
    ).lower()

    tags = entry.get("tags") or []

    if not isinstance(tags, list):
        return False

    normalized_tags = [
        str(tag).lower()
        for tag in tags
    ]

    return (
        category != "generated"
        and "generated" not in normalized_tags
        and bool(str(entry.get("answer") or "").strip())
    )


def embed_texts(texts):

    if not texts:
        return []

    if not all(
        isinstance(text, str) and text.strip()
        for text in texts
    ):
        raise ValueError(
            "All embedding inputs must be nonempty text."
        )

    with EMBEDDING_LOCK:

        model = get_model()

        vectors = model.encode(
            texts,
            batch_size=BATCH_SIZE,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

    vectors = np.asarray(
        vectors,
        dtype=np.float32,
    )

    if vectors.shape != (
        len(texts),
        EMBEDDING_DIMENSIONS,
    ):
        raise RuntimeError(
            "Unexpected embedding dimensions."
        )

    if not np.isfinite(vectors).all():
        raise RuntimeError(
            "Embedding contains invalid values."
        )

    return vectors.tolist()


def embed_text(text):

    return embed_texts([text])[0]


def embed_entry(entry):

    if not is_eligible_entry(entry):
        raise ValueError(
            "Entry is not eligible for embedding."
        )

    return embed_text(
        prepare_entry_text(entry)
    )
