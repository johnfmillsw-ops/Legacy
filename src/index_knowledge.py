
from __future__ import annotations

from uuid import uuid4

from psycopg.types.json import Jsonb
from pgvector.psycopg import register_vector

from database import database_connection
from embeddings import embed_texts, MODEL_NAME
from chunking import chunk_text


ALLOWED_SOURCE_TYPES = {
    "text",
    "document",
    "audio_transcript",
}


def index_document(
    profile_id,
    owner_id,
    title,
    original_text,
    source_type="text",
    metadata=None,
    processing_authorized=False,
):
    """
    Preserve a complete text document or transcript,
    generate local embeddings, and store searchable chunks.

    Requires verified profile ownership and explicit
    processing authorization from the calling service.
    """

    if not processing_authorized:
        raise PermissionError(
            "Document processing has not been authorized."
        )

    if source_type not in ALLOWED_SOURCE_TYPES:
        raise ValueError("Unsupported source type.")

    if not isinstance(original_text, str):
        raise ValueError("Document text must be a string.")

    if not original_text.strip():
        raise ValueError("Document cannot be empty.")

    if not isinstance(title, str):
        raise ValueError("Document title must be a string.")

    if metadata is None:
        metadata = {}

    if not isinstance(metadata, dict):
        raise ValueError("Metadata must be a dictionary.")

    # Verify ownership before processing any content.
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

    # Chunk the full document without discarding
    # the original text.
    chunks = chunk_text(original_text)

    if not chunks:
        raise ValueError(
            "No searchable text was produced."
        )

    # Generate embeddings locally.
    vectors = embed_texts([
        chunk["text"]
        for chunk in chunks
    ])

    if len(vectors) != len(chunks):
        raise RuntimeError(
            "Embedding count does not match chunk count."
        )

    document_id = uuid4().hex

    # Store document and all chunks atomically.
    with database_connection() as connection:

        register_vector(connection)

        with connection.cursor() as cursor:

            # Recheck ownership within the write transaction.
            cursor.execute(
                """
                SELECT id
                FROM profiles
                WHERE id = %s
                  AND owner_id = %s
                FOR KEY SHARE
                """,
                (profile_id, owner_id),
            )

            if cursor.fetchone() is None:
                raise PermissionError(
                    "Profile access denied."
                )

            cursor.execute(
                """
                INSERT INTO knowledge_documents (
                    id,
                    profile_id,
                    title,
                    source_type,
                    original_text,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    document_id,
                    profile_id,
                    title.strip(),
                    source_type,
                    original_text,
                    Jsonb(metadata),
                ),
            )

            for chunk, vector in zip(chunks, vectors):

                cursor.execute(
                    """
                    INSERT INTO knowledge_chunks (
                        id,
                        document_id,
                        chunk_index,
                        chunk_text,
                        token_start,
                        token_end,
                        embedding,
                        embedding_model
                    )
                    VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    """,
                    (
                        uuid4().hex,
                        document_id,
                        chunk["chunk_index"],
                        chunk["text"],
                        chunk["token_start"],
                        chunk["token_end"],
                        vector,
                        MODEL_NAME,
                    ),
                )

    return {
        "document_id": document_id,
        "profile_id": profile_id,
        "title": title.strip(),
        "source_type": source_type,
        "chunk_count": len(chunks),
        "embedding_model": MODEL_NAME,
        "status": "indexed",
    }
