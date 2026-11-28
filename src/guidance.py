
from __future__ import annotations

import os
import re

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from database import database_connection
from llm import generate_guidance_llm
from retrieval import search_knowledge


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by",
    "for", "from", "has", "have", "he", "her", "his", "i", "if",
    "in", "is", "it", "me", "my", "of", "on", "or", "our", "she",
    "so", "that", "their", "them", "then", "they", "this",
    "to", "was", "we", "were", "what", "when", "where", "which",
    "who", "why", "will", "with", "you", "your",
}

USE_LLM = os.getenv(
    "LEGACY_USE_LLM", "1"
).strip().lower() not in ("0", "false", "no")


def tokenize(text: str) -> List[str]:
    words = re.findall(
        r"[a-z0-9']+",
        str(text).lower(),
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

    haystack_tokens = set(tokenize(haystack))

    return sum(
        1 for token in set(query_tokens)
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


def retrieve_approved_memories(
    profile_id: str,
    owner_id: str,
    question: str,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant, owner-approved memories.

    Pending and rejected memories are excluded.
    The database also verifies profile ownership.

    This is lexical relevance ranking for now.
    Document search retains its existing hybrid
    semantic and keyword retrieval.
    """

    if not profile_id or not owner_id:
        return []

    query_tokens = set(tokenize(question))

    if not query_tokens:
        return []

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    m.id,
                    m.category,
                    m.memory_text,
                    m.source_excerpt,
                    m.interpretation_type,
                    m.event_date,
                    m.source_document_id,
                    m.source_chunk_id,
                    d.title AS document_title,
                    c.chunk_index AS chunk_index
                FROM structured_memories m
                JOIN profiles p
                    ON p.id = m.profile_id
                LEFT JOIN knowledge_documents d
                    ON d.id = m.source_document_id
                   AND d.profile_id = m.profile_id
                LEFT JOIN knowledge_chunks c
                    ON c.id = m.source_chunk_id
                   AND c.document_id = d.id
                WHERE m.profile_id = %s
                  AND p.owner_id = %s
                  AND m.status = 'approved'

                  -- Enforce written journal privacy.
                  AND (
                      COALESCE(
                          d.metadata ->> 'origin',
                          ''
                      ) <> 'written_journal'

                      OR EXISTS (
                          SELECT 1
                          FROM journal_entries e
                          JOIN journals j
                              ON j.id = e.journal_id

                          WHERE e.document_id = d.id
                            AND j.profile_id = m.profile_id

                            AND e.id = (
                                d.metadata
                                ->> 'journal_entry_id'
                            )

                            AND j.id = (
                                d.metadata
                                ->> 'journal_id'
                            )

                            AND e.status = 'published'
                            AND e.allow_ai_processing = TRUE

                            AND (
                                e.ai_preference = 'include'
                                OR (
                                    e.ai_preference = 'inherit'
                                    AND j.ai_default_enabled = TRUE
                                )
                            )

                            AND p.profile_data @>
                                '{"consent":{
                                    "has_consent":true,
                                    "allow_remote_processing":true
                                }}'::jsonb
                      )
                  )
                ORDER BY m.updated_utc DESC, m.id
                LIMIT 1000
                """,
                (
                    profile_id,
                    owner_id,
                ),
            )

            rows = cursor.fetchall()

    scored = []

    for memory in rows:
        memory_tokens = set(
            tokenize(memory["memory_text"])
        )

        category_tokens = set(
            tokenize(
                memory["category"].replace("_", " ")
            )
        )

        score = (
            2 * len(query_tokens & memory_tokens)
            + len(query_tokens & category_tokens)
        )

        if score > 0:
            scored.append((score, memory))

    scored.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    evidence = []

    for score, memory in scored[:limit]:
        document_title = (
            memory["document_title"]
            or "Original source"
        )

        passage_number = memory["chunk_index"]

        if passage_number is not None:
            source_label = (
                f"{document_title}, "
                f"passage {passage_number + 1}"
            )
        else:
            source_label = document_title

        interpretation = memory[
            "interpretation_type"
        ]

        if interpretation == "inferred":
            evidence_type = (
                "OWNER-APPROVED INTERPRETATION. "
                "Present as an interpretation, "
                "not an established fact."
            )
        else:
            evidence_type = (
                "OWNER-APPROVED EXPLICIT MEMORY. "
                "Treat as a statement supported "
                "by the person's recorded history, "
                "not independent verification."
            )

        answer = (
            f"{evidence_type}\n"
            f"Memory: {memory['memory_text']}\n"
            f"Supporting quotation: "
            f"{memory['source_excerpt'] or 'Not available'}\n"
            f"Source: {source_label}"
        )

        if memory["event_date"]:
            answer += (
                f"\nRecorded event date: "
                f"{memory['event_date']}"
            )

        evidence.append({
            "category": "approved_memory",
            "prompt": (
                f"Approved {memory['category']} "
                f"memory ({interpretation})"
            ),
            "answer": answer,
            "tags": [
                "approved",
                "structured_memory",
                interpretation,
            ],
            "memory_id": memory["id"],
            "source_document_id": (
                memory["source_document_id"]
            ),
            "source_chunk_id": (
                memory["source_chunk_id"]
            ),
            "relevance_score": score,
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

    # Source 1: Existing interview and profile entries.
    selected = top_k_relevant_entries(
        profile,
        question,
        k=k,
    )

    # Source 2: Existing hybrid document retrieval.
    document_evidence = []

    # Source 3: Relevant approved structured memories.
    approved_memories = []

    if profile_id and owner_id:
        document_evidence = retrieve_document_evidence(
            profile_id=profile_id,
            owner_id=owner_id,
            question=question,
            limit=5,
        )

        approved_memories = retrieve_approved_memories(
            profile_id=profile_id,
            owner_id=owner_id,
            question=question,
            limit=5,
        )

    # Approved memories are placed first so the
    # model sees the owner's curated knowledge.
    # Original document passages remain available
    # for detailed evidence and context.
    evidence = (
        approved_memories
        + document_evidence
        + selected
    )

    principles = profile.get(
        "guidance_principles", []
    )

    if not isinstance(principles, list):
        principles = []

    if USE_LLM:

        from cognitive_model_context import (
            build_cognitive_model_context,
            format_cognitive_model_context,
        )

        cognitive_context = build_cognitive_model_context(
            profile=profile,
            profile_id=profile_id,
            owner_id=owner_id,
        )

        cognitive_text = format_cognitive_model_context(
            cognitive_context
        )

        response_text = generate_guidance_llm(
            subject_name=subject,
            question=question,
            baseline_principles=principles,
            evidence=evidence,
            profile=profile,
            cognitive_context=cognitive_text,
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
        "approved_memory_count": len(
            approved_memories
        ),
        "document_evidence_count": len(
            document_evidence
        ),
        "evidence": evidence,
    }
