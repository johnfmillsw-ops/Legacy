from functools import wraps
import json

from flask import (
    Blueprint,
    jsonify,
    request,
    session,
)

from flask_login import current_user

from database import get_profile

from personality_baseline import get_assessment

from personality_baseline_storage import (
    get_or_create_draft,
    save_draft,
    complete_assessment,
    get_assessment_history,
    get_latest_baseline,
)


baseline_bp = Blueprint(
    "personality_baseline",
    __name__,
    url_prefix="/api/personality/baseline",
)


def authorized_profile(function):
    @wraps(function)
    def wrapped(*args, **kwargs):

        if not current_user.is_authenticated:
            return jsonify(
                error="Authentication required."
            ), 401

        profile_id = session.get("profile_id")

        if not profile_id:
            return jsonify(
                error="Select a profile first."
            ), 403

        profile = get_profile(
            profile_id,
            current_user.id,
        )

        if profile is None:
            return jsonify(
                error="Profile access denied."
            ), 403

        data = profile.get("profile_data") or {}
        consent = data.get("consent") or {}

        if not consent.get("has_consent"):
            return jsonify(
                error="Local processing consent required."
            ), 403

        try:
            return function(
                profile_id,
                current_user.id,
                *args,
                **kwargs,
            )

        except PermissionError:
            return jsonify(
                error="Profile access denied."
            ), 403

        except ValueError as error:
            return jsonify(error=str(error)), 400

    return wrapped


def serialize_assessment(record):
    if record is None:
        return None

    fields = (
        "id",
        "instrument_id",
        "instrument_version",
        "status",
        "responses",
        "raw_scores",
        "normalized_scores",
        "instrument_metadata",
        "created_utc",
        "updated_utc",
        "completed_utc",
    )

    result = {
        field: record.get(field)
        for field in fields
    }

    for field in (
        "created_utc",
        "updated_utc",
        "completed_utc",
    ):
        if result[field] is not None:
            result[field] = (
                result[field].isoformat()
            )

    result["answered_count"] = len(
        result.get("responses") or {}
    )

    return result


@baseline_bp.get("/instrument")
@authorized_profile
def instrument(profile_id, owner_id):
    return jsonify(get_assessment())


@baseline_bp.post("/start")
@authorized_profile
def start(profile_id, owner_id):

    draft = get_or_create_draft(
        profile_id,
        owner_id,
    )

    return jsonify(
        assessment=serialize_assessment(draft)
    )


@baseline_bp.post("/<assessment_id>/save")
@authorized_profile
def save(profile_id, owner_id, assessment_id):

    payload = request.form.get("responses")

    if not payload:
        raise ValueError("Responses are required.")

    if len(payload) > 10000:
        raise ValueError("Response payload too large.")

    try:
        responses = json.loads(payload)

    except json.JSONDecodeError:
        raise ValueError("Invalid response format.")

    draft = save_draft(
        profile_id,
        owner_id,
        assessment_id,
        responses,
    )

    return jsonify(
        assessment=serialize_assessment(draft)
    )


@baseline_bp.post("/<assessment_id>/complete")
@authorized_profile
def complete(profile_id, owner_id, assessment_id):

    assessment = complete_assessment(
        profile_id,
        owner_id,
        assessment_id,
    )

    return jsonify(
        assessment=serialize_assessment(assessment)
    )


@baseline_bp.get("/latest")
@authorized_profile
def latest(profile_id, owner_id):

    assessment = get_latest_baseline(
        profile_id,
        owner_id,
    )

    return jsonify(
        assessment=serialize_assessment(assessment)
    )


@baseline_bp.get("/history")
@authorized_profile
def history(profile_id, owner_id):

    records = get_assessment_history(
        profile_id,
        owner_id,
    )

    return jsonify(
        assessments=[
            serialize_assessment(record)
            for record in records
        ]
    )
