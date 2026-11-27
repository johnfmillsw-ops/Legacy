"""
Legacy psychological identity aggregation.

Identity weights represent estimated personal significance,
not psychological test scores or measured ability.
"""

from collections import defaultdict
from statistics import median

from database import database_connection

from psychological_framework import (
    DIMENSIONS,
    WEIGHT_FACTORS,
    calculate_identity_weight,
)

from psychological_processing import (
    authorized_memories,
    select_profile,
)


def aggregate_characteristic(evidence):

    supporting = [
        item for item in evidence
        if item["direction"] == "supporting"
        and item["temporal_type"] != "temporary_state"
    ]

    contradictory = [
        item for item in evidence
        if item["direction"] == "contradictory"
    ]

    temporary = [
        item for item in evidence
        if item["temporal_type"] == "temporary_state"
    ]

    # Multiple memories from one passage must not
    # artificially amplify its contribution.
    grouped = defaultdict(list)

    for item in supporting:
        grouped[item["source_chunk_id"]].append(item)

    factors = {}

    for factor in WEIGHT_FACTORS:

        passage_values = []

        for records in grouped.values():

            values = [
                record["weight_factors"].get(factor)
                for record in records
                if record["weight_factors"].get(factor)
                is not None
            ]

            if values:
                passage_values.append(median(values))

        factors[factor] = (
            round(median(passage_values), 2)
            if passage_values
            else None
        )

    weight = calculate_identity_weight(factors)

    source_documents = {
        item["source_document_id"]
        for item in supporting
    }

    direct_passages = {
        item["source_chunk_id"]
        for item in supporting
        if item["evidence_type"] in (
            "direct_statement",
            "reported_behavior",
            "reported_experience",
            "documented_assessment",
        )
    }

    # Qualitative evidence strength, not a probability.
    if not supporting:
        confidence = "insufficient"

    elif contradictory:
        confidence = "mixed evidence"

    elif (
        len(grouped) >= 3
        and len(source_documents) >= 2
        and len(direct_passages) >= 2
    ):
        confidence = "well supported"

    elif len(grouped) >= 2:
        confidence = "developing"

    else:
        confidence = "limited"

    temporal_types = {
        item["temporal_type"]
        for item in supporting
    }

    if (
        "enduring_characteristic" in temporal_types
        and len(grouped) >= 2
    ):
        temporal_type = "enduring_characteristic"

    elif (
        "recurring_pattern" in temporal_types
        or len(grouped) >= 2
    ):
        temporal_type = "recurring_pattern"

    elif temporary and not supporting:
        temporal_type = "temporary_state"

    else:
        temporal_type = "unknown"

    return {
        "identity_weight": weight,
        "evidence_strength": confidence,
        "weight_factors": factors,
        "temporal_type": temporal_type,
        "evidence_count": len(evidence),
        "supporting_count": len(supporting),
        "contradictory_count": len(contradictory),
        "temporary_count": len(temporary),
        "independent_passages": len(grouped),
        "source_documents": len(source_documents),
        "evidence": evidence,
    }


def build_psychological_portrait(profile_id, owner_id):

    with database_connection() as conn:
        with conn.cursor() as cur:

            authorized = {
                item["id"]: item
                for item in authorized_memories(
                    cur,
                    profile_id,
                    owner_id,
                    pending_only=False,
                )
            }

            cur.execute("""
                SELECT
                    c.id AS characteristic_id,
                    c.dimension,
                    c.characteristic_key,
                    c.label,
                    c.review_status,
                    c.user_correction,
                    e.id AS evidence_id,
                    e.source_memory_id,
                    e.evidence_type,
                    e.direction,
                    e.interpretation,
                    e.source_excerpt,
                    e.weight_factors,
                    e.temporal_type
                FROM psychological_characteristics c
                JOIN psychological_evidence e
                    ON e.characteristic_id = c.id
                   AND e.profile_id = c.profile_id
                WHERE c.profile_id = %s
                  AND c.review_status != 'rejected'
                ORDER BY c.dimension, c.label,
                         e.created_utc
            """, (profile_id,))

            rows = cur.fetchall()

    grouped = {}

    for row in rows:

        memory = authorized.get(
            row["source_memory_id"]
        )

        if memory is None:
            continue

        characteristic_id = row["characteristic_id"]

        if characteristic_id not in grouped:

            grouped[characteristic_id] = {
                "id": characteristic_id,
                "dimension": row["dimension"],
                "key": row["characteristic_key"],
                "label": row["label"],
                "review_status": row["review_status"],
                "user_correction": row["user_correction"],
                "evidence": [],
            }

        grouped[characteristic_id]["evidence"].append({
            "id": row["evidence_id"],
            "source_memory_id": row["source_memory_id"],
            "source_document_id": memory["source_document_id"],
            "source_chunk_id": memory["source_chunk_id"],
            "evidence_type": row["evidence_type"],
            "direction": row["direction"],
            "interpretation": row["interpretation"],
            "source_excerpt": row["source_excerpt"],
            "weight_factors": row["weight_factors"] or {},
            "temporal_type": row["temporal_type"],
        })

    portrait = {
        key: {
            "key": key,
            "label": definition["label"],
            "description": definition["description"],
            "characteristics": [],
        }
        for key, definition in DIMENSIONS.items()
    }

    for characteristic in grouped.values():

        result = aggregate_characteristic(
            characteristic["evidence"]
        )

        characteristic.update(result)

        portrait[
            characteristic["dimension"]
        ]["characteristics"].append(characteristic)

    for dimension in portrait.values():

        characteristics = dimension["characteristics"]

        characteristics.sort(
            key=lambda item: (
                item["identity_weight"] is not None,
                item["identity_weight"] or 0,
            ),
            reverse=True,
        )

        weighted = [
            item["identity_weight"]
            for item in characteristics
            if item["identity_weight"] is not None
        ]

        # Median significance of weighted characteristics.
        # Not a measure of intelligence, emotional capacity,
        # personality strength or psychological health.
        dimension["identity_weight"] = (
            round(median(weighted), 1)
            if weighted
            else None
        )

        dimension["characteristic_count"] = len(
            characteristics
        )

        dimension["weighted_count"] = len(weighted)

        dimension["evidence_count"] = sum(
            item["evidence_count"]
            for item in characteristics
        )

    return list(portrait.values())


def print_portrait(portrait):

    print("\nLEGACY PSYCHOLOGICAL IDENTITY")
    print("=" * 55)

    total_characteristics = 0
    total_evidence = 0

    for dimension in portrait:

        weight = dimension["identity_weight"]

        display_weight = (
            f"{weight:.1f}/100"
            if weight is not None
            else "Not established"
        )

        print(f"\n{dimension['label'].upper()}")
        print("Estimated significance:", display_weight)

        print(
            "Characteristics:",
            dimension["characteristic_count"]
        )

        print(
            "Evidence records:",
            dimension["evidence_count"]
        )

        total_characteristics += (
            dimension["characteristic_count"]
        )

        total_evidence += dimension["evidence_count"]

        for item in dimension["characteristics"]:

            weight = item["identity_weight"]

            score = (
                f"{weight:.1f}"
                if weight is not None
                else "Unknown"
            )

            print(
                f"  {item['label']}: {score}"
                f" | {item['evidence_strength']}"
                f" | {item['evidence_count']} evidence"
            )

    print("\n" + "=" * 55)

    print("Total characteristics:", total_characteristics)
    print("Total evidence records:", total_evidence)
    print("No AI requests made.")


if __name__ == "__main__":

    profile = select_profile()

    portrait = build_psychological_portrait(
        profile["id"],
        profile["owner_id"],
    )

    print_portrait(portrait)
