from uuid import uuid4

from flask import Blueprint, jsonify, request
from flask_login import login_required
from psycopg.types.json import Jsonb

from database import database_connection
from archive_gallery import authorized_profile
from archive_match_worker import evaluate


relationships_bp = Blueprint(
    "archive_relationships",
    __name__,
    url_prefix="/api/archive/relationships",
)


def get_asset(cursor, profile_id, asset_id):

    cursor.execute(
        """
        SELECT id, title, description,
               event_date, location, people
        FROM archive_assets
        WHERE id = %s AND profile_id = %s
        """,
        (asset_id, profile_id),
    )

    return cursor.fetchone()


def get_candidates(cursor, profile_id):

    cursor.execute(
        """
        SELECT
            'memory' AS target_type,
            id AS target_id,
            category AS title,
            event_date,
            CONCAT_WS(
                ' ',
                memory_text,
                source_excerpt
            ) AS text
        FROM structured_memories
        WHERE profile_id = %s
          AND status <> 'rejected'

        UNION ALL

        SELECT
            'journal' AS target_type,
            e.id AS target_id,
            e.title,
            e.entry_date::text AS event_date,
            e.content AS text
        FROM journal_entries e
        JOIN journals j ON j.id = e.journal_id
        WHERE j.profile_id = %s

        UNION ALL

        SELECT
            'voice' AS target_type,
            id AS target_id,
            title,
            NULL::text AS event_date,
            CONCAT_WS(
                ' ',
                title,
                COALESCE(
                    NULLIF(transcript, ''),
                    original_transcript,
                    ''
                )
            ) AS text
        FROM voice_journals
        WHERE profile_id = %s

        UNION ALL

        SELECT
            'document' AS target_type,
            id AS target_id,
            title,
            NULL::text AS event_date,
            original_text AS text
        FROM knowledge_documents
        WHERE profile_id = %s
        """,
        (
            profile_id,
            profile_id,
            profile_id,
            profile_id,
        ),
    )

    return cursor.fetchall()


def relationship_view(
    cursor,
    profile_id,
    asset_id,
    candidates,
):

    lookup = {
        (
            record["target_type"],
            record["target_id"],
        ): record
        for record in candidates
    }

    cursor.execute(
        """
        SELECT
            id,
            target_type,
            target_id,
            match_score,
            match_reasons,
            status
        FROM archive_relationships
        WHERE profile_id = %s
          AND asset_id = %s
          AND status <> 'rejected'
        ORDER BY
            CASE
                WHEN status = 'confirmed'
                THEN 0
                ELSE 1
            END,
            match_score DESC
        """,
        (profile_id, asset_id),
    )

    results = []

    for relationship in cursor.fetchall():

        target = lookup.get((
            relationship["target_type"],
            relationship["target_id"],
        ))

        if target is None:
            continue

        results.append({
            **relationship,
            "title": target["title"],
            "event_date": target["event_date"],
            "preview": (
                target["text"] or ""
            )[:350],
        })

    return results


@relationships_bp.get("/<asset_id>")
@login_required
def list_relationships(asset_id):

    profile_id = authorized_profile()

    if not profile_id:
        return jsonify({"error": "Access denied."}), 403

    with database_connection() as connection:
        with connection.cursor() as cursor:

            if not get_asset(
                cursor,
                profile_id,
                asset_id,
            ):
                return jsonify({
                    "error": "Photograph not found."
                }), 404

            candidates = get_candidates(
                cursor,
                profile_id,
            )

            relationships = relationship_view(
                cursor,
                profile_id,
                asset_id,
                candidates,
            )

    return jsonify({
        "relationships": relationships
    })


@relationships_bp.post("/<asset_id>/discover")
@login_required
def discover(asset_id):

    profile_id = authorized_profile()

    if not profile_id:
        return jsonify({"error": "Access denied."}), 403

    with database_connection() as connection:
        with connection.cursor() as cursor:

            asset = get_asset(
                cursor,
                profile_id,
                asset_id,
            )

            if not asset:
                return jsonify({
                    "error": "Photograph not found."
                }), 404

            candidates = get_candidates(
                cursor,
                profile_id,
            )

            cursor.execute("SELECT * FROM archive_match_sources WHERE profile_id = %s", (profile_id,))
            eligible = cursor.fetchall()
            matches = []
            for candidate in eligible:
                score, reasons = evaluate(asset, candidate, profile_id)
                if score >= 35:
                    matches.append({**candidate, "match_score": score, "match_reasons": reasons})

            # Rebuild only unreviewed suggestions.
            # Preserve all confirmed and rejected decisions.

            cursor.execute(
                """
                DELETE FROM archive_relationships
                WHERE profile_id = %s
                  AND asset_id = %s
                  AND status = 'suggested'
                """,
                (profile_id, asset_id),
            )

            for match in matches:

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
                        %s, %s, %s, 'suggested'
                    )
                    ON CONFLICT (
                        profile_id,
                        asset_id,
                        target_type,
                        target_id
                    )
                    DO NOTHING
                    """,
                    (
                        uuid4().hex,
                        profile_id,
                        asset_id,
                        match["target_type"],
                        match["target_id"],
                        match["match_score"],
                        Jsonb(match["match_reasons"]),
                    ),
                )

            relationships = relationship_view(
                cursor,
                profile_id,
                asset_id,
                candidates,
            )

    return jsonify({
        "relationships": relationships
    })


@relationships_bp.post("/decision/<relationship_id>")
@login_required
def decision(relationship_id):

    profile_id = authorized_profile()

    if not profile_id:
        return jsonify({"error": "Access denied."}), 403

    status = request.form.get("status")

    if status not in ("confirmed", "rejected"):

        return jsonify({
            "error": "Invalid relationship decision."
        }), 400

    with database_connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                UPDATE archive_relationships
                SET status = %s,
                    updated_utc = NOW()
                WHERE id = %s
                  AND profile_id = %s
                RETURNING id
                """,
                (
                    status,
                    relationship_id,
                    profile_id,
                ),
            )

            if cursor.fetchone() is None:

                return jsonify({
                    "error": "Relationship not found."
                }), 404

    return jsonify({"success": True})

@relationships_bp.get('/search')
@login_required
def archive_search():
    from flask import render_template
    from archive_matching import terms, passages
    profile_id = authorized_profile()
    if not profile_id:
        return jsonify({'error':'Access denied.'}), 403
    query = request.args.get('q','').strip()[:300]
    results = []
    if query:
        words = terms(query)
        with database_connection() as connection:
            with connection.cursor() as cursor:
                candidates = get_candidates(cursor, profile_id)
        for candidate in candidates:
            for passage in passages(candidate.get('text')):
                score = len(words & terms(passage))
                if score:
                    results.append((score, candidate, passage))
        results.sort(key=lambda r:r[0], reverse=True)
        seen = set()
        unique = []
        for score, candidate, passage in results:
            key = (candidate['target_type'],candidate['target_id'])
            if key not in seen:
                seen.add(key)
                unique.append(dict(candidate, preview=passage[:700]))
        results = unique[:50]
    return render_template('archive_search.html', query=query, results=results)
