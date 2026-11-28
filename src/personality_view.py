"""
Read-only psychological profile for the Identity interface.
"""

from database import database_connection

from personality_framework import (
    TRAIT_GROUPS,
    TRAITS,
    FORMULATION_AREAS,
    FRAMEWORK_VERSION,
)

from personality_storage import (
    load_authorized_sources,
)

from personality_analysis import source_hash

from personality_unified_storage import load_unified_personality


def build_personality_view(profile_id, owner_id):

    result = {
        "status": "developing",
        "total_memories": 0,
        "analyzed_memories": 0,
        "scored_traits": 0,
        "groups": [],
        "formulations": [],
    }

    traits = {}

    with database_connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                "SET TRANSACTION ISOLATION LEVEL "
                "REPEATABLE READ READ WRITE"
            )

            try:
                sources = load_authorized_sources(
                    cur, profile_id, owner_id
                )
            except PermissionError:
                sources = {}
                result["status"] = "private"

            result["total_memories"] = len(sources)

            cur.execute("""
                SELECT memory_id, source_hash
                FROM personality_memory_assessments
                WHERE profile_id = %s
                  AND framework_version = %s
            """, (
                profile_id,
                FRAMEWORK_VERSION,
            ))

            assessments = cur.fetchall()

            valid = [
                row for row in assessments
                if row["memory_id"] in sources
                and row["source_hash"] == source_hash(
                    sources[row["memory_id"]]
                )
            ]

            result["analyzed_memories"] = len(valid)

            cur.execute("""
                SELECT status, revision
                FROM personality_models
                WHERE profile_id = %s
            """, (profile_id,))

            model = cur.fetchone()

            cur.execute("""
                SELECT MAX(model_revision) AS revision
                FROM (
                    SELECT model_revision
                    FROM personality_trait_profiles
                    WHERE profile_id = %s
                      AND framework_version = %s

                    UNION ALL

                    SELECT model_revision
                    FROM personality_formulations
                    WHERE profile_id = %s
                      AND framework_version = %s
                ) AS snapshots
            """, (
                profile_id, FRAMEWORK_VERSION,
                profile_id, FRAMEWORK_VERSION,
            ))

            snapshot_revision = cur.fetchone()["revision"]

            ready = (
                model
                and snapshot_revision is not None
                and bool(sources)
                and len(valid) == len(assessments)
                and True
            )

            if ready:

                result["status"] = "ready"

                cur.execute("""
                    SELECT *
                    FROM personality_trait_profiles
                    WHERE profile_id = %s
                      AND model_revision = %s
                      AND framework_version = %s
                """, (
                    profile_id,
                    snapshot_revision,
                    FRAMEWORK_VERSION,
                ))

                traits = {
                    row["trait_key"]: dict(row)
                    for row in cur.fetchall()
                }

                cur.execute("""
                    SELECT *
                    FROM personality_formulations
                    WHERE profile_id = %s
                      AND model_revision = %s
                      AND framework_version = %s
                """, (
                    profile_id,
                    snapshot_revision,
                    FRAMEWORK_VERSION,
                ))

                for row in cur.fetchall():

                    item = dict(row)

                    item["label"] = (
                        item["formulation_key"]
                        .replace("_", " ")
                        .title()
                    )

                    result["formulations"].append(item)

            elif sources:
                result["status"] = "developing"

            try:
                unified = load_unified_personality(
                    cur,
                    profile_id,
                    owner_id,
                    authorized_sources=sources,
                )
            except PermissionError:
                unified = {
                    "baseline_completed": False,
                    "valid_evidence_count": 0,
                    "scores": {},
                }

    for group, definitions in TRAIT_GROUPS.items():

        items = []

        for key in definitions:

            definition = TRAITS[key]
            assessment = traits.get(key, {})

            score = assessment.get("expression_score")

            if score is not None:
                score = float(score)
                result["scored_traits"] += 1

            confidence = assessment.get(
                "evidence_confidence"
            )

            items.append({
                "key": key,
                "label": definition["label"],
                "low": definition["low_expression"],
                "high": definition["high_expression"],
                "score": score,
                "confidence": (
                    float(confidence)
                    if confidence is not None
                    else None
                ),
                "interpretation": assessment.get(
                    "interpretation", ""
                ),
                "patterns": assessment.get(
                    "behavioral_patterns", []
                ),
                "variations": assessment.get(
                    "contextual_variations", []
                ),
                "limitations": assessment.get(
                    "limitations", ""
                ),
                "evidence_count": assessment.get(
                    "evidence_count", 0
                ),
            })

        result["groups"].append({
            "key": group,
            "label": group.replace("_", " ").title(),
            "traits": items,
        })

    result["progress"] = (
        round(
            100 * result["analyzed_memories"]
            / result["total_memories"], 1
        )
        if result["total_memories"]
        else 0
    )


    # The five core scores have exactly one source of
    # truth. All remaining psychological interpretations
    # and formulations retain their existing storage.

    result["unified"] = unified

    # A completed local questionnaire remains available
    # independently of remote psychological processing.
    if unified["baseline_completed"]:

        if result["status"] == "ready":
            result["status"] = "integrated_ready"
        else:
            result["status"] = "baseline_ready"


    for group in result["groups"]:

        if group["key"] != "core_personality":
            continue

        for trait in group["traits"]:

            calculated = unified["scores"].get(
                trait["key"]
            )

            # Preserve historical synthesis metadata
            # separately from the current unified estimate.
            trait["previous_synthesis_confidence"] = (
                trait.get("confidence")
            )
            trait["previous_synthesis_evidence_count"] = (
                trait.get("evidence_count", 0)
            )

            # Unified confidence has not been calibrated.
            trait["confidence"] = None
            trait["evidence_count"] = (
                calculated["independent_evidence_count"]
                if calculated is not None
                else 0
            )

            if calculated is None:
                trait["score"] = None
                trait["method"] = "insufficient_evidence"
                trait["baseline_influence"] = None
                trait["independent_evidence_count"] = 0
                continue

            trait["score"] = calculated["score"]
            trait["method"] = calculated["method"]
            trait["baseline_influence"] = (
                calculated["baseline_influence"]
            )
            trait["independent_evidence_count"] = (
                calculated["independent_evidence_count"]
            )

    result["scored_traits"] = sum(
        trait["score"] is not None
        for group in result["groups"]
        for trait in group["traits"]
    )

    return result
