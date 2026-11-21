
BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

-- --------------------------------------------------
-- User accounts
-- --------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
ON users (LOWER(email));


-- --------------------------------------------------
-- Knowledge profiles
-- --------------------------------------------------

CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES users(id)
        ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    profile_data JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_profiles_owner
ON profiles(owner_id);


-- --------------------------------------------------
-- Individual knowledge entries
-- --------------------------------------------------

CREATE TABLE IF NOT EXISTS knowledge_entries (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES profiles(id)
        ON DELETE CASCADE,
    category TEXT NOT NULL,
    prompt TEXT NOT NULL DEFAULT '',
    answer TEXT NOT NULL,
    tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_type TEXT NOT NULL DEFAULT 'interview',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entries_profile
ON knowledge_entries(profile_id);

CREATE INDEX IF NOT EXISTS idx_entries_category
ON knowledge_entries(profile_id, category);


-- --------------------------------------------------
-- Individual entry embeddings
-- --------------------------------------------------

CREATE TABLE IF NOT EXISTS knowledge_embeddings (
    entry_id TEXT PRIMARY KEY
        REFERENCES knowledge_entries(id)
        ON DELETE CASCADE,
    embedding VECTOR(384) NOT NULL,
    embedding_model TEXT NOT NULL,
    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- --------------------------------------------------
-- Full document storage
-- --------------------------------------------------

CREATE TABLE IF NOT EXISTS knowledge_documents (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES profiles(id)
        ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL
        CHECK (
            source_type IN (
                'text',
                'document',
                'audio_transcript'
            )
        ),
    original_text TEXT NOT NULL,
    file_path TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_profile
ON knowledge_documents(profile_id);


-- --------------------------------------------------
-- Searchable document chunks
-- --------------------------------------------------

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL
        REFERENCES knowledge_documents(id)
        ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL
        CHECK (chunk_index >= 0),
    chunk_text TEXT NOT NULL,
    token_start INTEGER NOT NULL
        CHECK (token_start >= 0),
    token_end INTEGER NOT NULL
        CHECK (token_end > token_start),
    embedding VECTOR(384),
    embedding_model TEXT,
    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (document_id, chunk_index),

    CHECK (
        (
            embedding IS NULL
            AND embedding_model IS NULL
        )
        OR
        (
            embedding IS NOT NULL
            AND embedding_model IS NOT NULL
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_chunks_document
ON knowledge_chunks(document_id);


-- --------------------------------------------------
-- Full-text search indexes
-- --------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_entries_text_search
ON knowledge_entries
USING GIN (
    to_tsvector('english', prompt || ' ' || answer)
);

CREATE INDEX IF NOT EXISTS idx_chunks_text_search
ON knowledge_chunks
USING GIN (
    to_tsvector('english', chunk_text)
);

COMMIT;
