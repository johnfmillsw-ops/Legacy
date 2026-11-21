
BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

-- User accounts
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email
ON users (LOWER(email));


-- Knowledge profiles
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


-- Individual knowledge entries
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


-- Semantic embeddings
CREATE TABLE IF NOT EXISTS knowledge_embeddings (
    entry_id TEXT PRIMARY KEY
        REFERENCES knowledge_entries(id)
        ON DELETE CASCADE,
    embedding VECTOR(1536) NOT NULL,
    embedding_model TEXT NOT NULL,
    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- Keyword retrieval index
CREATE INDEX IF NOT EXISTS idx_entries_text_search
ON knowledge_entries
USING GIN (
    to_tsvector('english', prompt || ' ' || answer)
);

COMMIT;
