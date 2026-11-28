from uuid import uuid4

from psycopg.types.json import Jsonb

from database import database_connection

from personality_baseline import (
    INSTRUMENT_ID,
    INSTRUMENT_VERSION,
    validate_responses,
    score_assessment,
)


def authorize_profile(cur, profile_id, owner_id):
    cur.execute(
        """
        SELECT id, profile_data FROM profiles
        WHERE id = %s AND owner_id = %s
        FOR UPDATE
        """,
        (profile_id, owner_id),
    )

    profile = cur.fetchone()

    if profile is None:
        raise PermissionError("Profile access denied.")

    data = profile["profile_data"] or {}
    consent = data.get("consent") or {}

    if consent.get("has_consent") is not True:
        raise PermissionError(
            "Local processing consent required."
        )


def get_or_create_draft(profile_id, owner_id):
    with database_connection() as conn:
        with conn.cursor() as cur:
            authorize_profile(cur, profile_id, owner_id)

            cur.execute(
                """
                SELECT *
                FROM personality_baseline_assessments
                WHERE profile_id = %s
                  AND instrument_id = %s
                  AND instrument_version = %s
                  AND status = 'draft'
                """,
                (
                    profile_id,
                    INSTRUMENT_ID,
                    INSTRUMENT_VERSION,
                ),
            )

            draft = cur.fetchone()

            if draft:
                return draft

            cur.execute(
                """
                INSERT INTO personality_baseline_assessments (
                    id,
                    profile_id,
                    instrument_id,
                    instrument_version
                )
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (
                    uuid4().hex,
                    profile_id,
                    INSTRUMENT_ID,
                    INSTRUMENT_VERSION,
                ),
            )

            return cur.fetchone()


def load_draft(cur, profile_id, assessment_id):
    cur.execute(
        """
        SELECT *
        FROM personality_baseline_assessments
        WHERE id = %s
          AND profile_id = %s
          AND instrument_id = %s
          AND instrument_version = %s
          AND status = 'draft'
        FOR UPDATE
        """,
        (
            assessment_id,
            profile_id,
            INSTRUMENT_ID,
            INSTRUMENT_VERSION,
        ),
    )

    draft = cur.fetchone()

    if draft is None:
        raise ValueError(
            "Assessment unavailable or already completed."
        )

    return draft


def save_draft(
    profile_id,
    owner_id,
    assessment_id,
    responses,
):
    validate_responses(responses, complete=False)

    with database_connection() as conn:
        with conn.cursor() as cur:
            authorize_profile(cur, profile_id, owner_id)

            draft = load_draft(
                cur, profile_id, assessment_id
            )

            merged = dict(draft["responses"])
            merged.update(responses)

            validate_responses(merged, complete=False)

            cur.execute(
                """
                UPDATE personality_baseline_assessments
                SET responses = %s,
                    updated_utc = NOW()
                WHERE id = %s
                  AND profile_id = %s
                  AND status = 'draft'
                RETURNING *
                """,
                (
                    Jsonb(merged),
                    assessment_id,
                    profile_id,
                ),
            )

            return cur.fetchone()


def complete_assessment(
    profile_id,
    owner_id,
    assessment_id,
):
    with database_connection() as conn:
        with conn.cursor() as cur:
            authorize_profile(cur, profile_id, owner_id)

            draft = load_draft(
                cur, profile_id, assessment_id
            )

            responses = draft["responses"]

            validate_responses(responses, complete=True)

            result = score_assessment(responses)

            metadata = {
                key: value
                for key, value in result.items()
                if key not in ("raw_scores", "scores")
            }

            cur.execute(
                """
                UPDATE personality_baseline_assessments
                SET status = 'completed',
                    raw_scores = %s,
                    normalized_scores = %s,
                    instrument_metadata = %s,
                    completed_utc = NOW(),
                    updated_utc = NOW()
                WHERE id = %s
                  AND profile_id = %s
                  AND status = 'draft'
                RETURNING *
                """,
                (
                    Jsonb(result["raw_scores"]),
                    Jsonb(result["scores"]),
                    Jsonb(metadata),
                    assessment_id,
                    profile_id,
                ),
            )

            return cur.fetchone()


def get_assessment_history(profile_id, owner_id):
    with database_connection() as conn:
        with conn.cursor() as cur:
            authorize_profile(cur, profile_id, owner_id)

            cur.execute(
                """
                SELECT *
                FROM personality_baseline_assessments
                WHERE profile_id = %s
                  AND status = 'completed'
                ORDER BY completed_utc DESC, id DESC
                """,
                (profile_id,),
            )

            return cur.fetchall()


def get_latest_baseline(profile_id, owner_id):
    with database_connection() as conn:
        with conn.cursor() as cur:
            authorize_profile(cur, profile_id, owner_id)

            cur.execute(
                """
                SELECT *
                FROM personality_baseline_assessments
                WHERE profile_id = %s
                  AND instrument_id = %s
                  AND instrument_version = %s
                  AND status = 'completed'
                ORDER BY completed_utc DESC, id DESC
                LIMIT 1
                """,
                (
                    profile_id,
                    INSTRUMENT_ID,
                    INSTRUMENT_VERSION,
                ),
            )

            return cur.fetchone()
