
import os
import json
from urllib.request import Request, urlopen
from urllib.parse import quote

from voice_access import voice_playback_allowed


def synthesize_voice(text, owner_id, profile_id):

    if not voice_playback_allowed(owner_id, profile_id):
        raise PermissionError("Voice playback is disabled.")

    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    model_id = os.getenv("ELEVENLABS_MODEL_ID", "").strip()

    if not api_key or not voice_id or not model_id:
        raise RuntimeError("Voice synthesis is not configured.")

    text = text.strip()

    if not text or len(text) > 4000:
        raise ValueError("Invalid speech text length.")

    payload = json.dumps({
        "text": text,
        "model_id": model_id
    }).encode("utf-8")

    endpoint = (
        "https://api.elevenlabs.io/v1/text-to-speech/"
        + quote(voice_id, safe="")
    )

    request = Request(
        endpoint,
        data=payload,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        },
        method="POST"
    )

    with urlopen(request, timeout=60) as response:

        if response.headers.get_content_type() != "audio/mpeg":
            raise RuntimeError("Unexpected audio response.")

        audio = response.read(10 * 1024 * 1024 + 1)

        if not audio or len(audio) > 10 * 1024 * 1024:
            raise RuntimeError("Invalid audio response.")

        return audio
