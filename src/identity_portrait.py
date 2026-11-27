
from database import database_connection


DIMENSIONS = {
    "Experiences": {
        "description": "Life events and formative experiences.",
        "memories": ("life_event", "accomplishment"),
        "interviews": ("stories",),
    },
    "Values": {
        "description": "Principles and personal convictions.",
        "memories": ("value",),
        "interviews": ("values",),
    },
    "Beliefs": {
        "description": "Worldviews and personal philosophy.",
        "memories": ("belief",),
        "interviews": (),
    },
    "Purpose": {
        "description": "Aspirations and life's direction.",
        "memories": (),
        "interviews": ("purpose",),
    },
    "Relationships": {
        "description": "Meaningful personal connections.",
        "memories": ("relationship",),
        "interviews": (),
    },
    "Personality": {
        "description": "Personal characteristics and preferences.",
        "memories": ("personality_trait", "preference"),
        "interviews": (),
    },
}


def build_identity_portrait(profile_id, owner_id):

    with database_connection() as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT profile_data
                FROM profiles
                WHERE id = %s AND owner_id = %s
                """,
                (profile_id, owner_id),
            )

            profile = cur.fetchone()

            if not profile:
                raise PermissionError("Profile access denied.")

            consent = (
                profile["profile_data"] or {}
            ).get("consent", {})

            interviews = []
            memories = []

            if consent.get("has_consent") is True:

                cur.execute(
                    """
                    SELECT id, category, prompt, answer
                    FROM knowledge_entries
                    WHERE profile_id = %s
                      AND source_type = 'interview'
                    ORDER BY created_utc DESC
                    """,
                    (profile_id,),
                )

                interviews = cur.fetchall()

            if (
                consent.get("has_consent") is True
                and consent.get("allow_remote_processing") is True
            ):

                cur.execute(
                    """
                    SELECT
                        m.id,
                        m.category,
                        m.memory_text,
                        m.source_excerpt,
                        m.interpretation_type,
                        m.source_document_id,
                        d.title AS source_title
                    FROM structured_memories m
                    LEFT JOIN knowledge_documents d
                        ON d.id = m.source_document_id
                        AND d.profile_id = m.profile_id
                    WHERE m.profile_id = %s
                      AND m.status = 'approved'
                      AND d.id IS NOT NULL
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
                                AND j.profile_id = m.profile_id
                                AND e.id = d.metadata ->> 'journal_entry_id'
                                AND j.id = d.metadata ->> 'journal_id'
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
                    ORDER BY m.created_utc DESC
                    """,
                    (profile_id,),
                )

                memories = cur.fetchall()

    portrait = []

    for name, config in DIMENSIONS.items():

        evidence = []
        sources = set()
        seen = set()
        direct_count = 0

        for entry in interviews:

            if entry["category"] not in config["interviews"]:
                continue

            answer = (entry["answer"] or "").strip()

            if not answer:
                continue

            key = " ".join(answer.casefold().split())

            if key in seen:
                continue

            seen.add(key)
            sources.add("interview:" + entry["id"])
            direct_count += 1

            evidence.append({
                "text": answer,
                "source": entry["prompt"],
                "type": "Your reflection",
            })

        for memory in memories:

            if memory["category"] not in config["memories"]:
                continue

            value = (memory["memory_text"] or "").strip()

            if not value:
                continue

            key = " ".join(value.casefold().split())

            if key in seen:
                continue

            seen.add(key)

            sources.add(
                "document:" + memory["source_document_id"]
            )

            explicit = (
                memory["interpretation_type"] == "explicit"
            )

            if explicit:
                direct_count += 1

            evidence.append({
                "text": value,
                "source": memory["source_title"] or "Memory",
                "type": (
                    "Source-supported memory"
                    if explicit else "AI interpretation"
                ),
                "excerpt": memory["source_excerpt"],
            })

        count = len(evidence)

        if not count:
            level = 0
            status = "Not yet documented"

        elif (
            count >= 6
            and len(sources) >= 3
            and direct_count >= 3
        ):
            level = 3
            status = "Well documented"

        elif count >= 3 and direct_count >= 1:
            level = 2
            status = "Developing"

        else:
            level = 1
            status = "Early exploration"

        portrait.append({
            "name": name,
            "description": config["description"],
            "level": level,
            "status": status,
            "evidence_count": count,
            "source_count": len(sources),
            "evidence": evidence[:20],
        })

    return portrait
