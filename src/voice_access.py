
import os


def voice_playback_allowed(owner_id, profile_id):
    mode = os.getenv(
        "LEGACY_VOICE_MODE", "disabled"
    ).strip().lower()

    if not owner_id or not profile_id:
        return False

    if mode != "restricted":
        return False

    allowed_owner = os.getenv(
        "LEGACY_VOICE_OWNER_ID", ""
    ).strip()

    allowed_profile = os.getenv(
        "LEGACY_VOICE_PROFILE_ID", ""
    ).strip()

    if not allowed_owner or not allowed_profile:
        return False

    return (
        str(owner_id) == allowed_owner
        and str(profile_id) == allowed_profile
    )
