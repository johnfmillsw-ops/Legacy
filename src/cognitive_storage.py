
"""
Legacy Phase VII: PostgreSQL assessment storage.

Profile ownership, local processing consent,
transactional assessment administration and
persistent question and response records.
"""

from functools import lru_cache
from copy import deepcopy

from psycopg.types.json import Jsonb

from database import database_connection

from cognitive_engine import create_seed

from cognitive_composite_scoring import (
    score_completed_assessment,
    COMPOSITE_SCORING_VERSION,
)

from cognitive_research_bank import (
    build_research_bank,
)

from cognitive_blueprint import (
    assemble_assessment,
)

from cognitive_session import (
    AssessmentSession,
    SESSION_VERSION,
)

from cognitive_session_state import (
    serialize_session,
    restore_session,
    StateIntegrityError,
)

from cognitive_timing import (
    get_timing_protocol,
)

from cognitive_framework import (
    INSTRUMENT_VERSION,
    SCORING_VERSION,
)

ACTIVE_STATES = (
    "ready",
    "memorize",
    "respond",
    "answered",
)


class CognitiveStorageError(RuntimeError):
    pass


class CognitiveAccessDenied(
    CognitiveStorageError
):
    pass


class CognitiveConflict(
    CognitiveStorageError
):
    pass


@lru_cache(maxsize=1)
def research_bank():
    return build_research_bank()


def server_time_ms(cur):
    cur.execute("""
        SELECT FLOOR(
            EXTRACT(EPOCH FROM clock_timestamp())
            * 1000
        )::BIGINT AS now_ms
    """)

    return cur.fetchone()["now_ms"]


def authorize_profile(
    cur,
    profile_id,
    owner_id,
    require_consent=True,
):
    cur.execute("""
        SELECT id, owner_id, profile_data
        FROM profiles
        WHERE id = %s
          AND owner_id = %s
        FOR UPDATE
    """, (
        profile_id,
        owner_id,
    ))

    profile = cur.fetchone()

    if profile is None:
        raise CognitiveAccessDenied(
            "Profile unavailable."
        )

    data = profile["profile_data"]

    if require_consent and (
        not isinstance(data, dict)
        or not isinstance(data.get("consent"), dict)
        or data["consent"].get("has_consent") is not True
    ):
        raise CognitiveAccessDenied(
            "Profile processing consent required."
        )

    return profile


def record_event(
    cur,
    assessment_id,
    event_type,
    event_ms,
    event_data=None,
    block_index=None,
    item_index=None,
):
    cur.execute("""
        INSERT INTO cognitive_administration_events (
            assessment_id,
            event_type,
            block_index,
            item_index,
            event_ms,
            event_data
        )
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        assessment_id,
        event_type,
        block_index,
        item_index,
        event_ms,
        Jsonb(event_data or {}),
    ))


def previous_exposures(cur, profile_id):
    cur.execute("""
        SELECT DISTINCT
            e.event_data ->> 'exposure_hash'
                AS exposure_hash
        FROM cognitive_administration_events e
        JOIN cognitive_assessments a
          ON a.id = e.assessment_id
        WHERE a.profile_id = %s
          AND e.event_type = 'item_presented'
    """, (profile_id,))

    return {
        row["exposure_hash"]
        for row in cur.fetchall()
        if row["exposure_hash"]
    }


def insert_items(cur, session):
    rows = []

    for block_index, block in enumerate(
        session.blocks
    ):
        for item_index, record in enumerate(
            block["items"]
        ):
            question = record[
                "question_snapshot"
            ]

            rows.append((
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

    cur.executemany("""
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
    """, rows)


def create_assessment(
    profile_id,
    owner_id,
):
    bank = research_bank()

    with database_connection() as conn:
        with conn.cursor() as cur:
            authorize_profile(
                cur, profile_id, owner_id
            )

            cur.execute("""
                SELECT id
                FROM cognitive_assessments
                WHERE profile_id = %s
                  AND status IN (
                      'ready',
                      'memorize',
                      'respond',
                      'answered'
                  )
            """, (profile_id,))

            if cur.fetchone() is not None:
                raise CognitiveConflict(
                    "An active assessment already exists."
                )

            exclusions = previous_exposures(
                cur, profile_id
            )

            form = assemble_assessment(
                bank,
                create_seed(),
                excluded_exposures=exclusions,
            )

            now = server_time_ms(cur)

            session = AssessmentSession(
                form, bank, now
            )

            snapshot = serialize_session(
                session
            )

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
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
            """, (
                session.session_id,
                profile_id,
                INSTRUMENT_VERSION,
                SESSION_VERSION,
                form["manifest"][
                    "blueprint_version"
                ],
                form["manifest"]["bank_id"],
                form["form_id"],
                Jsonb(form["manifest"]),
                Jsonb(get_timing_protocol()),
                session.state,
                Jsonb(snapshot),
            ))

            insert_items(cur, session)

            record_event(
                cur,
                session.session_id,
                "assessment_created",
                now,
            )

            result = {
                **session.status(),
                "revision": 0,
            }

        conn.commit()

    return result


def load_locked_session(
    cur,
    assessment_id,
    profile_id,
    owner_id,
):
    authorize_profile(
        cur, profile_id, owner_id
    )

    cur.execute("""
        SELECT *
        FROM cognitive_assessments
        WHERE id = %s
          AND profile_id = %s
        FOR UPDATE
    """, (
        assessment_id,
        profile_id,
    ))

    row = cur.fetchone()

    if row is None:
        raise CognitiveAccessDenied(
            "Assessment unavailable."
        )

    if row["status"] == "abandoned":
        raise CognitiveConflict(
            "Assessment was abandoned."
        )

    manifest = row["form_manifest"]

    blocks = []

    for section in manifest["sections"]:
        for block in section["blocks"]:
            blocks.append({
                "domain": section["domain"],
                "family": block["family"],
                "mode": block["mode"],
                "duration_ms":
                    block["duration_ms"],
                "items": [],
                "item_count":
                    len(block["item_ids"]),
            })

    cur.execute("""
        SELECT
            block_index,
            item_index,
            item_record
        FROM cognitive_assessment_items
        WHERE assessment_id = %s
        ORDER BY block_index, item_index
    """, (assessment_id,))

    for item in cur.fetchall():
        block = blocks[item["block_index"]]

        if item["item_index"] != len(
            block["items"]
        ):
            raise StateIntegrityError(
                "Stored item order mismatch."
            )

        block["items"].append(
            item["item_record"]
        )

    session = restore_session(
        row["session_state"],
        blocks,
    )

    if (
        session.session_id != assessment_id
        or session.form_id != row["form_id"]
        or session.state != row["status"]
    ):
        raise StateIntegrityError(
            "Stored assessment identity mismatch."
        )

    return row, session


def persist_response(
    cur,
    assessment_id,
    response,
):
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


def persist_changes(
    cur,
    row,
    session,
    before,
    action,
):
    assessment_id = session.session_id

    now = session.last_event_ms

    old = before["payload"]["state"]

    if action == "begin_block":
        record_event(
            cur,
            assessment_id,
            "block_started",
            now,
            {
                "deadline_ms":
                    session.block_deadline_ms,
            },
            old["block_index"],
        )

    if action == "finish_memory_exposure":
        record_event(
            cur,
            assessment_id,
            "memory_exposure_completed",
            now,
            block_index=old["block_index"],
            item_index=old["item_index"],
        )

    for exposure in session.exposures[
        len(old["exposures"]):
    ]:
        record_event(
            cur,
            assessment_id,
            "item_presented",
            exposure["presented_ms"],
            exposure,
            session.block_index,
            session.item_index,
        )

    for response in session.responses[
        len(old["responses"]):
    ]:
        persist_response(
            cur,
            assessment_id,
            response,
        )

        record_event(
            cur,
            assessment_id,
            "response_recorded",
            response["recorded_ms"],
            {
                "outcome": response["outcome"],
                "question_id":
                    response["question_id"],
            },
            response["block_index"],
            response["item_index"],
        )

    for index in range(
        len(old["block_results"]),
        len(session.block_results),
    ):
        block_result = (
            session.block_results[index]
        )

        record_event(
            cur,
            assessment_id,
            "block_completed",
            block_result["closed_ms"],
            block_result,
            index,
        )

    for interruption in session.interruptions[
        len(old["interruptions"]):
    ]:
        record_event(
            cur,
            assessment_id,
            "assessment_interrupted",
            interruption["recorded_ms"],
            interruption,
        )

    cur.execute("""
        UPDATE cognitive_assessments
        SET session_state = %s,
            status = %s,
            revision = revision + 1,
            updated_utc = NOW(),
            completed_utc = CASE
                WHEN %s = 'completed'
                THEN NOW()
                ELSE NULL
            END
        WHERE id = %s
          AND revision = %s
    """, (
        Jsonb(serialize_session(session)),
        session.state,
        session.state,
        assessment_id,
        row["revision"],
    ))

    if cur.rowcount != 1:
        raise CognitiveConflict(
            "Assessment revision changed."
        )

    if (
        session.state == "completed"
        and old["state"] != "completed"
    ):
        results = session.results()

        scored = score_completed_assessment(
            session
        )

        if (
            scored["assessment_id"] != assessment_id
            or scored["form_id"] != session.form_id
            or scored["scientifically_validated"] is not False
            or scored["population_normed"] is not False
            or scored["population_percentile"] is not None
            or scored["validated_iq_interval"] is not None
        ):
            raise StateIntegrityError(
                "Invalid cognitive scoring result."
            )

        methodology = {
            **scored["scoring_methodology"],
            "scoring_model_id":
                scored["scoring_model_id"],
            "session_version":
                SESSION_VERSION,
            "instrument_version":
                INSTRUMENT_VERSION,
            "reporting_label":
                "Theoretical IQ-scale estimate",
            "reference_type":
                "assumed_latent_scale",
            "reference_is_empirical":
                False,
            "population_normed":
                False,
            "scientifically_validated":
                False,
            "composite_theta":
                scored["composite_theta"],
            "display_score":
                scored["display_score"],
            "raw_domain_results":
                results["domains"],
            "block_results":
                results["block_results"],
            "duration_ms":
                results["duration_ms"],
            "limitations": [
                "Item difficulties are theoretical.",
                "Population norms are unavailable.",
                "Guessing is not explicitly modeled.",
                "Processing speed is reported separately.",
                "The assessment has a finite measurement ceiling.",
                "The score is not a clinically validated IQ.",
            ],
        }

        cur.execute("""
            INSERT INTO cognitive_assessment_results (
                assessment_id,
                profile_id,
                scoring_version,
                reporting_status,
                domain_results,
                estimated_iq,
                iq_interval_lower,
                iq_interval_upper,
                population_percentile,
                scoring_methodology,
                reference_distribution_id,
                scientifically_validated
            )
            VALUES (
                %s, %s, %s,
                'provisional_estimate',
                %s, %s,
                NULL, NULL, NULL,
                %s, %s, FALSE
            )
        """, (
            assessment_id,
            row["profile_id"],
            COMPOSITE_SCORING_VERSION,
            Jsonb(scored["domain_results"]),
            scored["theoretical_iq_scale_score"],
            Jsonb(methodology),
            "legacy-assumed-latent-scale-v2",
        ))

        record_event(
            cur,
            assessment_id,
            "assessment_completed",
            now,
        )

    return row["revision"] + 1


def assessment_action(
    profile_id,
    owner_id,
    assessment_id,
    expected_revision,
    action,
    question_id=None,
    selected_option_id=None,
    interruption_reason=None,
):
    allowed = {
        "begin_block",
        "finish_memory_exposure",
        "submit_response",
        "advance",
        "tick",
        "interrupt",
    }

    if action not in allowed:
        raise ValueError(
            "Unknown assessment action."
        )

    if (
        type(expected_revision) is not int
        or expected_revision < 0
    ):
        raise ValueError(
            "Invalid assessment revision."
        )

    with database_connection() as conn:
        with conn.cursor() as cur:
            row, session = load_locked_session(
                cur,
                assessment_id,
                profile_id,
                owner_id,
            )

            if (
                row["revision"]
                != expected_revision
            ):
                raise CognitiveConflict(
                    "Assessment state changed."
                )

            if session.state not in ACTIVE_STATES:
                raise CognitiveConflict(
                    "Assessment is no longer active."
                )

            before = serialize_session(
                session
            )

            now = server_time_ms(cur)

            if action == "begin_block":
                payload = session.begin_block(
                    now
                )

            elif action == (
                "finish_memory_exposure"
            ):
                payload = (
                    session.finish_memory_exposure(
                        question_id,
                        now,
                    )
                )

            elif action == "submit_response":
                payload = session.submit_response(
                    question_id,
                    selected_option_id,
                    now,
                )

            elif action == "advance":
                payload = session.advance(
                    now
                )

            elif action == "tick":
                payload = session.tick(
                    now
                )

            else:
                payload = session.interrupt(
                    interruption_reason,
                    now,
                )

            revision = persist_changes(
                cur,
                row,
                session,
                before,
                action,
            )

            result = {
                **payload,
                "revision": revision,
                "server_now_ms": server_time_ms(cur),
            }

        conn.commit()

    return result


def assessment_status(
    profile_id,
    owner_id,
    assessment_id,
):
    with database_connection() as conn:
        with conn.cursor() as cur:
            row, session = load_locked_session(
                cur,
                assessment_id,
                profile_id,
                owner_id,
            )

            result = {
                **session.status(),
                "revision": row["revision"],
            }

        conn.commit()

    return result


def assessment_history(
    profile_id,
    owner_id,
):
    with database_connection() as conn:
        with conn.cursor() as cur:
            authorize_profile(
                cur,
                profile_id,
                owner_id,
            )

            cur.execute("""
                SELECT
                    a.id AS assessment_id,
                    a.status,
                    a.instrument_version,
                    a.created_utc,
                    a.completed_utc,
                    r.reporting_status,
                    r.estimated_iq,
                    r.scientifically_validated
                FROM cognitive_assessments a
                LEFT JOIN cognitive_assessment_results r
                  ON r.assessment_id = a.id
                WHERE a.profile_id = %s
                ORDER BY a.created_utc DESC
            """, (profile_id,))

            result = [
                dict(row)
                for row in cur.fetchall()
            ]

        conn.commit()

    return result


def assessment_results(
    profile_id,
    owner_id,
    assessment_id,
):
    with database_connection() as conn:
        with conn.cursor() as cur:
            authorize_profile(
                cur,
                profile_id,
                owner_id,
            )

            cur.execute("""
                SELECT
                    r.assessment_id,
                    r.scoring_version,
                    r.reporting_status,
                    r.domain_results,
                    r.estimated_iq,
                    r.iq_interval_lower,
                    r.iq_interval_upper,
                    r.population_percentile,
                    r.scoring_methodology,
                    r.reference_distribution_id,
                    r.scientifically_validated,
                    r.created_utc
                FROM cognitive_assessment_results r
                JOIN cognitive_assessments a
                  ON a.id = r.assessment_id
                WHERE r.assessment_id = %s
                  AND r.profile_id = %s
                  AND a.status = 'completed'
            """, (
                assessment_id,
                profile_id,
            ))

            row = cur.fetchone()

            if row is None:
                raise CognitiveAccessDenied(
                    "Completed results unavailable."
                )

            result = dict(row)

        conn.commit()

    return result
