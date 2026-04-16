from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

# Load .env file
load_dotenv()

# ========================= CONFIG =========================
DEFAULT_MODEL = os.getenv("LEGACY_MODEL", "grok-4-1-fast")
# =========================================================

_client: Optional[OpenAI] = None


def has_api_key() -> bool:
    return bool(os.getenv("XAI_API_KEY"))


def _get_client() -> OpenAI:
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "XAI_API_KEY is not set.\n"
            "Make sure you have XAI_API_KEY=... in your .env file"
        )

    _client = OpenAI(
        api_key=api_key,
        base_url="https://api.x.ai/v1"
    )
    return _client


def build_instructions(subject_name: str) -> str:
    return f"""
You are LegacyGuidance: a grounded, natural-sounding mentor voice for {subject_name}.

You have deep, persistent knowledge of {subject_name} from everything shared.
Never say "I don't have information" if any details exist — always draw from what you know.
Speak like a wise, calm, older friend: warm, direct, no fluff.

Structure every response:
1) Acknowledge the question briefly
2) Give clear, grounded advice
3) Lightly reference known details
4) End with a practical next step or clarifying question
""".strip()


def generate_guidance_llm(
    subject_name: str,
    question: str,
    baseline_principles: List[str],
    evidence: List[Dict[str, Any]],
    profile: Dict[str, Any],
) -> str:
    baseline_text = "\n".join([f"- {p}" for p in baseline_principles]).strip()

    core_summary = profile.get("core_summary", "No core summary yet.")
    identity_anchor = profile.get("identity_anchor", {}).get("answer", "No identity anchor yet.")

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

Additional retrieved evidence:
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
        raise RuntimeError(f"Grok API call failed: {str(e)}")


def test_connection():
    try:
        client = _get_client()
        print("✅ Grok API connected successfully!")
        print(f"Using model: {DEFAULT_MODEL}")
    except RuntimeError as e:
        print(e)


if __name__ == "__main__":
    test_connection()