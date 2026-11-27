CREATE TABLE IF NOT EXISTS personality_synthesis_checkpoints (
 profile_id TEXT PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
 last_assessment_count INTEGER NOT NULL DEFAULT 0,
 last_revision INTEGER NOT NULL DEFAULT 0,
 updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE personality_jobs ADD COLUMN IF NOT EXISTS synthesis_revision INTEGER;
ALTER TABLE personality_trait_profiles ADD COLUMN IF NOT EXISTS supporting_evidence JSONB NOT NULL DEFAULT '[]'::jsonb;
