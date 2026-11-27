
BEGIN;

CREATE TABLE IF NOT EXISTS psychological_characteristics (

    id TEXT PRIMARY KEY,

    profile_id TEXT NOT NULL
        REFERENCES profiles(id)
        ON DELETE CASCADE,

    dimension TEXT NOT NULL CHECK (
        dimension IN (
            'cognition',
            'emotion',
            'motivation',
            'personality',
            'attachment',
            'values',
            'interests',
            'social_identity',
            'behavior',
            'meaning'
        )
    ),

    characteristic_key TEXT NOT NULL,

    label TEXT NOT NULL,

    description TEXT NOT NULL DEFAULT '',

    identity_weight NUMERIC(5,2)
        CHECK (identity_weight BETWEEN 0 AND 100),

    evidence_confidence NUMERIC(5,2)
        CHECK (evidence_confidence BETWEEN 0 AND 100),

    weight_factors JSONB NOT NULL DEFAULT '{}'::JSONB,

    temporal_type TEXT NOT NULL DEFAULT 'unknown'
        CHECK (
            temporal_type IN (
                'temporary_state',
                'recurring_pattern',
                'enduring_characteristic',
                'unknown'
            )
        ),

    review_status TEXT NOT NULL DEFAULT 'unreviewed'
        CHECK (
            review_status IN (
                'unreviewed',
                'confirmed',
                'corrected',
                'rejected'
            )
        ),

    user_correction TEXT,

    framework_version INTEGER NOT NULL DEFAULT 1,

    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        profile_id,
        dimension,
        characteristic_key
    ),

    UNIQUE (id, profile_id)
);


CREATE TABLE IF NOT EXISTS psychological_evidence (

    id TEXT PRIMARY KEY,

    profile_id TEXT NOT NULL
        REFERENCES profiles(id)
        ON DELETE CASCADE,

    characteristic_id TEXT NOT NULL,

    source_memory_id TEXT
        REFERENCES structured_memories(id)
        ON DELETE CASCADE,

    source_entry_id TEXT
        REFERENCES knowledge_entries(id)
        ON DELETE CASCADE,

    evidence_type TEXT NOT NULL CHECK (
        evidence_type IN (
            'direct_statement',
            'documented_assessment',
            'reported_behavior',
            'reported_experience',
            'user_confirmation',
            'ai_inference'
        )
    ),

    direction TEXT NOT NULL DEFAULT 'supporting'
        CHECK (
            direction IN (
                'supporting',
                'contradictory',
                'contextual'
            )
        ),

    interpretation TEXT NOT NULL,

    source_excerpt TEXT NOT NULL DEFAULT '',

    weight_factors JSONB NOT NULL DEFAULT '{}'::JSONB,

    temporal_type TEXT NOT NULL DEFAULT 'unknown'
        CHECK (
            temporal_type IN (
                'temporary_state',
                'recurring_pattern',
                'enduring_characteristic',
                'unknown'
            )
        ),

    evidence_date DATE,

    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    FOREIGN KEY (characteristic_id, profile_id)
        REFERENCES psychological_characteristics(id, profile_id)
        ON DELETE CASCADE,

    CHECK (
        num_nonnulls(
            source_memory_id,
            source_entry_id
        ) = 1
    )
);


CREATE UNIQUE INDEX IF NOT EXISTS
    psychological_evidence_memory_unique
ON psychological_evidence (
    characteristic_id,
    source_memory_id
)
WHERE source_memory_id IS NOT NULL;


CREATE UNIQUE INDEX IF NOT EXISTS
    psychological_evidence_entry_unique
ON psychological_evidence (
    characteristic_id,
    source_entry_id
)
WHERE source_entry_id IS NOT NULL;


CREATE INDEX IF NOT EXISTS
    psychological_characteristics_profile_idx
ON psychological_characteristics (
    profile_id,
    dimension
);


CREATE INDEX IF NOT EXISTS
    psychological_evidence_characteristic_idx
ON psychological_evidence (
    characteristic_id
);


CREATE TABLE IF NOT EXISTS psychological_identity_history (

    id TEXT PRIMARY KEY,

    profile_id TEXT NOT NULL
        REFERENCES profiles(id)
        ON DELETE CASCADE,

    characteristic_id TEXT NOT NULL,

    identity_weight NUMERIC(5,2)
        CHECK (identity_weight BETWEEN 0 AND 100),

    evidence_confidence NUMERIC(5,2)
        CHECK (evidence_confidence BETWEEN 0 AND 100),

    evidence_count INTEGER NOT NULL DEFAULT 0
        CHECK (evidence_count >= 0),

    change_reason TEXT NOT NULL DEFAULT '',

    recorded_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    FOREIGN KEY (characteristic_id, profile_id)
        REFERENCES psychological_characteristics(id, profile_id)
        ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS psychological_analysis_progress (

    memory_id TEXT NOT NULL
        REFERENCES structured_memories(id)
        ON DELETE CASCADE,

    framework_version INTEGER NOT NULL,

    characteristics_created INTEGER NOT NULL DEFAULT 0,

    evidence_created INTEGER NOT NULL DEFAULT 0,

    completed_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (
        memory_id,
        framework_version
    )
);


COMMIT;
