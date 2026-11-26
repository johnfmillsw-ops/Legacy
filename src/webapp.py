
from __future__ import annotations

import os
import sys
import secrets

from io import BytesIO
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from dotenv import load_dotenv

load_dotenv()

from flask import (
    Flask,
    redirect,
    render_template,
    request,
    session,
    url_for,
    flash,
    abort,
    send_file,
)

from flask_login import login_required, current_user

from auth import initialize_auth, csrf_token

from database import (
    initialize_database,
    create_profile,
    get_user_profiles,
    get_profile,
    load_profile_data,
    save_profile_data,
)

from storage import save_upload
from questions import QUESTIONS
from guidance import generate_guidance_response
from exporter import render_summary_md
from summarizer import (
    update_core_summary,
    extract_upload_text,
)
from index_knowledge import index_document


# --------------------------------------------------
# Application configuration
# --------------------------------------------------

app = Flask(__name__)

app.secret_key = (
    os.getenv("LEGACY_FLASK_SECRET")
    or secrets.token_hex(32)
)

app.config.update(
    MAX_CONTENT_LENGTH=101 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(
        os.getenv(
            "LEGACY_SECURE_COOKIES",
            "false",
        ).lower() == "true"
    ),
)

initialize_database()
initialize_auth(app)
from memory_review import memory_review_bp

app.register_blueprint(memory_review_bp)
from voice_journal_routes import voice_journal_bp

app.register_blueprint(voice_journal_bp)

# --------------------------------------------------
# Application-wide security
# --------------------------------------------------

@app.context_processor
def inject_csrf_token():
    return {"csrf_token": csrf_token}


@app.before_request
def protect_post_requests():

    if request.method == "POST":

        expected = session.get(
            "_csrf_token",
            "",
        )

        provided = request.form.get(
            "_csrf_token",
            "",
        )

        if not expected or not secrets.compare_digest(
            expected,
            provided,
        ):
            abort(403)


@app.after_request
def security_headers(response):

    response.headers[
        "X-Content-Type-Options"
    ] = "nosniff"

    response.headers[
        "X-Frame-Options"
    ] = "DENY"

    response.headers[
        "Referrer-Policy"
    ] = "no-referrer"


    if request.endpoint == "static" and response.status_code in (200, 304):

        response.headers["Cache-Control"] = (
            "public, max-age=3600, must-revalidate"
        )

    else:

        response.headers["Cache-Control"] = "no-store"

    return response



# --------------------------------------------------
# Profile initialization
# --------------------------------------------------

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def default_identity_anchor():

    return {
        "timestamp_utc": utc_now(),
        "category": "identity",
        "prompt": (
            "Who is this person? Provide a full, "
            "honest overview."
        ),
        "answer": "",
        "tags": [
            "identity",
            "self",
            "about_me",
            "core",
            "permanent",
        ],
    }


def ensure_profile(record):

    return {
        "meta": {
            "project": "Legacy",
            "version": "2.0-dev",
            "created_utc": utc_now(),
            "profile_id": record["id"],
            "owner_id": record["owner_id"],
        },
        "subject": {
            "display_name": record["display_name"],
        },
        "consent": {
            "has_consent": False,
            "consent_utc": None,
            "scope": "local_storage_only",
            "allow_remote_processing": False,
            "remote_consent_utc": None,
            "remote_vendor": "xAI",
        },
        "values": {},
        "stories": [],
        "guidance_principles": [
            "Base guidance on available evidence.",
            "Distinguish facts from assumptions.",
            "Acknowledge missing information.",
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
# Profile ownership enforcement
# --------------------------------------------------

def active_profile():

    if not current_user.is_authenticated:
        return None

    profile_id = session.get("profile_id")

    if not profile_id:
        return None

    record = get_profile(
        profile_id,
        current_user.id,
    )

    if record is None:
        session.pop("profile_id", None)

    return record



def load_or_create(record):

    if record is None or record["owner_id"] != current_user.id:
        abort(403)

    authorized = record

    profile = authorized["profile_data"]

    if not profile:

        profile = ensure_profile(authorized)

        save_profile_data(
            authorized["id"],
            current_user.id,
            profile,
        )

    meta = profile.get("meta", {})

    if (
        meta.get("owner_id") != current_user.id
        or meta.get("profile_id") != authorized["id"]
    ):
        abort(403)

    return profile



def save_profile(record, profile):

    try:

        save_profile_data(
            record["id"],
            current_user.id,
            profile,
        )

    except PermissionError:

        abort(403)


def remote_allowed(profile):

    consent = profile.get("consent", {})

    return bool(
        consent.get("has_consent")
        and consent.get("allow_remote_processing")
    )


def local_processing_allowed(profile):

    consent = profile.get("consent", {})

    return bool(
        consent.get("has_consent")
    )


# --------------------------------------------------
# Profile management
# --------------------------------------------------

@app.route("/", methods=["GET", "POST"])
@login_required
def index():

    if request.method == "POST":

        subject = (
            request.form.get("subject") or ""
        ).strip()

        if not subject or len(subject) > 120:

            flash(
                "Enter a profile name between "
                "1 and 120 characters."
            )

            return redirect(url_for("index"))

        record = create_profile(
            current_user.id,
            subject,
        )

        load_or_create(record)

        session["profile_id"] = record["id"]

        flash("Knowledge profile created.")

        return redirect(url_for("dashboard"))

    profiles = get_user_profiles(
        current_user.id
    )

    return render_template(
        "profiles.html",
        profiles=profiles,
    )


@app.route(
    "/profiles/<profile_id>/select",
    methods=["POST"],
)
@login_required
def select_profile(profile_id):

    record = get_profile(
        profile_id,
        current_user.id,
    )

    if record is None:
        abort(404)

    load_or_create(record)

    session["profile_id"] = record["id"]

    return redirect(url_for("dashboard"))


# --------------------------------------------------
# Dashboard
# --------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():

    record = active_profile()

    if record is None:
        return redirect(url_for("index"))

    profile = load_or_create(record)

    return render_template(
        "dashboard.html",
        subject=record["display_name"],
        entry_count=len(
            profile.get("entries", [])
        ),
        consent=profile.get("consent", {}),
        has_key=bool(
            os.getenv("XAI_API_KEY", "").strip()
        ),
        categories=list(QUESTIONS.keys()),
        core_summary=profile.get(
            "core_summary",
            "",
        ),
        core_summary_meta=profile.get(
            "core_summary_meta",
            {},
        ),
    )


# --------------------------------------------------
# Consent management
# --------------------------------------------------

@app.route("/set-consent", methods=["POST"])
@login_required
def set_consent():

    record = active_profile()

    if record is None:
        return redirect(url_for("index"))

    profile = load_or_create(record)

    has_consent = (
        request.form.get("has_consent") == "on"
    )

    allow_remote = (
        has_consent
        and request.form.get(
            "allow_remote_processing"
        ) == "on"
    )

    profile["consent"].update({
        "has_consent": has_consent,
        "consent_utc": (
            utc_now() if has_consent else None
        ),
        "allow_remote_processing": allow_remote,
        "remote_consent_utc": (
            utc_now() if allow_remote else None
        ),
    })

    save_profile(record, profile)

    flash("Consent settings saved.")

    return redirect(url_for("dashboard"))


# --------------------------------------------------
# Core summary
# --------------------------------------------------

@app.route(
    "/update-core-summary",
    methods=["POST"],
)
@login_required
def update_core_summary_route():

    record = active_profile()

    if record is None:
        return redirect(url_for("index"))

    profile = load_or_create(record)

    if not remote_allowed(profile):

        flash(
            "Local and remote processing consent "
            "are required."
        )

        return redirect(url_for("dashboard"))

    try:

        profile = update_core_summary(
            profile,
            force=True,
        )

        save_profile(record, profile)

        flash("Core summary refresh completed.")

    except Exception:

        app.logger.exception(
            "Core summary refresh failed."
        )

        flash("Unable to refresh core summary.")

    return redirect(url_for("dashboard"))


# --------------------------------------------------
# Interview utilities
# --------------------------------------------------

def question_index(prompts):

    try:

        idx = int(
            request.args.get("i", "0") or "0"
        )

    except ValueError:

        idx = 0

    return max(
        0,
        min(idx, len(prompts) - 1),
    )


# --------------------------------------------------
# Interview system
# --------------------------------------------------

@app.route(
    "/interview/<category>",
    methods=["GET", "POST"],
)
@login_required
def interview(category):

    record = active_profile()

    if record is None:
        return redirect(url_for("index"))

    if category not in QUESTIONS:

        flash("Unknown interview category.")

        return redirect(url_for("dashboard"))

    profile = load_or_create(record)

    if not local_processing_allowed(profile):

        flash(
            "Consent is required before "
            "recording responses."
        )

        return redirect(url_for("dashboard"))

    prompts = QUESTIONS[category]

    if not prompts:
        return redirect(url_for("dashboard"))

    idx = question_index(prompts)

    prompt_text = prompts[idx]

    if request.method == "POST":

        answer = (
            request.form.get("answer") or ""
        ).strip()

        tags_raw = (
            request.form.get("tags") or ""
        ).strip()

        if not answer or len(answer) > 20000:

            flash(
                "Enter an answer between "
                "1 and 20,000 characters."
            )

            return redirect(
                url_for(
                    "interview",
                    category=category,
                    i=idx,
                )
            )

        tags = [
            tag.strip().lower()[:100]
            for tag in tags_raw.split(",")
            if tag.strip()
        ][:30]

        entry = {
            "timestamp_utc": utc_now(),
            "category": category,
            "prompt": prompt_text,
            "answer": answer,
            "tags": tags,
        }

        profile.setdefault(
            "entries",
            [],
        ).append(entry)

        save_profile(record, profile)

        nxt = idx + 1

        if nxt >= len(prompts):

            flash(
                f"Finished category '{category}'."
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
        subject=record["display_name"],
        category=category,
        idx=idx,
        total=len(prompts),
        prompt_text=prompt_text,
    )


# --------------------------------------------------
# Skip interview question
# --------------------------------------------------

@app.route("/interview/<category>/skip")
@login_required
def interview_skip(category):

    record = active_profile()

    if record is None:
        return redirect(url_for("index"))

    if category not in QUESTIONS:
        return redirect(url_for("dashboard"))

    profile = load_or_create(record)

    if not local_processing_allowed(profile):
        return redirect(url_for("dashboard"))

    prompts = QUESTIONS[category]

    if not prompts:
        return redirect(url_for("dashboard"))

    nxt = question_index(prompts) + 1

    if nxt >= len(prompts):
        return redirect(url_for("dashboard"))

    return redirect(
        url_for(
            "interview",
            category=category,
            i=nxt,
        )
    )


# --------------------------------------------------
# AI guidance with semantic retrieval
# --------------------------------------------------

@app.route("/guidance", methods=["GET", "POST"])
@login_required
def guidance():

    record = active_profile()

    if record is None:
        return redirect(url_for("index"))

    profile = load_or_create(record)

    if request.method == "POST":

        question = (
            request.form.get("question") or ""
        ).strip()

        if not question or len(question) > 4000:

            flash(
                "Enter a question between "
                "1 and 4,000 characters."
            )

            return redirect(url_for("guidance"))

        if not remote_allowed(profile):

            flash(
                "Local and remote consent "
                "are required for AI guidance."
            )

            return redirect(url_for("guidance"))

        if not os.getenv("XAI_API_KEY", "").strip():

            flash("XAI_API_KEY is not configured.")

            return redirect(url_for("guidance"))

        try:

            profile = update_core_summary(
                profile,
                force=False,
            )

            generated = generate_guidance_response(
                profile=profile,
                question=question,
                k=3,
                profile_id=record["id"],
                owner_id=current_user.id,
            )

            profile.setdefault(
                "entries",
                [],
            ).append(generated)

            save_profile(record, profile)

            return render_template(
                "guidance.html",
                subject=record["display_name"],
                answer=generated["answer"],
                question=question,
            )

        except Exception:

            app.logger.exception(
                "Guidance generation failed."
            )

            flash(
                "Unable to generate guidance. "
                "Please try again."
            )

            return redirect(url_for("guidance"))

    return render_template(
        "guidance.html",
        subject=record["display_name"],
        answer=None,
        question=None,
    )


# --------------------------------------------------
# Private profile export
# --------------------------------------------------

@app.route("/export", methods=["POST"])
@login_required
def export():

    record = active_profile()

    if record is None:
        return redirect(url_for("index"))

    profile = load_or_create(record)

    markdown = render_summary_md(profile)

    output = BytesIO(
        markdown.encode("utf-8")
    )

    return send_file(
        output,
        mimetype="text/markdown",
        as_attachment=True,
        download_name=(
            f"legacy_{record['id']}.md"
        ),
    )


# --------------------------------------------------
# Document ingestion with semantic indexing
# --------------------------------------------------

@app.route(
    "/upload-summary",
    methods=["POST"],
)
@login_required
def upload_summary():

    record = active_profile()

    if record is None:
        return redirect(url_for("index"))

    profile = load_or_create(record)

    # Local consent is sufficient for local indexing.
    # Remote processing consent is checked separately
    # before any document content is sent to Grok.
    if not local_processing_allowed(profile):

        flash(
            "Consent is required before "
            "uploading documents."
        )

        return redirect(url_for("dashboard"))

    file = request.files.get("file")

    if file is None or not file.filename:

        flash("No file selected.")

        return redirect(url_for("dashboard"))

    original_filename = Path(
        file.filename
    ).name

    path = None

    try:

        # Save to a temporary application upload path.
        # The existing storage module validates extensions.
        path = save_upload(
            record["id"],
            file,
        )

        # Extract the complete available text.
        # No character-based truncation.
        original_text = extract_upload_text(
            path
        )

        # Recheck current consent before indexing.
        latest_record = get_profile(
            record["id"],
            current_user.id,
        )

        if latest_record is None:
            abort(403)

        latest_profile = latest_record[
            "profile_data"
        ]

        if not local_processing_allowed(
            latest_profile
        ):
            abort(403)

        # Store the original text and its searchable
        # embeddings in PostgreSQL atomically.
        result = index_document(
            profile_id=record["id"],
            owner_id=current_user.id,
            title=original_filename,
            original_text=original_text,
            source_type="document",
            metadata={
                "original_filename": original_filename,
                "file_extension": path.suffix.lower(),
                "ingestion_method": "web_upload",
            },
            processing_authorized=True,
        )

        # Extract memories automatically after successful indexing.
        # Run separately so the upload request does not wait for Grok.
        from threading import Thread
        from memory_extraction import (
            extract_document_memories,
            find_document,
        )

        uploaded_document = find_document(
            record["id"],
            original_filename,
        )

        if uploaded_document is None:
            app.logger.error(
                "Indexed document could not be found for extraction."
            )
        elif remote_allowed(latest_profile):
            extraction_profile_id = record["id"]
            extraction_owner_id = current_user.id
            extraction_document_id = uploaded_document["id"]
            extraction_chunk_count = result["chunk_count"]

            def process_uploaded_memories():
                try:
                    extract_document_memories(
                        profile_id=extraction_profile_id,
                        owner_id=extraction_owner_id,
                        document_id=extraction_document_id,
                        max_chunks=extraction_chunk_count,
                    )
                except Exception:
                    app.logger.exception(
                        "Automatic memory extraction failed."
                    )

            Thread(
                target=process_uploaded_memories,
                daemon=True,
            ).start()
        else:
            app.logger.info(
                "Document indexed locally; remote extraction disabled."
            )

        # Do not duplicate the complete document
        # inside profile_data JSONB.
        #
        # The document and all searchable chunks
        # now live in PostgreSQL.
        #
        # Core summaries can be refreshed separately
        # through the existing dashboard action.

        flash(
            "Document indexed successfully. "
            f"{result['chunk_count']} searchable "
            "chunks created."
        )

    except ValueError as error:

        flash(f"Upload error: {error}")

    except PermissionError:

        abort(403)

    except Exception:

        app.logger.exception(
            "Document ingestion failed."
        )

        flash(
            "Unable to process or index "
            "the document."
        )

    finally:

        # Remove the temporary uploaded file.
        # The extracted text is preserved in PostgreSQL
        # after successful indexing.
        if path is not None:
            path.unlink(missing_ok=True)

    return redirect(url_for("dashboard"))


# --------------------------------------------------
# Health check
# --------------------------------------------------

@app.route("/health")
def health():

    return {"status": "ok"}, 200


# --------------------------------------------------
# Local development server
# --------------------------------------------------

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
    )
