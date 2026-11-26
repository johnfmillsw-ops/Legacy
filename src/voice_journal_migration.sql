
BEGIN;

-- --------------------------------------------------
-- Voice journal storage
-- --------------------------------------------------

CREATE TABLE IF NOT EXISTS voice_journals (

    id TEXT PRIMARY KEY,

    profile_id TEXT NOT NULL
        REFERENCES profiles(id)
        ON DELETE CASCADE,

    title TEXT NOT NULL DEFAULT 'Untitled Journal',

    -- Original audio information

    audio_path TEXT NOT NULL,

    original_filename TEXT,

    mime_type TEXT NOT NULL,

    file_size_bytes BIGINT NOT NULL
        CHECK (file_size_bytes > 0),

    duration_seconds DOUBLE PRECISION
        CHECK (duration_seconds >= 0),

    -- Transcription information

    original_transcript TEXT,

    transcript TEXT,

    transcription_model TEXT,

    transcription_language TEXT,

    transcription_error TEXT,

    -- Processing status

    status TEXT NOT NULL DEFAULT 'uploaded'
        CHECK (
            status IN (
                'uploaded',
                'transcribing',
                'transcribed',
                'approved',
                'indexing',
                'indexed',
                'failed'
            )
        ),

    -- Associated searchable knowledge document

    document_id TEXT UNIQUE
        REFERENCES knowledge_documents(id)
        ON DELETE SET NULL,

    -- Additional information

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    transcribed_utc TIMESTAMPTZ,

    approved_utc TIMESTAMPTZ,

    indexed_utc TIMESTAMPTZ

);


-- --------------------------------------------------
-- Journal lookup indexes
-- --------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_voice_journals_profile
ON voice_journals(profile_id);


CREATE INDEX IF NOT EXISTS idx_voice_journals_created
ON voice_journals(profile_id, created_utc DESC);


CREATE INDEX IF NOT EXISTS idx_voice_journals_status
ON voice_journals(status);


COMMIT;
