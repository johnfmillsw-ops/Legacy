BEGIN;
ALTER TABLE archive_assets ADD COLUMN IF NOT EXISTS preservation_mode text NOT NULL DEFAULT 'original';
ALTER TABLE archive_assets ADD COLUMN IF NOT EXISTS display_data bytea;
ALTER TABLE archive_assets ADD COLUMN IF NOT EXISTS thumbnail_mime text NOT NULL DEFAULT 'image/jpeg';
COMMIT;
