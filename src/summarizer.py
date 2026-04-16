from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from openai import OpenAI
from pathlib import Path
from PyPDF2 import PdfReader  # pip install PyPDF2

def _entries_as_notes(entries: List[Dict[str, Any]], max_items: int = 30) -> str:
    trimmed = entries[-max_items:]
    lines: List[str] = []
    for e in trimmed:
        cat = e.get("category", "unknown")
        prompt = e.get("prompt", "")
        answer = e.get("answer", "")
        if answer:
            lines.append(f"- ({cat}) {prompt}\n  {answer}")
    return "\n".join(lines) if lines else "- (no entries yet)"


def should_update_core_summary(profile: Dict[str, Any], min_new_entries: int = 5) -> bool:
    entries = profile.get("entries", [])
    meta = profile.get("core_summary_meta", {})
    last_count = meta.get("source_entry_count", 0)
    return (len(entries) - last_count) >= min_new_entries


def update_core_summary(profile: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
    if not os.getenv("OPENAI_API_KEY"):
        return profile

    if not force and not should_update_core_summary(profile):
        return profile

    subject = profile.get("subject", {}).get("display_name", "Unknown")
    entries = profile.get("entries", [])
    notes = _entries_as_notes(entries)

    system = "Create a concise identity summary from the notes. Do not invent facts."
    user = f"Subject: {subject}\n\nNotes:\n{notes}"

    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )

    text = resp.choices[0].message.content or ""

    profile["core_summary"] = text.strip()

    # Ensure core_summary_meta exists
    if "core_summary_meta" not in profile:
        profile["core_summary_meta"] = {}

    profile["core_summary_meta"]["source_entry_count"] = len(entries)
    profile["core_summary_meta"]["updated_utc"] = datetime.now(timezone.utc).isoformat()
    profile["core_summary_meta"]["model"] = "gpt-4o-mini"

    return profile


def extract_from_upload(profile: Dict[str, Any], upload_path: Path) -> List[Dict[str, Any]]:
    """Extract content from uploaded file and optionally use AI to categorize it."""
    text = ""
    if upload_path.suffix.lower() == '.pdf':
        try:
            with upload_path.open('rb') as f:
                reader = PdfReader(f)
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            print(f"PDF extraction failed: {e}")
            text = ""
    else:  # .txt or .md
        try:
            text = upload_path.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            print(f"Text file read failed: {e}")
            text = ""

    if not text.strip():
        return []

    consent = profile.get("consent", {})
    if consent.get("allow_remote_processing") and os.getenv("OPENAI_API_KEY"):
        try:
            system = (
                "You are extracting structured information from a user's self-summary. "
                "Output ONLY valid JSON: {\"entries\": [list of objects]} where each object has: "
                "{\"category\": \"values\" or \"stories\" or \"guidance\" or \"purpose\", "
                "\"prompt\": \"short descriptive title or question\", "
                "\"answer\": \"the extracted relevant text (keep meaningful length)\"}"
                "Only include entries that clearly fit one of the categories. "
                "Do not invent content."
            )
            user = f"Self-summary text (truncate if very long):\n{text[:8000]}"

            client = OpenAI()
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )

            result = json.loads(resp.choices[0].message.content or "{}")
            extracted = result.get("entries", [])
            if isinstance(extracted, list):
                return [
                    {
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "category": e.get("category", "imported"),
                        "prompt": e.get("prompt", "Extracted from upload"),
                        "answer": e.get("answer", ""),
                        "tags": ["imported", "ai_extracted"]
                    }
                    for e in extracted if isinstance(e, dict) and e.get("answer")
                ]
        except Exception as e:
            print(f"AI extraction failed: {e}")

    # Fallback: add as single raw imported entry
    return [{
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "category": "imported_summary",
        "prompt": f"Uploaded self-summary ({upload_path.name})",
        "answer": text[:10000],  # truncate very long texts
        "tags": ["imported", "summary_upload"]
    }]