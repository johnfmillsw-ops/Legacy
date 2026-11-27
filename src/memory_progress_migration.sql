
CREATE TABLE IF NOT EXISTS memory_extraction_progress (
    chunk_id TEXT NOT NULL
        REFERENCES knowledge_chunks(id)
        ON DELETE CASCADE,
    extraction_version INTEGER NOT NULL,
    memories_created INTEGER NOT NULL DEFAULT 0,
    completed_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (chunk_id, extraction_version)
);
