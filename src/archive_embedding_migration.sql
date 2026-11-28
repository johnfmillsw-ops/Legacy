BEGIN;
CREATE TABLE IF NOT EXISTS archive_embedding_cache (
 profile_id text NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
 model_version text NOT NULL,
 content_hash text NOT NULL,
 embedding vector(384) NOT NULL,
 created_utc timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(profile_id,model_version,content_hash)
);
COMMIT;
