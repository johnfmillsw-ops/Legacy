
BEGIN;

CREATE TABLE IF NOT EXISTS structured_memories (
    id TEXT PRIMARY KEY,

    profile_id TEXT NOT NULL
        REFERENCES profiles(id)
        ON DELETE CASCADE,

    source_document_id TEXT
        REFERENCES knowledge_documents(id)
        ON DELETE SET NULL,

    source_chunk_id TEXT
        REFERENCES knowledge_chunks(id)
        ON DELETE SET NULL,

    category TEXT NOT NULL
        CHECK (
            category IN (
                'life_event',
                'relationship',
                'belief',
                'value',
                'personality_trait',
                'accomplishment',
                'preference',
                'reflection'
            )
        ),

    memory_text TEXT NOT NULL
        CHECK (LENGTH(TRIM(memory_text)) > 0),

    source_excerpt TEXT,

    interpretation_type TEXT NOT NULL
        DEFAULT 'explicit'
        CHECK (
            interpretation_type IN (
                'explicit',
                'inferred'
            )
        ),

    status TEXT NOT NULL
        DEFAULT 'pending'
        CHECK (
            status IN (
                'pending',
                'approved',
                'rejected'
            )
        ),

    event_date TEXT,

    created_utc TIMESTAMPTZ NOT NULL
        DEFAULT NOW(),

    reviewed_utc TIMESTAMPTZ,

    updated_utc TIMESTAMPTZ NOT NULL
        DEFAULT NOW(),

    CHECK (
        status = 'pending'
        OR reviewed_utc IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS
    idx_structured_memories_profile
ON structured_memories(profile_id);

CREATE INDEX IF NOT EXISTS
    idx_structured_memories_review
ON structured_memories(profile_id, status);

CREATE INDEX IF NOT EXISTS
    idx_structured_memories_category
ON structured_memories(profile_id, category);

CREATE INDEX IF NOT EXISTS
    idx_structured_memories_source
ON structured_memories(source_document_id);

COMMIT;
