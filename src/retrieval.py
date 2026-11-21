
from __future__ import annotations

import re

import numpy as np
from pgvector.psycopg import register_vector

from database import database_connection
from embeddings import embed_text


RRF_K = 60
CANDIDATE_LIMIT = 100

SEARCH_STOPWORDS = {
    "a", "about", "affect", "and", "are", "as", "at",
    "be", "by", "can", "did", "do", "does", "for",
    "from", "had", "has", "have", "he", "her", "him",
    "his", "how", "i", "in", "is", "it", "john",
    "me", "my", "negatively", "of", "on", "or",
    "our", "positively", "say", "said", "she",
    "that", "the", "their", "them", "there",
    "these", "they", "this", "to", "was",
    "were", "what", "when", "where",
    "which", "who", "why", "will",
    "with", "you", "your",
}


def _keywords(question):
    tokens = re.findall(
        r"[a-zA-Z][a-zA-Z'-]*",
        question.lower(),
    )

    terms = []

    for token in tokens:
        token = token.strip("'-")

        if len(token) < 3:
            continue

        if token in SEARCH_STOPWORDS:
            continue

        if token not in terms:
            terms.append(token)

    return terms[:12]


def search_knowledge(
    profile_id,
    owner_id,
    question,
    limit=5,
):
    """
    Hybrid knowledge retrieval.

    Combines semantic vector search and PostgreSQL
    full-text keyword search using Reciprocal Rank
    Fusion (RRF).

    All results are restricted to the authorized profile.
    """

    if not isinstance(question, str) or not question.strip():
        raise ValueError("Question cannot be empty.")

    if not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("Limit must be between 1 and 20.")

    # Verify ownership before performing retrieval.
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

    # Generate semantic embedding.
    query_vector = np.asarray(
        embed_text(question.strip()),
        dtype=np.float32,
    )

    # Search distinctive terms with OR instead
    # of requiring the entire question to match.
    keywords = _keywords(question)
    keyword_query = " OR ".join(keywords)

    with database_connection() as connection:
        register_vector(connection)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                WITH authorized AS (
                    SELECT
                        c.id AS chunk_id,
                        c.document_id,
                        c.chunk_index,
                        c.chunk_text,
                        c.embedding,
                        d.title,
                        d.source_type
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
                ),

                semantic_results AS (
                    SELECT
                        chunk_id,
                        ROW_NUMBER() OVER (
                            ORDER BY
                                embedding <=> %s::vector,
                                chunk_id
                        ) AS semantic_rank,
                        1 - (
                            embedding <=> %s::vector
                        ) AS similarity
                    FROM authorized
                    ORDER BY
                        embedding <=> %s::vector,
                        chunk_id
                    LIMIT %s
                ),

                lexical_results AS (
                    SELECT
                        chunk_id,
                        ROW_NUMBER() OVER (
                            ORDER BY
                                lexical_score DESC,
                                chunk_id
                        ) AS lexical_rank
                    FROM (
                        SELECT
                            chunk_id,
                            ts_rank_cd(
                                to_tsvector(
                                    'english',
                                    chunk_text
                                ),
                                websearch_to_tsquery(
                                    'english',
                                    %s
                                )
                            ) AS lexical_score
                        FROM authorized
                        WHERE %s <> ''
                          AND to_tsvector(
                              'english',
                              chunk_text
                          ) @@ websearch_to_tsquery(
                              'english',
                              %s
                          )
                    ) candidate
                    ORDER BY
                        lexical_score DESC,
                        chunk_id
                    LIMIT %s
                ),

                combined AS (
                    SELECT
                        COALESCE(
                            s.chunk_id,
                            l.chunk_id
                        ) AS chunk_id,

                        s.semantic_rank,
                        l.lexical_rank,
                        s.similarity,

                        COALESCE(
                            1.0 / (
                                %s + s.semantic_rank
                            ),
                            0
                        ) +

                        COALESCE(
                            1.0 / (
                                %s + l.lexical_rank
                            ),
                            0
                        ) AS hybrid_score

                    FROM semantic_results s

                    FULL OUTER JOIN lexical_results l
                        ON l.chunk_id = s.chunk_id
                )

                SELECT
                    a.chunk_id,
                    a.document_id,
                    a.title,
                    a.source_type,
                    a.chunk_index,
                    a.chunk_text,
                    combined.similarity,
                    combined.semantic_rank,
                    combined.lexical_rank,
                    combined.hybrid_score

                FROM combined

                JOIN authorized a
                    ON a.chunk_id = combined.chunk_id

                ORDER BY
                    combined.hybrid_score DESC,
                    combined.lexical_rank NULLS LAST,
                    combined.semantic_rank NULLS LAST,
                    a.chunk_id

                LIMIT %s
                """,
                (
                    profile_id,
                    owner_id,
                    query_vector,
                    query_vector,
                    query_vector,
                    CANDIDATE_LIMIT,
                    keyword_query,
                    keyword_query,
                    keyword_query,
                    CANDIDATE_LIMIT,
                    RRF_K,
                    RRF_K,
                    limit,
                ),
            )

            rows = cursor.fetchall()

    return [
        {
            "chunk_id": row["chunk_id"],
            "document_id": row["document_id"],
            "title": row["title"],
            "source_type": row["source_type"],
            "chunk_index": row["chunk_index"],
            "text": row["chunk_text"],

            "similarity": (
                round(
                    float(row["similarity"]),
                    4,
                )
                if row["similarity"] is not None
                else None
            ),

            "semantic_rank": (
                int(row["semantic_rank"])
                if row["semantic_rank"] is not None
                else None
            ),

            "lexical_rank": (
                int(row["lexical_rank"])
                if row["lexical_rank"] is not None
                else None
            ),

            "hybrid_score": round(
                float(row["hybrid_score"]),
                6,
            ),
        }
        for row in rows
    ]
