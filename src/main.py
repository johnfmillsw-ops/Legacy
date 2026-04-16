# src/main.py
from __future__ import annotations

import os
from datetime import datetime, timezone

from exporter import write_summary_md
from guidance import generate_guidance_response
from questions import QUESTIONS
from storage import load_json, profile_path, save_json


# --------------------------------------------------
# Profile handling
# --------------------------------------------------

def ensure_profile(subject: str) -> dict:
    path = profile_path(subject)
    try:
        return load_json(path)
    except FileNotFoundError:
        return {
            "meta": {
                "project": "Legacy",
                "version": "0.6.0",
                "created_utc": datetime.now(timezone.utc).isoformat(),
            },
            "subject": {"display_name": subject},
            "consent": {
                # Recording consent (local storage)
                "has_consent": False,
                "consent_utc": None,
                "scope": "local_storage_only",

                # NEW: permission for sending prompts/evidence to a remote model API
                "allow_remote_processing": False,
                "remote_consent_utc": None,
                "remote_vendor": "openai",
            },
            "values": {},
            "stories": [],
            # Baseline scaffold so guidance is coherent even early
            "guidance_principles": [
                "Tell the truth clearly and kindly.",
                "Choose the option that increases responsibility and long-term stability.",
                "When overwhelmed: slow down, name the constraint, take the next right step.",
            ],
            "entries": [],
        }


def require_consent(profile: dict) -> bool:
    consent = profile.get("consent", {})

    if consent.get("has_consent") is True:
        return True

    print("\nConsent required before recording any entries.")
    print("This prototype stores responses locally in /data as JSON.")
    ans = input("Do you have the subject's explicit consent to record? (yes/no): ").strip().lower()

    if ans in ("yes", "y"):
        profile["consent"]["has_consent"] = True
        profile["consent"]["consent_utc"] = datetime.now(timezone.utc).isoformat()
        return True

    print("Consent not granted. Exiting without saving.")
    return False


def require_remote_processing_consent(profile: dict) -> bool:
    """
    If OPENAI_API_KEY is set, guidance mode will call a remote model unless disabled.
    We require explicit consent for that.
    """
    has_key = bool(os.getenv("OPENAI_API_KEY", "").strip())
    if not has_key:
        print("\nOPENAI_API_KEY not found. Guidance will fail unless you set it.")
        print("Set it with: export OPENAI_API_KEY='...'\n")
        return False

    consent = profile.get("consent", {})
    if consent.get("allow_remote_processing") is True:
        return True

    print("\nRemote processing consent required for guidance mode.")
    print("Guidance may send the question + selected evidence entries to a model API.")
    print("No consent = no remote call.")
    ans = input("Do you have consent to use remote processing for guidance? (yes/no): ").strip().lower()

    if ans in ("yes", "y"):
        profile["consent"]["allow_remote_processing"] = True
        profile["consent"]["remote_consent_utc"] = datetime.now(timezone.utc).isoformat()
        return True

    print("Remote processing consent not granted. Guidance mode cannot run.")
    return False


# --------------------------------------------------
# Input helpers (quality enforcement)
# --------------------------------------------------

def prompt_long_answer(prompt: str, min_chars: int = 30) -> str:
    """
    Keep prompting until the user provides a sufficiently detailed answer,
    or they type 'skip' / 'quit'.
    Returns 'skip' or 'quit' literally when typed.
    """
    while True:
        answer = input(f"{prompt}\n> ").strip()
        low = answer.lower()

        if low in ("quit", "skip"):
            return low

        if len(answer) >= min_chars:
            return answer

        print(f"Too short. Please answer in 2–3 sentences (at least {min_chars} characters), or type 'skip'.\n")


def prompt_tags() -> list[str]:
    """
    Ask for optional comma-separated tags. Returns a list of normalized tags.
    """
    raw = input("Optional tags (comma-separated, or press Enter): ").strip()
    if not raw:
        return []
    tags = [t.strip().lower() for t in raw.split(",")]
    return [t for t in tags if t]


# --------------------------------------------------
# Interview mode
# --------------------------------------------------

def choose_category() -> str:
    categories = list(QUESTIONS.keys())
    print("\nChoose a category:")
    for i, cat in enumerate(categories, start=1):
        print(f"  {i}. {cat}")

    while True:
        choice = input("> ").strip()
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(categories):
                return categories[idx - 1]
        print("Enter a valid number.")


def interview_mode(subject: str) -> None:
    path = profile_path(subject)
    profile = ensure_profile(subject)

    print(f"\nLoaded profile: {subject}")
    print(f"Current entries: {len(profile.get('entries', []))}")

    if not require_consent(profile):
        return

    # Save immediately so consent is recorded even if user quits
    save_json(path, profile)

    category = choose_category()
    prompts = QUESTIONS[category]

    print(f"\nCategory: {category}")
    print("Type 'skip' to skip a question, or 'quit' to stop.\n")

    for prompt in prompts:
        answer = prompt_long_answer(prompt, min_chars=30)

        if answer == "quit":
            break
        if answer == "skip" or answer == "":
            continue

        tags = prompt_tags()

        entry = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "category": category,
            "prompt": prompt,
            "answer": answer,
            "tags": tags,
        }

        profile.setdefault("entries", []).append(entry)
        save_json(path, profile)

        print(f"(saved) total entries: {len(profile['entries'])}\n")

    print(f"Session ended. Profile saved -> {path}")


# --------------------------------------------------
# Export mode
# --------------------------------------------------

def export_mode(subject: str) -> None:
    path = profile_path(subject)

    try:
        profile = load_json(path)
    except FileNotFoundError:
        profile = ensure_profile(subject)
        save_json(path, profile)

    out = write_summary_md(profile)
    print(f"Exported summary -> {out}")


# --------------------------------------------------
# Guidance mode
# --------------------------------------------------

def guidance_mode(subject: str) -> None:
    path = profile_path(subject)

    try:
        profile = load_json(path)
    except FileNotFoundError:
        profile = ensure_profile(subject)
        save_json(path, profile)

    print(f"\nLoaded profile: {subject}")
    print(f"Current entries: {len(profile.get('entries', []))}")

    if not require_remote_processing_consent(profile):
        # Save profile in case user granted local consent earlier but not remote
        save_json(path, profile)
        return

    # Save immediately so remote consent is recorded even if user quits
    save_json(path, profile)

    question = input("\nAsk a guidance question:\n> ").strip()
    if not question:
        print("No question entered.")
        return

    generated = generate_guidance_response(profile, question, k=3)

    profile.setdefault("entries", []).append(generated)
    save_json(path, profile)

    print("\n--- Guidance Response ---\n")
    print(generated["answer"])
    print("\n(saved to profile entries)")


# --------------------------------------------------
# Main dispatcher
# --------------------------------------------------

def main() -> None:
    print("Legacy system online.")

    subject = input("Enter subject name: ").strip() or "Unknown"

    mode = input(
        "\nChoose mode:\n"
        "  (1) interview\n"
        "  (2) export summary\n"
        "  (3) ask guidance question\n"
        "> "
    ).strip()

    if mode == "2":
        export_mode(subject)
    elif mode == "3":
        guidance_mode(subject)
    else:
        interview_mode(subject)


if __name__ == "__main__":
    main()