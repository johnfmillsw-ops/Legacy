
from __future__ import annotations

import math

from threading import Thread

from flask import (
    Blueprint,
    request,
    jsonify,
    session,
    send_file,
    current_app,
    url_for,
)

from flask_login import login_required, current_user

from database import get_profile

from voice_storage import (
    save_voice_recording,
    resolve_voice_recording,
    delete_voice_recording,
)

from voice_journal_db import (
    generate_journal_id,
    create_voice_journal,
    get_voice_journal,
    list_voice_journals,
    save_voice_transcript,
    update_voice_transcript,
    approve_voice_transcript,
)

from transcription import transcribe_audio


voice_journal_bp = Blueprint(
    "voice_journal",
    __name__,
    url_prefix="/voice-journal",
)


# --------------------------------------------------
# Profile authorization
# --------------------------------------------------

def authorized_profile():

    profile_id = session.get("profile_id")

    if not profile_id:
        return None

    return get_profile(
        profile_id,
        current_user.id,
    )


# --------------------------------------------------
# Recording consent
# --------------------------------------------------

def recording_allowed(record):

    profile = record.get("profile_data") or {}
    consent = profile.get("consent") or {}

    return bool(consent.get("has_consent"))


# --------------------------------------------------
# Serialize journal data
# --------------------------------------------------

def serialize_journal(journal, include_transcript=False):

    result = {
        "id": journal["id"],
        "title": journal["title"],
        "status": journal["status"],
        "file_size_bytes": journal["file_size_bytes"],
        "duration_seconds": journal["duration_seconds"],
        "document_id": journal.get("document_id"),
        "created_utc": journal["created_utc"].isoformat(),
        "updated_utc": journal["updated_utc"].isoformat(),
        "audio_url": url_for(
            "voice_journal.play_recording",
            journal_id=journal["id"],
        ),
    }

    if include_transcript:

        result.update({
            "transcript": journal.get("transcript"),
            "original_transcript": journal.get(
                "original_transcript"
            ),
            "transcription_model": journal.get(
                "transcription_model"
            ),
            "transcription_language": journal.get(
                "transcription_language"
            ),
        })

    return result


# --------------------------------------------------
# Background transcription
# --------------------------------------------------

def process_voice_journal(
    app,
    journal_id,
    profile_id,
    owner_id,
):

    with app.app_context():

        try:

            journal = get_voice_journal(
                journal_id=journal_id,
                profile_id=profile_id,
                owner_id=owner_id,
            )

            if journal is None:
                return

            if journal["status"] != "uploaded":
                return

            profile = get_profile(
                profile_id,
                owner_id,
            )

            if profile is None or not recording_allowed(profile):
                return

            path = resolve_voice_recording(
                profile_id=profile_id,
                journal_id=journal_id,
                audio_path=journal["audio_path"],
            )

            result = transcribe_audio(path)

            save_voice_transcript(
                journal_id=journal_id,
                profile_id=profile_id,
                owner_id=owner_id,
                result=result,
            )

            app.logger.info(
                "Voice journal transcribed: %s",
                journal_id,
            )

        except Exception:

            app.logger.exception(
                "Voice journal transcription failed: %s",
                journal_id,
            )


# --------------------------------------------------
# Upload voice recording
# --------------------------------------------------

@voice_journal_bp.route("/upload", methods=["POST"])
@login_required
def upload_recording():

    record = authorized_profile()

    if record is None:

        return jsonify({
            "error": "Profile access denied."
        }), 403

    if not recording_allowed(record):

        return jsonify({
            "error": "Recording consent is required."
        }), 403

    profile_id = record["id"]
    owner_id = current_user.id

    file = request.files.get("audio")

    if file is None or not file.filename:

        return jsonify({
            "error": "No audio recording provided."
        }), 400

    title = request.form.get("title", "").strip()

    if len(title) > 200:

        return jsonify({
            "error": "Title exceeds 200 characters."
        }), 400

    duration = request.form.get("duration_seconds")
    duration_seconds = None

    if duration:

        try:

            duration_seconds = float(duration)

            if (
                not math.isfinite(duration_seconds)
                or duration_seconds < 0
                or duration_seconds > 3600
            ):
                raise ValueError()

        except ValueError:

            return jsonify({
                "error": "Invalid recording duration."
            }), 400

    journal_id = generate_journal_id()
    stored_audio = None

    try:

        stored_audio = save_voice_recording(
            profile_id=profile_id,
            journal_id=journal_id,
            file=file,
        )

        latest_record = get_profile(
            profile_id,
            owner_id,
        )

        if (
            latest_record is None
            or not recording_allowed(latest_record)
        ):

            raise PermissionError(
                "Recording authorization denied."
            )

        journal = create_voice_journal(
            journal_id=journal_id,
            profile_id=profile_id,
            owner_id=owner_id,
            title=title,
            audio_path=stored_audio["audio_path"],
            original_filename=stored_audio["original_filename"],
            mime_type=stored_audio["mime_type"],
            file_size_bytes=stored_audio["file_size_bytes"],
            duration_seconds=duration_seconds,
            metadata={
                "ingestion_method": "voice_journal"
            },
        )

    except Exception as error:

        if stored_audio is not None:

            try:

                delete_voice_recording(
                    profile_id,
                    journal_id,
                    stored_audio["audio_path"],
                )

            except Exception:

                current_app.logger.exception(
                    "Voice journal cleanup failed."
                )

        if isinstance(error, ValueError):

            return jsonify({
                "error": str(error)
            }), 400

        if isinstance(error, PermissionError):

            return jsonify({
                "error": "Recording authorization denied."
            }), 403

        current_app.logger.exception(
            "Voice journal upload failed."
        )

        return jsonify({
            "error": "Unable to save recording."
        }), 500

    transcription_started = False

    try:

        transcription_thread = Thread(
            target=process_voice_journal,
            args=(
                current_app._get_current_object(),
                journal_id,
                profile_id,
                owner_id,
            ),
            daemon=True,
        )

        transcription_thread.start()

        transcription_started = True

    except Exception:

        current_app.logger.exception(
            "Unable to start transcription: %s",
            journal_id,
        )

    return jsonify({
        "success": True,
        "transcription_started": transcription_started,
        "journal": serialize_journal(journal),
    }), 201


# --------------------------------------------------
# List saved voice journals
# --------------------------------------------------

@voice_journal_bp.route("/list", methods=["GET"])
@login_required
def journal_history():

    record = authorized_profile()

    if record is None:

        return jsonify({
            "error": "Profile access denied."
        }), 403

    journals = list_voice_journals(
        profile_id=record["id"],
        owner_id=current_user.id,
    )

    return jsonify({
        "journals": [
            serialize_journal(journal)
            for journal in journals
        ]
    })


# --------------------------------------------------
# Retrieve individual journal and transcript
# --------------------------------------------------

@voice_journal_bp.route(
    "/<journal_id>",
    methods=["GET"],
)
@login_required
def journal_details(journal_id):

    record = authorized_profile()

    if record is None:

        return jsonify({
            "error": "Profile access denied."
        }), 403

    journal = get_voice_journal(
        journal_id=journal_id,
        profile_id=record["id"],
        owner_id=current_user.id,
    )

    if journal is None:

        return jsonify({
            "error": "Journal not found."
        }), 404

    return jsonify({
        "journal": serialize_journal(
            journal,
            include_transcript=True,
        )
    })


# --------------------------------------------------
# Edit generated transcript
# --------------------------------------------------

@voice_journal_bp.route(
    "/<journal_id>/transcript",
    methods=["POST"],
)
@login_required
def edit_transcript(journal_id):

    record = authorized_profile()

    if record is None:

        return jsonify({
            "error": "Profile access denied."
        }), 403

    if not recording_allowed(record):

        return jsonify({
            "error": "Processing consent is required."
        }), 403

    transcript = request.form.get("transcript")

    try:

        journal = update_voice_transcript(
            journal_id=journal_id,
            profile_id=record["id"],
            owner_id=current_user.id,
            transcript=transcript,
        )

    except ValueError as error:

        return jsonify({
            "error": str(error)
        }), 400

    except Exception:

        current_app.logger.exception(
            "Transcript update failed."
        )

        return jsonify({
            "error": "Unable to update transcript."
        }), 500

    return jsonify({
        "success": True,
        "journal": serialize_journal(
            journal,
            include_transcript=True,
        ),
    })


# --------------------------------------------------
# Approve transcript
# --------------------------------------------------

@voice_journal_bp.route(
    "/<journal_id>/approve",
    methods=["POST"],
)
@login_required
def approve_transcript(journal_id):

    record = authorized_profile()

    if record is None:

        return jsonify({
            "error": "Profile access denied."
        }), 403

    if not recording_allowed(record):

        return jsonify({
            "error": "Processing consent is required."
        }), 403

    transcript = request.form.get("transcript")

    try:

        journal = approve_voice_transcript(
            journal_id=journal_id,
            profile_id=record["id"],
            owner_id=current_user.id,
            transcript=transcript,
        )

    except ValueError as error:

        return jsonify({
            "error": str(error)
        }), 400

    except Exception:

        current_app.logger.exception(
            "Transcript approval failed."
        )

        return jsonify({
            "error": "Unable to approve transcript."
        }), 500

    return jsonify({
        "success": True,
        "journal": serialize_journal(
            journal,
            include_transcript=True,
        ),
    })


# --------------------------------------------------
# Play original audio recording
# --------------------------------------------------

@voice_journal_bp.route(
    "/audio/<journal_id>",
    methods=["GET"],
)
@login_required
def play_recording(journal_id):

    record = authorized_profile()

    if record is None:

        return jsonify({
            "error": "Profile access denied."
        }), 403

    journal = get_voice_journal(
        journal_id=journal_id,
        profile_id=record["id"],
        owner_id=current_user.id,
    )

    if journal is None:

        return jsonify({
            "error": "Recording not found."
        }), 404

    try:

        path = resolve_voice_recording(
            profile_id=record["id"],
            journal_id=journal_id,
            audio_path=journal["audio_path"],
        )

    except (
        FileNotFoundError,
        PermissionError,
        ValueError,
    ):

        return jsonify({
            "error": "Audio file unavailable."
        }), 404

    return send_file(
        path,
        mimetype=journal["mime_type"],
        conditional=True,
        as_attachment=False,
        download_name=path.name,
    )
