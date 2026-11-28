"""
Legacy Phase VII: Cognitive assessment privacy controls.

Display permissions and AI model integration consent
are independent and disabled by default.
"""

from database import database_connection

from cognitive_storage import (
    authorize_profile,
    CognitiveAccessDenied,
    CognitiveConflict,
)


DEFAULT_PREFERENCES = {
    "model_integration_enabled": False,
    "model_assessment_id": None,
    "model_consent_utc": None,
    "display_on_home": False,
    "display_on_cognitive_page": False,
    "display_assessment_id": None,
}


def read_preferences(cur, profile_id):

    cur.execute("""
        SELECT
            model_integration_enabled,
            model_assessment_id,
            model_consent_utc,
            display_on_home,
            display_on_cognitive_page,
            display_assessment_id
        FROM cognitive_preferences
        WHERE profile_id = %s
    """, (profile_id,))

    row = cur.fetchone()

    if row is None:
        return dict(DEFAULT_PREFERENCES)

    return dict(row)


def get_preferences(profile_id, owner_id):

    with database_connection() as conn:
        with conn.cursor() as cur:

            authorize_profile(
                cur, profile_id, owner_id
            )

            result = read_preferences(
                cur, profile_id
            )

        conn.commit()

    return result


def require_completed_result(
    cur,
    profile_id,
    assessment_id,
):

    if (
        not isinstance(assessment_id, str)
        or not assessment_id.strip()
    ):
        raise ValueError(
            "A completed assessment is required."
        )

    cur.execute("""
        SELECT r.assessment_id
        FROM cognitive_assessment_results r
        JOIN cognitive_assessments a
          ON a.id = r.assessment_id
         AND a.profile_id = r.profile_id
        WHERE r.assessment_id = %s
          AND r.profile_id = %s
          AND a.status = 'completed'
    """, (
        assessment_id,
        profile_id,
    ))

    if cur.fetchone() is None:
        raise CognitiveAccessDenied(
            "Completed assessment unavailable."
        )


def set_model_integration(
    profile_id,
    owner_id,
    enabled,
    assessment_id=None,
):

    if type(enabled) is not bool:
        raise ValueError(
            "Explicit consent is required."
        )

    with database_connection() as conn:
        with conn.cursor() as cur:

            authorize_profile(
                cur, profile_id, owner_id, require_consent=enabled
            )

            if enabled:
                require_completed_result(
                    cur,
                    profile_id,
                    assessment_id,
                )
            else:
                assessment_id = None

            cur.execute("""
                INSERT INTO cognitive_preferences (
                    profile_id,
                    model_integration_enabled,
                    model_assessment_id,
                    model_consent_utc
                )
                VALUES (
                    %s, %s, %s,
                    CASE WHEN %s
                         THEN NOW()
                         ELSE NULL
                    END
                )
                ON CONFLICT (profile_id)
                DO UPDATE SET
                    model_integration_enabled =
                        EXCLUDED.model_integration_enabled,
                    model_assessment_id =
                        EXCLUDED.model_assessment_id,
                    model_consent_utc =
                        EXCLUDED.model_consent_utc,
                    updated_utc = NOW()
            """, (
                profile_id,
                enabled,
                assessment_id,
                enabled,
            ))

            result = read_preferences(
                cur, profile_id
            )

        conn.commit()

    return result


def set_display_preferences(
    profile_id,
    owner_id,
    display_on_home,
    display_on_cognitive_page,
    assessment_id=None,
):

    if (
        type(display_on_home) is not bool
        or type(display_on_cognitive_page) is not bool
    ):
        raise ValueError(
            "Display settings must be boolean."
        )

    with database_connection() as conn:
        with conn.cursor() as cur:

            authorize_profile(
                cur, profile_id, owner_id,
                require_consent=display_on_home or display_on_cognitive_page,
            )

            if (
                display_on_home
                or display_on_cognitive_page
            ):
                require_completed_result(
                    cur,
                    profile_id,
                    assessment_id,
                )
            else:
                assessment_id = None

            cur.execute("""
                INSERT INTO cognitive_preferences (
                    profile_id,
                    display_on_home,
                    display_on_cognitive_page,
                    display_assessment_id
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (profile_id)
                DO UPDATE SET
                    display_on_home =
                        EXCLUDED.display_on_home,
                    display_on_cognitive_page =
                        EXCLUDED.display_on_cognitive_page,
                    display_assessment_id =
                        EXCLUDED.display_assessment_id,
                    updated_utc = NOW()
            """, (
                profile_id,
                display_on_home,
                display_on_cognitive_page,
                assessment_id,
            ))

            result = read_preferences(
                cur, profile_id
            )

        conn.commit()

    return result


def selected_result(
    profile_id,
    owner_id,
    purpose,
):

    allowed = {
        "model": (
            "model_integration_enabled",
            "model_assessment_id",
        ),
        "home": (
            "display_on_home",
            "display_assessment_id",
        ),
        "cognitive_page": (
            "display_on_cognitive_page",
            "display_assessment_id",
        ),
    }

    if purpose not in allowed:
        raise ValueError(
            "Unknown cognitive result purpose."
        )

    enabled_key, assessment_key = allowed[purpose]

    with database_connection() as conn:
        with conn.cursor() as cur:

            profile = authorize_profile(
                cur, profile_id, owner_id
            )

            if purpose == "model" and profile["profile_data"]["consent"].get("allow_remote_processing") is not True:
                return None

            preferences = read_preferences(
                cur, profile_id
            )

            if preferences[enabled_key] is not True:
                return None

            assessment_id = preferences[
                assessment_key
            ]

            if purpose == "model":
                if preferences["model_consent_utc"] is None:
                    return None

            cur.execute("""
                SELECT
                    r.assessment_id,
                    r.scoring_version,
                    r.reporting_status,
                    r.domain_results,
                    r.estimated_iq,
                    r.scoring_methodology,
                    r.scientifically_validated,
                    a.completed_utc
                FROM cognitive_assessment_results r
                JOIN cognitive_assessments a
                  ON a.id = r.assessment_id
                 AND a.profile_id = r.profile_id
                WHERE r.assessment_id = %s
                  AND r.profile_id = %s
                  AND a.status = 'completed'
            """, (
                assessment_id,
                profile_id,
            ))

            row = cur.fetchone()

            result = (
                dict(row)
                if row is not None
                else None
            )

        conn.commit()

    return result


def delete_assessment(
    profile_id,
    owner_id,
    assessment_id,
):

    with database_connection() as conn:
        with conn.cursor() as cur:

            # Deletion remains available even if
            # processing consent has been revoked.

            cur.execute("""
                SELECT id
                FROM profiles
                WHERE id = %s
                  AND owner_id = %s
                FOR UPDATE
            """, (
                profile_id,
                owner_id,
            ))

            if cur.fetchone() is None:
                raise CognitiveAccessDenied(
                    "Profile unavailable."
                )

            cur.execute("""
                SELECT status
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

            if row["status"] not in (
                "completed",
                "interrupted",
                "abandoned",
            ):
                raise CognitiveConflict(
                    "End the active assessment before deletion."
                )

            cur.execute("""
                UPDATE cognitive_preferences
                SET model_integration_enabled = FALSE,
                    model_assessment_id = NULL,
                    model_consent_utc = NULL,
                    updated_utc = NOW()
                WHERE profile_id = %s
                  AND model_assessment_id = %s
            """, (
                profile_id,
                assessment_id,
            ))

            cur.execute("""
                UPDATE cognitive_preferences
                SET display_on_home = FALSE,
                    display_on_cognitive_page = FALSE,
                    display_assessment_id = NULL,
                    updated_utc = NOW()
                WHERE profile_id = %s
                  AND display_assessment_id = %s
            """, (
                profile_id,
                assessment_id,
            ))

            cur.execute("""
                DELETE FROM cognitive_assessments
                WHERE id = %s
                  AND profile_id = %s
            """, (
                assessment_id,
                profile_id,
            ))

            if cur.rowcount != 1:
                raise CognitiveConflict(
                    "Assessment deletion failed."
                )

        conn.commit()

    return {
        "deleted": True,
        "assessment_id": assessment_id,
    }
