from flask import Blueprint, jsonify, request, url_for
from flask_login import login_required

from archive_gallery import authorized_profile
from database import database_connection


timeline_bp = Blueprint(
    "archive_timeline",
    __name__,
    url_prefix="/api/archive/timeline",
)


COLLECTIONS = {
    "memory": "Memory",
    "journal": "Journal entry",
    "voice": "Oral history",
    "photo": "Photograph",
    "document": "Historical document",
}


@timeline_bp.get("")
@login_required
def timeline():

    profile_id = authorized_profile()

    if not profile_id:
        return jsonify({"error": "Access denied."}), 403

    mode = request.args.get("mode", "event")
    collection = request.args.get("collection", "all")
    direction = request.args.get("direction", "desc")
    search = request.args.get("q", "").strip()[:200]

    page = max(
        1,
        request.args.get("page", 1, type=int)
    )

    page_size = 20

    if mode not in ("event", "preserved"):
        return jsonify({"error": "Invalid chronology."}), 400

    if collection not in ("all", *COLLECTIONS):
        return jsonify({"error": "Invalid collection."}), 400

    if direction not in ("asc", "desc"):
        return jsonify({"error": "Invalid sort order."}), 400

    direction_sql = (
        "ASC" if direction == "asc" else "DESC"
    )

    date_column = (
        "event_date" if mode == "event"
        else "preserved_date"
    )

    pattern = "%" + (
        search.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    ) + "%"

    sql = """
        WITH historical_records AS (

            SELECT
                id,
                'memory'::text AS record_type,
                category AS title,
                LEFT(memory_text, 320) AS preview,
                NULLIF(TRIM(event_date), '') AS event_date,
                created_utc AS preserved_at
            FROM structured_memories
            WHERE profile_id = %s
              AND status <> 'rejected'

            UNION ALL

            SELECT
                e.id,
                'journal'::text,
                e.title,
                LEFT(e.content, 320),
                e.entry_date::text,
                e.created_utc
            FROM journal_entries e
            JOIN journals j ON j.id = e.journal_id
            WHERE j.profile_id = %s

            UNION ALL

            SELECT
                id,
                'voice'::text,
                title,
                LEFT(
                    COALESCE(
                        NULLIF(transcript, ''),
                        original_transcript,
                        ''
                    ),
                    320
                ),
                NULL::text,
                created_utc
            FROM voice_journals
            WHERE profile_id = %s

            UNION ALL

            SELECT
                id,
                'photo'::text,
                title,
                LEFT(description, 320),
                NULLIF(TRIM(event_date), ''),
                created_utc
            FROM archive_assets
            WHERE profile_id = %s

            UNION ALL

            SELECT
                id,
                'document'::text,
                title,
                LEFT(original_text, 320),
                NULL::text,
                created_utc
            FROM knowledge_documents
            WHERE profile_id = %s

        ),

        normalized_records AS (

            SELECT
                id,
                record_type,
                title,
                preview,
                CASE
                    WHEN event_date ~
                        '^[0-9]{4}(-[0-9]{2})?(-[0-9]{2})?$'
                    THEN event_date
                    ELSE NULL
                END AS event_date,
                event_date AS original_event_date,
                preserved_at,
                TO_CHAR(
                    preserved_at AT TIME ZONE 'UTC',
                    'YYYY-MM-DD'
                ) AS preserved_date
            FROM historical_records

        ),

        filtered_records AS (

            SELECT *
            FROM normalized_records
            WHERE (%s = 'all' OR record_type = %s)
              AND (
                  %s = ''
                  OR COALESCE(title, '') ILIKE %s
                  OR COALESCE(preview, '') ILIKE %s
              )

        )
    """

    params = (
        profile_id,
        profile_id,
        profile_id,
        profile_id,
        profile_id,
        collection,
        collection,
        search,
        pattern,
        pattern,
    )

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                sql + """
                    SELECT COUNT(*) AS total
                    FROM filtered_records
                """,
                params,
            )

            total = cursor.fetchone()["total"]

            pages = max(
                1,
                (total + page_size - 1) // page_size
            )

            page = min(page, pages)

            cursor.execute(
                sql + f"""
                    SELECT *
                    FROM filtered_records
                    ORDER BY
                        {date_column}
                        {direction_sql}
                        NULLS LAST,
                        preserved_at DESC,
                        record_type,
                        id
                    LIMIT %s OFFSET %s
                """,
                params + (
                    page_size,
                    (page - 1) * page_size,
                ),
            )

            records = cursor.fetchall()

    from archive_text import archive_plain_text

    result = []

    for record in records:

        item = dict(record)

        item["label"] = COLLECTIONS[
            item["record_type"]
        ]

        item["preview"] = archive_plain_text(
            item["preview"]
        )

        if item["preserved_at"]:
            item["preserved_at"] = (
                item["preserved_at"].isoformat()
            )

        if item["record_type"] == "photo":

            item["url"] = url_for(
                "archive_connections.photograph",
                asset_id=item["id"],
            )

            item["thumbnail"] = (
                "/api/archive/gallery/"
                + item["id"]
                + "/thumbnail"
            )

        else:

            item["url"] = url_for(
                "archive_connections.record",
                target_type=item["record_type"],
                target_id=item["id"],
            )

        result.append(item)

    return jsonify({
        "records": result,
        "total": total,
        "page": page,
        "pages": pages,
        "mode": mode,
    })
