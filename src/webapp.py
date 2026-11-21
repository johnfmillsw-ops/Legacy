
from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from flask import (
    Flask,
    redirect,
    render_template,
    request,
    session,
    url_for,
    flash,
)

from storage import (
    load_json,
    profile_path,
    save_json,
    save_upload,
)

from questions import QUESTIONS
from guidance import generate_guidance_response
from exporter import write_summary_md
from summarizer import update_core_summary, extract_from_upload


# --------------------------------------------------
# Application configuration
# --------------------------------------------------

app = Flask(__name__)

app.secret_key = os.getenv(
    "LEGACY_FLASK_SECRET",
    "dev-secret-change-me",
)


# --------------------------------------------------
# Default identity anchor
# --------------------------------------------------

def default_identity_anchor() -> Dict[str, Any]:
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "category": "identity",
        "prompt": "Who is this person? Provide a full, honest overview.",
        "answer": "",
        "tags": [
            "identity",
            "self",
            "about_me",
            "core",
            "permanent",
        ],
    }


# --------------------------------------------------
# New profile initialization
# --------------------------------------------------

def ensure_profile(subject: str) -> Dict[str, Any]:
    return {
        "meta": {
            "project": "Legacy",
            "version": "0.7.0-web",
            "created_utc": datetime.now(timezone.utc).isoformat(),
        },
        "subject": {
            "display_name": subject,
        },
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
        "identity_anchor": default_identity_anchor(),
    }


# --------------------------------------------------
# Profile loading and migration
# --------------------------------------------------

def load_or_create(subject: str) -> Dict[str, Any]:
    path = profile_path(subject)

    try:
        profile = load_json(path)

    except FileNotFoundError:
        profile = ensure_profile(subject)
        save_json(path, profile)
        return profile

    defaults = ensure_profile(subject)
    changed = False

    # Restore missing top-level fields
    for key, value in defaults.items():
        if key not in profile:
            profile[key] = value
            changed = True

    # Repair missing or invalid identity anchor
    if not isinstance(profile.get("identity_anchor"), dict):
        profile["identity_anchor"] = default_identity_anchor()
        changed = True

    # Restore missing identity anchor fields
    for key, value in defaults["identity_anchor"].items():
        if key not in profile["identity_anchor"]:
            profile["identity_anchor"][key] = value
            changed = True

    if changed:
        save_json(path, profile)

    return profile


def save_profile(
    subject: str,
    profile: Dict[str, Any],
) -> None:
    save_json(profile_path(subject), profile)


def require_subject() -> str:
    subject = session.get("subject")
    return str(subject).strip() if subject else ""


# --------------------------------------------------
# Home page
# --------------------------------------------------

@app.route("/", methods=["GET", "POST"])
def index():

    if request.method == "POST":

        subject = (
            request.form.get("subject") or ""
        ).strip()

        if not subject:
            flash("Enter a subject name.")
            return redirect(url_for("index"))

        load_or_create(subject)

        session["subject"] = subject

        return redirect(url_for("dashboard"))

    return render_template("index.html")


# --------------------------------------------------
# Dashboard
# --------------------------------------------------

@app.route("/dashboard")
def dashboard():

    subject = require_subject()

    if not subject:
        return redirect(url_for("index"))

    profile = load_or_create(subject)

    consent = profile.get("consent", {})
    entries = profile.get("entries", [])

    has_key = bool(
        os.getenv("XAI_API_KEY", "").strip()
    )

    return render_template(
        "dashboard.html",
        subject=subject,
        entry_count=len(entries),
        consent=consent,
        has_key=has_key,
        categories=list(QUESTIONS.keys()),
        core_summary=profile.get("core_summary", ""),
        core_summary_meta=profile.get(
            "core_summary_meta",
            {},
        ),
    )


# --------------------------------------------------
# Consent management
# --------------------------------------------------

@app.route("/set-consent", methods=["POST"])
def set_consent():

    subject = require_subject()

    if not subject:
        return redirect(url_for("index"))

    profile = load_or_create(subject)

    has_consent = (
        request.form.get("has_consent") == "on"
    )

    allow_remote = (
        request.form.get("allow_remote_processing") == "on"
    )

    profile.setdefault("consent", {})

    profile["consent"]["has_consent"] = bool(
        has_consent
    )

    profile["consent"]["consent_utc"] = (
        datetime.now(timezone.utc).isoformat()
        if has_consent
        else None
    )

    profile["consent"]["allow_remote_processing"] = bool(
        allow_remote
    )

    profile["consent"]["remote_consent_utc"] = (
        datetime.now(timezone.utc).isoformat()
        if allow_remote
        else None
    )

    save_profile(subject, profile)

    flash("Consent settings saved.")

    return redirect(url_for("dashboard"))


# --------------------------------------------------
# Core summary
# --------------------------------------------------

@app.route("/update-core-summary", methods=["POST"])
def update_core_summary_route():

    subject = require_subject()

    if not subject:
        return redirect(url_for("index"))

    profile = load_or_create(subject)

    if not profile.get("consent", {}).get(
        "allow_remote_processing"
    ):
        flash(
            "Enable 'Allow remote processing' "
            "before generating core summary."
        )

        return redirect(url_for("dashboard"))

    profile = update_core_summary(
        profile,
        force=True,
    )

    save_profile(subject, profile)

    meta = profile.get("core_summary_meta", {}) or {}

    flash(
        "Core Summary updated "
        f"(entries used: {meta.get('source_entry_count', 0)})."
    )

    return redirect(url_for("dashboard"))


# --------------------------------------------------
# Interview system
# --------------------------------------------------

@app.route(
    "/interview/<category>",
    methods=["GET", "POST"],
)
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
        flash(
            "Consent required before recording. "
            "Enable consent on dashboard."
        )

        return redirect(url_for("dashboard"))

    prompts: List[str] = QUESTIONS[category]

    try:
        idx = int(request.args.get("i", "0") or "0")

    except ValueError:
        idx = 0

    idx = max(0, min(idx, len(prompts) - 1))

    prompt_text = prompts[idx]

    if request.method == "POST":

        answer = (
            request.form.get("answer") or ""
        ).strip()

        tags_raw = (
            request.form.get("tags") or ""
        ).strip()

        if not answer:
            flash("Answer cannot be empty (or click Skip).")

            return redirect(
                url_for(
                    "interview",
                    category=category,
                    i=idx,
                )
            )

        tags = [
            tag.strip().lower()
            for tag in tags_raw.split(",")
            if tag.strip()
        ]

        entry = {
            "timestamp_utc": (
                datetime.now(timezone.utc).isoformat()
            ),
            "category": category,
            "prompt": prompt_text,
            "answer": answer,
            "tags": tags,
        }

        profile.setdefault("entries", []).append(entry)

        save_profile(subject, profile)

        nxt = idx + 1

        if nxt >= len(prompts):

            flash(
                f"Saved. Finished category '{category}'."
            )

            return redirect(url_for("dashboard"))

        return redirect(
            url_for(
                "interview",
                category=category,
                i=nxt,
            )
        )

    return render_template(
        "interview.html",
        subject=subject,
        category=category,
        idx=idx,
        total=len(prompts),
        prompt_text=prompt_text,
    )


# --------------------------------------------------
# Skip interview question
# --------------------------------------------------

@app.route("/interview/<category>/skip")
def interview_skip(category: str):

    subject = require_subject()

    if not subject:
        return redirect(url_for("index"))

    if category not in QUESTIONS:
        return redirect(url_for("dashboard"))

    prompts = QUESTIONS[category]

    try:
        idx = int(request.args.get("i", "0") or "0")

    except ValueError:
        idx = 0

    idx = max(0, min(idx, len(prompts) - 1))

    nxt = idx + 1

    if nxt >= len(prompts):

        flash(
            f"Skipped. Finished category '{category}'."
        )

        return redirect(url_for("dashboard"))

    return redirect(
        url_for(
            "interview",
            category=category,
            i=nxt,
        )
    )


# --------------------------------------------------
# AI guidance
# --------------------------------------------------

@app.route("/guidance", methods=["GET", "POST"])
def guidance():

    subject = require_subject()

    if not subject:
        return redirect(url_for("index"))

    profile = load_or_create(subject)

    consent = profile.get("consent", {})

    has_key = bool(
        os.getenv("XAI_API_KEY", "").strip()
    )

    if request.method == "POST":

        question = (
            request.form.get("question") or ""
        ).strip()

        if not question:
            flash("Ask a question.")
            return redirect(url_for("guidance"))

        if not has_key:
            flash(
                "XAI_API_KEY is not set "
                "in this terminal/session."
            )

            return redirect(url_for("guidance"))

        if not consent.get("allow_remote_processing"):
            flash(
                "Remote processing consent "
                "is required for guidance."
            )

            return redirect(url_for("guidance"))

        profile = update_core_summary(
            profile,
            force=False,
        )

        save_profile(subject, profile)

        generated = generate_guidance_response(
            profile,
            question,
            k=3,
        )

        profile.setdefault("entries", []).append(
            generated
        )

        save_profile(subject, profile)

        return render_template(
            "guidance.html",
            subject=subject,
            answer=generated["answer"],
            question=question,
        )

    return render_template(
        "guidance.html",
        subject=subject,
        answer=None,
        question=None,
    )


# --------------------------------------------------
# Profile export
# --------------------------------------------------

@app.route("/export", methods=["POST"])
def export():

    subject = require_subject()

    if not subject:
        return redirect(url_for("index"))

    profile = load_or_create(subject)

    out_path = write_summary_md(profile)

    flash(f"Exported summary -> {out_path}")

    return redirect(url_for("dashboard"))


# --------------------------------------------------
# Document ingestion
# --------------------------------------------------

@app.route("/upload-summary", methods=["POST"])
def upload_summary():

    subject = require_subject()

    if not subject:
        return redirect(url_for("index"))

    profile = load_or_create(subject)

    consent = profile.get("consent", {})

    if not consent.get("has_consent"):

        flash(
            "Consent required before uploading summaries."
        )

        return redirect(url_for("dashboard"))

    if (
        "file" not in request.files
        or not request.files["file"].filename
    ):
        flash("No file selected.")
        return redirect(url_for("dashboard"))

    file = request.files["file"]
    path = None

    try:

        path = save_upload(subject, file)

        extracted_entries = extract_from_upload(
            profile,
            path,
        )

        if extracted_entries:

            profile.setdefault("entries", []).extend(
                extracted_entries
            )

            # Only process remotely with consent
            if consent.get("allow_remote_processing"):

                profile = update_core_summary(
                    profile,
                    force=True,
                )

            new_text = " ".join(
                str(entry.get("answer", ""))
                for entry in extracted_entries
                if entry.get("answer")
            )

            if new_text:

                previous_answer = str(
                    profile["identity_anchor"].get(
                        "answer",
                        "",
                    )
                )

                profile["identity_anchor"]["answer"] = (
                    previous_answer
                    + "\n\nUpdated from recent upload: "
                    + new_text[:500]
                ).strip()

            save_profile(subject, profile)

            flash(
                "Upload successful. "
                f"{len(extracted_entries)} "
                "entry/entries added."
            )

        else:

            flash(
                "File was empty or could not be processed."
            )

    except ValueError as error:

        flash(f"Upload error: {str(error)}")

    except Exception:

        app.logger.exception(
            "Upload processing failed."
        )

        flash(
            "An error occurred during upload processing."
        )

    finally:

        if path is not None:
            path.unlink(missing_ok=True)

    return redirect(url_for("dashboard"))


# --------------------------------------------------
# Local development server
# --------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
