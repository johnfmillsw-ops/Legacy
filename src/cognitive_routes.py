"""
Legacy Phase VII: Cognitive assessment API.

Authenticated, profile-scoped assessment administration,
historical results and independent privacy controls.
"""

from functools import wraps
from datetime import datetime
from decimal import Decimal

from flask import (
    Blueprint,
    jsonify,
    request,
    session,
)

from flask_login import current_user

from database import get_profile

import cognitive_storage as storage
import cognitive_preferences as preferences

from cognitive_session import SessionStateError
from cognitive_session_state import StateIntegrityError


cognitive_bp = Blueprint(
    "cognitive",
    __name__,
    url_prefix="/api/cognitive",
)


@cognitive_bp.after_request
def prevent_cognitive_caching(response):
    response.headers["Cache-Control"] = "no-store, private"
    return response


def serialize(value):

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, dict):
        return {
            key: serialize(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            serialize(item)
            for item in value
        ]

    return value


def authorized_profile(
    require_consent=True,
):

    def decorate(function):

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

            if (
                require_consent
                and consent.get("has_consent") is not True
            ):
                return jsonify(
                    error="Local processing consent required."
                ), 403

            try:

                response = function(
                    profile_id,
                    current_user.id,
                    *args,
                    **kwargs,
                )

                return jsonify(
                    serialize(response)
                )

            except storage.CognitiveAccessDenied:
                return jsonify(
                    error="Profile or assessment access denied."
                ), 403

            except (
                storage.CognitiveConflict,
                SessionStateError,
            ) as error:
                return jsonify(
                    error=str(error)
                ), 409

            except StateIntegrityError:
                return jsonify(
                    error="Assessment integrity verification failed."
                ), 500

            except ValueError as error:
                return jsonify(
                    error=str(error)
                ), 400

        return wrapped

    return decorate


def boolean_field(name):

    value = request.form.get(name)

    if value not in ("true", "false"):
        raise ValueError(
            name + " must be true or false."
        )

    return value == "true"


def revision_field():

    value = request.form.get("revision")

    if (
        value is None
        or not value.isascii()
        or not value.isdecimal()
        or len(value) > 18
    ):
        raise ValueError(
            "Invalid assessment revision."
        )

    return int(value)


@cognitive_bp.post("/start")
@authorized_profile()
def start(profile_id, owner_id):

    return {
        "assessment": storage.create_assessment(
            profile_id,
            owner_id,
        )
    }


@cognitive_bp.get("/history")
@authorized_profile()
def history(profile_id, owner_id):

    return {
        "assessments": storage.assessment_history(
            profile_id,
            owner_id,
        )
    }


@cognitive_bp.get("/<assessment_id>/status")
@authorized_profile()
def status(
    profile_id,
    owner_id,
    assessment_id,
):

    return {
        "assessment": storage.assessment_status(
            profile_id,
            owner_id,
            assessment_id,
        )
    }


@cognitive_bp.post("/<assessment_id>/action")
@authorized_profile()
def action(
    profile_id,
    owner_id,
    assessment_id,
):

    action_name = request.form.get("action")

    if action_name not in {
        "begin_block",
        "finish_memory_exposure",
        "submit_response",
        "advance",
        "tick",
        "interrupt",
    }:
        raise ValueError(
            "Unknown assessment action."
        )

    result = storage.assessment_action(
        profile_id=profile_id,
        owner_id=owner_id,
        assessment_id=assessment_id,
        expected_revision=revision_field(),
        action=action_name,
        question_id=request.form.get("question_id"),
        selected_option_id=request.form.get(
            "selected_option_id"
        ),
        interruption_reason=request.form.get(
            "interruption_reason"
        ),
    )

    return {
        "assessment": result,
    }


@cognitive_bp.get("/<assessment_id>/results")
@authorized_profile()
def results(
    profile_id,
    owner_id,
    assessment_id,
):

    return {
        "results": storage.assessment_results(
            profile_id,
            owner_id,
            assessment_id,
        )
    }


@cognitive_bp.get("/preferences")
@authorized_profile()
def get_preferences(profile_id, owner_id):

    return {
        "preferences": preferences.get_preferences(
            profile_id,
            owner_id,
        )
    }


@cognitive_bp.post("/preferences/model")
@authorized_profile(require_consent=False)
def model_preferences(profile_id, owner_id):

    return {
        "preferences":
            preferences.set_model_integration(
                profile_id,
                owner_id,
                enabled=boolean_field("enabled"),
                assessment_id=request.form.get(
                    "assessment_id"
                ),
            )
    }


@cognitive_bp.post("/preferences/display")
@authorized_profile(require_consent=False)
def display_preferences(profile_id, owner_id):

    return {
        "preferences":
            preferences.set_display_preferences(
                profile_id,
                owner_id,
                display_on_home=boolean_field(
                    "display_on_home"
                ),
                display_on_cognitive_page=boolean_field(
                    "display_on_cognitive_page"
                ),
                assessment_id=request.form.get(
                    "assessment_id"
                ),
            )
    }


@cognitive_bp.post("/<assessment_id>/delete")
@authorized_profile(require_consent=False)
def delete(
    profile_id,
    owner_id,
    assessment_id,
):

    return preferences.delete_assessment(
        profile_id,
        owner_id,
        assessment_id,
    )
