# src/webapp.py
from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List

# Ensure src/ is on the import path
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from flask import Flask, redirect, render_template, request, session, url_for, flash

from storage import load_json, profile_path, save_json, upload_dir, save_upload
from questions import QUESTIONS
from guidance import generate_guidance_response
from exporter import write_summary_md
from summarizer import update_core_summary, extract_from_upload

app = Flask(__name__)
app.secret_key = os.getenv("LEGACY_FLASK_SECRET", "dev-secret-change-me")


def ensure_profile(subject: str) -> Dict[str, Any]:
    path = profile_path(subject)
    try:
        return load_json(path)
    except FileNotFoundError:
        return {
            "meta": {
                "project": "Legacy",
                "version": "0.7.0-web",
                "created_utc": datetime.now(timezone.utc).isoformat(),
            },
            "subject": {"display_name": subject},
            "consent": {
                "has_consent": False,
                "consent_utc": None,
                "scope": "local_storage_only",
                "allow_remote_processing": False,
                "remote_consent_utc": None,
                "remote_vendor": "openai",
            },
            "values": {},
            "stories": [],
            "guidance_principles": [
                "Tell the truth clearly and kindly.",
                "Choose the option that increases responsibility and long-term stability.",
                "When overwhelmed: slow down, name the constraint, take the next right step.",
            ],
            "entries": [],
            "core_summary": "",
            "core_summary_meta": {
                "updated_utc": None,
                "source_entry_count": 0,
                "model": None,
            },
            # NEW: Permanent identity anchor (will be updated dynamically later if needed)
            "identity_anchor": {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "category": "identity",
                "prompt": "Who is this person? Provide a full, honest overview.",
                "answer": "This is a self-constructed individual focused on building durable stability for future generations instead of chaos. "
                          "Core values include duty over comfort, mastery over mediocrity, clarity over ambiguity, freedom with purpose, and generational repair. "
                          "Life trajectory reflects resilience and self-construction. Strengths include strategic thinking in chaos, high endurance, and long-horizon planning.",
                "tags": ["identity", "self", "about_me", "core", "permanent"]
            }
        }


def load_or_create(subject: str) -> Dict[str, Any]:
    path = profile_path(subject)
    try:
        profile = load_json(path)
        # Ensure identity_anchor exists (migrate old profiles)
        if "identity_anchor" not in profile:
            profile["identity_anchor"] = ensure_profile(subject)["identity_anchor"]
            save_json(path, profile)
        return profile
    except FileNotFoundError:
        profile = ensure_profile(subject)
        save_json(path, profile)
        return profile


def save_profile(subject: str, profile: Dict[str, Any]) -> None:
    save_json(profile_path(subject), profile)


def require_subject() -> str:
    subject = session.get("subject")
    return str(subject).strip() if subject else ""


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        subject = (request.form.get("subject") or "").strip()
        if not subject:
            flash("Enter a subject name.")
            return redirect(url_for("index"))
        session["subject"] = subject
        load_or_create(subject)
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    subject = require_subject()
    if not subject:
        return redirect(url_for("index"))

    profile = load_or_create(subject)
    consent = profile.get("consent", {})
    entries = profile.get("entries", [])
    has_key = bool(os.getenv("XAI_API_KEY", "").strip())

    return render_template(
        "dashboard.html",
        subject=subject,
        entry_count=len(entries),
        consent=consent,
        has_key=has_key,
        categories=list(QUESTIONS.keys()),
        core_summary=profile.get("core_summary", ""),
        core_summary_meta=profile.get("core_summary_meta", {}),
    )


@app.route("/set-consent", methods=["POST"])
def set_consent():
    subject = require_subject()
    if not subject:
        return redirect(url_for("index"))

    profile = load_or_create(subject)
    has_consent = request.form.get("has_consent") == "on"
    allow_remote = request.form.get("allow_remote_processing") == "on"

    profile.setdefault("consent", {})
    profile["consent"]["has_consent"] = bool(has_consent)
    profile["consent"]["consent_utc"] = datetime.now(timezone.utc).isoformat() if has_consent else None

    profile["consent"]["allow_remote_processing"] = bool(allow_remote)
    profile["consent"]["remote_consent_utc"] = datetime.now(timezone.utc).isoformat() if allow_remote else None

    save_profile(subject, profile)
    flash("Consent settings saved.")
    return redirect(url_for("dashboard"))


@app.route("/update-core-summary", methods=["POST"])
def update_core_summary_route():
    subject = require_subject()
    if not subject:
        return redirect(url_for("index"))

    profile = load_or_create(subject)

    if not profile.get("consent", {}).get("allow_remote_processing"):
        flash("Enable 'Allow remote processing' before generating core summary.")
        return redirect(url_for("dashboard"))

    profile = update_core_summary(profile, force=True)
    save_profile(subject, profile)

    meta = profile.get("core_summary_meta", {}) or {}
    flash(f"Core Summary updated (entries used: {meta.get('source_entry_count', 0)}).")
    return redirect(url_for("dashboard"))


@app.route("/interview/<category>", methods=["GET", "POST"])
def interview(category: str):
    subject = require_subject()
    if not subject:
        return redirect(url_for("index"))

    category = category.strip()
    if category not in QUESTIONS:
        flash("Unknown category.")
        return redirect(url_for("dashboard"))

    profile = load_or_create(subject)
    consent = profile.get("consent", {})
    if not consent.get("has_consent"):
        flash("Consent required before recording. Enable consent on dashboard.")
        return redirect(url_for("dashboard"))

    prompts: List[str] = QUESTIONS[category]
    idx = int(request.args.get("i", "0") or "0")
    idx = max(0, min(idx, len(prompts) - 1))
    prompt_text = prompts[idx]

    if request.method == "POST":
        answer = (request.form.get("answer") or "").strip()
        tags_raw = (request.form.get("tags") or "").strip()

        if not answer:
            flash("Answer cannot be empty (or click Skip).")
            return redirect(url_for("interview", category=category, i=idx))

        tags = [t.strip().lower() for t in tags_raw.split(",") if t.strip()]

        entry = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "category": category,
            "prompt": prompt_text,
            "answer": answer,
            "tags": tags,
        }

        profile.setdefault("entries", []).append(entry)
        save_profile(subject, profile)

        nxt = idx + 1
        if nxt >= len(prompts):
            flash(f"Saved. Finished category '{category}'.")
            return redirect(url_for("dashboard"))
        return redirect(url_for("interview", category=category, i=nxt))

    return render_template(
        "interview.html",
        subject=subject,
        category=category,
        idx=idx,
        total=len(prompts),
        prompt_text=prompt_text,
    )


@app.route("/interview/<category>/skip")
def interview_skip(category: str):
    subject = require_subject()
    if not subject:
        return redirect(url_for("index"))

    if category not in QUESTIONS:
        return redirect(url_for("dashboard"))

    prompts = QUESTIONS[category]
    idx = int(request.args.get("i", "0") or "0")
    idx = max(0, min(idx, len(prompts) - 1))

    nxt = idx + 1
    if nxt >= len(prompts):
        flash(f"Skipped. Finished category '{category}'.")
        return redirect(url_for("dashboard"))

    return redirect(url_for("interview", category=category, i=nxt))


@app.route("/guidance", methods=["GET", "POST"])
def guidance():
    subject = require_subject()
    if not subject:
        return redirect(url_for("index"))

    profile = load_or_create(subject)
    consent = profile.get("consent", {})
    has_key = bool(os.getenv("XAI_API_KEY", "").strip())

    if request.method == "POST":
        question = (request.form.get("question") or "").strip()
        if not question:
            flash("Ask a question.")
            return redirect(url_for("guidance"))

        if not has_key:
            flash("XAI_API_KEY is not set in this terminal/session.")
            return redirect(url_for("guidance"))

        if not consent.get("allow_remote_processing"):
            flash("Remote processing consent is required for guidance.")
            return redirect(url_for("guidance"))

        # Auto-refresh summary if enough new entries accumulated
        profile = update_core_summary(profile, force=False)
        save_profile(subject, profile)

        # Generate with full profile context (persistent memory)
        generated = generate_guidance_response(profile, question, k=3)
        profile.setdefault("entries", []).append(generated)
        save_profile(subject, profile)

        return render_template("guidance.html", subject=subject, answer=generated["answer"], question=question)

    return render_template("guidance.html", subject=subject, answer=None, question=None)


@app.route("/export", methods=["POST"])
def export():
    subject = require_subject()
    if not subject:
        return redirect(url_for("index"))

    profile = load_or_create(subject)
    out_path = write_summary_md(profile)
    flash(f"Exported summary -> {out_path}")
    return redirect(url_for("dashboard"))


@app.route("/upload-summary", methods=["POST"])
def upload_summary():
    subject = require_subject()
    if not subject:
        return redirect(url_for("index"))

    profile = load_or_create(subject)
    consent = profile.get("consent", {})

    if not consent.get("has_consent"):
        flash("Consent required before uploading summaries.")
        return redirect(url_for("dashboard"))

    if 'file' not in request.files or not request.files['file'].filename:
        flash("No file selected.")
        return redirect(url_for("dashboard"))

    file = request.files['file']
    try:
        path = save_upload(subject, file)
        extracted_entries = extract_from_upload(profile, path)
        if extracted_entries:
            profile.setdefault("entries", []).extend(extracted_entries)
            # Force update core summary after upload
            profile = update_core_summary(profile, force=True)
            # Optionally update identity anchor with new info (simple concatenation)
            if "identity_anchor" in profile and extracted_entries:
                new_text = " ".join(e["answer"] for e in extracted_entries if "answer" in e)
                profile["identity_anchor"]["answer"] += f"\n\nUpdated from recent upload: {new_text[:500]}..."
            save_profile(subject, profile)
            flash(f"Upload successful. {len(extracted_entries)} entry/entries added. Core summary refreshed.")
        else:
            flash("File was empty or could not be processed.")
        # Clean up the uploaded file
        path.unlink(missing_ok=True)
    except ValueError as ve:
        flash(f"Upload error: {str(ve)}")
    except Exception as e:
        flash("An error occurred during upload processing.")
        print(f"Upload processing error: {e}")

    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True)
