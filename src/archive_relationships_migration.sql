CREATE TABLE IF NOT EXISTS archive_relationships (
    id TEXT PRIMARY KEY,

    profile_id TEXT NOT NULL
        REFERENCES profiles(id)
        ON DELETE CASCADE,

    asset_id TEXT NOT NULL
        REFERENCES archive_assets(id)
        ON DELETE CASCADE,

    target_type TEXT NOT NULL
        CHECK (
            target_type IN (
                'memory',
                'journal',
                'document'
            )
        ),

    target_id TEXT NOT NULL,

    match_score INTEGER NOT NULL
        CHECK (match_score BETWEEN 0 AND 100),

    match_reasons JSONB NOT NULL
        DEFAULT '[]'::jsonb,

    status TEXT NOT NULL
        DEFAULT 'suggested'
        CHECK (
            status IN (
                'suggested',
                'confirmed',
                'rejected'
            )
        ),

    created_utc TIMESTAMPTZ NOT NULL
        DEFAULT NOW(),

    updated_utc TIMESTAMPTZ NOT NULL
        DEFAULT NOW(),

    UNIQUE (
        profile_id,
        asset_id,
        target_type,
        target_id
    )
);

CREATE INDEX IF NOT EXISTS archive_relationships_asset_idx
    ON archive_relationships(profile_id, asset_id, status);

CREATE INDEX IF NOT EXISTS archive_relationships_target_idx
    ON archive_relationships(
        profile_id,
        target_type,
        target_id,
        status
    );
