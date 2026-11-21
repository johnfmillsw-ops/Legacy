
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict
from datetime import datetime, timezone
from uuid import uuid4

from werkzeug.datastructures import FileStorage
from dotenv import load_dotenv

load_dotenv()


# --------------------------------------------------
# Base directories
# --------------------------------------------------

def base_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    configured_path = os.getenv("LEGACY_DATA_DIR")

    if configured_path:
        directory = Path(configured_path).expanduser().resolve()
    else:
        directory = base_dir() / "data"

    directory.mkdir(parents=True, exist_ok=True)
    return directory


def exports_dir() -> Path:
    configured_path = os.getenv("LEGACY_EXPORT_DIR")

    if configured_path:
        directory = Path(configured_path).expanduser().resolve()
    else:
        directory = base_dir() / "exports"

    directory.mkdir(parents=True, exist_ok=True)
    return directory


def upload_dir(subject: str) -> Path:
    directory = data_dir() / "uploads" / safe_name(subject)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


# --------------------------------------------------
# Filename helpers
# --------------------------------------------------

def safe_name(name: str) -> str:
    name = name.strip().lower()

    cleaned = "".join(
        ch if ch.isalnum() else "_"
        for ch in name
    )

    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")

    return cleaned.strip("_") or "unknown"


def profile_path(subject: str) -> Path:
    return data_dir() / f"profile_{safe_name(subject)}.json"


def export_path(subject: str, ext: str = "md") -> Path:
    ext = ext.lower().lstrip(".")

    if not ext.isascii() or not ext.isalnum():
        raise ValueError("Invalid export extension.")

    return exports_dir() / (
        f"legacy_summary_{safe_name(subject)}.{ext}"
    )


# --------------------------------------------------
# Atomic JSON operations
# --------------------------------------------------

def save_json(path: Path, payload: Dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be a dictionary.")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:

            temporary_path = Path(temporary_file.name)

            json.dump(
                payload,
                temporary_file,
                ensure_ascii=False,
                indent=2,
            )

            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, path)

    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_json(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            "Profile JSON must be an object at the top level."
        )

    return data


# --------------------------------------------------
# Upload handling
# --------------------------------------------------

def save_upload(subject: str, file: FileStorage) -> Path:
    if not file or not file.filename:
        raise ValueError(
            "No file provided or empty filename."
        )

    ext = Path(file.filename).suffix.lower()
    allowed_extensions = {".txt", ".md", ".pdf"}

    if ext not in allowed_extensions:
        raise ValueError(
            "Unsupported file type. Allowed: "
            + ", ".join(sorted(allowed_extensions))
        )

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%d_%H%M%S"
    )

    unique_id = uuid4().hex[:12]

    safe_filename = (
        f"summary_{timestamp}_{unique_id}{ext}"
    )

    target_path = upload_dir(subject) / safe_filename

    try:
        file.save(target_path)
    except Exception:
        target_path.unlink(missing_ok=True)
        raise

    return target_path
