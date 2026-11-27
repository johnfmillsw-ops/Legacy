
from __future__ import annotations

from database import database_connection


VALID_PREFERENCES = {
    "inherit",
    "include",
    "private",
}


# --------------------------------------------------
# Resolve effective AI permission
# --------------------------------------------------

def resolve_ai_permission(
    journal_default,
    entry_preference,
    entry_status,
    consent,
):
    """
    Determine whether a journal entry is eligible
    for AI processing.

    Account consent takes precedence over journal
    defaults and individual entry preferences.
    """

    if not isinstance(consent, dict):
        return False

    if not (
        consent.get("has_consent") is True
        and consent.get("allow_remote_processing") is True
    ):
        return False

    if entry_status != "published":
        return False

    if entry_preference not in VALID_PREFERENCES:
        return False

    if entry_preference == "private":
        return False

    if entry_preference == "include":
        return True

    return journal_default is True


# --------------------------------------------------
# Profile ownership and consent
# --------------------------------------------------

def lock_profile(cursor, profile_id, owner_id):
    """
    Lock the authorized profile for the duration
    of the current database transaction.
    """

    cursor.execute(
        """
        SELECT
            id,
            owner_id,
            profile_data
        FROM profiles
        WHERE id = %s
          AND owner_id = %s
        FOR UPDATE
        """,
        (profile_id, owner_id),
    )

    profile = cursor.fetchone()

    if profile is None:
        raise PermissionError(
            "Profile access denied."
        )

    return profile


def get_profile_consent(profile):
    data = profile.get("profile_data") or {}

    if not isinstance(data, dict):
        return {}

    consent = data.get("consent") or {}

    if not isinstance(consent, dict):
        return {}

    return consent


# --------------------------------------------------
# Entry ownership and privacy state
# --------------------------------------------------

def load_entry_privacy(
    cursor,
    entry_id,
    profile_id,
    owner_id,
    lock=False,
):
    """
    Load an entry and its parent journal while
    verifying profile ownership.
    """

    query = """
        SELECT
            e.id,
            e.journal_id,
            e.status,
            e.ai_preference,
            e.allow_ai_processing,
            e.document_id,
            j.ai_default_enabled,
            j.profile_id,
            p.profile_data
        FROM journal_entries e
        JOIN journals j
            ON j.id = e.journal_id
        JOIN profiles p
            ON p.id = j.profile_id
        WHERE e.id = %s
          AND j.profile_id = %s
          AND p.owner_id = %s
    """

    if lock:
        query += " FOR UPDATE OF j, e"

    cursor.execute(
        query,
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


def entry_is_eligible(entry):
    """
    Calculate permission from the current
    database record.
    """

    return resolve_ai_permission(
        journal_default=entry[
            "ai_default_enabled"
        ],
        entry_preference=entry[
            "ai_preference"
        ],
        entry_status=entry["status"],
        consent=get_profile_consent(entry),
    )


# --------------------------------------------------
# Public permission check
# --------------------------------------------------

def get_entry_ai_permission(
    entry_id,
    profile_id,
    owner_id,
):
    """
    Return the current permission state.

    Eligibility does not mean indexing has
    completed.
    """

    with database_connection() as connection:
        with connection.cursor() as cursor:

            entry = load_entry_privacy(
                cursor,
                entry_id,
                profile_id,
                owner_id,
            )

            eligible = entry_is_eligible(entry)

            return {
                "entry_id": entry["id"],
                "journal_id": entry["journal_id"],
                "journal_default_enabled": entry[
                    "ai_default_enabled"
                ],
                "entry_preference": entry[
                    "ai_preference"
                ],
                "eligible": eligible,
                "allow_ai_processing": (
                    eligible
                    and entry["allow_ai_processing"]
                ),
                "indexed": bool(
                    eligible
                    and entry["allow_ai_processing"]
                    and entry["document_id"]
                ),
            }


def require_entry_ai_permission(
    entry_id,
    profile_id,
    owner_id,
):
    """
    Reject unauthorized AI processing.
    """

    permission = get_entry_ai_permission(
        entry_id,
        profile_id,
        owner_id,
    )

    if not permission["allow_ai_processing"]:
        raise PermissionError(
            "AI processing is not authorized "
            "for this journal entry."
        )

    return permission


# --------------------------------------------------
# Remove indexed journal knowledge
# --------------------------------------------------

def remove_indexed_knowledge(
    cursor,
    entry_id,
    profile_id,
    owner_id,
):
    """
    Remove the indexed representation of an entry.

    The original journal entry is preserved.

    The caller must hold the profile lock and
    execute this function within a transaction.
    """

    entry = load_entry_privacy(
        cursor,
        entry_id,
        profile_id,
        owner_id,
        lock=True,
    )

    document_id = entry["document_id"]

    if document_id:

        # Confirm that the linked document belongs
        # to this profile and this journal entry.

        cursor.execute(
            """
            SELECT
                id,
                metadata
            FROM knowledge_documents
            WHERE id = %s
              AND profile_id = %s
            FOR UPDATE
            """,
            (
                document_id,
                profile_id,
            ),
        )

        document = cursor.fetchone()

        if document is None:
            raise PermissionError(
                "Indexed document ownership "
                "could not be verified."
            )

        metadata = document.get("metadata") or {}

        if (
            not isinstance(metadata, dict)
            or metadata.get("journal_entry_id")
            != entry_id
            or metadata.get("origin")
            != "written_journal"
        ):
            raise ValueError(
                "Indexed document provenance "
                "could not be verified."
            )

        # Remove derived memories before deleting
        # their source document and chunks.
        #
        # The existing foreign keys use SET NULL,
        # so deleting only the document would leave
        # derived memories behind.

        cursor.execute(
            """
            DELETE FROM structured_memories
            WHERE profile_id = %s
              AND (
                  source_document_id = %s
                  OR source_chunk_id IN (
                      SELECT id
                      FROM knowledge_chunks
                      WHERE document_id = %s
                  )
              )
            """,
            (
                profile_id,
                document_id,
                document_id,
            ),
        )

        # Disconnect the journal entry from its
        # indexed document and disable processing.

        cursor.execute(
            """
            UPDATE journal_entries
            SET
                document_id = NULL,
                allow_ai_processing = FALSE,
                updated_utc = NOW()
            WHERE id = %s
            """,
            (entry_id,),
        )

        # Deleting the document also deletes its
        # knowledge chunks and vector embeddings
        # through the existing cascade constraint.

        cursor.execute(
            """
            DELETE FROM knowledge_documents
            WHERE id = %s
              AND profile_id = %s
            """,
            (
                document_id,
                profile_id,
            ),
        )

    else:

        cursor.execute(
            """
            UPDATE journal_entries
            SET
                allow_ai_processing = FALSE,
                updated_utc = NOW()
            WHERE id = %s
              AND allow_ai_processing = TRUE
            """,
            (entry_id,),
        )

    return {
        "entry_id": entry_id,
        "removed_document_id": document_id,
        "allow_ai_processing": False,
    }


# --------------------------------------------------
# Synchronize effective entry permission
# --------------------------------------------------

def synchronize_entry_permission(
    cursor,
    entry_id,
    profile_id,
    owner_id,
):
    """
    Recalculate and persist effective permission.

    The caller must hold the profile lock.
    """

    entry = load_entry_privacy(
        cursor,
        entry_id,
        profile_id,
        owner_id,
        lock=True,
    )

    eligible = entry_is_eligible(entry)

    if not eligible:

        remove_indexed_knowledge(
            cursor,
            entry_id,
            profile_id,
            owner_id,
        )

    else:

        cursor.execute(
            """
            UPDATE journal_entries
            SET
                allow_ai_processing = TRUE,
                updated_utc = NOW()
            WHERE id = %s
              AND allow_ai_processing = FALSE
            """,
            (entry_id,),
        )

    return {
        "entry_id": entry_id,
        "journal_id": entry["journal_id"],
        "allow_ai_processing": eligible,
        "needs_indexing": (
            eligible
            and not entry["document_id"]
        ),
    }


# --------------------------------------------------
# Change individual entry preference
# --------------------------------------------------

def set_entry_ai_preference(
    entry_id,
    profile_id,
    owner_id,
    preference,
):
    """
    Set an individual entry's AI preference.

    Supported preferences:
        inherit
        include
        private
    """

    if (
        not isinstance(preference, str)
        or preference not in VALID_PREFERENCES
    ):
        raise ValueError(
            "Invalid AI preference."
        )

    with database_connection() as connection:
        with connection.cursor() as cursor:

            lock_profile(
                cursor,
                profile_id,
                owner_id,
            )

            load_entry_privacy(
                cursor,
                entry_id,
                profile_id,
                owner_id,
                lock=True,
            )

            cursor.execute(
                """
                UPDATE journal_entries
                SET
                    ai_preference = %s,
                    updated_utc = NOW()
                WHERE id = %s
                """,
                (
                    preference,
                    entry_id,
                ),
            )

            result = synchronize_entry_permission(
                cursor,
                entry_id,
                profile_id,
                owner_id,
            )

            result["ai_preference"] = preference

            return result


# --------------------------------------------------
# Change journal-wide preference
# --------------------------------------------------

def set_journal_ai_default(
    journal_id,
    profile_id,
    owner_id,
    enabled,
    apply_to_existing=False,
):
    """
    Change the journal's default AI preference.

    Existing entries using 'inherit' follow the
    new default automatically.

    Explicit entry overrides are preserved unless
    apply_to_existing is True.
    """

    if not isinstance(enabled, bool):
        raise ValueError(
            "Journal AI preference must be boolean."
        )

    if not isinstance(apply_to_existing, bool):
        raise ValueError(
            "Invalid apply-to-existing preference."
        )

    with database_connection() as connection:
        with connection.cursor() as cursor:

            lock_profile(
                cursor,
                profile_id,
                owner_id,
            )

            cursor.execute(
                """
                SELECT j.id
                FROM journals j
                JOIN profiles p
                    ON p.id = j.profile_id
                WHERE j.id = %s
                  AND j.profile_id = %s
                  AND p.owner_id = %s
                FOR UPDATE OF j
                """,
                (
                    journal_id,
                    profile_id,
                    owner_id,
                ),
            )

            if cursor.fetchone() is None:
                raise PermissionError(
                    "Journal access denied."
                )

            cursor.execute(
                """
                UPDATE journals
                SET
                    ai_default_enabled = %s,
                    updated_utc = NOW()
                WHERE id = %s
                """,
                (
                    enabled,
                    journal_id,
                ),
            )

            if apply_to_existing:

                cursor.execute(
                    """
                    UPDATE journal_entries
                    SET
                        ai_preference = 'inherit',
                        updated_utc = NOW()
                    WHERE journal_id = %s
                    """,
                    (journal_id,),
                )

            cursor.execute(
                """
                SELECT id
                FROM journal_entries
                WHERE journal_id = %s
                ORDER BY id
                """,
                (journal_id,),
            )

            entry_ids = [
                row["id"]
                for row in cursor.fetchall()
            ]

            results = []

            for entry_id in entry_ids:

                result = synchronize_entry_permission(
                    cursor,
                    entry_id,
                    profile_id,
                    owner_id,
                )

                results.append(result)

            return {
                "journal_id": journal_id,
                "ai_default_enabled": enabled,
                "applied_to_existing": apply_to_existing,
                "entries_updated": len(results),
                "entries_eligible": sum(
                    1
                    for item in results
                    if item["allow_ai_processing"]
                ),
                "entries_needing_indexing": [
                    item["entry_id"]
                    for item in results
                    if item["needs_indexing"]
                ],
            }


# --------------------------------------------------
# Profile-wide permission synchronization
# --------------------------------------------------

def synchronize_profile_journals(
    profile_id,
    owner_id,
):
    """
    Reevaluate every journal entry belonging to
    a profile.

    Intended for use after account-level consent
    changes.
    """

    with database_connection() as connection:
        with connection.cursor() as cursor:

            lock_profile(
                cursor,
                profile_id,
                owner_id,
            )

            cursor.execute(
                """
                SELECT e.id
                FROM journal_entries e
                JOIN journals j
                    ON j.id = e.journal_id
                WHERE j.profile_id = %s
                ORDER BY j.id, e.id
                """,
                (profile_id,),
            )

            entry_ids = [
                row["id"]
                for row in cursor.fetchall()
            ]

            results = []

            for entry_id in entry_ids:

                results.append(
                    synchronize_entry_permission(
                        cursor,
                        entry_id,
                        profile_id,
                        owner_id,
                    )
                )

            return {
                "entries_checked": len(results),
                "entries_eligible": sum(
                    1
                    for item in results
                    if item["allow_ai_processing"]
                ),
                "entries_needing_indexing": [
                    item["entry_id"]
                    for item in results
                    if item["needs_indexing"]
                ],
            }
