
from __future__ import annotations

import os
import json
import sqlite3

from datetime import datetime, timezone
from uuid import uuid5, NAMESPACE_URL
from contextlib import closing

import psycopg

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from dotenv import load_dotenv
from storage import data_dir, profile_path

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "dbname=legacy",
)

SQLITE_PATH = data_dir() / "legacy.db"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def migrate():

    print("\nLEGACY DATABASE MIGRATION")
    print("=" * 50)

    if not SQLITE_PATH.is_file():
        raise FileNotFoundError(
            f"SQLite database not found: {SQLITE_PATH}"
        )

    # Read existing SQLite data without modifying it.
    with closing(
        sqlite3.connect(
            SQLITE_PATH.as_uri() + "?mode=ro",
            uri=True,
        )
    ) as source:

        source.row_factory = sqlite3.Row

        users = source.execute(
            "SELECT * FROM users"
        ).fetchall()

        profiles = source.execute(
            "SELECT * FROM profiles"
        ).fetchall()

    print(f"Source accounts: {len(users)}")
    print(f"Source profiles: {len(profiles)}")

    user_ids = {user["id"] for user in users}

    prepared_profiles = []
    total_entries = 0

    # Validate all profiles before writing anything.
    for profile in profiles:

        profile_id = profile["id"]
        owner_id = profile["owner_id"]

        if owner_id not in user_ids:
            raise ValueError(
                f"Invalid owner for profile {profile_id}"
            )

        path = profile_path(profile_id)

        if not path.is_file():
            raise FileNotFoundError(
                f"Profile data missing: {path}"
            )

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:

            payload = json.load(file)

        if not isinstance(payload, dict):
            raise ValueError(
                f"Invalid profile data: {profile_id}"
            )

        meta = payload.get("meta", {})

        if (
            meta.get("owner_id") != owner_id
            or meta.get("profile_id") != profile_id
        ):
            raise ValueError(
                f"Ownership mismatch: {profile_id}"
            )

        entries = payload.get("entries", [])

        if not isinstance(entries, list):
            raise ValueError(
                f"Invalid entries: {profile_id}"
            )

        if any(
            not isinstance(entry, dict)
            for entry in entries
        ):
            raise ValueError(
                f"Invalid knowledge entry: {profile_id}"
            )

        prepared_profiles.append(
            (profile, payload, entries)
        )

        total_entries += len(entries)

    print(f"Source knowledge entries: {total_entries}")
    print("Ownership validation passed.")

    # All PostgreSQL changes occur in one transaction.
    # Any error causes the entire migration to roll back.
    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
    ) as connection:

        with connection.cursor() as cursor:

            # Prevent overwriting existing PostgreSQL data.
            for table in (
                "users",
                "profiles",
                "knowledge_entries",
                "knowledge_embeddings",
            ):

                cursor.execute(
                    f"SELECT COUNT(*) AS total FROM {table}"
                )

                if cursor.fetchone()["total"] != 0:
                    raise RuntimeError(
                        f"Destination table {table} "
                        "is not empty. Migration stopped."
                    )

            print("\nMigrating user accounts...")

            for user in users:

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
                        user["id"],
                        user["email"],
                        user["password_hash"],
                        user["created_utc"],
                    ),
                )

            print(f"Accounts copied: {len(users)}")

            print("\nMigrating knowledge profiles...")

            migrated_entries = 0

            for profile, payload, entries in prepared_profiles:

                profile_id = profile["id"]

                cursor.execute(
                    """
                    INSERT INTO profiles (
                        id,
                        owner_id,
                        display_name,
                        created_utc,
                        updated_utc,
                        profile_data
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        profile_id,
                        profile["owner_id"],
                        profile["display_name"],
                        profile["created_utc"],
                        utc_now(),
                        Jsonb(payload),
                    ),
                )

                for index, entry in enumerate(entries):

                    entry_id = uuid5(
                        NAMESPACE_URL,
                        f"legacy:{profile_id}:{index}",
                    ).hex

                    category = str(
                        entry.get("category")
                        or "uncategorized"
                    )

                    tags = entry.get("tags") or []

                    if (
                        category == "generated"
                        or "generated" in tags
                    ):
                        source_type = "ai_generated"
                    else:
                        source_type = "legacy_import"

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
                            or profile["created_utc"],
                        ),
                    )

                    migrated_entries += 1

            # Verify destination record counts.
            expected_counts = {
                "users": len(users),
                "profiles": len(profiles),
                "knowledge_entries": total_entries,
            }

            print("\nValidating migration...")

            for table, expected in expected_counts.items():

                cursor.execute(
                    f"SELECT COUNT(*) AS total FROM {table}"
                )

                actual = cursor.fetchone()["total"]

                if actual != expected:
                    raise RuntimeError(
                        f"Validation failed for {table}: "
                        f"expected {expected}, found {actual}"
                    )

                print(
                    f"{table}: {actual}/{expected} verified"
                )

            # Verify copied credentials exactly match.
            for user in users:

                cursor.execute(
                    """
                    SELECT email, password_hash
                    FROM users
                    WHERE id = %s
                    """,
                    (user["id"],),
                )

                copied = cursor.fetchone()

                if (
                    copied is None
                    or copied["email"] != user["email"]
                    or copied["password_hash"]
                    != user["password_hash"]
                ):
                    raise RuntimeError(
                        "Credential verification failed."
                    )

            # Verify profile ownership and JSON content.
            for profile, payload, _ in prepared_profiles:

                cursor.execute(
                    """
                    SELECT owner_id, profile_data
                    FROM profiles
                    WHERE id = %s
                    """,
                    (profile["id"],),
                )

                copied = cursor.fetchone()

                if (
                    copied is None
                    or copied["owner_id"]
                    != profile["owner_id"]
                    or copied["profile_data"] != payload
                ):
                    raise RuntimeError(
                        "Profile verification failed."
                    )

    print("\n" + "=" * 50)
    print("MIGRATION SUCCESSFUL")
    print(f"Accounts migrated: {len(users)}")
    print(f"Profiles migrated: {len(profiles)}")
    print(f"Knowledge entries migrated: {migrated_entries}")
    print("Existing SQLite and JSON files preserved.")
    print("=" * 50)


if __name__ == "__main__":

    try:

        migrate()

    except Exception as error:

        print(f"\nMIGRATION FAILED: {error}")
        print("Uncommitted PostgreSQL changes rolled back.")
        raise SystemExit(1)
