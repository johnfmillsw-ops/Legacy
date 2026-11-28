"""
Authorized, resumable psychological evidence processing.
"""

import argparse
import json
from uuid import uuid4

from psycopg.types.json import Jsonb

from database import database_connection
from llm import _get_client, DEFAULT_MODEL

from psychological_framework import FRAMEWORK_VERSION

from psychological_analysis import (
    BATCH_SIZE,
    SYSTEM_PROMPT,
    build_analysis_prompt,
    validate_observations,
)

from journal_privacy import (
    load_entries_privacy,
    entry_is_eligible,
)


def verify_profile(cursor, profile_id, owner_id):

    cursor.execute("""
        SELECT profile_data
        FROM profiles
        WHERE id = %s
          AND owner_id = %s
        FOR UPDATE
    """, (profile_id, owner_id))

    row = cursor.fetchone()

    if row is None:
        raise PermissionError("Profile access denied.")

    consent = (
        row["profile_data"] or {}
    ).get("consent", {})

    if not (
        consent.get("has_consent") is True
        and consent.get("allow_remote_processing") is True
    ):
        raise PermissionError(
            "Remote AI processing consent required."
        )


def authorized_memories(
    cursor,
    profile_id,
    owner_id,
    pending_only=True,
):

    verify_profile(
        cursor,
        profile_id,
        owner_id,
    )

    cursor.execute("""
        SELECT
            m.id,
            m.category,
            m.memory_text,
            m.interpretation_type,
            m.event_date,
            m.source_document_id,
            m.source_chunk_id,
            d.metadata
        FROM structured_memories m
        JOIN knowledge_documents d
            ON d.id = m.source_document_id
           AND d.profile_id = m.profile_id
        JOIN knowledge_chunks c
            ON c.id = m.source_chunk_id
           AND c.document_id = d.id
        LEFT JOIN psychological_analysis_progress a
            ON a.memory_id = m.id
           AND a.framework_version = %s
        WHERE m.profile_id = %s
          AND m.status = 'approved'
          AND (%s = FALSE OR a.memory_id IS NULL)
        ORDER BY m.created_utc, m.id
    """, (
        FRAMEWORK_VERSION,
        profile_id,
        pending_only,
    ))

    rows = cursor.fetchall()
    authorized = []
    entry_ids = {
        metadata["journal_entry_id"]
        for row in rows
        for metadata in [row["metadata"] or {}]
        if metadata.get("origin") == "written_journal"
        and isinstance(metadata.get("journal_entry_id"), str)
        and metadata["journal_entry_id"]
    }

    entry_privacy_cache = load_entries_privacy(
        cursor,
        sorted(entry_ids),
        profile_id,
        owner_id,
        lock=True,
    )

    for row in rows:

        metadata = row["metadata"] or {}

        if metadata.get("origin") == "written_journal":

            entry_id = metadata.get("journal_entry_id")

            if not isinstance(entry_id, str) or not entry_id:
                continue

            try:

                entry = entry_privacy_cache.get(entry_id)

                if entry is None:
                    continue

                if not (
                    entry_is_eligible(entry)
                    and entry["allow_ai_processing"]
                    and entry["document_id"]
                    == row["source_document_id"]
                ):
                    continue

            except (PermissionError, ValueError, KeyError):
                continue

        authorized.append(row)

    return authorized


def load_pending(profile_id, owner_id):

    with database_connection() as conn:
        with conn.cursor() as cur:

            return authorized_memories(
                cur,
                profile_id,
                owner_id,
            )


def request_analysis(memories):

    client = _get_client()

    response = client.chat.completions.create(
        model=DEFAULT_MODEL,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": build_analysis_prompt(memories),
            },
        ],
        temperature=0.1,
        max_tokens=10000,
    )

    choice = response.choices[0]

    if choice.finish_reason != "stop":
        raise ValueError(
            "Incomplete AI response. Batch not saved."
        )

    content = (choice.message.content or "").strip()

    if content.startswith("```"):

        lines = content.splitlines()

        if lines[-1].strip() != "```":
            raise ValueError("Incomplete JSON response.")

        content = "\n".join(lines[1:-1])

    data = json.loads(content)

    result = validate_observations(
        data,
        memories,
    )

    # Do not mark a partially invalid response complete.
    if result["rejected"]:
        raise ValueError(
            "Response validation failed: "
            + "; ".join(
                sorted(set(result["rejected"]))
            )
        )

    return result["observations"]


def save_batch(
    profile_id,
    owner_id,
    memories,
    observations,
):

    with database_connection() as conn:
        with conn.cursor() as cur:

            current = {
                row["id"]: row
                for row in authorized_memories(
                    cur,
                    profile_id,
                    owner_id,
                )
            }

            # Revalidate all source records after the
            # remote request and before saving.
            for memory in memories:

                if current.get(memory["id"]) != memory:
                    raise PermissionError(
                        "Source changed, access revoked, "
                        "or analysis already completed."
                    )

            created = 0
            evidence_count = 0

            counts = {
                memory["id"]: {
                    "characteristics": 0,
                    "evidence": 0,
                }
                for memory in memories
            }

            for item in observations:

                memory_id = item["memory_id"]

                cur.execute("""
                    INSERT INTO psychological_characteristics (
                        id,
                        profile_id,
                        dimension,
                        characteristic_key,
                        label,
                        framework_version
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (
                        profile_id,
                        dimension,
                        characteristic_key
                    )
                    DO NOTHING
                    RETURNING id
                """, (
                    uuid4().hex,
                    profile_id,
                    item["dimension"],
                    item["characteristic_key"],
                    item["label"],
                    FRAMEWORK_VERSION,
                ))

                inserted = cur.fetchone()

                if inserted:

                    characteristic_id = inserted["id"]
                    created += 1

                    counts[memory_id][
                        "characteristics"
                    ] += 1

                else:

                    cur.execute("""
                        SELECT id, review_status
                        FROM psychological_characteristics
                        WHERE profile_id = %s
                          AND dimension = %s
                          AND characteristic_key = %s
                    """, (
                        profile_id,
                        item["dimension"],
                        item["characteristic_key"],
                    ))

                    existing = cur.fetchone()

                    if existing["review_status"] == "rejected":
                        continue

                    characteristic_id = existing["id"]

                cur.execute("""
                    INSERT INTO psychological_evidence (
                        id,
                        profile_id,
                        characteristic_id,
                        source_memory_id,
                        evidence_type,
                        direction,
                        interpretation,
                        source_excerpt,
                        weight_factors,
                        temporal_type
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    ON CONFLICT DO NOTHING
                    RETURNING id
                """, (
                    uuid4().hex,
                    profile_id,
                    characteristic_id,
                    memory_id,
                    item["evidence_type"],
                    item["direction"],
                    item["interpretation"],
                    item["source_excerpt"],
                    Jsonb(item["weight_factors"]),
                    item["temporal_type"],
                ))

                if cur.fetchone():

                    evidence_count += 1
                    counts[memory_id]["evidence"] += 1

            for memory in memories:

                memory_id = memory["id"]

                cur.execute("""
                    INSERT INTO psychological_analysis_progress (
                        memory_id,
                        framework_version,
                        characteristics_created,
                        evidence_created
                    )
                    VALUES (%s, %s, %s, %s)
                """, (
                    memory_id,
                    FRAMEWORK_VERSION,
                    counts[memory_id]["characteristics"],
                    counts[memory_id]["evidence"],
                ))

    return created, evidence_count


def select_profile():

    with database_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT id, owner_id, display_name
                FROM profiles
                ORDER BY display_name, id
            """)

            profiles = cur.fetchall()

    if not profiles:
        raise ValueError("No profiles found.")

    print("\nAvailable profiles:\n")

    for index, profile in enumerate(profiles, 1):

        print(
            f"{index}. {profile['display_name']}"
        )

    choice = int(input("\nSelect profile: "))

    if not 1 <= choice <= len(profiles):
        raise ValueError("Invalid profile selection.")

    return profiles[choice - 1]


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--run",
        action="store_true",
    )

    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
    )

    args = parser.parse_args()

    if (
        args.max_batches is not None
        and args.max_batches < 1
    ):
        parser.error("--max-batches must be positive.")

    profile = select_profile()

    profile_id = profile["id"]
    owner_id = profile["owner_id"]

    pending = load_pending(
        profile_id,
        owner_id,
    )

    total = len(pending)

    batches = (
        total + BATCH_SIZE - 1
    ) // BATCH_SIZE

    planned = batches

    if args.max_batches is not None:
        planned = min(planned, args.max_batches)

    print("\nPsychological identity analysis")
    print("Profile:", profile["display_name"])
    print("Pending authorized memories:", total)
    print("Memories per batch:", BATCH_SIZE)
    print("Total pending batches:", batches)
    print("Planned API requests:", planned)

    if not args.run:

        print("\nPreview only. No API requests made.")
        return

    if not total:

        print("\nNo pending authorized memories.")
        return

    if input("\nProceed? [y/N]: ").strip().lower() != "y":

        print("Cancelled.")
        return

    completed = 0
    total_characteristics = 0
    total_evidence = 0

    for index in range(planned):

        pending = load_pending(
            profile_id,
            owner_id,
        )

        if not pending:
            break

        batch = pending[:BATCH_SIZE]

        print(
            f"\nBatch {index + 1}/{planned}: "
            f"{len(batch)} memories"
        )

        try:

            observations = request_analysis(batch)

            characteristics, evidence = save_batch(
                profile_id,
                owner_id,
                batch,
                observations,
            )

            completed += len(batch)
            total_characteristics += characteristics
            total_evidence += evidence

            print("New characteristics:", characteristics)
            print("New evidence records:", evidence)

        except Exception as error:

            print(
                "Batch stopped:",
                type(error).__name__,
                getattr(error, "status_code", ""),
                str(error) if isinstance(error, ValueError)
                else "",
            )

            print(
                "Completed batches preserved. "
                "Unfinished batch remains pending."
            )

            break

    print("\nProcessing summary")
    print("Memories analyzed:", completed)
    print("Characteristics created:", total_characteristics)
    print("Evidence records created:", total_evidence)

    print(
        "Remaining authorized memories:",
        len(load_pending(profile_id, owner_id)),
    )


if __name__ == "__main__":
    main()
