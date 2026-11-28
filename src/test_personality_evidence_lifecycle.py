from uuid import uuid4
from psycopg.types.json import Jsonb

from database import database_connection
from personality_baseline_storage import (
    get_or_create_draft,
    save_draft,
    complete_assessment,
    get_latest_baseline,
)
from personality_unified_storage import get_unified_personality
from personality_storage import load_authorized_sources
from personality_analysis import source_hash
from personality_framework import FRAMEWORK_VERSION
from personality_view import build_personality_view


def uid():
    return uuid4().hex


owner_id = uid()
profile_id = uid()
document_id = uid()
chunk_id = uid()
memory_id = uid()
assessment_id = uid()
evidence_id = uid()

passage = (
    "I regularly explore unfamiliar subjects and "
    "experiment with new approaches to solving problems."
)

with database_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT current_database() AS name,
                   inet_server_addr()::text AS host
        """)
        db = cur.fetchone()

assert db["name"] == "legacy", "Not the local database."
assert db["host"] in (None, "127.0.0.1", "::1")


def execute(sql, params):
    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)


def complete_baseline(answer):
    draft = get_or_create_draft(profile_id, owner_id)

    save_draft(
        profile_id,
        owner_id,
        draft["id"],
        {str(i): answer for i in range(1, 51)},
    )

    return complete_assessment(
        profile_id, owner_id, draft["id"]
    )


def current_score():
    model = get_unified_personality(profile_id, owner_id)
    return model["scores"]["openness"]


def change_consent(remote):
    execute("""
        UPDATE profiles
        SET profile_data = jsonb_set(
            profile_data, '{consent}', %s
        )
        WHERE id = %s AND owner_id = %s
    """, (
        Jsonb({
            "has_consent": True,
            "allow_remote_processing": remote,
        }),
        profile_id,
        owner_id,
    ))


def check_score(expected, method, count):
    score = current_score()

    assert score["score"] == expected, score
    assert score["method"] == method, score
    assert score["independent_evidence_count"] == count, score


print("\nDATABASE-BACKED PERSONALITY INTEGRATION")
print("=" * 60)

try:
    with database_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                INSERT INTO users (
                    id, email, password_hash, created_utc
                )
                VALUES (%s, %s, %s, NOW())
            """, (
                owner_id,
                f"integration-{owner_id}@example.invalid",
                "temporary-test-only",
            ))

            cur.execute("""
                INSERT INTO profiles (
                    id, owner_id, display_name, profile_data
                )
                VALUES (%s, %s, %s, %s)
            """, (
                profile_id,
                owner_id,
                "Temporary Integration Test",
                Jsonb({
                    "consent": {
                        "has_consent": True,
                        "allow_remote_processing": True,
                    },
                    "entries": [],
                }),
            ))

    first = complete_baseline(3)

    check_score(50, "questionnaire", 0)
    print("Stored questionnaire baseline: PASSED")

    with database_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                INSERT INTO knowledge_documents (
                    id, profile_id, title,
                    source_type, original_text
                )
                VALUES (%s, %s, %s, 'text', %s)
            """, (
                document_id,
                profile_id,
                "Synthetic test document",
                passage,
            ))

            cur.execute("""
                INSERT INTO knowledge_chunks (
                    id, document_id, chunk_index,
                    chunk_text, token_start, token_end
                )
                VALUES (%s, %s, 0, %s, 0, 25)
            """, (
                chunk_id,
                document_id,
                passage,
            ))

            cur.execute("""
                INSERT INTO structured_memories (
                    id, profile_id, source_document_id,
                    source_chunk_id, category, memory_text,
                    source_excerpt, interpretation_type,
                    status, reviewed_utc
                )
                VALUES (
                    %s, %s, %s, %s,
                    'personality_trait', %s, %s,
                    'explicit', 'approved', NOW()
                )
            """, (
                memory_id,
                profile_id,
                document_id,
                chunk_id,
                passage,
                passage,
            ))

            # Initialize the parent psychological model.
            cur.execute("""
                INSERT INTO personality_models (
                    profile_id, framework_version
                )
                VALUES (%s, %s)
                ON CONFLICT (profile_id) DO NOTHING
            """, (profile_id, FRAMEWORK_VERSION))

            sources = load_authorized_sources(
                cur, profile_id, owner_id
            )

            assert memory_id in sources
            digest = source_hash(sources[memory_id])

            cur.execute("""
                INSERT INTO personality_memory_assessments (
                    id, profile_id, memory_id,
                    framework_version, source_hash,
                    psychological_interpretation,
                    provider_model
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                assessment_id,
                profile_id,
                memory_id,
                FRAMEWORK_VERSION,
                digest,
                "Synthetic openness observation",
                "local-regression-test",
            ))

            cur.execute("""
                INSERT INTO personality_trait_evidence (
                    id, profile_id, assessment_id,
                    trait_key, expression_score,
                    evidence_confidence, evidence_type,
                    temporal_scope, interpretation,
                    source_excerpt
                )
                VALUES (
                    %s, %s, %s, 'openness',
                    90, 100, 'explicit_self_report',
                    'recurring', %s, %s
                )
            """, (
                evidence_id,
                profile_id,
                assessment_id,
                "Synthetic evidence for testing",
                passage,
            ))

    check_score(51.90, "integrated", 1)

    print("Stored memory evidence integration: PASSED")
    print("Integrated openness:", current_score()["score"])

    view = build_personality_view(profile_id, owner_id)

    core = next(
        g for g in view["groups"]
        if g["key"] == "core_personality"
    )

    openness = next(
        t for t in core["traits"]
        if t["key"] == "openness"
    )

    assert openness["score"] == 51.90
    assert openness["method"] == "integrated"

    print("Integrated Identity display: PASSED")

    change_consent(False)

    check_score(50, "questionnaire", 0)
    print("Remote consent revocation: PASSED")

    change_consent(True)

    check_score(51.90, "integrated", 1)
    print("Remote consent restoration: PASSED")

    execute("""
        UPDATE structured_memories
        SET memory_text = %s
        WHERE id = %s AND profile_id = %s
    """, (
        "This memory has been edited.",
        memory_id,
        profile_id,
    ))

    check_score(50, "questionnaire", 0)
    print("Stale assessment exclusion after edit: PASSED")

    execute("""
        UPDATE structured_memories
        SET memory_text = %s
        WHERE id = %s AND profile_id = %s
    """, (
        passage,
        memory_id,
        profile_id,
    ))

    check_score(51.90, "integrated", 1)
    print("Restored source consistency: PASSED")

    execute("""
        UPDATE structured_memories
        SET status = 'rejected',
            reviewed_utc = NOW()
        WHERE id = %s AND profile_id = %s
    """, (memory_id, profile_id))

    check_score(50, "questionnaire", 0)
    print("Rejected memory exclusion: PASSED")

    execute("""
        UPDATE structured_memories
        SET status = 'approved',
            reviewed_utc = NOW()
        WHERE id = %s AND profile_id = %s
    """, (memory_id, profile_id))

    check_score(51.90, "integrated", 1)
    print("Reapproved memory integration: PASSED")

    execute("""
        DELETE FROM personality_trait_evidence
        WHERE id = %s AND profile_id = %s
    """, (evidence_id, profile_id))

    check_score(50, "questionnaire", 0)
    print("Evidence deletion recalculation: PASSED")

    second = complete_baseline(5)

    assert second["id"] != first["id"]

    latest = get_latest_baseline(profile_id, owner_id)

    assert latest["id"] == second["id"]

    check_score(70, "questionnaire", 0)

    print("Assessment retake: PASSED")
    print("Latest baseline selection: PASSED")
    print("Updated openness:", current_score()["score"])

    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS total
                FROM personality_baseline_assessments
                WHERE profile_id = %s
                  AND status = 'completed'
            """, (profile_id,))

            assert cur.fetchone()["total"] == 2

    print("Historical assessment preservation: PASSED")
    print("\nSTEP 9G.3: PASSED")

finally:
    with database_connection() as conn:
        with conn.cursor() as cur:

            for table in (
                "personality_trait_evidence",
                "personality_memory_assessments",
                "personality_baseline_assessments",
                "structured_memories",
            ):
                cur.execute(
                    f"DELETE FROM {table} WHERE profile_id = %s",
                    (profile_id,),
                )

            cur.execute("""
                DELETE FROM knowledge_chunks
                WHERE document_id = %s
            """, (document_id,))

            cur.execute("""
                DELETE FROM knowledge_documents
                WHERE id = %s AND profile_id = %s
            """, (document_id, profile_id))

            cur.execute(
                "DELETE FROM profiles WHERE id = %s",
                (profile_id,),
            )

            cur.execute(
                "DELETE FROM users WHERE id = %s",
                (owner_id,),
            )

    print("Temporary test records removed.")
    print("Personal profile: UNTOUCHED")
    print("External AI requests: NONE")
