"""
Legacy psychological processing worker.

Processes persistent memory analysis jobs for
any user profile.
"""

import argparse
from uuid import uuid4

from database import database_connection

from personality_framework import FRAMEWORK_VERSION

from personality_analysis import (
    analyze_memories,
    AnalysisResponseError,
    BATCH_SIZE,
    source_hash,
)

from personality_storage import (
    synchronize_profile,
    load_authorized_sources,
    save_assessment,
    record_usage,
)

WORKER_ID = uuid4().hex


def claim_batch(profile_id, owner_id, limit):

    with database_connection() as conn:
        with conn.cursor() as cur:

            sources = load_authorized_sources(
                cur, profile_id, owner_id
            )

            # Recover interrupted jobs.

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
                  AND status = 'processing'
                  AND lease_expires_utc < NOW()
            """, (profile_id,))

            cur.execute("""
                SELECT id, memory_id, attempts
                FROM personality_jobs
                WHERE profile_id = %s
                  AND framework_version = %s
                  AND job_type = 'analyze_memory'
                  AND status IN ('pending', 'retry')
                  AND attempts < max_attempts
                  AND available_utc <= NOW()
                ORDER BY (attempts > 0) DESC, created_utc, id
                LIMIT %s
                FOR UPDATE SKIP LOCKED
            """, (
                profile_id,
                FRAMEWORK_VERSION,
                limit,
            ))

            jobs = cur.fetchall()
            if jobs and jobs[0]["attempts"] > 0:
                jobs = jobs[:1]
            claimed = []

            for job in jobs:

                memory = sources.get(job["memory_id"])

                if memory is None:

                    cur.execute("""
                        UPDATE personality_jobs
                        SET status = 'cancelled',
                            updated_utc = NOW()
                        WHERE id = %s
                    """, (job["id"],))

                    continue

                cur.execute("""
                    SELECT 1
                    FROM personality_memory_assessments
                    WHERE profile_id = %s
                      AND memory_id = %s
                      AND framework_version = %s
                      AND source_hash = %s
                """, (
                    profile_id,
                    memory["id"],
                    FRAMEWORK_VERSION,
                    source_hash(memory),
                ))

                if cur.fetchone():

                    cur.execute("""
                        UPDATE personality_jobs
                        SET status = 'completed',
                            completed_utc = NOW(),
                            updated_utc = NOW()
                        WHERE id = %s
                    """, (job["id"],))

                    continue

                cur.execute("""
                    UPDATE personality_jobs
                    SET status = 'processing',
                        attempts = attempts + 1,
                        worker_id = %s,
                        lease_expires_utc =
                            NOW() + INTERVAL '30 minutes',
                        updated_utc = NOW()
                    WHERE id = %s
                """, (WORKER_ID, job["id"]))

                claimed.append({
                    "job_id": job["id"],
                    "memory": memory,
                    "recovery": job["attempts"] > 0,
                })

            return claimed


def fail_batch(profile_id, jobs, error):

    usage = getattr(error, "usage", None)

    with database_connection() as conn:
        with conn.cursor() as cur:

            if usage:

                record_usage(
                    cur,
                    profile_id,
                    jobs[0]["job_id"],
                    "memory_analysis_batch",
                    usage,
                    "invalid_response",
                )

            for job in jobs:

                cur.execute("""
                    UPDATE personality_jobs
                    SET status = CASE
                            WHEN attempts >= max_attempts AND NOT (max_attempts = 3 AND %s)
                            THEN 'failed'
                            ELSE 'retry'
                        END,
                        max_attempts = CASE WHEN attempts >= max_attempts AND max_attempts = 3 AND %s THEN 4 ELSE max_attempts END,
                        available_utc =
                            NOW() + INTERVAL '1 minute',
                        last_error = %s,
                        worker_id = NULL,
                        lease_expires_utc = NULL,
                        updated_utc = NOW()
                    WHERE id = %s
                      AND worker_id = %s
                      AND status = 'processing'
                """, (
                    "Model omitted one or more memories." in str(error),
                    "Model omitted one or more memories." in str(error),
                    (
    f"{type(error).__name__}: {str(error)[:500]}"
    if isinstance(error, (AnalysisResponseError, ValueError))
    else type(error).__name__
),
                    job["job_id"],
                    WORKER_ID,
                ))


def process_batch(profile_id, owner_id, limit=BATCH_SIZE):

    jobs = claim_batch(
        profile_id,
        owner_id,
        min(limit, BATCH_SIZE),
    )

    if not jobs:
        return None

    memories = [
        job["memory"] for job in jobs
    ]

    try:

        result = analyze_memories(memories, recovery=any(job["recovery"] for job in jobs))

    except Exception as error:

        fail_batch(profile_id, jobs, error)
        raise

    usage = result["usage"]

    # Persist usage independently of assessment storage.

    with database_connection() as conn:
        with conn.cursor() as cur:

            record_usage(
                cur,
                profile_id,
                jobs[0]["job_id"],
                "memory_analysis_batch",
                usage,
                "success" if not result["errors"] else "invalid_response",
            )

    assessments = {
        item["memory_id"]: item
        for item in result["assessments"]
    }

    for job in jobs:
        key = str(job["memory"]["id"])
        if key in result["errors"]:
            fail_batch(profile_id, [job], ValueError(result["errors"][key]))

    jobs = [job for job in jobs if str(job["memory"]["id"]) in assessments]
    saved = 0
    traits = 0
    formulations = 0

    try:

        with database_connection() as conn:
            with conn.cursor() as cur:

                sources = load_authorized_sources(
                    cur,
                    profile_id,
                    owner_id,
                )

                for job in jobs:

                    cur.execute("""
                        SELECT id
                        FROM personality_jobs
                        WHERE id = %s
                          AND worker_id = %s
                          AND status = 'processing'
                          AND lease_expires_utc > NOW()
                        FOR UPDATE
                    """, (
                        job["job_id"],
                        WORKER_ID,
                    ))

                    if not cur.fetchone():
                        raise RuntimeError(
                            "Processing lease lost."
                        )

                    memory_id = job["memory"]["id"]

                    assessment = assessments[memory_id]

                    created = save_assessment(
                        cur,
                        profile_id,
                        owner_id,
                        assessment,
                        usage["model"],
                        authorized_sources=sources,
                    )

                    if created:

                        saved += 1

                        traits += len(
                            assessment["trait_evidence"]
                        )

                        formulations += len(
                            assessment["formulation_evidence"]
                        )

                    cur.execute("""
                        UPDATE personality_jobs
                        SET status = 'completed',
                            worker_id = NULL,
                            lease_expires_utc = NULL,
                            completed_utc = NOW(),
                            updated_utc = NOW(),
                            last_error = NULL
                        WHERE id = %s
                    """, (job["job_id"],))

    except Exception as error:

        fail_batch(profile_id, jobs, error)
        raise

    return {
        "memories_assessed": len(jobs),
        "failed_memories": len(result["errors"]),
        "assessments_saved": saved,
        "trait_observations": traits,
        "formulation_observations": formulations,
        "usage": usage,
    }


def main():

    from psychological_processing import select_profile

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--run",
        action="store_true",
    )

    parser.add_argument(
        "--max-batches",
        type=int,
        default=1,
    )

    args = parser.parse_args()

    if args.max_batches < 1:
        parser.error("--max-batches must be positive")

    profile = select_profile()

    profile_id = profile["id"]
    owner_id = profile["owner_id"]

    state = synchronize_profile(
        profile_id,
        owner_id,
    )

    print("\nLEGACY PSYCHOLOGICAL ENGINE")
    print("=" * 55)

    for key, value in state.items():
        print(key.replace("_", " ").title(), ":", value)

    if not args.run:

        print("Queue initialized.")
        print("No API requests made.")
        return

    for number in range(args.max_batches):

        print(
            f"\nProcessing batch "
            f"{number + 1}/{args.max_batches}"
        )

        try:

            result = process_batch(
                profile_id,
                owner_id,
            )

        except Exception as error:

            print("Processing stopped:", (
    f"{type(error).__name__}: {str(error)[:500]}"
    if isinstance(error, AnalysisResponseError)
    else type(error).__name__
))

            if isinstance(error, AnalysisResponseError):
                print("Validation error:", str(error))

            print(
                "Provider status:",
                getattr(error, "status_code", None)
            )

            print("Previously completed work preserved.")
            break

        if result is None:

            print("No available jobs.")
            break

        for key, value in result.items():

            if key != "usage":

                print(
                    key.replace("_", " ").title(),
                    ":",
                    value,
                )

        print("\nAPI TOKEN USAGE")

        for key, value in result["usage"].items():
            print(key, ":", value)

    print("\nProcessing finished.")


if __name__ == "__main__":
    main()
