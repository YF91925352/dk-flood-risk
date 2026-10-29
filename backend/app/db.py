from pathlib import Path

from psycopg_pool import ConnectionPool

SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"

pool: ConnectionPool | None = None


def open_pool(url: str) -> ConnectionPool:
    global pool
    pool = ConnectionPool(url, min_size=1, max_size=5, open=True, kwargs={"autocommit": False})
    return pool


def apply_schema(p: ConnectionPool) -> None:
    with p.connection() as conn:
        conn.execute(SCHEMA.read_text())


def get_conn():
    """FastAPI dependency: one connection (and transaction) per request."""
    assert pool is not None, "database pool not initialised"
    with pool.connection() as conn:
        yield conn
