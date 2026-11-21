
from __future__ import annotations

import re
from typing import List, Dict


# MiniLM supports a relatively short context window.
# We use conservative character lengths and verify
# actual token lengths before producing embeddings.

MAX_TOKENS = 220
OVERLAP_TOKENS = 40


def normalize_text(text: str) -> str:
    """
    Normalize whitespace without discarding content.
    """

    if not isinstance(text, str):
        raise ValueError("Text must be a string.")

    return re.sub(r"\s+", " ", text).strip()


def chunk_text(
    text: str,
    max_tokens: int = MAX_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> List[Dict]:
    """
    Split a document into overlapping passages.

    Every token is covered by at least one chunk.
    The original text should be stored separately.
    """

    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive.")

    if overlap_tokens < 0 or overlap_tokens >= max_tokens:
        raise ValueError(
            "overlap_tokens must be smaller than max_tokens."
        )

    text = normalize_text(text)

    if not text:
        return []

    # Use the embedding model's own tokenizer so
    # chunks fit within its supported input length.
    from embeddings import get_model

    tokenizer = get_model().tokenizer

    token_ids = tokenizer.encode(
        text,
        add_special_tokens=False,
        truncation=False,
    )

    # Reserve room for special tokens.
    model_limit = get_model().max_seq_length - 2

    if max_tokens > model_limit:
        raise ValueError(
            f"max_tokens exceeds model limit of {model_limit}."
        )

    chunks = []
    step = max_tokens - overlap_tokens

    for start in range(0, len(token_ids), step):

        end = min(start + max_tokens, len(token_ids))

        piece_ids = token_ids[start:end]

        passage = tokenizer.decode(
            piece_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        ).strip()

        if passage:

            chunks.append({
                "chunk_index": len(chunks),
                "text": passage,
                "token_start": start,
                "token_end": end,
            })

        if end == len(token_ids):
            break

    return chunks
