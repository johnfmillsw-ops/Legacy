"""
Read-only integration of questionnaire baselines
and authorized personality evidence.
"""

import hashlib
import unicodedata

from database import database_connection

from personality_framework import FRAMEWORK_VERSION

from personality_baseline import (
    INSTRUMENT_ID,
    INSTRUMENT_VERSION,
)

from personality_storage import load_authorized_sources
from personality_analysis import source_hash

from personality_unified_scoring import (
    CORE_TRAITS,
    build_unified_scores,
)


def normalize_text(value):
    value = unicodedata.normalize(
        "NFKC", str(value or "")
    ).casefold()

    return " ".join(
        "".join(
            char if char.isalnum() else " "
            for char in value
        ).split()
    )


def passage_shingles(value):
    words = normalize_text(value).split()

    if len(words) < 15:
        return set()

    return {
        tuple(words[i:i + 3])
        for i in range(len(words) - 2)
    }


def near_duplicate_passages(first, second):
    if not first or not second:
        return False

    shared = len(first & second)
    total = len(first | second)

    return (
        shared >= 10
        and shared / total >= 0.80
    )


def independence_keys(rows):
    """
    Group records sharing a source chunk or identical
    normalized evidence text.

    This is not semantic event identification.
    """

    parents = list(range(len(rows)))
    seen = {}

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first, second):
        first = find(first)
        second = find(second)

        if first != second:
            parents[max(first, second)] = min(first, second)

    for index, row in enumerate(rows):

        tokens = []

        chunk_id = row.get("source_chunk_id")

        if chunk_id:
            tokens.append(("chunk", str(chunk_id)))

        for field in (
            "original_passage",
            "source_excerpt",
        ):
            normalized = normalize_text(row.get(field))

            if len(normalized) >= 40:
                digest = hashlib.sha256(
                    normalized.encode("utf-8")
                ).hexdigest()

                tokens.append(("text", digest))

        for token in tokens:

            if token in seen:
                union(index, seen[token])
            else:
                seen[token] = index

    # Compare evidence excerpts conservatively.
    # Similar topics alone are not duplicate evidence.
    passages = [
        passage_shingles(row.get("source_excerpt"))
        for row in rows
    ]

    for first in range(len(rows)):
        if not passages[first]:
            continue

        for second in range(first + 1, len(rows)):
            if find(first) == find(second):
                continue

            if near_duplicate_passages(
                passages[first],
                passages[second],
            ):
                union(first, second)

    return [
        "evidence-group-" + str(find(index))
        for index in range(len(rows))
    ]


def load_unified_personality(
    cur,
    profile_id,
    owner_id,
):

    cur.execute("""
        SELECT profile_data
        FROM profiles
        WHERE id = %s
          AND owner_id = %s
        FOR UPDATE
    """, (profile_id, owner_id))

    profile = cur.fetchone()

    if not profile:
        raise PermissionError("Profile access denied.")

    profile_data = profile["profile_data"] or {}
    consent = profile_data.get("consent") or {}

    if consent.get("has_consent") is not True:
        raise PermissionError(
            "Local processing consent required."
        )

    cur.execute("""
        SELECT id,
               normalized_scores,
               completed_utc
        FROM personality_baseline_assessments
        WHERE profile_id = %s
          AND instrument_id = %s
          AND instrument_version = %s
          AND status = 'completed'
        ORDER BY completed_utc DESC, id DESC
        LIMIT 1
    """, (
        profile_id,
        INSTRUMENT_ID,
        INSTRUMENT_VERSION,
    ))

    baseline = cur.fetchone()

    baseline_scores = (
        baseline["normalized_scores"]
        if baseline else {}
    )

    evidence = {
        trait: []
        for trait in CORE_TRAITS
    }

    valid_rows = []

    if consent.get("allow_remote_processing") is True:

        sources = load_authorized_sources(
            cur,
            profile_id,
            owner_id,
        )

        cur.execute("""
            SELECT
                e.id,
                e.trait_key,
                e.expression_score,
                e.evidence_confidence,
                e.source_excerpt,
                a.memory_id,
                a.source_hash,
                m.source_chunk_id
            FROM personality_trait_evidence e
            JOIN personality_memory_assessments a
                ON a.id = e.assessment_id
               AND a.profile_id = e.profile_id
            JOIN structured_memories m
                ON m.id = a.memory_id
               AND m.profile_id = a.profile_id
            WHERE e.profile_id = %s
              AND a.framework_version = %s
              AND e.trait_key = ANY(%s)
              AND m.status = 'approved'
              AND e.expression_score IS NOT NULL
              AND e.evidence_confidence IS NOT NULL
            ORDER BY e.id
        """, (
            profile_id,
            FRAMEWORK_VERSION,
            list(CORE_TRAITS),
        ))

        rows = cur.fetchall()

        hashes = {
            memory_id: source_hash(source)
            for memory_id, source in sources.items()
        }

        for row in rows:

            memory_id = row["memory_id"]

            if memory_id not in sources:
                continue

            if row["source_hash"] != hashes[memory_id]:
                continue

            item = dict(row)

            item["original_passage"] = sources[
                memory_id
            ].get("original_passage", "")

            valid_rows.append(item)

        keys = independence_keys(valid_rows)

        for row, key in zip(valid_rows, keys):

            evidence[row["trait_key"]].append({
                "independence_key": key,
                "score": row["expression_score"],
                "confidence": row["evidence_confidence"],
                "relevance": 100,
            })

    scores = build_unified_scores(
        baseline_scores=baseline_scores,
        evidence_by_trait=evidence,
    )

    return {
        "baseline_completed": baseline is not None,
        "baseline_assessment_id": (
            baseline["id"] if baseline else None
        ),
        "baseline_completed_utc": (
            baseline["completed_utc"].isoformat()
            if baseline else None
        ),
        "valid_evidence_count": len(valid_rows),
        "scores": scores,
        "experimental": True,
    }


def get_unified_personality(profile_id, owner_id):

    with database_connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "SET TRANSACTION ISOLATION LEVEL "
                "REPEATABLE READ READ WRITE"
            )

            return load_unified_personality(
                cur,
                profile_id,
                owner_id,
            )


if __name__ == "__main__":

    passage = (
        "This is a sufficiently long original "
        "source passage describing a personal experience."
    )

    rows = [
        {
            "source_chunk_id": "chunk-a",
            "original_passage": passage,
        },
        {
            "source_chunk_id": "chunk-a",
            "original_passage": "Different text",
        },
        {
            "source_chunk_id": "chunk-b",
            "original_passage": passage.upper(),
        },
        {
            "source_chunk_id": "chunk-c",
            "original_passage": "Unrelated passage",
        },
    ]

    keys = independence_keys(rows)

    assert keys[0] == keys[1] == keys[2]
    assert keys[0] != keys[3]

    print("Source passage grouping: PASSED")
    print("Normalized text grouping: PASSED")
    print("Independent passage separation: PASSED")
