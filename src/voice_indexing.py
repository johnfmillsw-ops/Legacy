
from __future__ import annotations

from uuid import uuid4

from psycopg.types.json import Jsonb
from pgvector.psycopg import register_vector

from database import database_connection
from embeddings import embed_texts, MODEL_NAME
from chunking import chunk_text


def index_voice_journal(journal_id, profile_id, owner_id):
    """
    Convert an approved voice journal into searchable
    knowledge for Legacy.

    Preserve the original recording and transcription.
    Index only the user-approved transcript.
    """

    # --------------------------------------------------
    # Verify ownership, consent, and approval
    # --------------------------------------------------

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    journal.id,
                    journal.title,
                    journal.transcript,
                    journal.status,
                    journal.document_id,
                    journal.created_utc,
                    journal.transcription_model,
                    journal.transcription_language
                FROM voice_journals AS journal
                JOIN profiles AS profile
                    ON profile.id = journal.profile_id
                WHERE journal.id = %s
                  AND journal.profile_id = %s
                  AND profile.owner_id = %s
                  AND profile.profile_data @>
                      '{"consent":{"has_consent":true}}'::jsonb
                """,
                (journal_id, profile_id, owner_id),
            )

            journal = cursor.fetchone()

    if journal is None:

        raise PermissionError(
            "Journal access or processing consent denied."
        )

    if journal["status"] == "indexed" and journal["document_id"]:

        return {
            "journal_id": journal_id,
            "document_id": journal["document_id"],
            "status": "indexed",
            "already_indexed": True,
        }

    if journal["status"] != "approved":

        raise ValueError(
            "Only approved voice journals can be indexed."
        )

    transcript = journal["transcript"]

    if not isinstance(transcript, str) or not transcript.strip():

        raise ValueError(
            "Approved transcript is empty."
        )

    # --------------------------------------------------
    # Generate knowledge chunks and local embeddings
    # --------------------------------------------------

    chunks = chunk_text(transcript)

    if not chunks:

        raise ValueError(
            "No searchable text was produced."
        )

    vectors = embed_texts([
        chunk["text"]
        for chunk in chunks
    ])

    if len(vectors) != len(chunks):

        raise RuntimeError(
            "Embedding count does not match chunk count."
        )

    document_id = uuid4().hex

    metadata = {
        "voice_journal_id": journal_id,
        "ingestion_method": "voice_journal",
        "transcription_model": journal["transcription_model"],
        "transcription_language": journal["transcription_language"],
        "recorded_utc": (
            journal["created_utc"].isoformat()
            if journal["created_utc"]
            else None
        ),
        "user_approved": True,
    }

    # --------------------------------------------------
    # Store document, chunks, and journal link atomically
    # --------------------------------------------------

    with database_connection() as connection:

        register_vector(connection)

        with connection.cursor() as cursor:

            # Recheck ownership and consent.
            # Lock the profile against concurrent changes.

            cursor.execute(
                """
                SELECT id
                FROM profiles
                WHERE id = %s
                  AND owner_id = %s
                  AND profile_data @>
                      '{"consent":{"has_consent":true}}'::jsonb
                FOR SHARE
                """,
                (profile_id, owner_id),
            )

            if cursor.fetchone() is None:

                raise PermissionError(
                    "Profile access or processing consent denied."
                )

            # Lock the journal to prevent duplicate indexing.

            cursor.execute(
                """
                SELECT
                    id,
                    status,
                    document_id,
                    transcript
                FROM voice_journals
                WHERE id = %s
                  AND profile_id = %s
                FOR UPDATE
                """,
                (journal_id, profile_id),
            )

            current = cursor.fetchone()

            if current is None:

                raise ValueError(
                    "Voice journal no longer exists."
                )

            if (
                current["status"] == "indexed"
                and current["document_id"]
            ):

                return {
                    "journal_id": journal_id,
                    "document_id": current["document_id"],
                    "status": "indexed",
                    "already_indexed": True,
                }

            if current["status"] != "approved":

                raise ValueError(
                    "Journal is no longer approved."
                )

            if current["document_id"] is not None:

                raise RuntimeError(
                    "Journal already has a knowledge document."
                )

            if current["transcript"] != transcript:

                raise RuntimeError(
                    "Transcript changed during indexing."
                )

            # Preserve the complete approved transcript.

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
                    journal["title"],
                    "audio_transcript",
                    transcript,
                    Jsonb(metadata),
                ),
            )

            # Store searchable chunks and embeddings.

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

            # Link the journal to its knowledge document.

            cursor.execute(
                """
                UPDATE voice_journals
                SET
                    document_id = %s,
                    status = 'indexed',
                    indexed_utc = NOW(),
                    updated_utc = NOW()
                WHERE id = %s
                  AND profile_id = %s
                  AND status = 'approved'
                """,
                (
                    document_id,
                    journal_id,
                    profile_id,
                ),
            )

            if cursor.rowcount != 1:

                raise RuntimeError(
                    "Unable to finalize journal indexing."
                )

    return {
        "journal_id": journal_id,
        "document_id": document_id,
        "profile_id": profile_id,
        "title": journal["title"],
        "source_type": "audio_transcript",
        "chunk_count": len(chunks),
        "embedding_model": MODEL_NAME,
        "status": "indexed",
        "already_indexed": False,
    }


def index_approved_voice_journals(profile_id, owner_id):
    """
    Process previously approved journals that have
    not yet been added to Legacy's knowledge system.
    """

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT journal.id
                FROM voice_journals AS journal
                JOIN profiles AS profile
                    ON profile.id = journal.profile_id
                WHERE journal.profile_id = %s
                  AND profile.owner_id = %s
                  AND journal.status = 'approved'
                  AND journal.document_id IS NULL
                  AND profile.profile_data @>
                      '{"consent":{"has_consent":true}}'::jsonb
                ORDER BY journal.created_utc ASC
                """,
                (profile_id, owner_id),
            )

            journals = cursor.fetchall()

    results = []

    for journal in journals:

        try:

            result = index_voice_journal(
                journal_id=journal["id"],
                profile_id=profile_id,
                owner_id=owner_id,
            )

            results.append(result)

        except Exception as error:

            results.append({
                "journal_id": journal["id"],
                "status": "error",
                "error": str(error),
            })

    return results
