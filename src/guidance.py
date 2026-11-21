
from __future__ import annotations

import os
import re

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from llm import generate_guidance_llm
from retrieval import search_knowledge


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by",
    "for", "from", "has", "have", "he", "her", "his", "i", "if",
    "in", "is", "it", "me", "my", "of", "on", "or", "our", "she",
    "so", "that", "their", "them", "then", "they", "this",
    "to", "was", "we", "were", "what", "when", "where", "which",
    "who", "why", "will", "with", "you", "your"
}

USE_LLM = os.getenv(
    "LEGACY_USE_LLM", "1"
).strip().lower() not in ("0", "false", "no")


def tokenize(text: str) -> List[str]:

    words = re.findall(
        r"[a-z0-9']+",
        str(text).lower()
    )

    return [
        word for word in words
        if word not in STOPWORDS and len(word) > 1
    ]


def is_generated_entry(entry: Dict[str, Any]) -> bool:

    category = str(
        entry.get("category") or ""
    ).lower()

    tags = entry.get("tags") or []

    return (
        category in ("generated", "guidance_generated")
        or (
            isinstance(tags, list)
            and "generated" in [
                str(tag).lower() for tag in tags
            ]
        )
    )


def score_entry(
    query_tokens: List[str],
    entry: Dict[str, Any],
) -> int:

    tags = entry.get("tags") or []

    tag_text = (
        " ".join(str(tag) for tag in tags)
        if isinstance(tags, list)
        else ""
    )

    haystack = (
        f"{entry.get('prompt', '')} "
        f"{entry.get('answer', '')} "
        f"{tag_text}"
    )

    haystack_tokens = set(
        tokenize(haystack)
    )

    return sum(
        1 for token in query_tokens
        if token in haystack_tokens
    )


def top_k_relevant_entries(
    profile: Dict[str, Any],
    question: str,
    k: int = 3,
) -> List[Dict[str, Any]]:

    query_tokens = tokenize(question)

    scored: List[Tuple[int, Dict[str, Any]]] = []

    for entry in profile.get("entries", []):

        if is_generated_entry(entry):
            continue

        score = score_entry(
            query_tokens,
            entry,
        )

        if score > 0:
            scored.append((score, entry))

    scored.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return [
        entry for _, entry in scored[:k]
    ]


def retrieve_document_evidence(
    profile_id: str,
    owner_id: str,
    question: str,
    limit: int = 5,
) -> List[Dict[str, Any]]:

    results = search_knowledge(
        profile_id=profile_id,
        owner_id=owner_id,
        question=question,
        limit=limit,
    )

    evidence = []

    for result in results:

        evidence.append({
            "category": "document_evidence",
            "prompt": (
                f"Source: {result['title']} "
                f"(passage {result['chunk_index'] + 1})"
            ),
            "answer": result["text"],
            "tags": ["retrieved", "document"],
            "source_document_id": result["document_id"],
            "source_chunk_id": result["chunk_id"],
            "similarity": result["similarity"],
        })

    return evidence


def generate_guidance_response(
    profile: Dict[str, Any],
    question: str,
    k: int = 3,
    profile_id: str = None,
    owner_id: str = None,
) -> Dict[str, Any]:

    subject = profile.get(
        "subject", {}
    ).get("display_name", "Unknown")

    # Existing interview and profile knowledge.
    selected = top_k_relevant_entries(
        profile,
        question,
        k=k,
    )

    # New semantic retrieval from documents.
    document_evidence = []

    if profile_id and owner_id:

        document_evidence = retrieve_document_evidence(
            profile_id=profile_id,
            owner_id=owner_id,
            question=question,
            limit=5,
        )

    evidence = selected + document_evidence

    principles = profile.get(
        "guidance_principles", []
    )

    if not isinstance(principles, list):
        principles = []

    if USE_LLM:

        response_text = generate_guidance_llm(
            subject_name=subject,
            question=question,
            baseline_principles=principles,
            evidence=evidence,
            profile=profile,
        )

        if not response_text:
            response_text = (
                "I couldn't generate a response right now."
            )

    else:

        if evidence:

            response_text = (
                "Relevant captured insights:\n\n"
                + "\n\n".join(
                    str(item.get("answer", ""))
                    for item in evidence
                )
            )

        else:

            response_text = (
                "Not enough relevant information yet."
            )

    return {
        "timestamp_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "category": "guidance_generated",
        "prompt": question,
        "answer": response_text,
        "tags": ["generated", "guidance"],
        "evidence_count": len(evidence),
        "evidence": evidence,
    }
