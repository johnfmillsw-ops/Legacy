BEGIN;

-- Independent psychological model for each profile.

CREATE TABLE IF NOT EXISTS personality_models (
    profile_id TEXT PRIMARY KEY
        REFERENCES profiles(id) ON DELETE CASCADE,

    framework_version INTEGER NOT NULL DEFAULT 1,

    revision INTEGER NOT NULL DEFAULT 0,

    status TEXT NOT NULL DEFAULT 'developing'
        CHECK (status IN (
            'developing',
            'processing',
            'ready',
            'stale',
            'failed'
        )),

    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- Psychological analysis of each individual memory.

CREATE TABLE IF NOT EXISTS personality_memory_assessments (
    id TEXT PRIMARY KEY,

    profile_id TEXT NOT NULL
        REFERENCES personality_models(profile_id)
        ON DELETE CASCADE,

    memory_id TEXT NOT NULL
        REFERENCES structured_memories(id)
        ON DELETE CASCADE,

    framework_version INTEGER NOT NULL,

    source_hash TEXT NOT NULL,

    psychological_interpretation TEXT NOT NULL,

    emotional_context JSONB NOT NULL DEFAULT '{}',

    behavioral_context JSONB NOT NULL DEFAULT '{}',

    formulation_evidence JSONB NOT NULL DEFAULT '[]',

    provider_model TEXT NOT NULL,

    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        profile_id,
        memory_id,
        framework_version
    ),

    UNIQUE (id, profile_id)
);


-- Specific psychological evidence extracted from memories.

CREATE TABLE IF NOT EXISTS personality_trait_evidence (
    id TEXT PRIMARY KEY,

    profile_id TEXT NOT NULL,

    assessment_id TEXT NOT NULL,

    trait_key TEXT NOT NULL,

    expression_score NUMERIC(5,2)
        CHECK (expression_score BETWEEN 0 AND 100),

    evidence_confidence NUMERIC(5,2)
        CHECK (evidence_confidence BETWEEN 0 AND 100),

    evidence_type TEXT NOT NULL
        CHECK (evidence_type IN (
            'explicit_self_report',
            'reported_behavior',
            'reported_experience',
            'psychological_inference'
        )),

    temporal_scope TEXT NOT NULL
        CHECK (temporal_scope IN (
            'situational',
            'recurring',
            'enduring',
            'unknown'
        )),

    interpretation TEXT NOT NULL,

    source_excerpt TEXT NOT NULL,

    situational_context TEXT NOT NULL DEFAULT '',

    alternative_explanation TEXT NOT NULL DEFAULT '',

    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    FOREIGN KEY (assessment_id, profile_id)
        REFERENCES personality_memory_assessments(
            id, profile_id
        )
        ON DELETE CASCADE,

    UNIQUE (assessment_id, trait_key)
);


-- Synthesized psychological traits across all memories.

CREATE TABLE IF NOT EXISTS personality_trait_profiles (
    profile_id TEXT NOT NULL
        REFERENCES personality_models(profile_id)
        ON DELETE CASCADE,

    trait_key TEXT NOT NULL,

    framework_version INTEGER NOT NULL,

    model_revision INTEGER NOT NULL,

    expression_score NUMERIC(5,2)
        CHECK (expression_score BETWEEN 0 AND 100),

    evidence_confidence NUMERIC(5,2)
        CHECK (evidence_confidence BETWEEN 0 AND 100),

    interpretation TEXT NOT NULL DEFAULT '',

    behavioral_patterns JSONB NOT NULL DEFAULT '[]',

    contextual_variations JSONB NOT NULL DEFAULT '[]',

    contradictory_evidence JSONB NOT NULL DEFAULT '[]',

    limitations TEXT NOT NULL DEFAULT '',

    evidence_count INTEGER NOT NULL DEFAULT 0
        CHECK (evidence_count >= 0),

    updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (profile_id, trait_key)
);


-- Deep psychological formulation.

CREATE TABLE IF NOT EXISTS personality_formulations (
    profile_id TEXT NOT NULL
        REFERENCES personality_models(profile_id)
        ON DELETE CASCADE,

    formulation_key TEXT NOT NULL,

    framework_version INTEGER NOT NULL,

    model_revision INTEGER NOT NULL,

    interpretation TEXT NOT NULL,

    supporting_evidence JSONB NOT NULL DEFAULT '[]',

    contradictory_evidence JSONB NOT NULL DEFAULT '[]',

    alternative_explanations JSONB NOT NULL DEFAULT '[]',

    evidence_confidence NUMERIC(5,2)
        CHECK (evidence_confidence BETWEEN 0 AND 100),

    updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (profile_id, formulation_key)
);


-- Persistent background processing queue.

CREATE TABLE IF NOT EXISTS personality_jobs (
    id TEXT PRIMARY KEY,

    profile_id TEXT NOT NULL
        REFERENCES profiles(id) ON DELETE CASCADE,

    memory_id TEXT
        REFERENCES structured_memories(id)
        ON DELETE CASCADE,

    framework_version INTEGER NOT NULL,

    job_type TEXT NOT NULL
        CHECK (job_type IN (
            'analyze_memory',
            'synthesize_profile'
        )),

    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending',
            'processing',
            'completed',
            'retry',
            'failed',
            'cancelled'
        )),

    attempts INTEGER NOT NULL DEFAULT 0
        CHECK (attempts >= 0),

    max_attempts INTEGER NOT NULL DEFAULT 3
        CHECK (max_attempts > 0),

    available_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    lease_expires_utc TIMESTAMPTZ,

    worker_id TEXT,

    last_error TEXT,

    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    completed_utc TIMESTAMPTZ,

    CHECK (
        (job_type = 'analyze_memory'
            AND memory_id IS NOT NULL)
        OR
        (job_type = 'synthesize_profile'
            AND memory_id IS NULL)
    )
);


-- Prevent duplicate active jobs for the same memory.

CREATE UNIQUE INDEX IF NOT EXISTS
    personality_active_memory_job_idx
ON personality_jobs (
    profile_id,
    memory_id,
    framework_version
)
WHERE job_type = 'analyze_memory'
AND status IN ('pending', 'processing', 'retry');


-- Prevent simultaneous active synthesis jobs.

CREATE UNIQUE INDEX IF NOT EXISTS
    personality_active_synthesis_job_idx
ON personality_jobs (
    profile_id,
    framework_version
)
WHERE job_type = 'synthesize_profile'
AND status IN ('pending', 'processing', 'retry');


-- Actual provider token usage.

CREATE TABLE IF NOT EXISTS personality_api_usage (
    id TEXT PRIMARY KEY,

    profile_id TEXT NOT NULL
        REFERENCES profiles(id) ON DELETE CASCADE,

    job_id TEXT
        REFERENCES personality_jobs(id)
        ON DELETE SET NULL,

    operation TEXT NOT NULL,

    provider TEXT NOT NULL,

    model TEXT NOT NULL,

    input_tokens BIGINT
        CHECK (input_tokens >= 0),

    output_tokens BIGINT
        CHECK (output_tokens >= 0),

    reasoning_tokens BIGINT
        CHECK (reasoning_tokens >= 0),

    total_tokens BIGINT
        CHECK (total_tokens >= 0),

    estimated_cost_usd NUMERIC(14,8)
        CHECK (estimated_cost_usd >= 0),

    status TEXT NOT NULL
        CHECK (status IN (
            'success',
            'failed',
            'invalid_response'
        )),

    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- Processing and retrieval indexes.

CREATE INDEX IF NOT EXISTS
    personality_jobs_pending_idx
ON personality_jobs (
    status,
    available_utc
);

CREATE INDEX IF NOT EXISTS
    personality_jobs_profile_idx
ON personality_jobs (profile_id, status);

CREATE INDEX IF NOT EXISTS
    personality_assessments_profile_idx
ON personality_memory_assessments (profile_id);

CREATE INDEX IF NOT EXISTS
    personality_evidence_trait_idx
ON personality_trait_evidence (
    profile_id,
    trait_key
);

CREATE INDEX IF NOT EXISTS
    personality_usage_profile_idx
ON personality_api_usage (
    profile_id,
    created_utc
);


-- Invalidate synthesized profiles when evidence changes.
-- Stale psychological conclusions must not remain accessible.

CREATE OR REPLACE FUNCTION
    invalidate_personality_synthesis()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    affected_profile TEXT;
BEGIN

    IF TG_OP = 'DELETE' THEN
        affected_profile := OLD.profile_id;
    ELSE
        affected_profile := NEW.profile_id;
    END IF;

    DELETE FROM personality_trait_profiles
    WHERE profile_id = affected_profile;

    DELETE FROM personality_formulations
    WHERE profile_id = affected_profile;

    UPDATE personality_models
    SET
        status = 'stale',
        revision = revision + 1,
        updated_utc = NOW()
    WHERE profile_id = affected_profile;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;

    RETURN NEW;

END;
$$;


DROP TRIGGER IF EXISTS
    personality_assessment_invalidation
ON personality_memory_assessments;

CREATE TRIGGER personality_assessment_invalidation
AFTER INSERT OR UPDATE OR DELETE
ON personality_memory_assessments
FOR EACH ROW
EXECUTE FUNCTION invalidate_personality_synthesis();


DROP TRIGGER IF EXISTS
    personality_evidence_invalidation
ON personality_trait_evidence;

CREATE TRIGGER personality_evidence_invalidation
AFTER INSERT OR UPDATE OR DELETE
ON personality_trait_evidence
FOR EACH ROW
EXECUTE FUNCTION invalidate_personality_synthesis();

COMMIT;
