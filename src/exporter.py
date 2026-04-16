from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from storage import export_path


def render_summary_md(profile: Dict[str, Any]) -> str:
    subject = profile.get("subject", {}).get("display_name", "Unknown")
    consent = profile.get("consent", {})
    entries: List[Dict[str, Any]] = profile.get("entries", [])

    lines: List[str] = []
    lines.append(f"# Legacy Summary: {subject}")
    lines.append("")
    lines.append(f"Generated (UTC): {datetime.utcnow().isoformat()}Z")
    lines.append("")

    lines.append("## Consent")
    lines.append(f"- Has consent: {bool(consent.get('has_consent'))}")
    if consent.get("consent_utc"):
        lines.append(f"- Consent recorded (UTC): {consent.get('consent_utc')}")
    if consent.get("scope"):
        lines.append(f"- Scope: {consent.get('scope')}")
    lines.append("")

    lines.append("## Entries")
    lines.append(f"- Total entries: {len(entries)}")
    lines.append("")

    # Group entries by category
    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for e in entries:
        cat = e.get("category", "uncategorized")
        by_cat.setdefault(cat, []).append(e)

    for cat, items in by_cat.items():
        lines.append(f"### {cat.capitalize()}")
        for i, e in enumerate(items, start=1):
            prompt = str(e.get("prompt", "")).strip()
            answer = str(e.get("answer", "")).strip()
            ts = str(e.get("timestamp_utc", "")).strip()

            lines.append(f"**{i}. {prompt}**")
            if ts:
                lines.append(f"- _{ts}_")
            lines.append(f"- {answer}")
            lines.append("")

    return "\n".join(lines)


def write_summary_md(profile: Dict[str, Any]) -> str:
    subject = profile.get("subject", {}).get("display_name", "Unknown")
    path = export_path(subject, ext="md")
    md = render_summary_md(profile)
    path.write_text(md, encoding="utf-8")
    return str(path)
