
CREATE OR REPLACE FUNCTION invalidate_personality_synthesis()
RETURNS TRIGGER AS $$
DECLARE
    affected_profile TEXT;
BEGIN

    IF TG_OP = 'DELETE' THEN
        affected_profile := OLD.profile_id;
    ELSE
        affected_profile := NEW.profile_id;
    END IF;

    -- Existing evidence changed or was removed.
    -- Invalidate the portrait to prevent outdated
    -- or withdrawn information from remaining visible.

    IF TG_OP IN ('DELETE', 'UPDATE') THEN

        DELETE FROM personality_trait_profiles
        WHERE profile_id = affected_profile;

        DELETE FROM personality_formulations
        WHERE profile_id = affected_profile;

    END IF;

    -- New evidence does not erase the existing portrait.
    -- The revision identifies evidence awaiting synthesis.

    UPDATE personality_models
    SET status = 'stale',
        revision = revision + 1,
        updated_utc = NOW()
    WHERE profile_id = affected_profile;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;

    RETURN NEW;

END;
$$ LANGUAGE plpgsql;
