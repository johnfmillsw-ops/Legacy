
from __future__ import annotations

import os
import re
import tempfile

from pathlib import Path

from werkzeug.datastructures import FileStorage

from storage import data_dir


# --------------------------------------------------
# Audio storage configuration
# --------------------------------------------------

MAX_AUDIO_SIZE = 100 * 1024 * 1024

ALLOWED_AUDIO_TYPES = {
    ".webm": "audio/webm",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
}


# --------------------------------------------------
# Directory management
# --------------------------------------------------

def voice_journal_root() -> Path:

    directory = data_dir() / "voice_journals"

    directory.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    return directory.resolve()


def validate_identifier(value: str) -> str:

    value = str(value)

    if not re.fullmatch(r"[a-fA-F0-9]{32}", value):

        raise ValueError(
            "Invalid profile or journal identifier."
        )

    return value


def journal_directory(
    profile_id: str,
    journal_id: str,
) -> Path:

    profile_id = validate_identifier(profile_id)
    journal_id = validate_identifier(journal_id)

    root = voice_journal_root()

    directory = (
        root / profile_id / journal_id
    ).resolve()

    if not directory.is_relative_to(root):

        raise PermissionError(
            "Invalid audio storage location."
        )

    return directory


# --------------------------------------------------
# Permanent audio storage
# --------------------------------------------------

def save_voice_recording(
    profile_id: str,
    journal_id: str,
    file: FileStorage,
) -> dict:

    if file is None or not file.filename:

        raise ValueError(
            "No audio recording was provided."
        )

    original_filename = Path(file.filename).name

    extension = Path(
        original_filename
    ).suffix.lower()

    if extension not in ALLOWED_AUDIO_TYPES:

        raise ValueError(
            "Unsupported audio format."
        )

    directory = journal_directory(
        profile_id,
        journal_id,
    )

    directory.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    target_path = directory / (
        f"original{extension}"
    )

    if target_path.exists():

        raise FileExistsError(
            "This recording already exists."
        )

    temporary_path = None
    file_size = 0

    try:

        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=directory,
            prefix=".recording_",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:

            temporary_path = Path(
                temporary_file.name
            )

            while True:

                chunk = file.stream.read(
                    1024 * 1024
                )

                if not chunk:
                    break

                file_size += len(chunk)

                if file_size > MAX_AUDIO_SIZE:

                    raise ValueError(
                        "Audio exceeds the 100 MB limit."
                    )

                temporary_file.write(chunk)

            if file_size == 0:

                raise ValueError(
                    "The audio recording is empty."
                )

            temporary_file.flush()

            os.fsync(
                temporary_file.fileno()
            )

        os.link(
            temporary_path,
            target_path,
        )

        relative_path = target_path.relative_to(
            voice_journal_root()
        )

        return {
            "audio_path": str(relative_path),
            "original_filename": original_filename,
            "mime_type": ALLOWED_AUDIO_TYPES[extension],
            "file_size_bytes": file_size,
        }

    finally:

        if temporary_path is not None:

            temporary_path.unlink(
                missing_ok=True
            )


# --------------------------------------------------
# Resolve stored audio
# --------------------------------------------------

def resolve_voice_recording(
    profile_id: str,
    journal_id: str,
    audio_path: str,
) -> Path:

    directory = journal_directory(
        profile_id,
        journal_id,
    )

    path = (
        voice_journal_root() / audio_path
    ).resolve()

    if path.parent != directory:

        raise PermissionError(
            "Invalid recording path."
        )

    if not path.is_file():

        raise FileNotFoundError(
            "The audio recording could not be found."
        )

    return path


# --------------------------------------------------
# Delete stored audio
# --------------------------------------------------

def delete_voice_recording(
    profile_id: str,
    journal_id: str,
    audio_path: str,
) -> None:

    try:

        path = resolve_voice_recording(
            profile_id,
            journal_id,
            audio_path,
        )

    except FileNotFoundError:

        return

    path.unlink()

    try:

        path.parent.rmdir()

    except OSError:

        pass
