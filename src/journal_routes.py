
from datetime import date, datetime

from flask import (
    Blueprint,
    request,
    jsonify,
    session,
)

from flask_login import (
    login_required,
    current_user,
)

from database import get_profile

from journal_db import (
    create_journal,
    list_journals,
    get_journal,
    update_journal_design,
    create_journal_entry,
    list_journal_entries,
    get_journal_entry,
    save_journal_entry,
)


journal_bp = Blueprint(
    "written_journal",
    __name__,
    url_prefix="/api/journals",
)


# --------------------------------------------------
# Authorization
# --------------------------------------------------

def authorized_profile():

    profile_id = session.get("profile_id")

    if not profile_id:
        return None

    return get_profile(
        profile_id,
        current_user.id,
    )


def writing_allowed(record):

    profile = record.get("profile_data") or {}
    consent = profile.get("consent") or {}

    return bool(consent.get("has_consent"))


# --------------------------------------------------
# Response serialization
# --------------------------------------------------

def serialize_record(record):

    result = {}

    for key, value in record.items():

        if isinstance(value, (datetime, date)):
            result[key] = value.isoformat()
        else:
            result[key] = value

    return result


def error_response(message, status):

    return jsonify({
        "success": False,
        "error": message,
    }), status


# --------------------------------------------------
# Journal library
# --------------------------------------------------

@journal_bp.get("")
@login_required
def library():

    record = authorized_profile()

    if record is None:
        return error_response(
            "Profile access denied.",
            403,
        )

    journals = list_journals(
        record["id"],
        current_user.id,
    )

    return jsonify({
        "success": True,
        "journals": [
            serialize_record(journal)
            for journal in journals
        ],
    })


# --------------------------------------------------
# Create journal
# --------------------------------------------------

@journal_bp.post("")
@login_required
def create():

    record = authorized_profile()

    if record is None:
        return error_response(
            "Profile access denied.",
            403,
        )

    if not writing_allowed(record):
        return error_response(
            "Consent is required.",
            403,
        )

    title = request.form.get(
        "title",
        "My Journal",
    )

    subtitle = request.form.get(
        "subtitle",
        "",
    )

    try:

        journal = create_journal(
            record["id"],
            current_user.id,
            title,
            subtitle,
        )

    except ValueError as exc:
        return error_response(str(exc), 400)

    except PermissionError:
        return error_response(
            "Profile access denied.",
            403,
        )

    return jsonify({
        "success": True,
        "journal": serialize_record(journal),
    }), 201


# --------------------------------------------------
# Open journal
# --------------------------------------------------

@journal_bp.get("/<journal_id>")
@login_required
def detail(journal_id):

    record = authorized_profile()

    if record is None:
        return error_response(
            "Profile access denied.",
            403,
        )

    journal = get_journal(
        journal_id,
        record["id"],
        current_user.id,
    )

    if journal is None:
        return error_response(
            "Journal not found.",
            404,
        )

    entries = list_journal_entries(
        journal_id,
        record["id"],
        current_user.id,
    )

    return jsonify({
        "success": True,
        "journal": serialize_record(journal),
        "entries": [
            serialize_record(entry)
            for entry in entries
        ],
    })


# --------------------------------------------------
# Save journal design
# --------------------------------------------------

@journal_bp.post("/<journal_id>/design")
@login_required
def save_design(journal_id):

    record = authorized_profile()

    if record is None:
        return error_response(
            "Profile access denied.",
            403,
        )

    if not writing_allowed(record):
        return error_response(
            "Consent is required.",
            403,
        )

    fields = (
        "cover_style",
        "cover_color",
        "accent_color",
        "emblem",
        "typography",
        "paper_style",
        "page_layout",
    )

    design = {
        key: request.form[key]
        for key in fields
        if key in request.form
    }

    try:

        journal = update_journal_design(
            journal_id,
            record["id"],
            current_user.id,
            design,
        )

    except ValueError as exc:
        return error_response(str(exc), 400)

    except PermissionError:
        return error_response(
            "Journal access denied.",
            403,
        )

    return jsonify({
        "success": True,
        "journal": serialize_record(journal),
    })


# --------------------------------------------------
# Create written entry
# --------------------------------------------------

@journal_bp.post("/<journal_id>/entries")
@login_required
def create_entry(journal_id):

    record = authorized_profile()

    if record is None:
        return error_response(
            "Profile access denied.",
            403,
        )

    if not writing_allowed(record):
        return error_response(
            "Consent is required.",
            403,
        )

    try:

        entry = create_journal_entry(
            journal_id,
            record["id"],
            current_user.id,
        )

    except PermissionError:
        return error_response(
            "Journal access denied.",
            403,
        )

    return jsonify({
        "success": True,
        "entry": serialize_record(entry),
    }), 201


# --------------------------------------------------
# Open written entry
# --------------------------------------------------

@journal_bp.get("/entries/<entry_id>")
@login_required
def entry_detail(entry_id):

    record = authorized_profile()

    if record is None:
        return error_response(
            "Profile access denied.",
            403,
        )

    entry = get_journal_entry(
        entry_id,
        record["id"],
        current_user.id,
    )

    if entry is None:
        return error_response(
            "Entry not found.",
            404,
        )

    return jsonify({
        "success": True,
        "entry": serialize_record(entry),
    })


# --------------------------------------------------
# Save or finalize written entry
# --------------------------------------------------

@journal_bp.post("/entries/<entry_id>/save")
@login_required
def save_entry(entry_id):

    record = authorized_profile()

    if record is None:
        return error_response(
            "Profile access denied.",
            403,
        )

    if not writing_allowed(record):
        return error_response(
            "Consent is required.",
            403,
        )

    title = request.form.get("title", "")
    content = request.form.get("content", "")

    publish = (
        request.form.get("publish") == "true"
    )

    try:

        entry = save_journal_entry(
            entry_id,
            record["id"],
            current_user.id,
            title,
            content,
            publish=publish,
        )

        # Index finalized, authorized writing.
        # Autosave never triggers indexing.
        if (
            request.form.get("publish") == "true"
            and entry.get("allow_ai_processing")
        ):
            try:
                index_journal_entry(
                    entry["id"],
                    session.get("profile_id"),
                    current_user.id,
                )
            except Exception:
                # Preserve the saved entry if indexing fails.
                # The index endpoint allows retrying.
                pass


    except ValueError as exc:
        return error_response(str(exc), 400)

    except PermissionError:
        return error_response(
            "Entry unavailable for editing.",
            403,
        )

    return jsonify({
        "success": True,
        "entry": serialize_record(entry),
    })


# JOURNAL AI INTEGRATION

from journal_privacy import (
    set_entry_ai_preference,
    set_journal_ai_default,
    get_entry_ai_permission,
)

from journal_indexing import (
    index_journal_entry as _index_journal_entry,
    index_pending_journal_entries as _index_pending_journal_entries,
)

from memory_extraction import (
    extract_written_journal_memories,
)

from threading import Thread, Lock

_extraction_jobs = set()
_extraction_lock = Lock()



def schedule_journal_extraction(
    profile_id,
    owner_id,
    result,
):
    document_id = result.get("document_id")

    if not document_id:
        return

    with _extraction_lock:
        if document_id in _extraction_jobs:
            return

        if not begin_journal_learning(
            profile_id, owner_id, document_id
        ):
            return

        _extraction_jobs.add(document_id)

    def worker():
        try:
            outcome = extract_written_journal_memories(
                profile_id,
                owner_id,
                document_id,
            )

            if not isinstance(outcome, dict):
                raise RuntimeError("Extraction did not complete.")

            finish_journal_learning(
                profile_id,
                document_id,
                "complete",
                outcome,
            )

        except Exception:
            finish_journal_learning(
                profile_id,
                document_id,
                "failed",
            )

        finally:
            with _extraction_lock:
                _extraction_jobs.discard(document_id)

    try:
        Thread(target=worker, daemon=True).start()
    except Exception:
        with _extraction_lock:
            _extraction_jobs.discard(document_id)

        finish_journal_learning(
            profile_id, document_id, "failed"
        )
        raise


def index_journal_entry(
    entry_id,
    profile_id,
    owner_id,
):
    result = _index_journal_entry(
        entry_id,
        profile_id,
        owner_id,
    )

    schedule_journal_extraction(
        profile_id,
        owner_id,
        result,
    )

    return result


def index_pending_journal_entries(
    profile_id,
    owner_id,
    journal_id=None,
    limit=10,
):
    result = _index_pending_journal_entries(
        profile_id,
        owner_id,
        journal_id=journal_id,
        limit=limit,
    )

    for item in result["results"]:
        if item["status"] == "indexed":
            schedule_journal_extraction(
                profile_id,
                owner_id,
                item,
            )

    return result


@journal_bp.route(
    "/entries/<entry_id>/privacy",
    methods=["GET", "POST"],
)
@login_required
def entry_ai_privacy(entry_id):

    profile_id = session.get("profile_id")
    owner_id = current_user.id

    if not profile_id:
        return error_response(
            "No active profile.", 403
        )

    try:

        if request.method == "GET":
            result = get_entry_ai_permission(
                entry_id,
                profile_id,
                owner_id,
            )

            return jsonify(
                success=True,
                privacy=result,
            )

        preference = request.form.get(
            "ai_preference", ""
        )

        result = set_entry_ai_preference(
            entry_id,
            profile_id,
            owner_id,
            preference,
        )

        indexing = None

        if result.get("needs_indexing"):
            try:
                indexing = index_journal_entry(
                    entry_id,
                    profile_id,
                    owner_id,
                )
            except Exception:
                indexing = {
                    "status": "retry_required"
                }

        return jsonify(
            success=True,
            privacy=result,
            indexing=indexing,
        )

    except PermissionError:
        return error_response(
            "Journal access denied.", 403
        )

    except ValueError as error:
        return error_response(str(error), 400)


@journal_bp.route(
    "/<journal_id>/privacy",
    methods=["POST"],
)
@login_required
def journal_ai_privacy(journal_id):

    profile_id = session.get("profile_id")
    owner_id = current_user.id

    if not profile_id:
        return error_response(
            "No active profile.", 403
        )

    enabled = request.form.get(
        "ai_default_enabled"
    )

    if enabled not in ("true", "false"):
        return error_response(
            "Invalid AI setting.", 400
        )

    apply_existing = request.form.get(
        "apply_to_existing", "false"
    )

    if apply_existing not in ("true", "false"):
        return error_response(
            "Invalid entry setting.", 400
        )

    try:

        result = set_journal_ai_default(
            journal_id,
            profile_id,
            owner_id,
            enabled == "true",
            apply_existing == "true",
        )

        indexing = index_pending_journal_entries(
            profile_id,
            owner_id,
            journal_id=journal_id,
            limit=10,
        )

        return jsonify(
            success=True,
            privacy=result,
            indexing=indexing,
        )

    except PermissionError:
        return error_response(
            "Journal access denied.", 403
        )

    except ValueError as error:
        return error_response(str(error), 400)


@journal_bp.route(
    "/entries/<entry_id>/index",
    methods=["POST"],
)
@login_required
def index_written_entry(entry_id):

    profile_id = session.get("profile_id")
    owner_id = current_user.id

    if not profile_id:
        return error_response(
            "No active profile.", 403
        )

    try:

        result = index_journal_entry(
            entry_id,
            profile_id,
            owner_id,
        )

        return jsonify(
            success=True,
            indexing=result,
        )

    except PermissionError:
        return error_response(
            "AI processing is not authorized.",
            403,
        )

    except ValueError as error:
        return error_response(str(error), 400)

    except Exception:
        return error_response(
            "Indexing failed. Please retry.",
            503,
        )


# JOURNAL LEARNING STATUS

from database import database_connection
from journal_privacy import (
    lock_profile,
    load_entry_privacy,
    entry_is_eligible,
)
from psycopg.types.json import Jsonb


def begin_journal_learning(
    profile_id, owner_id, document_id
):
    with database_connection() as conn:
        with conn.cursor() as cur:
            lock_profile(cur, profile_id, owner_id)

            cur.execute(
                """
                SELECT metadata
                FROM knowledge_documents
                WHERE id = %s AND profile_id = %s
                FOR UPDATE
                """,
                (document_id, profile_id),
            )

            row = cur.fetchone()

            if not row:
                return False

            metadata = row["metadata"] or {}

            if metadata.get("origin") != "written_journal":
                return False

            entry = load_entry_privacy(
                cur,
                metadata["journal_entry_id"],
                profile_id,
                owner_id,
                lock=True,
            )

            if not (
                entry_is_eligible(entry)
                and entry["allow_ai_processing"]
                and entry["document_id"] == document_id
            ):
                return False

            if metadata.get("learning_status") == "complete":
                return False

            cur.execute(
                """
                UPDATE knowledge_documents
                SET metadata = metadata || %s
                WHERE id = %s AND profile_id = %s
                """,
                (
                    Jsonb({"learning_status": "processing"}),
                    document_id,
                    profile_id,
                ),
            )

            return True


def finish_journal_learning(
    profile_id, document_id, status, outcome=None
):
    with database_connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM knowledge_chunks
                WHERE document_id = %s
                """,
                (document_id,),
            )

            total = cur.fetchone()["total"]

            if status == "complete":
                processed = (outcome or {}).get(
                    "chunks_processed", 0
                )

                if not total or processed != total:
                    status = "failed"

            cur.execute(
                """
                UPDATE knowledge_documents
                SET metadata = metadata || %s
                WHERE id = %s
                  AND profile_id = %s
                  AND metadata ->> 'origin' = 'written_journal'
                """,
                (
                    Jsonb({"learning_status": status}),
                    document_id,
                    profile_id,
                ),
            )


@journal_bp.get("/entries/<entry_id>/learning")
@login_required
def entry_learning_status(entry_id):

    profile_id = session.get("profile_id")
    owner_id = current_user.id

    if not profile_id:
        return error_response("No active profile.", 403)

    try:
        with database_connection() as conn:
            with conn.cursor() as cur:

                lock_profile(cur, profile_id, owner_id)

                entry = load_entry_privacy(
                    cur,
                    entry_id,
                    profile_id,
                    owner_id,
                    lock=True,
                )

                status = "private"
                memory_count = 0
                searchable = False

                if entry["status"] != "published":
                    status = "draft"

                elif entry_is_eligible(entry):

                    status = "retry_required"

                    if (
                        entry["allow_ai_processing"]
                        and entry["document_id"]
                    ):
                        document_id = entry["document_id"]

                        cur.execute(
                            """
                            SELECT metadata
                            FROM knowledge_documents
                            WHERE id = %s
                              AND profile_id = %s
                              AND metadata ->> 'origin'
                                  = 'written_journal'
                              AND metadata ->> 'journal_entry_id'
                                  = %s
                            """,
                            (document_id, profile_id, entry_id),
                        )

                        document = cur.fetchone()

                        if document:
                            searchable = True
                            metadata = document["metadata"] or {}

                            cur.execute(
                                """
                                SELECT COUNT(*) AS total
                                FROM structured_memories
                                WHERE profile_id = %s
                                  AND source_document_id = %s
                                  AND status = 'approved'
                                """,
                                (profile_id, document_id),
                            )

                            memory_count = cur.fetchone()["total"]

                            if metadata.get("learning_status") == "complete":
                                status = "complete"
                            elif document_id in _extraction_jobs:
                                status = "processing"

                return jsonify(
                    success=True,
                    status=status,
                    memory_count=memory_count,
                    searchable=searchable,
                )

    except PermissionError:
        return error_response("Entry access denied.", 403)



# MASTER AI CONSENT STATUS

@journal_bp.get("/ai-consent")
@login_required
def journal_master_ai_consent():

    record = authorized_profile()

    if record is None:
        return error_response("Profile access denied.", 403)

    profile = record.get("profile_data") or {}
    consent = profile.get("consent") or {}

    enabled = (
        consent.get("has_consent") is True
        and consent.get("allow_remote_processing") is True
    )

    return jsonify(
        success=True,
        ai_enabled=enabled,
    )
