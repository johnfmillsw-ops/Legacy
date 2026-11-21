
from __future__ import annotations

import os

from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4, uuid5, NAMESPACE_URL

import psycopg

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "dbname=legacy",
)


# --------------------------------------------------
# Database connection
# --------------------------------------------------

@contextmanager
def database_connection():

    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
        connect_timeout=10,
    ) as connection:

        yield connection


def utc_now():

    return datetime.now(timezone.utc).isoformat()


def initialize_database():

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    to_regclass('public.users') AS users,
                    to_regclass('public.profiles') AS profiles,
                    to_regclass('public.knowledge_entries') AS entries,
                    to_regclass('public.knowledge_embeddings') AS embeddings
                """
            )

            tables = cursor.fetchone()

            if not all(tables.values()):

                raise RuntimeError(
                    "PostgreSQL schema is incomplete."
                )


# --------------------------------------------------
# User accounts
# --------------------------------------------------

def create_user(email, password_hash):

    user_id = uuid4().hex

    email = email.strip().lower()

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                INSERT INTO users (
                    id,
                    email,
                    password_hash,
                    created_utc
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    user_id,
                    email,
                    password_hash,
                    utc_now(),
                ),
            )

    return get_user_by_id(user_id)


def get_user_by_id(user_id):

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT *
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            )

            return cursor.fetchone()


def get_user_by_email(email):

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT *
                FROM users
                WHERE LOWER(email) = %s
                """,
                (email.strip().lower(),),
            )

            return cursor.fetchone()


# --------------------------------------------------
# Profile management
# --------------------------------------------------

def create_profile(owner_id, display_name):

    profile_id = uuid4().hex

    display_name = display_name.strip()

    if not display_name:

        raise ValueError(
            "Profile name cannot be empty."
        )

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                INSERT INTO profiles (
                    id,
                    owner_id,
                    display_name,
                    created_utc
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    profile_id,
                    owner_id,
                    display_name,
                    utc_now(),
                ),
            )

    return get_profile(profile_id, owner_id)


def format_profile(record):

    if record is None:
        return None

    result = dict(record)

    for field in (
        "created_utc",
        "updated_utc",
    ):

        if isinstance(result.get(field), datetime):

            result[field] = result[field].isoformat()

    return result


def get_user_profiles(owner_id):

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    id,
                    owner_id,
                    display_name,
                    created_utc,
                    updated_utc
                FROM profiles
                WHERE owner_id = %s
                ORDER BY created_utc DESC
                """,
                (owner_id,),
            )

            return [
                format_profile(record)
                for record in cursor.fetchall()
            ]


def get_profile(profile_id, owner_id):

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT *
                FROM profiles
                WHERE id = %s
                AND owner_id = %s
                """,
                (
                    profile_id,
                    owner_id,
                ),
            )

            return format_profile(
                cursor.fetchone()
            )


# --------------------------------------------------
# Knowledge profile storage
# --------------------------------------------------

def load_profile_data(profile_id, owner_id):

    record = get_profile(
        profile_id,
        owner_id,
    )

    if record is None:

        raise PermissionError(
            "Profile access denied."
        )

    return record["profile_data"]


def save_profile_data(
    profile_id,
    owner_id,
    profile_data,
):

    meta = profile_data.get("meta", {})

    if (
        meta.get("profile_id") != profile_id
        or meta.get("owner_id") != owner_id
    ):

        raise PermissionError(
            "Profile ownership mismatch."
        )

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                UPDATE profiles
                SET profile_data = %s,
                    updated_utc = NOW()
                WHERE id = %s
                AND owner_id = %s
                """,
                (
                    Jsonb(profile_data),
                    profile_id,
                    owner_id,
                ),
            )

            if cursor.rowcount != 1:

                raise PermissionError(
                    "Profile access denied."
                )


            # Synchronize individual knowledge entries.
            entries = profile_data.get("entries", [])
            entry_ids = []

            for index, entry in enumerate(entries):

                entry_id = uuid5(
                    NAMESPACE_URL,
                    f"legacy:{profile_id}:{index}",
                ).hex

                entry_ids.append(entry_id)

                category = str(
                    entry.get("category")
                    or "uncategorized"
                )

                tags = entry.get("tags") or []

                source_type = (
                    "ai_generated"
                    if category == "generated"
                    or "generated" in tags
                    else "legacy_import"
                )

                # Invalidate embeddings if text changes.
                cursor.execute(
                    """
                    DELETE FROM knowledge_embeddings
                    WHERE entry_id = %s
                    AND EXISTS (
                        SELECT 1
                        FROM knowledge_entries
                        WHERE id = %s
                        AND (
                            prompt IS DISTINCT FROM %s
                            OR answer IS DISTINCT FROM %s
                        )
                    )
                    """,
                    (
                        entry_id,
                        entry_id,
                        str(entry.get("prompt") or ""),
                        str(entry.get("answer") or ""),
                    ),
                )

                cursor.execute(
                    """
                    INSERT INTO knowledge_entries (
                        id,
                        profile_id,
                        category,
                        prompt,
                        answer,
                        tags,
                        source_type,
                        metadata,
                        created_utc
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    ON CONFLICT (id)
                    DO UPDATE SET
                        category = EXCLUDED.category,
                        prompt = EXCLUDED.prompt,
                        answer = EXCLUDED.answer,
                        tags = EXCLUDED.tags,
                        source_type = EXCLUDED.source_type,
                        metadata = EXCLUDED.metadata,
                        created_utc = EXCLUDED.created_utc
                    """,
                    (
                        entry_id,
                        profile_id,
                        category,
                        str(entry.get("prompt") or ""),
                        str(entry.get("answer") or ""),
                        Jsonb(tags),
                        source_type,
                        Jsonb(entry),
                        entry.get("timestamp_utc")
                        or utc_now(),
                    ),
                )

            cursor.execute(
                """
                DELETE FROM knowledge_entries
                WHERE profile_id = %s
                AND NOT (id = ANY(%s::text[]))
                """,
                (profile_id, entry_ids),
            )
