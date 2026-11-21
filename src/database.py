
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from storage import data_dir


# --------------------------------------------------
# Database connection
# --------------------------------------------------

def database_path():
    return data_dir() / "legacy.db"


@contextmanager
def database_connection():
    connection = sqlite3.connect(
        database_path(),
        timeout=10,
    )

    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA foreign_keys = ON")

    try:
        yield connection
        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------
# Database initialization
# --------------------------------------------------

def initialize_database():

    with database_connection() as connection:

        connection.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_utc TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                created_utc TEXT NOT NULL,
                FOREIGN KEY (owner_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_profiles_owner
                ON profiles(owner_id);
        """)


# --------------------------------------------------
# User operations
# --------------------------------------------------

def create_user(email, password_hash):

    user_id = uuid4().hex
    email = email.strip().lower()

    with database_connection() as connection:

        connection.execute(
            """
            INSERT INTO users (
                id,
                email,
                password_hash,
                created_utc
            )
            VALUES (?, ?, ?, ?)
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

        user = connection.execute(
            """
            SELECT *
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()

    return dict(user) if user else None


def get_user_by_email(email):

    with database_connection() as connection:

        user = connection.execute(
            """
            SELECT *
            FROM users
            WHERE email = ?
            """,
            (email.strip().lower(),),
        ).fetchone()

    return dict(user) if user else None


# --------------------------------------------------
# Profile operations
# --------------------------------------------------

def create_profile(owner_id, display_name):

    profile_id = uuid4().hex
    display_name = display_name.strip()

    if not display_name:
        raise ValueError("Profile name is required.")

    with database_connection() as connection:

        connection.execute(
            """
            INSERT INTO profiles (
                id,
                owner_id,
                display_name,
                created_utc
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                profile_id,
                owner_id,
                display_name,
                utc_now(),
            ),
        )

    return get_profile(profile_id, owner_id)


def get_user_profiles(owner_id):

    with database_connection() as connection:

        profiles = connection.execute(
            """
            SELECT *
            FROM profiles
            WHERE owner_id = ?
            ORDER BY created_utc DESC
            """,
            (owner_id,),
        ).fetchall()

    return [dict(profile) for profile in profiles]


def get_profile(profile_id, owner_id):

    with database_connection() as connection:

        profile = connection.execute(
            """
            SELECT *
            FROM profiles
            WHERE id = ?
            AND owner_id = ?
            """,
            (profile_id, owner_id),
        ).fetchone()

    return dict(profile) if profile else None
