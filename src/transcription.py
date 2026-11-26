
from __future__ import annotations

from pathlib import Path
from functools import lru_cache

from faster_whisper import WhisperModel


MODEL_NAME = "small"


# --------------------------------------------------
# Load and cache transcription model
# --------------------------------------------------

@lru_cache(maxsize=1)
def get_transcription_model():

    return WhisperModel(
        MODEL_NAME,
        device="cpu",
        compute_type="int8",
        cpu_threads=4,
    )


# --------------------------------------------------
# Transcribe audio recording
# --------------------------------------------------

def transcribe_audio(audio_path):

    path = Path(audio_path)

    if not path.is_file():

        raise FileNotFoundError(
            "Audio recording not found."
        )

    if path.stat().st_size == 0:

        raise ValueError(
            "Audio recording is empty."
        )

    model = get_transcription_model()

    segments, info = model.transcribe(
        str(path),
        beam_size=5,
        vad_filter=True,
        word_timestamps=False,
        task="transcribe",
    )

    transcript_parts = []
    transcript_segments = []

    for segment in segments:

        text = segment.text.strip()

        if not text:
            continue

        transcript_parts.append(text)

        transcript_segments.append({
            "start": float(segment.start),
            "end": float(segment.end),
            "text": text,
        })

    transcript = " ".join(
        transcript_parts
    ).strip()

    if not transcript:

        raise ValueError(
            "No recognizable speech detected."
        )

    return {
        "transcript": transcript,
        "model": MODEL_NAME,
        "language": info.language,
        "language_probability": float(
            info.language_probability
        ),
        "duration_seconds": float(info.duration),
        "segments": transcript_segments,
    }
