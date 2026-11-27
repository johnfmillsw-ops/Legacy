
from __future__ import annotations

from uuid import uuid4

from psycopg.types.json import Jsonb
from pgvector.psycopg import register_vector

from database import database_connection
from embeddings import embed_texts, MODEL_NAME
from chunking import chunk_text

from journal_privacy import (
    lock_profile,
    load_entry_privacy,
    entry_is_eligible,
)


# --------------------------------------------------
# Load authorized journal content
# --------------------------------------------------

def load_indexing_source(
    cursor,
    entry_id,
    profile_id,
    owner_id,
    lock=False,
):
    """
    Load journal content only after verifying
    ownership and effective AI permission.
    """

    privacy = load_entry_privacy(
        cursor,
        entry_id,
        profile_id,
        owner_id,
        lock=lock,
    )

    if not (
        entry_is_eligible(privacy)
        and privacy["allow_ai_processing"]
    ):
        raise PermissionError(
            "AI processing is not authorized "
            "for this journal entry."
        )

    cursor.execute(
        """
        SELECT
            e.id,
            e.journal_id,
            e.title,
            e.content,
            e.entry_date,
            e.status,
            e.document_id,
            e.updated_utc,
            j.title AS journal_title
        FROM journal_entries e
        JOIN journals j
            ON j.id = e.journal_id
        JOIN profiles p
            ON p.id = j.profile_id
        WHERE e.id = %s
          AND j.profile_id = %s
          AND p.owner_id = %s
        """,
        (
            entry_id,
            profile_id,
            owner_id,
        ),
    )

    entry = cursor.fetchone()

    if entry is None:
        raise PermissionError(
            "Journal entry access denied."
        )

    return entry


# --------------------------------------------------
# Validate an existing indexed document
# --------------------------------------------------

def verify_indexed_document(
    cursor,
    document_id,
    entry_id,
    profile_id,
):
    """
    Ensure an existing document belongs to
    the correct profile and journal entry.
    """

    cursor.execute(
        """
        SELECT
            id,
            metadata,
            original_text
        FROM knowledge_documents
        WHERE id = %s
          AND profile_id = %s
        """,
        (
            document_id,
            profile_id,
        ),
    )

    document = cursor.fetchone()

    if document is None:
        raise RuntimeError(
            "Indexed journal document is missing."
        )

    metadata = document.get("metadata") or {}

    if (
        not isinstance(metadata, dict)
        or metadata.get("origin") != "written_journal"
        or metadata.get("journal_entry_id") != entry_id
    ):
        raise PermissionError(
            "Indexed document provenance "
            "could not be verified."
        )

    return document


# --------------------------------------------------
# Prepare searchable journal text
# --------------------------------------------------

def build_document_title(entry):

    entry_title = (
        entry.get("title") or ""
    ).strip()

    if not entry_title:
        entry_title = (
            "Journal entry — "
            + entry["entry_date"].isoformat()
        )

    journal_title = (
        entry.get("journal_title")
        or "Journal"
    ).strip()

    return f"{journal_title}: {entry_title}"


def build_searchable_text(entry):
    """
    Preserve journal content while adding
    useful chronological context for retrieval.
    """

    content = entry.get("content")

    if (
        not isinstance(content, str)
        or not content.strip()
    ):
        raise ValueError(
            "Journal entry contains no searchable text."
        )

    title = (
        entry.get("title") or ""
    ).strip()

    date = entry["entry_date"].isoformat()

    parts = [
        f"Journal entry dated {date}."
    ]

    if title:
        parts.append(title)

    parts.append(content)

    return "\n\n".join(parts)


# --------------------------------------------------
# Index an authorized written journal entry
# --------------------------------------------------

def index_journal_entry(
    entry_id,
    profile_id,
    owner_id,
):
    """
    Convert an authorized written journal entry
    into searchable knowledge.

    Processing uses local embeddings only.

    Ownership, consent, entry permissions and
    source content are checked again before
    the database transaction is committed.
    """

    # ----------------------------------------------
    # 1. Verify permission and capture source
    # ----------------------------------------------

    with database_connection() as connection:
        with connection.cursor() as cursor:

            lock_profile(
                cursor,
                profile_id,
                owner_id,
            )

            entry = load_indexing_source(
                cursor,
                entry_id,
                profile_id,
                owner_id,
                lock=True,
            )

            searchable_text = build_searchable_text(
                entry
            )

            document_title = build_document_title(
                entry
            )

            if entry["document_id"]:

                document = verify_indexed_document(
                    cursor,
                    entry["document_id"],
                    entry_id,
                    profile_id,
                )

                if (
                    document["original_text"]
                    != searchable_text
                ):
                    raise RuntimeError(
                        "Indexed content is outdated. "
                        "Reindexing is required."
                    )

                return {
                    "entry_id": entry_id,
                    "document_id": document["id"],
                    "status": "indexed",
                    "already_indexed": True,
                }

    # ----------------------------------------------
    # 2. Generate chunks and local embeddings
    # ----------------------------------------------

    chunks = chunk_text(searchable_text)

    if not chunks:
        raise ValueError(
            "No searchable chunks were produced."
        )

    vectors = embed_texts([
        chunk["text"]
        for chunk in chunks
    ])

    if len(vectors) != len(chunks):
        raise RuntimeError(
            "Embedding count does not match "
            "chunk count."
        )

    document_id = uuid4().hex

    metadata = {
        "origin": "written_journal",
        "ingestion_method": "written_journal",
        "journal_id": entry["journal_id"],
        "journal_entry_id": entry_id,
        "entry_date": entry["entry_date"].isoformat(),
        "source_updated_utc": (
            entry["updated_utc"].isoformat()
        ),
        "user_authorized": True,
        "embedding_model": MODEL_NAME,
    }

    # ----------------------------------------------
    # 3. Recheck permissions and source content
    # ----------------------------------------------

    with database_connection() as connection:

        register_vector(connection)

        with connection.cursor() as cursor:

            lock_profile(
                cursor,
                profile_id,
                owner_id,
            )

            current = load_indexing_source(
                cursor,
                entry_id,
                profile_id,
                owner_id,
                lock=True,
            )

            if (
                current["updated_utc"]
                != entry["updated_utc"]
                or current["content"]
                != entry["content"]
                or current["title"]
                != entry["title"]
                or current["entry_date"]
                != entry["entry_date"]
                or current["journal_title"]
                != entry["journal_title"]
            ):
                raise RuntimeError(
                    "Journal entry changed during "
                    "indexing. Please retry."
                )

            # Another indexing request may have
            # completed while embeddings were
            # being generated.

            if current["document_id"]:

                document = verify_indexed_document(
                    cursor,
                    current["document_id"],
                    entry_id,
                    profile_id,
                )

                if (
                    document["original_text"]
                    != searchable_text
                ):
                    raise RuntimeError(
                        "Indexed content is outdated."
                    )

                return {
                    "entry_id": entry_id,
                    "document_id": document["id"],
                    "status": "indexed",
                    "already_indexed": True,
                }

            # --------------------------------------
            # 4. Create knowledge document
            # --------------------------------------

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
                VALUES (
                    %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    document_id,
                    profile_id,
                    document_title,
                    "text",
                    searchable_text,
                    Jsonb(metadata),
                ),
            )

            # --------------------------------------
            # 5. Store chunks and vector embeddings
            # --------------------------------------

            for chunk, vector in zip(
                chunks,
                vectors,
            ):

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

            # --------------------------------------
            # 6. Link indexed knowledge to entry
            # --------------------------------------

            cursor.execute(
                """
                UPDATE journal_entries
                SET
                    document_id = %s,
                    updated_utc = NOW()
                WHERE id = %s
                  AND status = 'published'
                  AND allow_ai_processing = TRUE
                  AND document_id IS NULL
                """,
                (
                    document_id,
                    entry_id,
                ),
            )

            if cursor.rowcount != 1:
                raise RuntimeError(
                    "Unable to finalize "
                    "journal indexing."
                )

    return {
        "entry_id": entry_id,
        "journal_id": entry["journal_id"],
        "document_id": document_id,
        "profile_id": profile_id,
        "chunk_count": len(chunks),
        "embedding_model": MODEL_NAME,
        "status": "indexed",
        "already_indexed": False,
    }


# --------------------------------------------------
# Find authorized entries awaiting indexing
# --------------------------------------------------

def list_pending_journal_entries(
    profile_id,
    owner_id,
    journal_id=None,
    limit=10,
):
    """
    Return authorized, completed entries that
    have not yet been indexed.
    """

    if (
        not isinstance(limit, int)
        or not 1 <= limit <= 100
    ):
        raise ValueError(
            "Limit must be between 1 and 100."
        )

    with database_connection() as connection:
        with connection.cursor() as cursor:

            lock_profile(
                cursor,
                profile_id,
                owner_id,
            )

            query = """
                SELECT
                    e.id,
                    e.journal_id
                FROM journal_entries e
                JOIN journals j
                    ON j.id = e.journal_id
                JOIN profiles p
                    ON p.id = j.profile_id
                WHERE j.profile_id = %s
                  AND p.owner_id = %s
                  AND e.status = 'published'
                  AND e.allow_ai_processing = TRUE
                  AND e.document_id IS NULL
                  AND (
                      e.ai_preference = 'include'
                      OR (
                          e.ai_preference = 'inherit'
                          AND j.ai_default_enabled = TRUE
                      )
                  )
                  AND p.profile_data @>
                      '{"consent":{
                          "has_consent":true,
                          "allow_remote_processing":true
                      }}'::jsonb
            """

            parameters = [
                profile_id,
                owner_id,
            ]

            if journal_id is not None:

                query += " AND j.id = %s"

                parameters.append(journal_id)

            query += """
                ORDER BY
                    e.entry_date ASC,
                    e.created_utc ASC,
                    e.id ASC
                LIMIT %s
            """

            parameters.append(limit)

            cursor.execute(
                query,
                tuple(parameters),
            )

            return cursor.fetchall()


# --------------------------------------------------
# Batch indexing
# --------------------------------------------------

def index_pending_journal_entries(
    profile_id,
    owner_id,
    journal_id=None,
    limit=10,
):
    """
    Index a bounded batch of authorized entries.

    Every entry is independently checked again
    before processing.

    This function does not call Grok.
    """

    pending = list_pending_journal_entries(
        profile_id=profile_id,
        owner_id=owner_id,
        journal_id=journal_id,
        limit=limit,
    )

    results = []

    for entry in pending:

        try:

            result = index_journal_entry(
                entry_id=entry["id"],
                profile_id=profile_id,
                owner_id=owner_id,
            )

            results.append(result)

        except PermissionError:

            results.append({
                "entry_id": entry["id"],
                "status": "skipped",
                "reason": "Permission denied or revoked",
            })

        except Exception:

            # Do not expose private journal content
            # through exception messages or logs.

            results.append({
                "entry_id": entry["id"],
                "status": "error",
                "reason": "Indexing failed; retry required",
            })

    return {
        "entries_checked": len(pending),
        "entries_indexed": sum(
            1
            for item in results
            if item["status"] == "indexed"
        ),
        "entries_skipped": sum(
            1
            for item in results
            if item["status"] == "skipped"
        ),
        "entries_failed": sum(
            1
            for item in results
            if item["status"] == "error"
        ),
        "results": results,
    }
