
from uuid import uuid4

from psycopg.types.json import Jsonb

from database import database_connection


DEFAULT_DESIGN = {
    "cover_style": "leather",
    "cover_color": "#594536",
    "accent_color": "#c5ab85",
    "emblem": "none",
    "typography": "classic",
    "paper_style": "lined",
    "page_layout": "single",
}


# --------------------------------------------------
# Create journal
# --------------------------------------------------

def create_journal(
    profile_id,
    owner_id,
    title="My Journal",
    subtitle="",
):

    title = title.strip()
    subtitle = subtitle.strip()

    if not title or len(title) > 200:
        raise ValueError("Invalid journal title.")

    if len(subtitle) > 500:
        raise ValueError("Subtitle is too long.")

    journal_id = uuid4().hex

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                INSERT INTO journals (
                    id,
                    profile_id,
                    title,
                    subtitle,
                    design
                )
                SELECT
                    %s,
                    p.id,
                    %s,
                    %s,
                    %s
                FROM profiles p
                WHERE p.id = %s
                AND p.owner_id = %s
                RETURNING *
                """,
                (
                    journal_id,
                    title,
                    subtitle,
                    Jsonb(DEFAULT_DESIGN),
                    profile_id,
                    owner_id,
                ),
            )

            journal = cursor.fetchone()

            if journal is None:
                raise PermissionError(
                    "Profile access denied."
                )

            return journal


# --------------------------------------------------
# List journals
# --------------------------------------------------

def list_journals(profile_id, owner_id):

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    j.*,
                    (
                        SELECT COUNT(*)
                        FROM journal_entries e
                        WHERE e.journal_id = j.id
                    ) AS entry_count
                FROM journals j
                JOIN profiles p
                    ON p.id = j.profile_id
                WHERE j.profile_id = %s
                AND p.owner_id = %s
                ORDER BY j.updated_utc DESC
                """,
                (
                    profile_id,
                    owner_id,
                ),
            )

            return cursor.fetchall()


# --------------------------------------------------
# Retrieve individual journal
# --------------------------------------------------

def get_journal(
    journal_id,
    profile_id,
    owner_id,
):

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT j.*
                FROM journals j
                JOIN profiles p
                    ON p.id = j.profile_id
                WHERE j.id = %s
                AND j.profile_id = %s
                AND p.owner_id = %s
                """,
                (
                    journal_id,
                    profile_id,
                    owner_id,
                ),
            )

            return cursor.fetchone()


# --------------------------------------------------
# Update journal design
# --------------------------------------------------

def update_journal_design(
    journal_id,
    profile_id,
    owner_id,
    design,
):

    if not isinstance(design, dict):
        raise ValueError("Invalid journal design.")

    allowed_options = {
        "cover_style": {
            "leather", "linen", "minimal"
        },
        "emblem": {
            "none", "compass", "tree", "stars"
        },
        "typography": {
            "classic", "modern", "elegant"
        },
        "paper_style": {
            "lined", "blank", "dotted", "dark"
        },
        "page_layout": {
            "single", "spread"
        },
    }

    import re

    validated = {}

    for key, value in design.items():

        if not isinstance(value, str):
            raise ValueError("Invalid design value.")

        if key in allowed_options:

            if value not in allowed_options[key]:
                raise ValueError(
                    f"Invalid option: {key}"
                )

        elif key in {
            "cover_color",
            "accent_color",
        }:

            if not re.fullmatch(
                r"#[0-9a-fA-F]{6}",
                value,
            ):
                raise ValueError("Invalid color.")

        else:
            raise ValueError(
                f"Unknown design option: {key}"
            )

        validated[key] = value

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                UPDATE journals j
                SET design = j.design || %s,
                    updated_utc = NOW()
                FROM profiles p
                WHERE j.profile_id = p.id
                AND j.id = %s
                AND j.profile_id = %s
                AND p.owner_id = %s
                RETURNING j.*
                """,
                (
                    Jsonb(validated),
                    journal_id,
                    profile_id,
                    owner_id,
                ),
            )

            journal = cursor.fetchone()

            if journal is None:
                raise PermissionError(
                    "Journal access denied."
                )

            return journal


# --------------------------------------------------
# Create written entry
# --------------------------------------------------

def create_journal_entry(
    journal_id,
    profile_id,
    owner_id,
):

    entry_id = uuid4().hex

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                INSERT INTO journal_entries (
                    id,
                    journal_id
                )
                SELECT
                    %s,
                    j.id
                FROM journals j
                JOIN profiles p
                    ON p.id = j.profile_id
                WHERE j.id = %s
                AND j.profile_id = %s
                AND p.owner_id = %s
                RETURNING *
                """,
                (
                    entry_id,
                    journal_id,
                    profile_id,
                    owner_id,
                ),
            )

            entry = cursor.fetchone()

            if entry is None:
                raise PermissionError(
                    "Journal access denied."
                )

            cursor.execute(
                """
                UPDATE journals
                SET updated_utc = NOW()
                WHERE id = %s
                """,
                (journal_id,),
            )

            return entry


# --------------------------------------------------
# List written entries
# --------------------------------------------------

def list_journal_entries(
    journal_id,
    profile_id,
    owner_id,
):

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    e.id,
                    e.journal_id,
                    e.title,
                    e.entry_date,
                    e.status,
                    e.allow_ai_processing,
                    e.created_utc,
                    e.updated_utc,
                    LEFT(e.content, 240) AS preview
                FROM journal_entries e
                JOIN journals j
                    ON j.id = e.journal_id
                JOIN profiles p
                    ON p.id = j.profile_id
                WHERE j.id = %s
                AND j.profile_id = %s
                AND p.owner_id = %s
                ORDER BY
                    e.entry_date DESC,
                    e.created_utc DESC
                """,
                (
                    journal_id,
                    profile_id,
                    owner_id,
                ),
            )

            return cursor.fetchall()


# --------------------------------------------------
# Retrieve written entry
# --------------------------------------------------

def get_journal_entry(
    entry_id,
    profile_id,
    owner_id,
):

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT e.*
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

            return cursor.fetchone()


# --------------------------------------------------
# Save draft or finalize entry
# --------------------------------------------------

def save_journal_entry(
    entry_id,
    profile_id,
    owner_id,
    title,
    content,
    publish=False,
):
    from journal_privacy import (
        lock_profile,
        load_entry_privacy,
        remove_indexed_knowledge,
        synchronize_entry_permission,
    )

    if not isinstance(title, str):
        raise ValueError("Invalid title.")

    if not isinstance(content, str):
        raise ValueError("Invalid content.")

    if not isinstance(publish, bool):
        raise ValueError("Invalid publish status.")

    title = title.strip()

    if len(title) > 200:
        raise ValueError("Title is too long.")

    if len(content) > 250000:
        raise ValueError("Entry is too long.")

    if publish and not content.strip():
        raise ValueError(
            "Cannot finalize an empty entry."
        )

    with database_connection() as connection:
        with connection.cursor() as cursor:

            # Maintain consistent lock ordering.
            lock_profile(
                cursor,
                profile_id,
                owner_id,
            )

            privacy = load_entry_privacy(
                cursor,
                entry_id,
                profile_id,
                owner_id,
                lock=True,
            )

            # Read the current entry while locked.
            cursor.execute(
                """
                SELECT *
                FROM journal_entries
                WHERE id = %s
                """,
                (entry_id,),
            )

            current = cursor.fetchone()

            if current is None:
                raise PermissionError(
                    "Entry unavailable for editing."
                )

            changed = (
                current["title"] != title
                or current["content"] != content
            )

            # Remove outdated indexed knowledge
            # before saving modified content.
            if changed and (
                privacy["document_id"]
                or privacy["allow_ai_processing"]
            ):
                remove_indexed_knowledge(
                    cursor,
                    entry_id,
                    profile_id,
                    owner_id,
                )

            # A modified entry becomes a draft
            # unless explicitly finalized.
            if publish:
                status = "published"
            elif changed:
                status = "draft"
            else:
                status = current["status"]

            # Avoid unnecessary writes when
            # autosave submits unchanged content.
            if (
                not changed
                and status == current["status"]
                and not publish
            ):
                return current

            cursor.execute(
                """
                UPDATE journal_entries
                SET
                    title = %s,
                    content = %s,
                    status = %s,

                    published_utc = CASE
                        WHEN %s = 'published'
                        THEN COALESCE(
                            published_utc,
                            NOW()
                        )
                        ELSE NULL
                    END,

                    updated_utc = NOW()

                WHERE id = %s
                RETURNING *
                """,
                (
                    title,
                    content,
                    status,
                    status,
                    entry_id,
                ),
            )

            entry = cursor.fetchone()

            if entry is None:
                raise RuntimeError(
                    "Unable to save journal entry."
                )

            # Resolve effective AI permission
            # using the newly saved entry status.
            #
            # This does not generate embeddings
            # or make external AI calls.

            synchronize_entry_permission(
                cursor,
                entry_id,
                profile_id,
                owner_id,
            )

            cursor.execute(
                """
                UPDATE journals
                SET updated_utc = NOW()
                WHERE id = %s
                """,
                (entry["journal_id"],),
            )

            # Return the final synchronized state.
            cursor.execute(
                """
                SELECT *
                FROM journal_entries
                WHERE id = %s
                """,
                (entry_id,),
            )

            return cursor.fetchone()
