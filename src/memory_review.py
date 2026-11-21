
from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import login_required, current_user

from database import database_connection


memory_review_bp = Blueprint(
    "memory_review",
    __name__,
)


def current_profile():
    profile_id = session.get("profile_id")

    if not profile_id:
        return None

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, display_name
                FROM profiles
                WHERE id = %s
                  AND owner_id = %s
                """,
                (profile_id, current_user.id),
            )

            return cursor.fetchone()


@memory_review_bp.route(
    "/memories",
    methods=["GET"],
)
@login_required
def review_memories():
    profile = current_profile()

    if profile is None:
        return redirect(url_for("index"))

    selected_status = request.args.get(
        "status",
        "pending",
    )

    if selected_status not in {
        "pending",
        "approved",
        "rejected",
    }:
        selected_status = "pending"

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    m.id,
                    m.category,
                    m.memory_text,
                    m.source_excerpt,
                    m.interpretation_type,
                    m.status,
                    m.event_date,
                    m.created_utc,
                    d.title AS document_title,
                    c.chunk_index + 1 AS passage_number,
                    c.chunk_text AS original_passage
                FROM structured_memories m
                LEFT JOIN knowledge_documents d
                    ON d.id = m.source_document_id
                   AND d.profile_id = m.profile_id
                LEFT JOIN knowledge_chunks c
                    ON c.id = m.source_chunk_id
                   AND c.document_id = d.id
                WHERE m.profile_id = %s
                  AND m.status = %s
                ORDER BY
                    m.created_utc ASC,
                    m.id ASC
                LIMIT 200
                """,
                (
                    profile["id"],
                    selected_status,
                ),
            )

            memories = cursor.fetchall()

            cursor.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM structured_memories
                WHERE profile_id = %s
                GROUP BY status
                """,
                (profile["id"],),
            )

            counts = {
                "pending": 0,
                "approved": 0,
                "rejected": 0,
            }

            for row in cursor.fetchall():
                counts[row["status"]] = row["total"]

    return render_template(
        "memory_review.html",
        subject=profile["display_name"],
        memories=memories,
        counts=counts,
        selected_status=selected_status,
    )


@memory_review_bp.route(
    "/memories/<memory_id>/review",
    methods=["POST"],
)
@login_required
def review_memory(memory_id):
    profile = current_profile()

    if profile is None:
        abort(403)

    action = (
        request.form.get("action") or ""
    ).strip().lower()

    if action not in {
        "approve",
        "reject",
    }:
        abort(400)

    memory_text = (
        request.form.get("memory_text") or ""
    ).strip()

    if action == "approve":
        if not memory_text:
            flash("Memory text cannot be empty.")
            return redirect(
                url_for("memory_review.review_memories")
            )

        if len(memory_text) > 1000:
            flash(
                "Memory text must be 1,000 "
                "characters or fewer."
            )
            return redirect(
                url_for("memory_review.review_memories")
            )

    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT m.id, m.status
                FROM structured_memories m
                JOIN profiles p
                    ON p.id = m.profile_id
                WHERE m.id = %s
                  AND m.profile_id = %s
                  AND p.owner_id = %s
                FOR UPDATE OF m
                """,
                (
                    memory_id,
                    profile["id"],
                    current_user.id,
                ),
            )

            memory = cursor.fetchone()

            if memory is None:
                abort(404)

            if memory["status"] != "pending":
                flash(
                    "This memory has already "
                    "been reviewed."
                )
                return redirect(
                    url_for(
                        "memory_review.review_memories"
                    )
                )

            if action == "approve":
                cursor.execute(
                    """
                    UPDATE structured_memories
                    SET
                        memory_text = %s,
                        status = 'approved',
                        reviewed_utc = NOW(),
                        updated_utc = NOW()
                    WHERE id = %s
                      AND profile_id = %s
                      AND status = 'pending'
                    """,
                    (
                        memory_text,
                        memory_id,
                        profile["id"],
                    ),
                )

                flash("Memory approved.")

            else:
                cursor.execute(
                    """
                    UPDATE structured_memories
                    SET
                        status = 'rejected',
                        reviewed_utc = NOW(),
                        updated_utc = NOW()
                    WHERE id = %s
                      AND profile_id = %s
                      AND status = 'pending'
                    """,
                    (
                        memory_id,
                        profile["id"],
                    ),
                )

                flash("Memory rejected.")

    return redirect(
        url_for(
            "memory_review.review_memories"
        )
    )
