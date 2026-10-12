"""
Single place to open Postgres connections.

Every module imports get_connection() from here instead of hardcoding
credentials, so the whole system reads one config (.env -> core/config.py).
"""
from core.config import config


def get_connection(with_vector: bool = True, readonly: bool = False):
    import psycopg2
    from pgvector.psycopg2 import register_vector

    conn = psycopg2.connect(config.DATABASE_URL)
    if readonly:
        conn.set_session(readonly=True)
    if with_vector:
        register_vector(conn)
    return conn
