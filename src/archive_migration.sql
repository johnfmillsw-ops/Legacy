BEGIN;

CREATE TABLE IF NOT EXISTS archive_assets (
    id TEXT PRIMARY KEY,

    profile_id TEXT NOT NULL
        REFERENCES profiles(id)
        ON DELETE CASCADE,

    asset_type TEXT NOT NULL
        DEFAULT 'photo',

    title TEXT NOT NULL,

    description TEXT NOT NULL
        DEFAULT '',

    event_date TEXT NOT NULL
        DEFAULT '',

    location TEXT NOT NULL
        DEFAULT '',

    people TEXT NOT NULL
        DEFAULT '',

    original_filename TEXT NOT NULL,

    mime_type TEXT NOT NULL,

    file_size_bytes BIGINT NOT NULL,

    content_hash TEXT NOT NULL,

    original_data BYTEA NOT NULL,

    thumbnail_data BYTEA NOT NULL,

    created_utc TIMESTAMPTZ NOT NULL
        DEFAULT NOW(),

    updated_utc TIMESTAMPTZ NOT NULL
        DEFAULT NOW(),

    CONSTRAINT archive_asset_type_check
        CHECK (asset_type = 'photo'),

    CONSTRAINT archive_asset_size_check
        CHECK (
            file_size_bytes > 0
            AND file_size_bytes <= 15728640
        ),

    UNIQUE (profile_id, content_hash)
);

CREATE INDEX IF NOT EXISTS archive_assets_profile_idx
    ON archive_assets(profile_id, created_utc DESC);

COMMIT;
