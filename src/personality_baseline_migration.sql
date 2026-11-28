CREATE TABLE IF NOT EXISTS personality_baseline_assessments (
    id TEXT PRIMARY KEY,

    profile_id TEXT NOT NULL
        REFERENCES profiles(id) ON DELETE CASCADE,

    instrument_id TEXT NOT NULL,

    instrument_version INTEGER NOT NULL
        CHECK (instrument_version > 0),

    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'completed')),

    responses JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(responses) = 'object'),

    raw_scores JSONB,

    normalized_scores JSONB,

    instrument_metadata JSONB NOT NULL
        DEFAULT '{}'::jsonb,

    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    completed_utc TIMESTAMPTZ,

    CONSTRAINT baseline_completion_integrity CHECK (
        (
            status = 'draft'
            AND completed_utc IS NULL
            AND raw_scores IS NULL
            AND normalized_scores IS NULL
        )
        OR
        (
            status = 'completed'
            AND completed_utc IS NOT NULL
            AND raw_scores IS NOT NULL
            AND normalized_scores IS NOT NULL
            AND jsonb_typeof(raw_scores) = 'object'
            AND jsonb_typeof(normalized_scores) = 'object'
        )
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS
    personality_baseline_one_draft
ON personality_baseline_assessments (
    profile_id,
    instrument_id,
    instrument_version
)
WHERE status = 'draft';

CREATE INDEX IF NOT EXISTS
    personality_baseline_profile_history
ON personality_baseline_assessments (
    profile_id,
    completed_utc DESC
)
WHERE status = 'completed';
