
"""
Legacy Phase VII: Persistent assessment integration tests.

Uses temporary local database fixtures.
All fixture changes are rolled back.
"""

from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

from psycopg.types.json import Jsonb

from database import database_connection

import cognitive_storage as storage

from cognitive_session import SessionStateError

from cognitive_timing import (
    memory_exposure_duration,
)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def expect_rejection(operation, exception, label):
    try:
        operation()
    except exception:
        print(label + ": PASSED")
        return

    raise AssertionError(
        f"Invalid operation accepted: {label}"
    )


def create_profile(cur, consent):
    owner_id = uuid4().hex
    profile_id = uuid4().hex

    cur.execute("""
        INSERT INTO users (
            id, email, password_hash, created_utc
        )
        VALUES (%s, %s, %s, NOW())
    """, (
        owner_id,
        f"cognitive-{owner_id}@example.invalid",
        "integration-test-only",
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
        VALUES (%s, %s, %s, NOW(), NOW(), %s)
    """, (
        profile_id,
        owner_id,
        "Cognitive Integration Test",
        Jsonb({
            "consent": {"has_consent": consent},
            "allow_remote_processing": False,
        }),
    ))

    return profile_id, owner_id


class TestConnection:
    """
    Wrap a real connection using savepoints.

    Storage operations retain their normal SQL
    behavior, while the outer test transaction
    prevents permanent fixture changes.
    """

    def __init__(self, connection):
        self.connection = connection

    def cursor(self):
        return self.connection.cursor()

    def commit(self):
        pass


def run_tests():
    with database_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        current_database() AS name,
                        inet_server_addr()::text
                            AS address
                """)

                database = cur.fetchone()

                require(
                    database["address"] in (
                        None, "127.0.0.1", "::1"
                    ),
                    "STOP: Database is not local.",
                )

                cur.execute(
                    "SET LOCAL lock_timeout = '5s'"
                )

                cur.execute(
                    "SET LOCAL statement_timeout = '60s'"
                )

                profile_a, owner_a = create_profile(
                    cur, True
                )

                profile_b, owner_b = create_profile(
                    cur, True
                )

                profile_c, owner_c = create_profile(
                    cur, False
                )

            @contextmanager
            def test_connection():
                with conn.transaction():
                    yield TestConnection(conn)

            clock = [1700000000000]

            with patch.object(
                storage,
                "database_connection",
                test_connection,
            ), patch.object(
                storage,
                "server_time_ms",
                side_effect=lambda cur: clock[0],
            ):
                expect_rejection(
                    lambda: storage.create_assessment(
                        profile_c, owner_c
                    ),
                    storage.CognitiveAccessDenied,
                    "Processing consent enforcement",
                )

                expect_rejection(
                    lambda: storage.create_assessment(
                        profile_a, owner_b
                    ),
                    storage.CognitiveAccessDenied,
                    "Profile ownership enforcement",
                )

                status = storage.create_assessment(
                    profile_a, owner_a
                )

                assessment_id = status["session_id"]

                require(
                    status["state"] == "ready"
                    and status["revision"] == 0,
                    "Incorrect initial state.",
                )

                print(
                    "Persistent assessment creation: PASSED"
                )

                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT COUNT(*) AS total
                        FROM cognitive_assessment_items
                        WHERE assessment_id = %s
                    """, (assessment_id,))

                    require(
                        cur.fetchone()["total"] == 135,
                        "Incorrect stored item count.",
                    )

                print(
                    "135 persistent item snapshots: PASSED"
                )

                restored = storage.assessment_status(
                    profile_a,
                    owner_a,
                    assessment_id,
                )

                require(
                    restored == status,
                    "Restored status mismatch.",
                )

                print(
                    "Database session reconstruction: PASSED"
                )

                expect_rejection(
                    lambda: storage.create_assessment(
                        profile_a, owner_a
                    ),
                    storage.CognitiveConflict,
                    "Active assessment conflict prevention",
                )

                expect_rejection(
                    lambda: storage.assessment_status(
                        profile_b,
                        owner_b,
                        assessment_id,
                    ),
                    storage.CognitiveAccessDenied,
                    "Cross-profile assessment isolation",
                )

                expect_rejection(
                    lambda: storage.assessment_results(
                        profile_a,
                        owner_a,
                        assessment_id,
                    ),
                    storage.CognitiveAccessDenied,
                    "Premature result access prevention",
                )

                def action(name, **kwargs):
                    nonlocal status

                    status = storage.assessment_action(
                        profile_a,
                        owner_a,
                        assessment_id,
                        status["revision"],
                        name,
                        **kwargs,
                    )

                    return status

                def current_question():
                    # Test-only access to the private
                    # server-side scoring key.
                    with conn.cursor() as cur:
                        row, session = (
                            storage.load_locked_session(
                                cur,
                                assessment_id,
                                profile_a,
                                owner_a,
                            )
                        )

                        return session._question()

                action("begin_block")

                require(
                    status["state"] == "respond",
                    "First question not presented.",
                )

                require(
                    "correct_option_id"
                    not in status["question"]
                    and "explanation"
                    not in status["question"],
                    "Private scoring information exposed.",
                )

                print(
                    "Public question isolation: PASSED"
                )

                expect_rejection(
                    lambda: storage.assessment_action(
                        profile_a,
                        owner_a,
                        assessment_id,
                        0,
                        "begin_block",
                    ),
                    storage.CognitiveConflict,
                    "Stale revision rejection",
                )

                revision = status["revision"]

                expect_rejection(
                    lambda: action(
                        "submit_response",
                        question_id="invalid-question",
                        selected_option_id="A",
                    ),
                    SessionStateError,
                    "Invalid question rejection",
                )

                restored = storage.assessment_status(
                    profile_a,
                    owner_a,
                    assessment_id,
                )

                require(
                    restored["revision"] == revision
                    and restored["state"] == "respond",
                    "Rejected action changed stored state.",
                )

                print(
                    "Rejected action rollback: PASSED"
                )

                question = current_question()

                clock[0] += 1000

                action(
                    "submit_response",
                    question_id=question["id"],
                    selected_option_id=question[
                        "correct_option_id"
                    ],
                )

                require(
                    status["state"] == "answered"
                    and "correct" not in status,
                    "Premature answer feedback.",
                )

                expect_rejection(
                    lambda: action(
                        "submit_response",
                        question_id=question["id"],
                        selected_option_id=question[
                            "correct_option_id"
                        ],
                    ),
                    SessionStateError,
                    "Duplicate response rejection",
                )

                memory_count = 0
                speed_count = 0

                while status["state"] != "completed":

                    if status["state"] == "ready":
                        clock[0] += 1000

                        action("begin_block")

                        if status["mode"] == (
                            "timed_queue"
                        ):
                            speed_count += 1

                            deadline = status[
                                "block_deadline_ms"
                            ]

                            question = current_question()

                            clock[0] = deadline - 1

                            action(
                                "submit_response",
                                question_id=question["id"],
                                selected_option_id=question[
                                    "correct_option_id"
                                ],
                            )

                            action("advance")

                            clock[0] = deadline

                            action("tick")

                    elif status["state"] == "memorize":
                        question = current_question()

                        duration = (
                            memory_exposure_duration(
                                question["difficulty"]
                            )
                        )

                        require(
                            "memorize"
                            in status["question"],
                            "Missing memory stimulus.",
                        )

                        require(
                            "options"
                            not in status["question"],
                            "Premature memory options.",
                        )

                        clock[0] += duration

                        action(
                            "finish_memory_exposure",
                            question_id=question["id"],
                        )

                        require(
                            "memorize"
                            not in status["question"],
                            "Memory stimulus leaked.",
                        )

                        memory_count += 1

                    elif status["state"] == "respond":
                        question = current_question()

                        clock[0] += 1000

                        action(
                            "submit_response",
                            question_id=question["id"],
                            selected_option_id=question[
                                "correct_option_id"
                            ],
                        )

                    elif status["state"] == "answered":
                        clock[0] += 100

                        action("advance")

                    else:
                        raise AssertionError(
                            f"Unexpected state: {status}"
                        )

                require(
                    memory_count == 12,
                    "Incorrect memory item count.",
                )

                require(
                    speed_count == 3,
                    "Incorrect speed block count.",
                )

                print(
                    "12 persistent memory items: PASSED"
                )

                print(
                    "Three persistent timed blocks: PASSED"
                )

                results = storage.assessment_results(
                    profile_a,
                    owner_a,
                    assessment_id,
                )

                require(
                    len(results["domain_results"]) == 6,
                    "Incomplete domain results.",
                )

                require(
                    results["reporting_status"]
                    == "provisional_estimate",
                    "Incorrect reporting status.",
                )

                require(
                    results["scoring_version"] == 2,
                    "Incorrect scoring version.",
                )

                require(
                    results["estimated_iq"] is not None
                    and abs(
                        float(results["estimated_iq"])
                        - 132.14
                    ) < 0.01,
                    "Incorrect stored numerical score.",
                )

                require(
                    results["scientifically_validated"]
                    is False,
                    "Unsupported scientific validation.",
                )

                require(
                    results["population_percentile"] is None
                    and results["iq_interval_lower"] is None
                    and results["iq_interval_upper"] is None,
                    "Unsupported population statistics.",
                )

                require(
                    results["reference_distribution_id"]
                    == "legacy-assumed-latent-scale-v2",
                    "Incorrect reference identifier.",
                )

                methodology = results["scoring_methodology"]

                require(
                    methodology["population_normed"] is False
                    and methodology["reference_is_empirical"]
                    is False
                    and methodology["display_score"] == 132,
                    "Incorrect scoring methodology.",
                )

                expected_domains = {
                    "fluid_reasoning",
                    "visual_spatial",
                    "verbal_comprehension",
                    "quantitative_reasoning",
                    "working_memory",
                    "processing_speed",
                }

                require(
                    set(results["domain_results"])
                    == expected_domains,
                    "Incorrect stored cognitive domains.",
                )

                for domain in expected_domains - {
                    "processing_speed"
                }:
                    require(
                        abs(
                            results["domain_results"][domain][
                                "theoretical_scale_score"
                            ] - 132.14
                        ) < 0.01,
                        "Incorrect domain score: " + domain,
                    )

                speed = results["domain_results"][
                    "processing_speed"
                ]

                require(
                    speed["composite_weight"] == 0
                    and speed["theoretical_scale_score"] is None
                    and abs(
                        speed["correct_per_minute"] - 0.5
                    ) < 0.000001,
                    "Incorrect processing speed results.",
                )

                print("Stored numerical score: PASSED")
                print("Scoring version persistence: PASSED")
                print("Five numerical domain scores: PASSED")
                print("Processing speed persistence: PASSED")
                print("Scientific reporting safeguards: PASSED")
                print("Scoring methodology persistence: PASSED")
                print(
                    "Stored theoretical IQ-scale estimate:",
                    results["estimated_iq"],
                )

                print(
                    "Completed result persistence: PASSED"
                )

                with conn.cursor() as cur:
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
                        f"Incorrect outcome totals: {counts}",
                    )

                    exposures = storage.previous_exposures(
                        cur, profile_a
                    )

                    require(
                        len(exposures) == 66,
                        "Incorrect exposure history.",
                    )

                print(
                    "135 persisted response outcomes: PASSED"
                )

                print(
                    "66 actual presentation events: PASSED"
                )

                history = storage.assessment_history(
                    profile_a,
                    owner_a,
                )

                require(
                    len(history) == 1
                    and history[0]["status"]
                    == "completed",
                    "Assessment history mismatch.",
                )

                print(
                    "Completed assessment history: PASSED"
                )

                expect_rejection(
                    lambda: action("advance"),
                    storage.CognitiveConflict,
                    "Completed assessment immutability",
                )

                expect_rejection(
                    lambda: storage.assessment_results(
                        profile_b,
                        owner_b,
                        assessment_id,
                    ),
                    storage.CognitiveAccessDenied,
                    "Cross-profile result isolation",
                )

                second = storage.create_assessment(
                    profile_a,
                    owner_a,
                )

                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT exposure_hash
                        FROM cognitive_assessment_items
                        WHERE assessment_id = %s
                    """, (second["session_id"],))

                    second_exposures = {
                        row["exposure_hash"]
                        for row in cur.fetchall()
                    }

                require(
                    not (
                        exposures & second_exposures
                    ),
                    "Previously exposed items repeated.",
                )

                print(
                    "Cross-session exposure exclusion: PASSED"
                )

                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE profiles
                        SET profile_data = %s
                        WHERE id = %s
                    """, (
                        Jsonb({"consent": {"has_consent": False}}),
                        profile_a,
                    ))

                expect_rejection(
                    lambda: storage.assessment_status(
                        profile_a,
                        owner_a,
                        second["session_id"],
                    ),
                    storage.CognitiveAccessDenied,
                    "Revoked processing consent enforcement",
                )

        finally:
            conn.rollback()

        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) AS total
                FROM users
                WHERE id IN (%s, %s, %s)
            """, (owner_a, owner_b, owner_c))

            require(
                cur.fetchone()["total"] == 0,
                "Temporary test accounts remain.",
            )

        conn.rollback()

    print("Temporary fixture rollback: PASSED")

    print()
    print("ALL COGNITIVE STORAGE LIFECYCLE TESTS PASSED")


if __name__ == "__main__":
    run_tests()
