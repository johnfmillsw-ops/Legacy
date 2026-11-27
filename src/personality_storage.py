"""
Legacy personality engine persistence.

Profile-scoped authorization, memory synchronization,
assessment storage and persistent job scheduling.
"""

from uuid import uuid4

from psycopg.types.json import Jsonb

from database import database_connection

from personality_framework import FRAMEWORK_VERSION

from personality_analysis import source_hash

from psychological_processing import authorized_memories


def new_id():
    return uuid4().hex


def load_authorized_sources(cur, profile_id, owner_id):

    memories = authorized_memories(
        cur,
        profile_id,
        owner_id,
        pending_only=False,
    )

    if not memories:
        return {}

    ids = [memory["id"] for memory in memories]

    cur.execute("""
        SELECT
            m.id,
            m.source_excerpt,
            c.chunk_text AS original_passage
        FROM structured_memories m
        JOIN knowledge_chunks c
            ON c.id = m.source_chunk_id
        JOIN knowledge_documents d
            ON d.id = c.document_id
           AND d.id = m.source_document_id
           AND d.profile_id = m.profile_id
        WHERE m.profile_id = %s
          AND m.id = ANY(%s)
          AND m.status = 'approved'
    """, (profile_id, ids))

    excerpts = {
        row["id"]: row
        for row in cur.fetchall()
    }

    result = {}

    for memory in memories:

        memory_id = memory["id"]

        if memory_id not in excerpts:
            continue

        source = dict(memory)

        source["source_excerpt"] = (
            excerpts[memory_id]["source_excerpt"] or ""
        )

        source["original_passage"] = (
            excerpts[memory_id]["original_passage"] or ""
        )

        result[memory_id] = source

    return result


def initialize_model(cur, profile_id):

    cur.execute("""
        INSERT INTO personality_models (
            profile_id,
            framework_version
        )
        VALUES (%s, %s)
        ON CONFLICT (profile_id) DO NOTHING
    """, (profile_id, FRAMEWORK_VERSION))


def invalidate_model(cur, profile_id):

    cur.execute("""
        DELETE FROM personality_trait_profiles
        WHERE profile_id = %s
    """, (profile_id,))

    cur.execute("""
        DELETE FROM personality_formulations
        WHERE profile_id = %s
    """, (profile_id,))

    cur.execute("""
        UPDATE personality_models
        SET status = 'stale',
            revision = revision + 1,
            updated_utc = NOW()
        WHERE profile_id = %s
    """, (profile_id,))


def enqueue_memory(cur, profile_id, memory_id):

    cur.execute("""
        INSERT INTO personality_jobs (
            id,
            profile_id,
            memory_id,
            framework_version,
            job_type
        )
        VALUES (%s, %s, %s, %s, 'analyze_memory')
        ON CONFLICT DO NOTHING
        RETURNING id
    """, (
        new_id(),
        profile_id,
        memory_id,
        FRAMEWORK_VERSION,
    ))

    return cur.fetchone() is not None


def enqueue_synthesis(cur, profile_id):

    cur.execute("""
        INSERT INTO personality_jobs (
            id,
            profile_id,
            framework_version,
            job_type
        )
        VALUES (%s, %s, %s, 'synthesize_profile')
        ON CONFLICT DO NOTHING
        RETURNING id
    """, (
        new_id(),
        profile_id,
        FRAMEWORK_VERSION,
    ))

    return cur.fetchone() is not None


def cancel_unauthorized_jobs(
    cur,
    profile_id,
    authorized_ids,
):

    cur.execute("""
        UPDATE personality_jobs
        SET status = 'cancelled',
            worker_id = NULL,
            lease_expires_utc = NULL,
            updated_utc = NOW()
        WHERE profile_id = %s
          AND job_type = 'analyze_memory'
          AND status IN (
              'pending', 'retry', 'processing'
          )
          AND NOT (memory_id = ANY(%s::text[]))
    """, (profile_id, authorized_ids))

    return cur.rowcount


def purge_profile_analysis(cur, profile_id):

    cur.execute("""
        UPDATE personality_jobs
        SET status = 'cancelled',
            worker_id = NULL,
            lease_expires_utc = NULL,
            updated_utc = NOW()
        WHERE profile_id = %s
          AND status IN (
              'pending', 'retry', 'processing'
          )
    """, (profile_id,))

    cur.execute("""
        DELETE FROM personality_memory_assessments
        WHERE profile_id = %s
    """, (profile_id,))

    invalidate_model(cur, profile_id)


def synchronize_profile(profile_id, owner_id):

    with database_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT profile_data
                FROM profiles
                WHERE id = %s
                  AND owner_id = %s
                FOR UPDATE
            """, (profile_id, owner_id))

            profile = cur.fetchone()

            if not profile:
                raise PermissionError(
                    "Profile access denied."
                )

            data = profile["profile_data"] or {}

            initialize_model(cur, profile_id)

            try:

                sources = load_authorized_sources(
                    cur,
                    profile_id,
                    owner_id,
                )

            except PermissionError:

                purge_profile_analysis(
                    cur, profile_id
                )

                return {
                    "authorized": False,
                    "queued": 0,
                    "available_memories": 0,
                    "current_assessments": 0,
                }

            cancelled = cancel_unauthorized_jobs(
                cur,
                profile_id,
                list(sources),
            )

            cur.execute("""
                SELECT id,
                       memory_id,
                       source_hash,
                       framework_version
                FROM personality_memory_assessments
                WHERE profile_id = %s
            """, (profile_id,))

            existing = cur.fetchall()

            current = set()
            removed = 0

            for assessment in existing:

                memory_id = assessment["memory_id"]

                source = sources.get(memory_id)

                valid = (
                    source is not None
                    and assessment["framework_version"]
                        == FRAMEWORK_VERSION
                    and assessment["source_hash"]
                        == source_hash(source)
                )

                if valid:

                    current.add(memory_id)
                    continue

                cur.execute("""
                    DELETE FROM
                        personality_memory_assessments
                    WHERE id = %s
                      AND profile_id = %s
                """, (
                    assessment["id"],
                    profile_id,
                ))

                removed += cur.rowcount

            queued = 0

            for memory_id in sources:

                if memory_id in current:
                    continue

                # Do not endlessly recreate failed jobs.
                # Failed assessments require an explicit retry.

                cur.execute("""
                    SELECT 1
                    FROM personality_jobs
                    WHERE profile_id = %s
                      AND memory_id = %s
                      AND framework_version = %s
                      AND job_type = 'analyze_memory'
                      AND status = 'failed'
                    LIMIT 1
                """, (
                    profile_id,
                    memory_id,
                    FRAMEWORK_VERSION,
                ))

                if cur.fetchone():
                    continue

                if enqueue_memory(
                    cur, profile_id, memory_id
                ):
                    queued += 1

            if removed:
                invalidate_model(cur, profile_id)
            elif queued:
                cur.execute("""
                    UPDATE personality_models
                    SET status = 'stale',
                        revision = revision + 1,
                        updated_utc = NOW()
                    WHERE profile_id = %s
                """, (profile_id,))

            return {
                "authorized": True,
                "available_memories": len(sources),
                "current_assessments": len(current),
                "queued": queued,
                "removed_assessments": removed,
                "cancelled_jobs": cancelled,
            }


def record_usage(
    cur,
    profile_id,
    job_id,
    operation,
    usage,
    status,
):

    cur.execute("""
        INSERT INTO personality_api_usage (
            id,
            profile_id,
            job_id,
            operation,
            provider,
            model,
            input_tokens,
            output_tokens,
            reasoning_tokens,
            total_tokens,
            status
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        )
    """, (
        new_id(),
        profile_id,
        job_id,
        operation,
        usage["provider"],
        usage["model"],
        usage.get("input_tokens"),
        usage.get("output_tokens"),
        usage.get("reasoning_tokens"),
        usage.get("total_tokens"),
        status,
    ))


def save_assessment(
    cur,
    profile_id,
    owner_id,
    assessment,
    provider_model,
    authorized_sources=None,
):

    sources = authorized_sources

    if sources is None:

        sources = load_authorized_sources(
            cur,
            profile_id,
            owner_id,
        )

    memory_id = assessment["memory_id"]

    source = sources.get(memory_id)

    if source is None:
        raise PermissionError(
            "Memory is no longer authorized."
        )

    if source_hash(source) != assessment["source_hash"]:
        raise ValueError(
            "Memory changed during analysis."
        )

    initialize_model(cur, profile_id)

    cur.execute("""
        SELECT id, source_hash
        FROM personality_memory_assessments
        WHERE profile_id = %s
          AND memory_id = %s
          AND framework_version = %s
    """, (
        profile_id,
        memory_id,
        FRAMEWORK_VERSION,
    ))

    existing = cur.fetchone()

    if existing:

        if (
            existing["source_hash"]
            == assessment["source_hash"]
        ):
            return False

        cur.execute("""
            DELETE FROM personality_memory_assessments
            WHERE id = %s
              AND profile_id = %s
        """, (
            existing["id"],
            profile_id,
        ))

    assessment_id = new_id()

    cur.execute("""
        INSERT INTO personality_memory_assessments (
            id,
            profile_id,
            memory_id,
            framework_version,
            source_hash,
            psychological_interpretation,
            emotional_context,
            behavioral_context,
            formulation_evidence,
            provider_model
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
    """, (
        assessment_id,
        profile_id,
        memory_id,
        FRAMEWORK_VERSION,
        assessment["source_hash"],
        assessment["psychological_interpretation"],
        Jsonb(assessment["emotional_context"]),
        Jsonb(assessment["behavioral_context"]),
        Jsonb(assessment["formulation_evidence"]),
        provider_model,
    ))

    for evidence in assessment["trait_evidence"]:

        cur.execute("""
            INSERT INTO personality_trait_evidence (
                id,
                profile_id,
                assessment_id,
                trait_key,
                expression_score,
                evidence_confidence,
                evidence_type,
                temporal_scope,
                interpretation,
                source_excerpt,
                situational_context,
                alternative_explanation
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
        """, (
            new_id(),
            profile_id,
            assessment_id,
            evidence["trait_key"],
            evidence["expression_score"],
            evidence["evidence_confidence"],
            evidence["evidence_type"],
            evidence["temporal_scope"],
            evidence["interpretation"],
            evidence["source_excerpt"],
            evidence["situational_context"],
            evidence["alternative_explanation"],
        ))

    return True


def load_psychological_evidence(
    profile_id,
    owner_id,
):

    with database_connection() as conn:
        with conn.cursor() as cur:

            sources = load_authorized_sources(
                cur,
                profile_id,
                owner_id,
            )

            cur.execute("""
                SELECT *
                FROM personality_memory_assessments
                WHERE profile_id = %s
                  AND framework_version = %s
                ORDER BY created_utc, id
            """, (
                profile_id,
                FRAMEWORK_VERSION,
            ))

            assessments = []

            for row in cur.fetchall():

                source = sources.get(row["memory_id"])

                if source is None:
                    continue

                if (
                    row["source_hash"]
                    != source_hash(source)
                ):
                    continue

                assessment = dict(row)

                assessment["source_document_id"] = (
                    source.get("source_document_id")
                )

                assessment["source_chunk_id"] = (
                    source.get("source_chunk_id")
                )

                assessment["event_date"] = (
                    source.get("event_date")
                )

                assessment["memory_text"] = (
                    source["memory_text"]
                )

                assessment["trait_evidence"] = []

                assessments.append(assessment)

            by_id = {
                row["id"]: row
                for row in assessments
            }

            if not by_id:
                return []

            cur.execute("""
                SELECT *
                FROM personality_trait_evidence
                WHERE profile_id = %s
                  AND assessment_id = ANY(%s)
                ORDER BY created_utc, id
            """, (
                profile_id,
                list(by_id),
            ))

            for evidence in cur.fetchall():

                assessment = by_id.get(
                    evidence["assessment_id"]
                )

                if assessment is not None:

                    assessment["trait_evidence"].append(
                        dict(evidence)
                    )

            return assessments


def run_tests():

    with database_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name LIKE 'personality_%'
            """)

            tables = {
                row["table_name"]
                for row in cur.fetchall()
            }

            required = {
                "personality_models",
                "personality_memory_assessments",
                "personality_trait_evidence",
                "personality_trait_profiles",
                "personality_formulations",
                "personality_jobs",
                "personality_api_usage",
            }

            assert required.issubset(tables)

            print("PASS: Personality database available")

            cur.execute("""
                SELECT id, owner_id, display_name
                FROM profiles
                ORDER BY display_name
            """)

            profiles = cur.fetchall()

            for profile in profiles:

                try:

                    sources = load_authorized_sources(
                        cur,
                        profile["id"],
                        profile["owner_id"],
                    )

                    for source in sources.values():

                        assert "source_excerpt" in source
                        assert len(source_hash(source)) == 64

                    print(
                        "PASS:",
                        profile["display_name"],
                        "-",
                        len(sources),
                        "authorized memories",
                    )

                except PermissionError:

                    print(
                        "PASS:",
                        profile["display_name"],
                        "- AI processing not authorized",
                    )

    print("\nStorage validation complete.")
    print("No jobs created.")
    print("No assessments modified.")
    print("No API requests made.")


if __name__ == "__main__":
    run_tests()
