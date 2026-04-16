from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
from datetime import datetime, timezone
from werkzeug.datastructures import FileStorage  # For type hinting on file


# --------------------------------------------------
# Base directories
# --------------------------------------------------

def base_dir() -> Path:
    """
    Returns the project root directory.
    (Legacy/src/storage.py -> Legacy/)
    """
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """
    Returns the /data directory, creating it if necessary.
    """
    d = base_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def exports_dir() -> Path:
    """
    Returns the /exports directory, creating it if necessary.
    """
    e = base_dir() / "exports"
    e.mkdir(parents=True, exist_ok=True)
    return e


def upload_dir(subject: str) -> Path:
    """
    Returns the uploads directory for a specific subject, creating it if necessary.
    Example: data/uploads/john_mills/
    """
    d = data_dir() / f"uploads/{safe_name(subject)}"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------
# Filename helpers
# --------------------------------------------------

def safe_name(name: str) -> str:
    """
    Convert a string into a filesystem-safe name.
    Example: "Mary Mills" -> "mary_mills"
    """
    name = name.strip().lower()
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in name)

    # Remove double underscores
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")

    return cleaned.strip("_") or "unknown"


def profile_path(subject: str) -> Path:
    """
    Returns full path to a subject's profile JSON file.
    """
    return data_dir() / f"profile_{safe_name(subject)}.json"


def export_path(subject: str, ext: str = "md") -> Path:
    """
    Returns full path for exported summary file.
    """
    return exports_dir() / f"legacy_summary_{safe_name(subject)}.{ext}"


# --------------------------------------------------
# JSON operations
# --------------------------------------------------

def save_json(path: Path, payload: Dict[str, Any]) -> None:
    """
    Save dictionary as formatted JSON.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_json(path: Path) -> Dict[str, Any]:
    """
    Load JSON file into a dictionary.
    """
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Profile JSON must be an object at the top level.")

    return data


# --------------------------------------------------
# Upload handling (new for self-summary feature)
# --------------------------------------------------

def save_upload(subject: str, file: FileStorage) -> Path:
    """
    Save an uploaded file securely to the subject's upload directory.
    Returns the saved Path.
    Raises ValueError on invalid file/type.
    """
    if not file or not file.filename:
        raise ValueError("No file provided or empty filename")

    ext = Path(file.filename).suffix.lower()
    allowed_extensions = {'.txt', '.md', '.pdf'}
    if ext not in allowed_extensions:
        raise ValueError(f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}")

    # Generate a safe, timestamped filename
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_filename = f"summary_{timestamp}{ext}"
    target_path = upload_dir(subject) / safe_filename

    # Save the file
    file.save(target_path)

    return target_path