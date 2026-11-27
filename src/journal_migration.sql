
BEGIN;

-- --------------------------------------------------
-- Personalized journals
-- --------------------------------------------------

CREATE TABLE IF NOT EXISTS journals (

    id TEXT PRIMARY KEY,

    profile_id TEXT NOT NULL
        REFERENCES profiles(id)
        ON DELETE CASCADE,

    title TEXT NOT NULL DEFAULT 'My Journal'
        CHECK (char_length(trim(title)) BETWEEN 1 AND 200),

    subtitle TEXT NOT NULL DEFAULT '',

    design JSONB NOT NULL DEFAULT '{
        "cover_style": "leather",
        "cover_color": "#594536",
        "accent_color": "#c5ab85",
        "emblem": "none",
        "typography": "classic",
        "paper_style": "lined",
        "page_layout": "single"
    }'::jsonb
        CHECK (jsonb_typeof(design) = 'object'),

    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()

);


CREATE INDEX IF NOT EXISTS idx_journals_profile
ON journals(profile_id);


-- --------------------------------------------------
-- Written journal entries
-- --------------------------------------------------

CREATE TABLE IF NOT EXISTS journal_entries (

    id TEXT PRIMARY KEY,

    journal_id TEXT NOT NULL
        REFERENCES journals(id)
        ON DELETE CASCADE,

    title TEXT NOT NULL DEFAULT '',

    content TEXT NOT NULL DEFAULT '',

    entry_date DATE NOT NULL DEFAULT CURRENT_DATE,

    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (
            status IN (
                'draft',
                'published'
            )
        ),

    allow_ai_processing BOOLEAN NOT NULL DEFAULT FALSE,

    document_id TEXT UNIQUE
        REFERENCES knowledge_documents(id)
        ON DELETE SET NULL,

    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    published_utc TIMESTAMPTZ,

    CHECK (
        status <> 'published'
        OR published_utc IS NOT NULL
    )

);


CREATE INDEX IF NOT EXISTS idx_journal_entries_journal
ON journal_entries(journal_id);


CREATE INDEX IF NOT EXISTS idx_journal_entries_date
ON journal_entries(journal_id, entry_date DESC);


COMMIT;
