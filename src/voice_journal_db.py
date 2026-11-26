
from __future__ import annotations

from uuid import uuid4

from database import database_connection
from psycopg.types.json import Jsonb


# --------------------------------------------------
# Generate journal ID
# --------------------------------------------------

def generate_journal_id():

    return uuid4().hex


# --------------------------------------------------
# Create voice journal
# --------------------------------------------------

def create_voice_journal(
    journal_id,
    profile_id,
    owner_id,
    title,
    audio_path,
    original_filename,
    mime_type,
    file_size_bytes,
    duration_seconds=None,
    metadata=None,
):

    title = (title or "").strip() or "Untitled Journal"

    if len(title) > 200:
        raise ValueError(
            "Journal title cannot exceed 200 characters."
        )

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                INSERT INTO voice_journals (
                    id,
                    profile_id,
                    title,
                    audio_path,
                    original_filename,
                    mime_type,
                    file_size_bytes,
                    duration_seconds,
                    metadata,
                    status
                )
                SELECT
                    %s, profiles.id, %s, %s, %s,
                    %s, %s, %s, %s, 'uploaded'
                FROM profiles
                WHERE profiles.id = %s
                AND profiles.owner_id = %s
                RETURNING *
                """,
                (
                    journal_id,
                    title,
                    audio_path,
                    original_filename,
                    mime_type,
                    file_size_bytes,
                    duration_seconds,
                    Jsonb(metadata or {}),
                    profile_id,
                    owner_id,
                ),
            )

            record = cursor.fetchone()

            if record is None:
                raise PermissionError("Profile access denied.")

            return record


# --------------------------------------------------
# Retrieve individual journal
# --------------------------------------------------

def get_voice_journal(
    journal_id,
    profile_id,
    owner_id,
):

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT voice_journals.*
                FROM voice_journals
                JOIN profiles
                    ON profiles.id = voice_journals.profile_id
                WHERE voice_journals.id = %s
                AND voice_journals.profile_id = %s
                AND profiles.owner_id = %s
                """,
                (
                    journal_id,
                    profile_id,
                    owner_id,
                ),
            )

            return cursor.fetchone()


# --------------------------------------------------
# Retrieve journal history
# --------------------------------------------------

def list_voice_journals(
    profile_id,
    owner_id,
):

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    voice_journals.id,
                    voice_journals.profile_id,
                    voice_journals.title,
                    voice_journals.original_filename,
                    voice_journals.mime_type,
                    voice_journals.file_size_bytes,
                    voice_journals.duration_seconds,
                    voice_journals.status,
                    voice_journals.document_id,
                    voice_journals.created_utc,
                    voice_journals.updated_utc
                FROM voice_journals
                JOIN profiles
                    ON profiles.id = voice_journals.profile_id
                WHERE voice_journals.profile_id = %s
                AND profiles.owner_id = %s
                ORDER BY voice_journals.created_utc DESC
                """,
                (
                    profile_id,
                    owner_id,
                ),
            )

            return cursor.fetchall()


# --------------------------------------------------
# Save generated transcription
# --------------------------------------------------

def save_voice_transcript(
    journal_id,
    profile_id,
    owner_id,
    result,
):

    transcript = result["transcript"].strip()

    if not transcript:
        raise ValueError("Transcript cannot be empty.")

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                UPDATE voice_journals AS journal
                SET
                    original_transcript = %s,
                    transcript = %s,
                    transcription_model = %s,
                    transcription_language = %s,
                    duration_seconds = %s,
                    transcription_error = NULL,
                    status = 'transcribed',
                    transcribed_utc = NOW(),
                    updated_utc = NOW()
                FROM profiles
                WHERE journal.id = %s
                AND journal.profile_id = %s
                AND profiles.id = journal.profile_id
                AND profiles.owner_id = %s
                AND journal.status IN (
                    'uploaded',
                    'transcribing',
                    'failed'
                )
                AND journal.original_transcript IS NULL
                AND profiles.profile_data
                    @> '{"consent":{"has_consent":true}}'::jsonb
                RETURNING journal.*
                """,
                (
                    transcript,
                    transcript,
                    result["model"],
                    result["language"],
                    result["duration_seconds"],
                    journal_id,
                    profile_id,
                    owner_id,
                ),
            )

            record = cursor.fetchone()

            if record is None:
                raise ValueError(
                    "Journal unavailable or transcription not authorized."
                )

            return record


# --------------------------------------------------
# Validate editable transcript
# --------------------------------------------------

def validate_transcript(transcript):

    if not isinstance(transcript, str):
        raise ValueError("Invalid transcript.")

    transcript = transcript.strip()

    if not transcript:
        raise ValueError("Transcript cannot be empty.")

    if len(transcript) > 250000:
        raise ValueError("Transcript exceeds character limit.")

    return transcript


# --------------------------------------------------
# Edit transcript before approval
# --------------------------------------------------

def update_voice_transcript(
    journal_id,
    profile_id,
    owner_id,
    transcript,
):

    transcript = validate_transcript(transcript)

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                UPDATE voice_journals AS journal
                SET
                    transcript = %s,
                    updated_utc = NOW()
                FROM profiles
                WHERE journal.id = %s
                AND journal.profile_id = %s
                AND profiles.id = journal.profile_id
                AND profiles.owner_id = %s
                AND journal.status = 'transcribed'
                AND journal.original_transcript IS NOT NULL
                AND profiles.profile_data
                    @> '{"consent":{"has_consent":true}}'::jsonb
                RETURNING journal.*
                """,
                (
                    transcript,
                    journal_id,
                    profile_id,
                    owner_id,
                ),
            )

            record = cursor.fetchone()

            if record is None:
                raise ValueError(
                    "Journal unavailable or cannot be edited."
                )

            return record


# --------------------------------------------------
# Approve transcript for knowledge indexing
# --------------------------------------------------

def approve_voice_transcript(
    journal_id,
    profile_id,
    owner_id,
    transcript=None,
):

    if transcript is not None:
        transcript = validate_transcript(transcript)

    with database_connection() as connection:

        with connection.cursor() as cursor:

            cursor.execute(
                """
                UPDATE voice_journals AS journal
                SET
                    transcript = COALESCE(
                        %s, journal.transcript
                    ),
                    status = 'approved',
                    approved_utc = NOW(),
                    updated_utc = NOW()
                FROM profiles
                WHERE journal.id = %s
                AND journal.profile_id = %s
                AND profiles.id = journal.profile_id
                AND profiles.owner_id = %s
                AND journal.status = 'transcribed'
                AND journal.original_transcript IS NOT NULL
                AND LENGTH(
                    TRIM(COALESCE(%s, journal.transcript))
                ) > 0
                AND profiles.profile_data
                    @> '{"consent":{"has_consent":true}}'::jsonb
                RETURNING journal.*
                """,
                (
                    transcript,
                    journal_id,
                    profile_id,
                    owner_id,
                    transcript,
                ),
            )

            record = cursor.fetchone()

            if record is None:
                raise ValueError(
                    "Journal unavailable or cannot be approved."
                )

            return record
