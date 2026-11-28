
"""
Legacy Phase VII database integrity tests.

All database changes are rolled back.
No production data is modified.
"""

from pathlib import Path
from uuid import uuid4

from psycopg import IntegrityError
from psycopg.types.json import Jsonb

from database import database_connection

from cognitive_research_bank import (
    build_research_bank,
)

from cognitive_blueprint import (
    assemble_assessment,
)

from cognitive_session import (
    AssessmentSession,
)

from cognitive_timing import (
    get_timing_protocol,
    memory_exposure_duration,
)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def expect_rejection(cur, operation, label):
    cur.execute("SAVEPOINT integrity_test")

    rejected = False

    try:
        operation()

    except IntegrityError:
        rejected = True

    finally:
        cur.execute(
            "ROLLBACK TO SAVEPOINT integrity_test"
        )

        cur.execute(
            "RELEASE SAVEPOINT integrity_test"
        )

    require(
        rejected,
        f"Invalid operation accepted: {label}",
    )

    print(label + ": PASSED")


def create_profile(cur, label):
    owner_id = uuid4().hex
    profile_id = uuid4().hex

    cur.execute("""
        INSERT INTO users (
            id,
            email,
            password_hash,
            created_utc
        )
        VALUES (%s, %s, %s, NOW())
    """, (
        owner_id,
        f"cognitive-test-{owner_id}@example.invalid",
        "test-account-not-for-authentication",
    ))

    cur.execute("""
        INSERT INTO profiles (
            id,
            owner_id,
            display_name,
            created_utc,
            updated_utc,
            profile_data
        )
        VALUES (
            %s, %s, %s, NOW(), NOW(), %s
        )
    """, (
        profile_id,
        owner_id,
        label,
        Jsonb({}),
    ))

    return profile_id


def insert_assessment(
    cur,
    assessment_id,
    profile_id,
    form,
):
    cur.execute("""
        INSERT INTO cognitive_assessments (
            id,
            profile_id,
            instrument_version,
            session_version,
            blueprint_version,
            bank_id,
            form_id,
            form_manifest,
            administration_protocol,
            status,
            session_state
        )
        VALUES (
            %s, %s, 1, 1, %s,
            %s, %s, %s, %s,
            'ready', %s
        )
    """, (
        assessment_id,
        profile_id,
        form["manifest"]["blueprint_version"],
        form["manifest"]["bank_id"],
        form["form_id"],
        Jsonb(form["manifest"]),
        Jsonb(get_timing_protocol()),
        Jsonb({"state": "ready"}),
    ))


def insert_items(cur, session):
    total = 0

    for block_index, block in enumerate(
        session.blocks
    ):
        for item_index, record in enumerate(
            block["items"]
        ):
            question = record["question_snapshot"]

            cur.execute("""
                INSERT INTO cognitive_assessment_items (
                    assessment_id,
                    block_index,
                    item_index,
                    item_id,
                    presentation_id,
                    question_id,
                    exposure_hash,
                    domain,
                    family,
                    programmed_difficulty,
                    item_record
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
            """, (
                session.session_id,
                block_index,
                item_index,
                record["item_id"],
                record["presentation_id"],
                question["id"],
                question["exposure_hash"],
                question["domain"],
                question["family"],
                question["difficulty"],
                Jsonb(record),
            ))

            total += 1

    return total


def insert_response(cur, assessment_id, response):
    cur.execute("""
        INSERT INTO cognitive_responses (
            assessment_id,
            block_index,
            item_index,
            outcome,
            selected_option_id,
            correct,
            presented_ms,
            response_started_ms,
            recorded_ms,
            response_latency_ms
        )
        VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
    """, (
        assessment_id,
        response["block_index"],
        response["item_index"],
        response["outcome"],
        response["selected_option_id"],
        response["correct"],
        response["presented_ms"],
        response["response_started_ms"],
        response["recorded_ms"],
        response["response_latency_ms"],
    ))


def complete_session(session):
    now = 1000

    while session.state != "completed":

        if session.state == "ready":
            now += 1000

            session.begin_block(now)

            if session._block()["mode"] == (
                "timed_queue"
            ):
                question = session._question()

                now = session.block_deadline_ms - 1

                session.submit_response(
                    question["id"],
                    question["correct_option_id"],
                    now,
                )

                session.advance(now)

                now = session.block_deadline_ms

                session.tick(now)

        elif session.state == "memorize":
            question = session._question()

            now += memory_exposure_duration(
                question["difficulty"]
            )

            session.finish_memory_exposure(
                question["id"],
                now,
            )

        elif session.state == "respond":
            question = session._question()

            now += 1000

            session.submit_response(
                question["id"],
                question["correct_option_id"],
                now,
            )

        elif session.state == "answered":
            now += 100

            session.advance(now)

        else:
            raise RuntimeError(
                f"Unexpected state: {session.state}"
            )

    return session.results()


def run_tests():
    bank = build_research_bank()

    form = assemble_assessment(
        bank,
        "database-integrity-test-v1",
    )

    session = AssessmentSession(
        form,
        bank,
        1000,
    )

    assessment_id = session.session_id

    migration = Path(
        "cognitive_migration.sql"
    ).read_text(encoding="utf-8")

    with database_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SET LOCAL lock_timeout = '5s'"
                )

                cur.execute(
                    "SET LOCAL statement_timeout = '60s'"
                )

                cur.execute(migration)

                profile_a = create_profile(
                    cur, "Cognitive Test A"
                )

                profile_b = create_profile(
                    cur, "Cognitive Test B"
                )

                insert_assessment(
                    cur,
                    assessment_id,
                    profile_a,
                    form,
                )

                total = insert_items(
                    cur, session
                )

                require(
                    total == 135,
                    "Incorrect item count.",
                )

                print(
                    "135 assessment item snapshots: PASSED"
                )

                expect_rejection(
                    cur,
                    lambda: insert_assessment(
                        cur,
                        uuid4().hex,
                        profile_a,
                        form,
                    ),
                    "Overlapping assessment prevention",
                )

                results = complete_session(
                    session
                )

                require(
                    len(session.responses) == 135,
                    "Incomplete session responses.",
                )

                for response in session.responses:
                    insert_response(
                        cur,
                        assessment_id,
                        response,
                    )

                print(
                    "135 actual controller outcomes: PASSED"
                )

                expect_rejection(
                    cur,
                    lambda: insert_response(
                        cur,
                        assessment_id,
                        session.responses[0],
                    ),
                    "Duplicate response prevention",
                )

                expect_rejection(
                    cur,
                    lambda: cur.execute("""
                        UPDATE cognitive_responses
                        SET correct = FALSE
                        WHERE assessment_id = %s
                          AND outcome = 'correct'
                    """, (assessment_id,)),
                    "Response correctness consistency",
                )

                expect_rejection(
                    cur,
                    lambda: cur.execute("""
                        UPDATE cognitive_responses
                        SET response_latency_ms = -1
                        WHERE assessment_id = %s
                          AND outcome = 'correct'
                    """, (assessment_id,)),
                    "Negative latency prevention",
                )

                expect_rejection(
                    cur,
                    lambda: cur.execute("""
                        UPDATE cognitive_responses
                        SET response_latency_ms =
                            response_latency_ms + 1
                        WHERE assessment_id = %s
                          AND outcome = 'correct'
                    """, (assessment_id,)),
                    "Response latency consistency",
                )

                expect_rejection(
                    cur,
                    lambda: cur.execute("""
                        UPDATE cognitive_responses
                        SET presented_ms = 1000
                        WHERE assessment_id = %s
                          AND outcome = 'not_reached'
                    """, (assessment_id,)),
                    "Unreached item exposure consistency",
                )

                cur.execute("""
                    SELECT outcome, COUNT(*) AS total
                    FROM cognitive_responses
                    WHERE assessment_id = %s
                    GROUP BY outcome
                """, (assessment_id,))

                counts = {
                    row["outcome"]: row["total"]
                    for row in cur.fetchall()
                }

                require(
                    counts == {
                        "correct": 63,
                        "timed_out": 3,
                        "not_reached": 69,
                    },
                    f"Incorrect outcomes: {counts}",
                )

                print(
                    "Complete outcome accounting: PASSED"
                )

                cur.execute("""
                    UPDATE cognitive_assessments
                    SET status = 'completed',
                        completed_utc = NOW(),
                        updated_utc = NOW(),
                        revision = revision + 1,
                        session_state = %s
                    WHERE id = %s
                """, (
                    Jsonb({"state": "completed"}),
                    assessment_id,
                ))

                cur.execute("""
                    INSERT INTO cognitive_assessment_results (
                        assessment_id,
                        profile_id,
                        scoring_version,
                        reporting_status,
                        domain_results,
                        scoring_methodology
                    )
                    VALUES (
                        %s, %s, 1,
                        'experimental_raw',
                        %s, %s
                    )
                """, (
                    assessment_id,
                    profile_a,
                    Jsonb(results["domains"]),
                    Jsonb({
                        "method": "observed_raw_performance",
                        "scientifically_validated": False,
                    }),
                ))

                print(
                    "Completed assessment result storage: PASSED"
                )

                expect_rejection(
                    cur,
                    lambda: cur.execute("""
                        UPDATE cognitive_assessment_results
                        SET estimated_iq = 125
                        WHERE assessment_id = %s
                    """, (assessment_id,)),
                    "Unsupported IQ reporting prevention",
                )

                expect_rejection(
                    cur,
                    lambda: cur.execute("""
                        UPDATE cognitive_assessment_results
                        SET reporting_status =
                            'provisional_estimate',
                            estimated_iq = 125
                        WHERE assessment_id = %s
                    """, (assessment_id,)),
                    "Missing reference distribution prevention",
                )

                for profile_id in (
                    profile_a, profile_b
                ):
                    cur.execute("""
                        INSERT INTO cognitive_preferences (
                            profile_id
                        )
                        VALUES (%s)
                    """, (profile_id,))

                cur.execute("""
                    SELECT *
                    FROM cognitive_preferences
                    WHERE profile_id = %s
                """, (profile_a,))

                preferences = cur.fetchone()

                require(
                    not preferences[
                        "model_integration_enabled"
                    ]
                    and not preferences[
                        "display_on_home"
                    ]
                    and not preferences[
                        "display_on_cognitive_page"
                    ],
                    "Privacy defaults failed.",
                )

                print(
                    "Private-by-default preferences: PASSED"
                )

                expect_rejection(
                    cur,
                    lambda: cur.execute("""
                        UPDATE cognitive_preferences
                        SET model_integration_enabled = TRUE
                        WHERE profile_id = %s
                    """, (profile_a,)),
                    "Required model consent metadata",
                )

                expect_rejection(
                    cur,
                    lambda: cur.execute("""
                        UPDATE cognitive_preferences
                        SET model_integration_enabled = TRUE,
                            model_assessment_id = %s,
                            model_consent_utc = NOW()
                        WHERE profile_id = %s
                    """, (
                        assessment_id,
                        profile_b,
                    )),
                    "Cross-profile model integration prevention",
                )

                expect_rejection(
                    cur,
                    lambda: cur.execute("""
                        UPDATE cognitive_preferences
                        SET display_on_home = TRUE,
                            display_assessment_id = %s
                        WHERE profile_id = %s
                    """, (
                        assessment_id,
                        profile_b,
                    )),
                    "Cross-profile display prevention",
                )

                cur.execute("""
                    UPDATE cognitive_preferences
                    SET display_on_home = TRUE,
                        display_assessment_id = %s
                    WHERE profile_id = %s
                """, (
                    assessment_id,
                    profile_a,
                ))

                cur.execute("""
                    SELECT *
                    FROM cognitive_preferences
                    WHERE profile_id = %s
                """, (profile_a,))

                preferences = cur.fetchone()

                require(
                    preferences["display_on_home"]
                    and not preferences[
                        "display_on_cognitive_page"
                    ]
                    and not preferences[
                        "model_integration_enabled"
                    ],
                    "Display independence failed.",
                )

                print(
                    "Independent display preferences: PASSED"
                )

                cur.execute("""
                    UPDATE cognitive_preferences
                    SET model_integration_enabled = TRUE,
                        model_assessment_id = %s,
                        model_consent_utc = NOW()
                    WHERE profile_id = %s
                """, (
                    assessment_id,
                    profile_a,
                ))

                print(
                    "Authorized integration record: PASSED"
                )

                cur.execute("""
                    UPDATE cognitive_preferences
                    SET model_integration_enabled = FALSE,
                        model_assessment_id = NULL,
                        model_consent_utc = NULL
                    WHERE profile_id = %s
                """, (profile_a,))

                cur.execute("""
                    SELECT *
                    FROM cognitive_preferences
                    WHERE profile_id = %s
                """, (profile_a,))

                preferences = cur.fetchone()

                require(
                    not preferences[
                        "model_integration_enabled"
                    ]
                    and preferences["display_on_home"],
                    "Integration revocation failed.",
                )

                print(
                    "Independent integration revocation: PASSED"
                )

                expect_rejection(
                    cur,
                    lambda: cur.execute("""
                        DELETE FROM cognitive_assessments
                        WHERE id = %s
                    """, (assessment_id,)),
                    "Referenced assessment deletion protection",
                )

                cur.execute("""
                    INSERT INTO cognitive_administration_events (
                        assessment_id,
                        event_type,
                        event_ms,
                        event_data
                    )
                    VALUES (
                        %s,
                        'assessment_completed',
                        %s,
                        %s
                    )
                """, (
                    assessment_id,
                    session.completed_ms,
                    Jsonb({
                        "test_fixture": True,
                    }),
                ))

                print(
                    "Administration event storage: PASSED"
                )

                cur.execute("""
                    UPDATE cognitive_preferences
                    SET display_on_home = FALSE,
                        display_on_cognitive_page = FALSE,
                        display_assessment_id = NULL
                    WHERE profile_id = %s
                """, (profile_a,))

                cur.execute("""
                    DELETE FROM cognitive_assessments
                    WHERE id = %s
                """, (assessment_id,))

                for table in (
                    "cognitive_assessment_items",
                    "cognitive_responses",
                    "cognitive_administration_events",
                    "cognitive_assessment_results",
                ):
                    cur.execute(
                        f"SELECT COUNT(*) AS total "
                        f"FROM {table} "
                        f"WHERE assessment_id = %s",
                        (assessment_id,),
                    )

                    require(
                        cur.fetchone()["total"] == 0,
                        f"Orphaned records in {table}",
                    )

                print(
                    "Assessment cascade cleanup: PASSED"
                )

                cur.execute("""
                    DELETE FROM profiles
                    WHERE id IN (%s, %s)
                """, (
                    profile_a,
                    profile_b,
                ))

                cur.execute("""
                    SELECT COUNT(*) AS total
                    FROM cognitive_preferences
                    WHERE profile_id IN (%s, %s)
                """, (
                    profile_a,
                    profile_b,
                ))

                require(
                    cur.fetchone()["total"] == 0,
                    "Profile preference cleanup failed.",
                )

                print(
                    "Profile preference cleanup: PASSED"
                )

        finally:
            conn.rollback()

        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS total
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name LIKE 'cognitive_%'
            """)

            require(
                cur.fetchone()["total"] == 0,
                "Migration rollback failed.",
            )

        conn.rollback()

    print("Complete transaction rollback: PASSED")

    print()
    print("ALL COGNITIVE DATABASE INTEGRITY TESTS PASSED")
    print("No permanent database changes made.")


if __name__ == "__main__":
    run_tests()
