"""
Legacy automated psychological processing service.

Coordinates memory analysis, longitudinal synthesis,
persistent storage and background execution.
"""

import os
import time
import threading
from uuid import uuid4

from psycopg.types.json import Jsonb

from database import database_connection

from personality_framework import (
    FRAMEWORK_VERSION,
    TRAITS,
    FORMULATION_AREAS,
)

from personality_storage import (
    synchronize_profile,
    load_authorized_sources,
    load_psychological_evidence,
    record_usage,
)

from personality_analysis import source_hash, AnalysisResponseError

from personality_worker import process_batch

from personality_synthesis import synthesize_assessments


SERVICE_ID = uuid4().hex

POLL_INTERVAL = 30

MAX_BATCHES_PER_CYCLE = 2

SYNTHESIS_GROUP_SIZE = 5

_service_thread = None
_service_lock = threading.Lock()


def list_profiles():

    with database_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT id, owner_id, display_name
                FROM profiles
                ORDER BY created_utc, id
            """)

            return cur.fetchall()


def get_processing_status(profile_id):

    with database_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT status, revision
                FROM personality_models
                WHERE profile_id = %s
            """, (profile_id,))

            model = cur.fetchone()

            cur.execute("""
                SELECT status, COUNT(*) AS total
                FROM personality_jobs
                WHERE profile_id = %s
                  AND framework_version = %s
                  AND job_type = 'analyze_memory'
                GROUP BY status
            """, (
                profile_id,
                FRAMEWORK_VERSION,
            ))

            jobs = {
                row["status"]: row["total"]
                for row in cur.fetchall()
            }

            cur.execute("""
                SELECT COUNT(*) AS total
                FROM personality_memory_assessments
                WHERE profile_id = %s
                  AND framework_version = %s
            """, (
                profile_id,
                FRAMEWORK_VERSION,
            ))

            assessments = cur.fetchone()["total"]

            return {
                "model": model,
                "jobs": jobs,
                "assessments": assessments,
            }


def assessment_signature(assessments):

    return sorted(
        (
            item["id"],
            item["memory_id"],
            item["source_hash"],
        )
        for item in assessments
    )


def partition_assessments(assessments, group_size=SYNTHESIS_GROUP_SIZE):

    trait_keys = sorted({
        evidence["trait_key"]
        for assessment in assessments
        for evidence in assessment["trait_evidence"]
    })

    formulation_keys = sorted({
        evidence["formulation_key"]
        for assessment in assessments
        for evidence in assessment["formulation_evidence"]
    })

    for keys, section, field in (
        (
            trait_keys,
            "trait_evidence",
            "trait_key",
        ),
        (
            formulation_keys,
            "formulation_evidence",
            "formulation_key",
        ),
    ):

        for start in range(
            0, len(keys), group_size
        ):

            selected = set(
                keys[start:start + group_size]
            )

            partition = []

            for assessment in assessments:

                evidence = [
                    dict(item, _original_index=index) if section == "formulation_evidence" else item
                    for index, item in enumerate(assessment[section])
                    if item[field] in selected
                ]

                if not evidence:
                    continue

                copy = dict(assessment)

                copy["trait_evidence"] = []
                copy["formulation_evidence"] = []

                copy[section] = evidence

                partition.append(copy)

            if partition:
                yield partition


def claim_synthesis(profile_id, owner_id):

    with database_connection() as conn:
        with conn.cursor() as cur:

            load_authorized_sources(
                cur, profile_id, owner_id
            )

            cur.execute("""
                SELECT revision, status
                FROM personality_models
                WHERE profile_id = %s
                FOR UPDATE
            """, (profile_id,))

            model = cur.fetchone()

            if not model:
                return None

            cur.execute("""
                SELECT COUNT(*) AS total FROM personality_memory_assessments
                WHERE profile_id=%s AND framework_version=%s
            """, (profile_id, FRAMEWORK_VERSION))
            count = cur.fetchone()["total"]
            if not count:
                return None
            cur.execute("""
                SELECT last_assessment_count, last_revision
                FROM personality_synthesis_checkpoints WHERE profile_id=%s
            """, (profile_id,))
            checkpoint = cur.fetchone()
            cur.execute("""
                SELECT COUNT(*) AS total FROM personality_jobs
                WHERE profile_id=%s AND framework_version=%s
                AND job_type='analyze_memory'
                AND status IN ('pending','retry','processing')
            """, (profile_id, FRAMEWORK_VERSION))
            remaining = cur.fetchone()["total"]
            if checkpoint:
                if checkpoint['last_revision'] == model['revision']:
                    return None
                if remaining and model['status'] == 'stale':
                    cur.execute("""
                        SELECT EXISTS(SELECT 1 FROM personality_trait_profiles WHERE profile_id=%s)
                        OR EXISTS(SELECT 1 FROM personality_formulations WHERE profile_id=%s) AS saved
                    """, (profile_id, profile_id))
                    if cur.fetchone()['saved'] and 0 <= count-checkpoint['last_assessment_count'] < 20:
                        return None
            elif remaining and count < 16:
                return None

            cur.execute("""
                UPDATE personality_jobs
                SET status = CASE
                        WHEN attempts >= max_attempts AND max_attempts <> 3
                        THEN 'failed'
                        ELSE 'retry'
                    END,
                    max_attempts = CASE WHEN attempts >= max_attempts AND max_attempts = 3 THEN 4 ELSE max_attempts END,
                    worker_id = NULL,
                    lease_expires_utc = NULL,
                    updated_utc = NOW()
                WHERE profile_id = %s
                  AND job_type = 'synthesize_profile'
                  AND status = 'processing'
                  AND lease_expires_utc < NOW()
            """, (profile_id,))

            cur.execute("""
                SELECT id, status, attempts,
                       max_attempts,
                       available_utc <= NOW() AS available
                FROM personality_jobs
                WHERE profile_id = %s
                  AND framework_version = %s
                  AND job_type = 'synthesize_profile'
                  AND status IN (
                      'pending', 'retry', 'processing'
                  )
                FOR UPDATE
            """, (
                profile_id,
                FRAMEWORK_VERSION,
            ))

            job = cur.fetchone()

            if job:

                if job["status"] == "processing":
                    return None

                if not job["available"]:
                    return None

                if job["attempts"] >= job["max_attempts"]:
                    return None

                job_id = job["id"]

            else:

                cur.execute("""
                    SELECT 1
                    FROM personality_jobs
                    WHERE profile_id = %s
                      AND framework_version = %s
                      AND job_type = 'synthesize_profile'
                      AND status = 'failed'
                      AND synthesis_revision = %s
                    LIMIT 1
                """, (
                    profile_id,
                    FRAMEWORK_VERSION,
                    model["revision"],
                ))

                if cur.fetchone():
                    return None

                job_id = uuid4().hex

                cur.execute("""
                    INSERT INTO personality_jobs (
                        id,
                        profile_id,
                        framework_version,
                        job_type
                    )
                    VALUES (
                        %s, %s, %s,
                        'synthesize_profile'
                    )
                """, (
                    job_id,
                    profile_id,
                    FRAMEWORK_VERSION,
                ))

            cur.execute("""
                UPDATE personality_jobs
                SET status = 'processing',
                    attempts = attempts + 1,
                    synthesis_revision = %s,
                    worker_id = %s,
                    lease_expires_utc =
                        NOW() + INTERVAL '60 minutes',
                    updated_utc = NOW()
                WHERE id = %s
            """, (model["revision"], SERVICE_ID, job_id))

            return {
                "id": job_id,
                "revision": model["revision"],
                "recovery": bool(job and job["attempts"] > 0),
            }


def save_synthesis(
    profile_id,
    owner_id,
    job,
    assessments,
    result,
):

    with database_connection() as conn:
        with conn.cursor() as cur:

            sources = load_authorized_sources(
                cur, profile_id, owner_id
            )

            for assessment in assessments:

                source = sources.get(
                    assessment["memory_id"]
                )

                if source is None:
                    raise ValueError(
                        "Source no longer available."
                    )

                if (
                    source_hash(source)
                    != assessment["source_hash"]
                ):
                    raise ValueError(
                        "Source changed during synthesis."
                    )

            cur.execute("""
                SELECT revision
                FROM personality_models
                WHERE profile_id = %s
                FOR UPDATE
            """, (profile_id,))

            model = cur.fetchone()

            if (
                not model
                or model["revision"] != job["revision"]
            ):
                raise ValueError(
                    "Psychological evidence changed."
                )

            cur.execute("""
                SELECT id
                FROM personality_jobs
                WHERE id = %s
                  AND worker_id = %s
                  AND status = 'processing'
                  AND lease_expires_utc > NOW()
                FOR UPDATE
            """, (
                job["id"],
                SERVICE_ID,
            ))

            if not cur.fetchone():
                raise RuntimeError(
                    "Synthesis lease lost."
                )

            cur.execute("""
                DELETE FROM personality_trait_profiles
                WHERE profile_id = %s
            """, (profile_id,))

            cur.execute("""
                DELETE FROM personality_formulations
                WHERE profile_id = %s
            """, (profile_id,))

            for item in result["traits"]:

                cur.execute("""
                    INSERT INTO personality_trait_profiles (
                        profile_id,
                        trait_key,
                        framework_version,
                        model_revision,
                        expression_score,
                        evidence_confidence,
                        interpretation,
                        behavioral_patterns,
                        contextual_variations,
                        contradictory_evidence,
                        supporting_evidence,
                        limitations,
                        evidence_count
                    )
                    VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                """, (
                    profile_id,
                    item["trait_key"],
                    FRAMEWORK_VERSION,
                    job["revision"],
                    item["expression_score"],
                    item["evidence_confidence"],
                    item["interpretation"],
                    Jsonb(item["behavioral_patterns"]),
                    Jsonb(item["contextual_variations"]),
                    Jsonb(item["contradictory_evidence"]),
                    Jsonb(item["supporting_evidence"]),
                    item["limitations"],
                    item["evidence_count"],
                ))

            for item in result["formulations"]:

                cur.execute("""
                    INSERT INTO personality_formulations (
                        profile_id,
                        formulation_key,
                        framework_version,
                        model_revision,
                        interpretation,
                        supporting_evidence,
                        contradictory_evidence,
                        alternative_explanations,
                        evidence_confidence
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                """, (
                    profile_id,
                    item["formulation_key"],
                    FRAMEWORK_VERSION,
                    job["revision"],
                    item["interpretation"],
                    Jsonb(item["supporting_evidence"]),
                    Jsonb(item["contradictory_evidence"]),
                    Jsonb(item["alternative_explanations"]),
                    item["evidence_confidence"],
                ))

            cur.execute("""
                INSERT INTO personality_synthesis_checkpoints
                    (profile_id,last_assessment_count,last_revision)
                VALUES (%s,%s,%s)
                ON CONFLICT(profile_id) DO UPDATE SET
                    last_assessment_count=EXCLUDED.last_assessment_count,
                    last_revision=EXCLUDED.last_revision, updated_utc=NOW()
            """, (profile_id,len(assessments),job['revision']))

            cur.execute("""
                UPDATE personality_models
                SET status = 'ready',
                    updated_utc = NOW()
                WHERE profile_id = %s
            """, (profile_id,))

            cur.execute("""
                UPDATE personality_jobs
                SET status = 'completed',
                    worker_id = NULL,
                    lease_expires_utc = NULL,
                    completed_utc = NOW(),
                    updated_utc = NOW()
                WHERE id = %s
            """, (job["id"],))


def fail_synthesis(job, error):

    with database_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                UPDATE personality_jobs
                SET status = CASE
                        WHEN attempts >= max_attempts
                        THEN 'failed'
                        ELSE 'retry'
                    END,
                    available_utc =
                        NOW() + INTERVAL '5 minutes',
                    worker_id = NULL,
                    lease_expires_utc = NULL,
                    last_error = %s,
                    updated_utc = NOW()
                WHERE id = %s
                  AND worker_id = %s
                  AND status = 'processing'
            """, (
                (f"{type(error).__name__}: {str(error)[:500]}"
                 if isinstance(error, AnalysisResponseError) else type(error).__name__),
                job["id"],
                SERVICE_ID,
            ))


def persist_usage(profile_id, job_id, usage, status):

    if usage is None:
        return

    with database_connection() as conn:
        with conn.cursor() as cur:

            record_usage(
                cur,
                profile_id,
                job_id,
                "psychological_synthesis",
                usage,
                status,
            )


def process_synthesis(profile_id, owner_id):

    job = claim_synthesis(profile_id, owner_id)

    if job is None:
        return None

    try:

        assessments = load_psychological_evidence(
            profile_id,
            owner_id,
        )

        result = {
            "traits": [],
            "formulations": [],
        }

        for partition in partition_assessments(
            assessments, group_size=2 if job["recovery"] else SYNTHESIS_GROUP_SIZE
        ):

            # Recheck the source snapshot before
            # sending another synthesis request.

            current = load_psychological_evidence(
                profile_id, owner_id
            )

            if (
                assessment_signature(current)
                != assessment_signature(assessments)
            ):
                raise ValueError(
                    "Evidence changed during synthesis."
                )

            try:

                partial = synthesize_assessments(
                    partition
                )

            except Exception as error:

                persist_usage(
                    profile_id,
                    job["id"],
                    getattr(error, "usage", None),
                    "invalid_response",
                )

                raise

            persist_usage(
                profile_id,
                job["id"],
                partial.get("usage"),
                "success",
            )

            result["traits"].extend(
                partial["traits"]
            )

            result["formulations"].extend(
                partial["formulations"]
            )

        save_synthesis(
            profile_id,
            owner_id,
            job,
            assessments,
            result,
        )

        return {
            "memories": len(assessments),
            "traits": len(result["traits"]),
            "formulations": len(result["formulations"]),
        }

    except Exception as error:

        fail_synthesis(job, error)
        raise


def process_profile(profile):

    profile_id = profile["id"]
    owner_id = profile["owner_id"]

    state = synchronize_profile(
        profile_id,
        owner_id,
    )

    if not state["authorized"]:
        return

    if not state["available_memories"]:
        return

    for _ in range(MAX_BATCHES_PER_CYCLE):

        try:
            result = process_batch(profile_id, owner_id)
        except Exception as error:
            print("[Personality] Analysis batch failed:", type(error).__name__, flush=True)
            break

        if result is None:
            break

        print(
            "[Personality]",
            profile_id,
            "saved:",
            result["assessments_saved"],
            "traits:",
            result["trait_observations"],
            "formulations:",
            result["formulation_observations"],
            flush=True,
        )

    synthesis = process_synthesis(
        profile_id,
        owner_id,
    )

    if synthesis:

        print(
            "[Personality] Synthesis complete:",
            profile_id,
            synthesis,
            flush=True,
        )


def run_cycle():

    for profile in list_profiles():

        try:

            process_profile(profile)

        except Exception as error:

            print(
                "[Personality] Processing error:",
                profile["id"],
                type(error).__name__,
                flush=True,
            )


def service_loop():

    print(
        "[Personality] Background service started.",
        flush=True,
    )

    while True:

        try:

            run_cycle()

        except Exception as error:

            print(
                "[Personality] Service error:",
                type(error).__name__,
                flush=True,
            )

        time.sleep(POLL_INTERVAL)


def initialize_personality_schema():
    from pathlib import Path
    root = Path(__file__).resolve().parent
    base = (root / 'personality_migration.sql').read_text().strip()
    base = base.removeprefix('BEGIN;').removesuffix('COMMIT;')
    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(74281930)")
            cur.execute(base)
            cur.execute((root / 'personality_persistence_migration.sql').read_text())
            cur.execute((root / 'personality_progressive_migration.sql').read_text())


def start_background_service():

    global _service_thread

    initialize_personality_schema()

    if (
        os.getenv(
            "LEGACY_PERSONALITY_ENABLED", "true"
        ).lower() != "true"
    ):
        return False

    with _service_lock:

        if (
            _service_thread is not None
            and _service_thread.is_alive()
        ):
            return False

        _service_thread = threading.Thread(
            target=service_loop,
            name="legacy-personality",
            daemon=True,
        )

        _service_thread.start()

        return True


def run_tests():

    assessments = [
        {
            "id": "assessment-1",
            "memory_id": "memory-1",
            "source_hash": "test-hash",
            "trait_evidence": [
                {"trait_key": key}
                for key in TRAITS
            ],
            "formulation_evidence": [
                {"formulation_key": key}
                for key in FORMULATION_AREAS
            ],
        }
    ]

    partitions = list(
        partition_assessments(assessments)
    )

    traits = []
    formulations = []

    for partition in partitions:

        for assessment in partition:

            traits.extend(
                item["trait_key"]
                for item in assessment["trait_evidence"]
            )

            formulations.extend(
                item["formulation_key"]
                for item in assessment["formulation_evidence"]
            )

    assert sorted(traits) == sorted(TRAITS)

    assert (
        sorted(formulations)
        == sorted(FORMULATION_AREAS)
    )

    print("PASS: All psychological traits preserved")
    print("PASS: All formulation areas preserved")
    print("PASS: Synthesis partitioning")

    print("\nCURRENT DATABASE STATUS")

    for profile in list_profiles():

        status = get_processing_status(
            profile["id"]
        )

        print("\nProfile:", profile["display_name"])
        print("Assessments:", status["assessments"])
        print("Jobs:", status["jobs"])
        print("Model:", status["model"])

    print("\nService validation complete.")
    print("No API requests made.")
    print("Background processing not started.")


if __name__ == "__main__":
    run_tests()
