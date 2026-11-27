import argparse

from database import database_connection

from memory_extraction import (
    EXTRACTION_VERSION,
    verify_access,
    extract_document_memories,
)


def list_profiles():

    with database_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT id, owner_id, display_name
                FROM profiles
                ORDER BY display_name
            """)

            return cur.fetchall()


def pending_documents(profile_id, owner_id):

    verify_access(profile_id, owner_id)

    with database_connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT
                    d.id,
                    d.title,
                    COUNT(c.id) AS pending_chunks
                FROM knowledge_documents d
                JOIN knowledge_chunks c
                    ON c.document_id = d.id
                LEFT JOIN memory_extraction_progress p
                    ON p.chunk_id = c.id
                    AND p.extraction_version = %s
                JOIN profiles pr
                    ON pr.id = d.profile_id
                WHERE d.profile_id = %s
                  AND pr.owner_id = %s
                  AND p.chunk_id IS NULL
                  AND pr.profile_data @>
                      '{"consent": {
                          "has_consent": true,
                          "allow_remote_processing": true
                      }}'::jsonb
                  AND (
                      COALESCE(
                          d.metadata ->> 'origin', ''
                      ) <> 'written_journal'
                      OR EXISTS (
                          SELECT 1
                          FROM journal_entries e
                          JOIN journals j
                              ON j.id = e.journal_id
                          WHERE e.document_id = d.id
                            AND j.profile_id = d.profile_id
                            AND e.id =
                                d.metadata ->> 'journal_entry_id'
                            AND j.id =
                                d.metadata ->> 'journal_id'
                            AND e.status = 'published'
                            AND e.allow_ai_processing = TRUE
                            AND (
                                e.ai_preference = 'include'
                                OR (
                                    e.ai_preference = 'inherit'
                                    AND j.ai_default_enabled = TRUE
                                )
                            )
                      )
                  )
                GROUP BY d.id, d.title, d.created_utc
                ORDER BY d.created_utc
                """,
                (
                    EXTRACTION_VERSION,
                    profile_id,
                    owner_id,
                ),
            )

            return cur.fetchall()


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--run",
        action="store_true",
        help="Perform AI extraction."
    )

    args = parser.parse_args()

    profiles = list_profiles()

    if not profiles:
        print("No profiles found.")
        return

    print("\nAvailable profiles:\n")

    for index, profile in enumerate(profiles, 1):
        print(
            "{}. {}".format(
                index,
                profile["display_name"]
            )
        )

    selection = int(input("\nSelect profile: ")) - 1

    if not 0 <= selection < len(profiles):
        raise SystemExit("Invalid profile selection.")

    profile = profiles[selection]

    profile_id = profile["id"]
    owner_id = profile["owner_id"]

    documents = pending_documents(
        profile_id,
        owner_id,
    )

    total = sum(
        doc["pending_chunks"]
        for doc in documents
    )

    print("\nIdentity knowledge backfill")
    print("Profile:", profile["display_name"])
    print("Documents remaining:", len(documents))
    print("Passages remaining:", total)
    print("Estimated extraction requests:", total)

    for doc in documents:
        print(
            " - {}: {} passages".format(
                doc["title"],
                doc["pending_chunks"],
            )
        )

    if not total:
        print("\nAll eligible passages are complete.")
        return

    if not args.run:
        print("\nPreview only. No AI requests made.")
        return

    created = 0
    failures = 0

    for index, doc in enumerate(documents, 1):

        print(
            "\n[{}/{}] {}".format(
                index,
                len(documents),
                doc["title"],
            )
        )

        try:

            result = extract_document_memories(
                profile_id,
                owner_id,
                doc["id"],
                max_chunks=None,
            )

            created += result["memories_created"]

        except PermissionError as exc:

            print("Access changed:", exc)
            print("Stopping backfill.")
            break

        except Exception as exc:

            failures += 1
            print("Processing failed:", exc)
            print("Document deferred. Continuing to next document.")
            continue

    remaining = pending_documents(
        profile_id,
        owner_id,
    )

    print("\nBackfill results")
    print("New memories created:", created)
    print("Processing failures:", failures)
    print(
        "Remaining passages:",
        sum(
            doc["pending_chunks"]
            for doc in remaining
        ),
    )


if __name__ == "__main__":
    main()
