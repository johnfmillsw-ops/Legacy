BEGIN;
CREATE TABLE IF NOT EXISTS archive_match_jobs (
 profile_id text NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
 asset_id text NOT NULL REFERENCES archive_assets(id) ON DELETE CASCADE,
 target_type text NOT NULL CHECK(target_type IN ('memory','journal','document','voice')),
 target_id text NOT NULL,
 attempts integer NOT NULL DEFAULT 0,
 available_utc timestamptz NOT NULL DEFAULT now(),
 failed boolean NOT NULL DEFAULT false,
 PRIMARY KEY(profile_id,asset_id,target_type,target_id)
);
CREATE INDEX IF NOT EXISTS archive_match_jobs_ready ON archive_match_jobs(available_utc) WHERE NOT failed;
CREATE OR REPLACE VIEW archive_match_sources AS
 SELECT profile_id,'memory'::text AS target_type,id AS target_id,category AS title,event_date,concat_ws(' ',memory_text,source_excerpt) AS text FROM structured_memories WHERE status='approved'
 UNION ALL SELECT j.profile_id,'journal',e.id,e.title,e.entry_date::text,concat_ws(' ',e.title,e.content) FROM journal_entries e JOIN journals j ON j.id=e.journal_id WHERE e.status='published' AND e.ai_preference='include'
 UNION ALL SELECT profile_id,'voice',id,title,NULL::text,concat_ws(' ',title,coalesce(nullif(transcript,''),original_transcript,'')) FROM voice_journals WHERE status IN ('approved','indexed')
 UNION ALL SELECT profile_id,'document',id,title,NULL::text,concat_ws(' ',title,original_text) FROM knowledge_documents d WHERE NOT EXISTS (SELECT 1 FROM journal_entries e WHERE e.document_id=d.id) AND NOT EXISTS (SELECT 1 FROM voice_journals v WHERE v.document_id=d.id);
CREATE OR REPLACE FUNCTION archive_enqueue_photo() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO archive_match_jobs(profile_id,asset_id,target_type,target_id)
 SELECT NEW.profile_id,NEW.id,s.target_type,s.target_id FROM archive_match_sources s WHERE s.profile_id=NEW.profile_id
 ON CONFLICT(profile_id,asset_id,target_type,target_id) DO UPDATE SET attempts=0,failed=false,available_utc=now();
 RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION archive_enqueue_record() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r jsonb; p text; k text; t text;
BEGIN
 IF TG_OP='DELETE' THEN r=to_jsonb(OLD); ELSE r=to_jsonb(NEW); END IF;
 k=r->>'id'; t=TG_ARGV[0];
 IF t='journal' THEN SELECT profile_id INTO p FROM journals WHERE id=r->>'journal_id'; ELSE p=r->>'profile_id'; END IF;
 IF p IS NOT NULL THEN
 INSERT INTO archive_match_jobs(profile_id,asset_id,target_type,target_id)
 SELECT p,a.id,t,k FROM archive_assets a WHERE a.profile_id=p
 ON CONFLICT(profile_id,asset_id,target_type,target_id) DO UPDATE SET attempts=0,failed=false,available_utc=now();
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF; RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS archive_match_photo ON archive_assets;
CREATE TRIGGER archive_match_photo AFTER INSERT OR UPDATE OF title,description,event_date,location,people ON archive_assets FOR EACH ROW EXECUTE FUNCTION archive_enqueue_photo();
DROP TRIGGER IF EXISTS archive_match_memory ON structured_memories;
CREATE TRIGGER archive_match_memory AFTER INSERT OR DELETE OR UPDATE OF memory_text,source_excerpt,event_date,status,category ON structured_memories FOR EACH ROW EXECUTE FUNCTION archive_enqueue_record('memory');
DROP TRIGGER IF EXISTS archive_match_journal ON journal_entries;
CREATE TRIGGER archive_match_journal AFTER INSERT OR DELETE OR UPDATE OF title,content,entry_date,status,ai_preference ON journal_entries FOR EACH ROW EXECUTE FUNCTION archive_enqueue_record('journal');
DROP TRIGGER IF EXISTS archive_match_voice ON voice_journals;
CREATE TRIGGER archive_match_voice AFTER INSERT OR DELETE OR UPDATE OF title,transcript,original_transcript,status ON voice_journals FOR EACH ROW EXECUTE FUNCTION archive_enqueue_record('voice');
DROP TRIGGER IF EXISTS archive_match_document ON knowledge_documents;
CREATE TRIGGER archive_match_document AFTER INSERT OR DELETE OR UPDATE OF title,original_text ON knowledge_documents FOR EACH ROW EXECUTE FUNCTION archive_enqueue_record('document');
INSERT INTO archive_match_jobs(profile_id,asset_id,target_type,target_id)
SELECT a.profile_id,a.id,s.target_type,s.target_id FROM archive_assets a JOIN archive_match_sources s ON s.profile_id=a.profile_id ON CONFLICT DO NOTHING;
COMMIT;
