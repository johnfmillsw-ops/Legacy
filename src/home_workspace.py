
from database import database_connection
from identity_portrait import build_identity_portrait
from math import sin, cos, pi


def build_home_workspace(profile_id, owner_id):

    portrait = build_identity_portrait(
        profile_id,
        owner_id,
    )

    def point(index, radius):
        angle = index * pi / 3
        return "{:.2f},{:.2f}".format(
            180 + sin(angle) * radius,
            140 - cos(angle) * radius,
        )

    radar = {
        "rings": [
            " ".join(point(i, r) for i in range(6))
            for r in (30, 60, 90)
        ],
        "shape": " ".join(
            point(i, item["level"] * 30)
            for i, item in enumerate(portrait)
        ),
        "labels": [
            {
                "name": item["name"],
                "x": 180 + sin(i * pi / 3) * 128,
                "y": 144 - cos(i * pi / 3) * 118,
            }
            for i, item in enumerate(portrait)
        ],
    }

    discoveries = []

    for dimension in portrait:
        for item in dimension["evidence"]:

            if item["type"] == "Your reflection":
                continue

            discoveries.append({
                "dimension": dimension["name"],
                "text": item["text"],
                "type": item["type"],
                "source": item["source"],
            })

            break

    with database_connection() as conn:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT
                    j.id,
                    j.title,
                    j.subtitle,
                    j.design,
                    j.updated_utc,
                    e.id AS entry_id,
                    e.title AS entry_title,
                    e.entry_date,
                    e.status AS entry_status
                FROM journals j
                JOIN profiles p
                    ON p.id = j.profile_id
                LEFT JOIN LATERAL (
                    SELECT id, title, entry_date, status
                    FROM journal_entries
                    WHERE journal_id = j.id
                    ORDER BY updated_utc DESC
                    LIMIT 1
                ) e ON TRUE
                WHERE j.profile_id = %s
                  AND p.owner_id = %s
                ORDER BY j.updated_utc DESC
                LIMIT 1
            """, (profile_id, owner_id))

            journal = cur.fetchone()

            cur.execute("""
                SELECT
                    title,
                    activity_type,
                    activity_date,
                    journal_id,
                    entry_id
                FROM (
                    SELECT
                        COALESCE(
                            NULLIF(e.title, ''),
                            'Untitled entry'
                        ) AS title,
                        'Journal entry' AS activity_type,
                        e.updated_utc AS activity_date,
                        j.id AS journal_id,
                        e.id AS entry_id
                    FROM journal_entries e
                    JOIN journals j
                        ON j.id = e.journal_id
                    JOIN profiles p
                        ON p.id = j.profile_id
                    WHERE j.profile_id = %s
                      AND p.owner_id = %s

                    UNION ALL

                    SELECT
                        d.title,
                        'Archived material',
                        d.created_utc,
                        NULL::TEXT AS journal_id,
                        NULL::TEXT AS entry_id
                    FROM knowledge_documents d
                    JOIN profiles p
                        ON p.id = d.profile_id
                    WHERE d.profile_id = %s
                      AND p.owner_id = %s
                      AND COALESCE(
                          d.metadata ->> 'origin', ''
                      ) <> 'written_journal'
                ) activity
                ORDER BY activity_date DESC
                LIMIT 5
            """, (
                profile_id,
                owner_id,
                profile_id,
                owner_id,
            ))

            activity = cur.fetchall()

    return {
        "portrait": portrait,
        "radar": radar,
        "journal": journal,
        "discoveries": discoveries[:3],
        "activity": activity,
    }
