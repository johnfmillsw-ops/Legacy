from uuid import uuid4

from flask import (
    Blueprint,
    abort,
    jsonify,
    render_template,
    request,
    url_for,
)

from flask_login import login_required
from psycopg.types.json import Jsonb

from database import database_connection
from archive_gallery import authorized_profile


connections_bp = Blueprint(
    "archive_connections",
    __name__,
    url_prefix="/archive/connections",
)

from archive_text import archive_plain_text

connections_bp.app_template_filter(
    "archive_plain_text"
)(archive_plain_text)


TARGET_TYPES = {
    "memory": "Memory",
    "journal": "Journal entry",
    "document": "Historical document",
    "voice": "Oral history",
}


def require_profile():

    profile_id = authorized_profile()

    if not profile_id:
        abort(403)

    return profile_id


def get_record(cursor, profile_id, target_type, target_id):

    if target_type == "memory":

        sql = """
            SELECT
                id,
                category AS title,
                memory_text AS content,
                event_date,
                source_excerpt
            FROM structured_memories
            WHERE profile_id = %s
              AND id = %s
              AND status <> 'rejected'
        """

    elif target_type == "journal":

        sql = """
            SELECT
                e.id,
                e.title,
                e.content,
                e.entry_date::text AS event_date,
                NULL::text AS source_excerpt
            FROM journal_entries e
            JOIN journals j ON j.id = e.journal_id
            WHERE j.profile_id = %s
              AND e.id = %s
        """

    elif target_type == "voice":

        sql = """
            SELECT
                id,
                title,
                COALESCE(
                    NULLIF(transcript, ''),
                    original_transcript,
                    ''
                ) AS content,
                NULL::text AS event_date,
                original_transcript AS source_excerpt,
                created_utc,
                duration_seconds,
                status
            FROM voice_journals
            WHERE profile_id = %s
              AND id = %s
        """

    elif target_type == "document":

        sql = """
            SELECT
                id,
                title,
                original_text AS content,
                NULL::text AS event_date,
                NULL::text AS source_excerpt
            FROM knowledge_documents
            WHERE profile_id = %s
              AND id = %s
        """

    else:

        return None

    cursor.execute(sql, (profile_id, target_id))

    return cursor.fetchone()


def get_photo(cursor, profile_id, asset_id):

    cursor.execute(
        """
        SELECT
            id,
            title,
            description,
            event_date,
            location,
            people
        FROM archive_assets
        WHERE profile_id = %s
          AND id = %s
        """,
        (profile_id, asset_id),
    )

    return cursor.fetchone()


@connections_bp.get("/record/<target_type>/<target_id>")
@login_required
def record(target_type, target_id):

    profile_id = require_profile()

    with database_connection() as connection:
        with connection.cursor() as cursor:

            historical_record = get_record(
                cursor,
                profile_id,
                target_type,
                target_id,
            )

            if not historical_record:
                abort(404)

            cursor.execute(
                """
                SELECT
                    a.id,
                    a.title,
                    a.description,
                    a.event_date,
                    r.id AS relationship_id
                FROM archive_relationships r
                JOIN archive_assets a
                    ON a.id = r.asset_id
                    AND a.profile_id = r.profile_id
                WHERE r.profile_id = %s
                  AND r.target_type = %s
                  AND r.target_id = %s
                  AND r.status = 'confirmed'
                ORDER BY a.event_date, a.created_utc
                """,
                (profile_id, target_type, target_id),
            )

            photographs = cursor.fetchall()

    return render_template(
        "archive_connected_record.html",
        record=historical_record,
        target_type=target_type,
        target_label=TARGET_TYPES[target_type],
        photographs=photographs,
    )


@connections_bp.get("/photo/<asset_id>")
@login_required
def photograph(asset_id):

    profile_id = require_profile()

    with database_connection() as connection:
        with connection.cursor() as cursor:

            photo = get_photo(
                cursor,
                profile_id,
                asset_id,
            )

            if not photo:
                abort(404)

            cursor.execute(
                """
                SELECT
                    id,
                    target_type,
                    target_id,
                    status
                FROM archive_relationships
                WHERE profile_id = %s
                  AND asset_id = %s
                  AND status = 'confirmed'
                ORDER BY created_utc
                """,
                (profile_id, asset_id),
            )

            relationships = cursor.fetchall()

            records = []

            for relationship in relationships:

                target = get_record(
                    cursor,
                    profile_id,
                    relationship["target_type"],
                    relationship["target_id"],
                )

                if target:

                    records.append({
                        **relationship,
                        "title": target["title"],
                        "preview": (
                            target["content"] or ""
                        )[:300],
                        "event_date": target["event_date"],
                    })

    return render_template(
        "archive_connected_photo.html",
        photo=photo,
        records=records,
        target_types=TARGET_TYPES,
    )


@connections_bp.get("/search")
@login_required
def search():

    profile_id = require_profile()

    query = request.args.get("q", "").strip()[:200]
    target_type = request.args.get("type", "memory")

    if target_type not in TARGET_TYPES:
        return jsonify({"error": "Invalid record type."}), 400

    if len(query) < 2:
        return jsonify({"records": []})

    # Escape LIKE wildcard characters.
    query = (
        query.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )

    pattern = "%" + query + "%"

    if target_type == "memory":

        sql = """
            SELECT
                id,
                category AS title,
                event_date,
                LEFT(memory_text, 280) AS preview
            FROM structured_memories
            WHERE profile_id = %s
              AND status <> 'rejected'
              AND (
                  memory_text ILIKE %s
                  OR category ILIKE %s
              )
            ORDER BY created_utc DESC
            LIMIT 25
        """

    elif target_type == "journal":

        sql = """
            SELECT
                e.id,
                e.title,
                e.entry_date::text AS event_date,
                LEFT(e.content, 280) AS preview
            FROM journal_entries e
            JOIN journals j ON j.id = e.journal_id
            WHERE j.profile_id = %s
              AND (
                  e.title ILIKE %s
                  OR e.content ILIKE %s
              )
            ORDER BY e.created_utc DESC
            LIMIT 25
        """

    elif target_type == "voice":

        sql = """
            SELECT
                id,
                title,
                NULL::text AS event_date,
                LEFT(
                    COALESCE(
                        NULLIF(transcript, ''),
                        original_transcript,
                        ''
                    ),
                    280
                ) AS preview
            FROM voice_journals
            WHERE profile_id = %s
              AND (
                  title ILIKE %s
                  OR COALESCE(
                      NULLIF(transcript, ''),
                      original_transcript,
                      ''
                  ) ILIKE %s
              )
            ORDER BY created_utc DESC
            LIMIT 25
        """

    else:

        sql = """
            SELECT
                id,
                title,
                NULL::text AS event_date,
                LEFT(original_text, 280) AS preview
            FROM knowledge_documents
            WHERE profile_id = %s
              AND (
                  title ILIKE %s
                  OR original_text ILIKE %s
              )
            ORDER BY created_utc DESC
            LIMIT 25
        """

    with database_connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                sql,
                (profile_id, pattern, pattern),
            )

            records = cursor.fetchall()

    return jsonify({"records": records})


@connections_bp.post("/link")
@login_required
def link():

    profile_id = require_profile()

    asset_id = request.form.get("asset_id", "")
    target_type = request.form.get("target_type", "")
    target_id = request.form.get("target_id", "")

    if target_type not in TARGET_TYPES:
        return jsonify({"error": "Invalid record type."}), 400

    with database_connection() as connection:
        with connection.cursor() as cursor:

            photo = get_photo(
                cursor,
                profile_id,
                asset_id,
            )

            target = get_record(
                cursor,
                profile_id,
                target_type,
                target_id,
            )

            if not photo or not target:

                return jsonify({
                    "error": "Historical record not found."
                }), 404

            cursor.execute(
                """
                INSERT INTO archive_relationships (
                    id,
                    profile_id,
                    asset_id,
                    target_type,
                    target_id,
                    match_score,
                    match_reasons,
                    status
                )
                VALUES (
                    %s, %s, %s, %s,
                    %s, 0, %s, 'confirmed'
                )
                ON CONFLICT (
                    profile_id,
                    asset_id,
                    target_type,
                    target_id
                )
                DO UPDATE SET
                    status = 'confirmed',
                    match_reasons = EXCLUDED.match_reasons,
                    updated_utc = NOW()
                RETURNING id
                """,
                (
                    uuid4().hex,
                    profile_id,
                    asset_id,
                    target_type,
                    target_id,
                    Jsonb(["Manually connected by the user"]),
                ),
            )

            relationship = cursor.fetchone()

    return jsonify({
        "success": True,
        "relationship_id": relationship["id"],
        "record_url": url_for(
            "archive_connections.record",
            target_type=target_type,
            target_id=target_id,
        ),
    })


@connections_bp.post("/unlink")
@login_required
def unlink():

    profile_id = require_profile()

    relationship_id = request.form.get(
        "relationship_id",
        "",
    )

    with database_connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                UPDATE archive_relationships
                SET
                    status = 'rejected',
                    updated_utc = NOW()
                WHERE id = %s
                  AND profile_id = %s
                RETURNING id
                """,
                (relationship_id, profile_id),
            )

            if not cursor.fetchone():
                return jsonify({
                    "error": "Connection not found."
                }), 404

    return jsonify({"success": True})
