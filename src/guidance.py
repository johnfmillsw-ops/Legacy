# src/guidance.py
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from llm import generate_guidance_llm

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by",
    "for", "from", "has", "have", "he", "her", "his", "i", "if",
    "in", "is", "it", "me", "my", "of", "on", "or", "our", "she",
    "so", "that", "their", "them", "then", "they", "this",
    "to", "was", "we", "were", "what", "when", "where", "which",
    "who", "why", "will", "with", "you", "your"
}

USE_LLM = os.getenv("LEGACY_USE_LLM", "1").strip() not in ("0", "false", "no")


def tokenize(text: str) -> List[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def score_entry(query_tokens: List[str], entry: Dict[str, Any]) -> int:
    tags_val = entry.get("tags", [])
    tags = " ".join(tags_val) if isinstance(tags_val, list) else ""
    hay = f"{entry.get('prompt', '')} {entry.get('answer', '')} {tags}".lower()
    hay_tokens = set(tokenize(hay))
    return sum(1 for t in query_tokens if t in hay_tokens)


def is_generated_entry(entry: Dict[str, Any]) -> bool:
    if entry.get("category") == "guidance_generated":
        return True
    tags_val = entry.get("tags", [])
    if isinstance(tags_val, list) and "generated" in tags_val:
        return True
    return False


def top_k_relevant_entries(profile: Dict[str, Any], question: str, k: int = 3) -> List[Dict[str, Any]]:
    query_tokens = tokenize(question)
    entries: List[Dict[str, Any]] = profile.get("entries", [])

    scored: List[Tuple[int, Dict[str, Any]]] = []
    for e in entries:
        if is_generated_entry(e):
            continue
        s = score_entry(query_tokens, e)
        if s > 0:
            scored.append((s, e))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:k]]


def generate_guidance_response(profile: Dict[str, Any], question: str, k: int = 3) -> Dict[str, Any]:
    subject = profile.get("subject", {}).get("display_name", "Unknown")
    selected = top_k_relevant_entries(profile, question, k=k)

    baseline_principles = profile.get("guidance_principles", [])
    if not isinstance(baseline_principles, list):
        baseline_principles = []

    if USE_LLM:
        # NEW: pass full profile for forced context
        response_text = generate_guidance_llm(
            subject_name=subject,
            question=question,
            baseline_principles=baseline_principles,
            evidence=selected,
            profile=profile  # <-- key change
        )
        if not response_text:
            response_text = "I couldn’t generate a response right now. Try again or share more details."
    else:
        # Fallback mode
        bullets = []
        for e in selected:
            cat = e.get("category", "unknown")
            ans = str(e.get("answer", "")).strip()
            tags_val = e.get("tags", [])
            tags = ", ".join(tags_val) if isinstance(tags_val, list) and tags_val else ""
            bullets.append(f"- ({cat}) {ans}" + (f"  [tags: {tags}]" if tags else ""))

        if not bullets:
            bullets = ["- Not enough relevant material yet. Add more via interview or upload."]

        response_text = (
            f"{subject}-aligned guidance (fallback)\n\n"
            f"Question: {question}\n\n"
            f"Relevant captured insights:\n" + "\n".join(bullets) + "\n\n"
            "Suggested framing:\n"
            "- Identify the decision.\n"
            "- Name the constraint.\n"
            "- Choose the option that best matches known values and lessons."
        )

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "category": "guidance_generated",
        "prompt": question,
        "answer": response_text,
        "tags": ["generated", "guidance"],
        "evidence_count": len(selected),
        "evidence": [
            {
                "category": e.get("category", "unknown"),
                "prompt": e.get("prompt", ""),
                "answer": e.get("answer", ""),
                "tags": e.get("tags", []),
                "timestamp_utc": e.get("timestamp_utc", ""),
            }
            for e in selected
        ],
    }