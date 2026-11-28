from flask import Blueprint, jsonify, session
from flask_login import login_required, current_user

from database import database_connection

archive_bp = Blueprint(
    "archive_records",
    __name__,
    url_prefix="/api/archive",
)


def serialize(record):
    return {
        key: value.isoformat()
        if hasattr(value, "isoformat")
        else value
        for key, value in record.items()
    }


def active_profile_id():
    return session.get("profile_id")


@archive_bp.get("/collections")
@login_required
def collections():

    profile_id = active_profile_id()

    if not profile_id:
        return jsonify({"error": "No active profile."}), 403

    with database_connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT id FROM profiles
                WHERE id = %s AND owner_id = %s
                """,
                (profile_id, current_user.id),
            )

            if cursor.fetchone() is None:
                return jsonify({"error": "Access denied."}), 403

            cursor.execute(
                """
                SELECT
                    d.id,
                    d.title,
                    d.source_type,
                    d.created_utc,
                    LEFT(d.original_text, 220) AS preview
                FROM knowledge_documents d
                JOIN profiles p ON p.id = d.profile_id
                WHERE d.profile_id = %s
                  AND p.owner_id = %s
                ORDER BY d.created_utc DESC
                """,
                (profile_id, current_user.id),
            )

            documents = [
                serialize(row)
                for row in cursor.fetchall()
            ]

            cursor.execute(
                """
                SELECT
                    m.id,
                    m.category,
                    m.status,
                    m.event_date,
                    m.created_utc,
                    m.source_document_id,
                    LEFT(m.memory_text, 220) AS preview
                FROM structured_memories m
                JOIN profiles p ON p.id = m.profile_id
                WHERE m.profile_id = %s
                  AND p.owner_id = %s
                  AND m.status <> 'rejected'
                ORDER BY m.created_utc DESC
                """,
                (profile_id, current_user.id),
            )

            memories = [
                serialize(row)
                for row in cursor.fetchall()
            ]

    return jsonify({
        "documents": documents,
        "memories": memories,
    })


@archive_bp.get("/documents/<document_id>")
@login_required
def document_detail(document_id):

    profile_id = active_profile_id()

    with database_connection() as connection:
        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    d.id,
                    d.title,
                    d.source_type,
                    d.original_text,
                    d.created_utc
                FROM knowledge_documents d
                JOIN profiles p ON p.id = d.profile_id
                WHERE d.id = %s
                  AND d.profile_id = %s
                  AND p.owner_id = %s
                """,
                (document_id, profile_id, current_user.id),
            )

            document = cursor.fetchone()

            if document is None:
                return jsonify({"error": "Document not found."}), 404

            cursor.execute(
                """
                SELECT
                    m.id,
                    m.category,
                    m.status,
                    m.event_date,
                    LEFT(m.memory_text, 220) AS preview
                FROM structured_memories m
                JOIN profiles p ON p.id = m.profile_id
                WHERE m.source_document_id = %s
                  AND m.profile_id = %s
                  AND p.owner_id = %s
                  AND m.status <> 'rejected'
                ORDER BY m.created_utc DESC
                """,
                (document_id, profile_id, current_user.id),
            )

            memories = [
                serialize(row)
                for row in cursor.fetchall()
            ]

    return jsonify({
        "document": serialize(document),
        "memories": memories,
    })


@archive_bp.get("/memories/<memory_id>")
@login_required
def memory_detail(memory_id):

    profile_id = active_profile_id()

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
                    d.id AS document_id,
                    d.title AS document_title
                FROM structured_memories m
                JOIN profiles p ON p.id = m.profile_id
                LEFT JOIN knowledge_documents d
                    ON d.id = m.source_document_id
                   AND d.profile_id = m.profile_id
                WHERE m.id = %s
                  AND m.profile_id = %s
                  AND p.owner_id = %s
                  AND m.status <> 'rejected'
                """,
                (memory_id, profile_id, current_user.id),
            )

            memory = cursor.fetchone()

            if memory is None:
                return jsonify({"error": "Memory not found."}), 404

    return jsonify({
        "memory": serialize(memory),
    })
