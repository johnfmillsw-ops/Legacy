"""Durable local-only matching. Run separately from the web server."""
import argparse
import logging
import time
from uuid import uuid4
from psycopg.types.json import Jsonb
from database import database_connection
from archive_matching import score_candidate


def evaluate(asset, target, profile_id):
    from archive_embedding_cache import embedding_scope
    with embedding_scope(profile_id):
        return score_candidate(asset, target, {}, 1)


def process_one():
    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('''SELECT * FROM archive_match_jobs WHERE NOT failed AND available_utc<=now()
                ORDER BY available_utc,asset_id,target_type,target_id LIMIT 1 FOR UPDATE SKIP LOCKED''')
            job=cur.fetchone()
            if not job:
                return False
            key=tuple(job[k] for k in ('profile_id','asset_id','target_type','target_id'))
            where='profile_id=%s AND asset_id=%s AND target_type=%s AND target_id=%s'
            try:
                with conn.transaction():
                    cur.execute('SELECT title,description,event_date,location,people FROM archive_assets WHERE profile_id=%s AND id=%s',key[:2])
                    asset=cur.fetchone()
                    cur.execute('SELECT * FROM archive_match_sources WHERE profile_id=%s AND target_type=%s AND target_id=%s',(key[0],key[2],key[3]))
                    target=cur.fetchone()
                    score,reasons=evaluate(asset,target,key[0]) if asset and target else (0,[])
                    if score>=35:
                        cur.execute('''INSERT INTO archive_relationships(id,profile_id,asset_id,target_type,target_id,match_score,match_reasons,status)
                            VALUES(%s,%s,%s,%s,%s,%s,%s,'suggested')
                            ON CONFLICT(profile_id,asset_id,target_type,target_id) DO UPDATE SET match_score=excluded.match_score,match_reasons=excluded.match_reasons,updated_utc=now()
                            WHERE archive_relationships.status='suggested' ''',(uuid4().hex,*key,score,Jsonb(reasons)))
                    else:
                        cur.execute('DELETE FROM archive_relationships WHERE '+where+" AND status='suggested'",key)
                    cur.execute('DELETE FROM archive_match_jobs WHERE '+where,key)
            except Exception as exc:
                logging.error('Archive matching job failed: %s',type(exc).__name__)
                cur.execute('UPDATE archive_match_jobs SET attempts=attempts+1,failed=(attempts+1>=5),available_utc=now()+interval \'60 seconds\' WHERE '+where,key)
            return True


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            worked=process_one()
            if not worked:
                if args.once: return
                time.sleep(5)
        except Exception as exc:
            logging.error('Archive worker database error: %s',type(exc).__name__)
            if args.once: raise
            time.sleep(15)

if __name__=='__main__': main()
