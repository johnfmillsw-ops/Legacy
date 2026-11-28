BEGIN;

ALTER TABLE archive_relationships
    DROP CONSTRAINT IF EXISTS
    archive_relationships_target_type_check;

ALTER TABLE archive_relationships
    ADD CONSTRAINT archive_relationships_target_type_check
    CHECK (
        target_type IN (
            'memory',
            'journal',
            'document',
            'voice'
        )
    );

COMMIT;
