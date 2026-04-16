from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

# Load .env file if it exists
load_dotenv()

DEFAULT_MODEL = os.getenv("LEGACY_MODEL", "gpt-4o-mini")
DEFAULT_REASONING = os.getenv("LEGACY_REASONING", "low")

_client: Optional[OpenAI] = None


def has_openai_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _get_client() -> OpenAI:
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set.\n"
            "1. Get your key from https://platform.openai.com/api-keys\n"
            "2. Create .env with: OPENAI_API_KEY=sk-...\n"
            "3. Or export OPENAI_API_KEY=sk-..."
        )

    _client = OpenAI(api_key=api_key)
    return _client


def build_instructions(subject_name: str) -> str:
    return f"""
You are LegacyGuidance: a grounded, natural-sounding mentor voice for {subject_name}.

You have deep, persistent knowledge of {subject_name} from everything shared (uploads, interviews, core summary).
Never say "I don't have information" or "not enough context" if any details exist — always draw from what you know.
Speak like a wise, calm, older friend: warm, direct, no corporate fluff, short sentences when possible.
Be encouraging but honest — no sugarcoating hard truths.

Structure every response:
1) Acknowledge the question/feelings briefly
2) Give clear, grounded advice (the core)
3) Lightly reference relevant details from known information
4) End with a practical next step OR a clarifying question if needed
""".strip()


def generate_guidance_llm(
    subject_name: str,
    question: str,
    baseline_principles: List[str],
    evidence: List[Dict[str, Any]],
    profile: Dict[str, Any],  # NEW: pass full profile for forced context
) -> str:
    baseline_text = "\n".join([f"- {p}" for p in baseline_principles]).strip()

    # === FORCED CONTEXT EVERY TIME ===
    core_summary = profile.get("core_summary", "No core summary yet.")
    identity_anchor = profile.get("identity_anchor", {}).get("answer", "No identity anchor yet.")

    # Pull 5 most recent/relevant imported or key entries
    entries = profile.get("entries", [])
    recent_entries = sorted(
        [e for e in entries if e.get("category") in ["identity", "imported_summary", "imported_summary_raw", "values", "stories", "purpose", "guidance"]],
        key=lambda e: e.get("timestamp_utc", ""),
        reverse=True
    )[:5]

    context_text = f"""
Permanent knowledge about {subject_name}:
Core summary:
{core_summary}

Identity anchor:
{identity_anchor}

Recent / key shared points:
""" + "\n".join(
        f"- {e.get('category').upper()}: {e.get('prompt')} → {e.get('answer')[:300]}{'...' if len(e.get('answer','')) > 300 else ''}"
        for e in recent_entries
    ) if recent_entries else "- (no additional key points yet)"

    # Optional retrieved evidence
    evidence_text = "\n".join(
        f"- [{e.get('category','unknown')}] Q: {str(e.get('prompt','')).strip()}\n  A: {str(e.get('answer','')).strip()}"
        for e in evidence
    ).strip() if evidence else "- (no additional retrieved evidence)"

    user_input = f"""
{context_text}

Question:
{question}

Baseline Principles:
{baseline_text if baseline_text else "- (none yet)"}

Additional retrieved evidence (use if directly relevant):
{evidence_text}
""".strip()

    client = _get_client()

    try:
        resp = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": build_instructions(subject_name)},
                {"role": "user", "content": user_input},
            ],
            temperature=0.7,
            max_tokens=800,
        )

        return (resp.choices[0].message.content or "").strip()

    except Exception as e:
        raise RuntimeError(f"OpenAI call failed: {str(e)}")


def test_connection():
    try:
        client = _get_client()
        print("OpenAI client initialized successfully.")
        print(f"Using model: {DEFAULT_MODEL}")
        print(f"Reasoning effort: {DEFAULT_REASONING}")
    except RuntimeError as e:
        print(e)


if __name__ == "__main__":
    test_connection()