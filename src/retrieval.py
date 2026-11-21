
from __future__ import annotations

import numpy as np

from pgvector.psycopg import register_vector

from database import database_connection
from embeddings import embed_text


def search_knowledge(
    profile_id,
    owner_id,
    question,
    limit=5,
):
    """
    Search document chunks by semantic similarity.

    Results are restricted to the authorized profile.
    """

    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question cannot be empty.")

    if not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("Limit must be between 1 and 20.")

    # Verify ownership before generating embeddings.
    with database_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM profiles
                WHERE id = %s
                  AND owner_id = %s
                """,
                (profile_id, owner_id),
            )

            if cursor.fetchone() is None:
                raise PermissionError(
                    "Profile access denied."
                )

    # NumPy float32 arrays are supported by
    # pgvector's registered psycopg adapter.
    query_vector = np.asarray(
        embed_text(question.strip()),
        dtype=np.float32,
    )

    with database_connection() as connection:

        register_vector(connection)

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    c.id AS chunk_id,
                    c.document_id,
                    d.title,
                    d.source_type,
                    c.chunk_index,
                    c.chunk_text,
                    1 - (c.embedding <=> %s::vector)
                        AS similarity
                FROM knowledge_chunks c
                JOIN knowledge_documents d
                    ON d.id = c.document_id
                WHERE d.profile_id = %s
                  AND EXISTS (
                      SELECT 1
                      FROM profiles p
                      WHERE p.id = d.profile_id
                        AND p.owner_id = %s
                  )
                  AND c.embedding IS NOT NULL
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                (
                    query_vector,
                    profile_id,
                    owner_id,
                    query_vector,
                    limit,
                ),
            )

            results = cursor.fetchall()

    return [
        {
            "chunk_id": row["chunk_id"],
            "document_id": row["document_id"],
            "title": row["title"],
            "source_type": row["source_type"],
            "chunk_index": row["chunk_index"],
            "text": row["chunk_text"],
            "similarity": round(
                float(row["similarity"]), 4
            ),
        }
        for row in results
    ]
