BEGIN;

ALTER TABLE journals
ADD COLUMN IF NOT EXISTS ai_default_enabled
BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE journal_entries
ADD COLUMN IF NOT EXISTS ai_preference
TEXT NOT NULL DEFAULT 'inherit'
CHECK (
    ai_preference IN (
        'inherit',
        'include',
        'private'
    )
);

COMMIT;
