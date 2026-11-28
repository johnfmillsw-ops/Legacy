"""Profile-scoped durable embedding cache; each successful vector commits independently."""
from contextvars import ContextVar
from contextlib import contextmanager
from hashlib import sha256
import json
import math

_scope = ContextVar('archive_embedding_profile', default=None)

@contextmanager
def embedding_scope(profile_id):
    token = _scope.set(profile_id)
    try:
        yield
    finally:
        _scope.reset(token)

def cached_vector(text):
    from embeddings import MODEL_NAME, embed_text
    from database import database_connection
    profile_id = _scope.get()
    if not profile_id:
        raise RuntimeError('Archive embedding requires a profile scope')
    key = (profile_id, MODEL_NAME + ':normalized:v1', sha256(text.encode('utf-8')).hexdigest())
    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT embedding::text AS value FROM archive_embedding_cache WHERE profile_id=%s AND model_version=%s AND content_hash=%s', key)
            row = cur.fetchone()
    if row:
        return tuple(json.loads(row['value']))
    value = tuple(float(x) for x in embed_text(text))
    if len(value) != 384 or not all(math.isfinite(x) for x in value):
        raise ValueError('Invalid archive embedding')
    with database_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO archive_embedding_cache(profile_id,model_version,content_hash,embedding) VALUES (%s,%s,%s,%s::vector) ON CONFLICT DO NOTHING', (*key,json.dumps(value)))
    return value
