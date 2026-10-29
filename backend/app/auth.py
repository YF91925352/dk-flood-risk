"""API keys: one per client. Only a SHA-256 hash is stored, and every query that touches
customer data is filtered by the client id resolved here."""
import hashlib
import secrets
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from .db import get_conn


@dataclass(frozen=True)
class Client:
    id: int
    name: str


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_key() -> str:
    return "fk_" + secrets.token_urlsafe(24)


def create_client(conn, name: str) -> str:
    """Create a client and return its API key. The key is not stored and cannot be shown again."""
    key = new_key()
    conn.execute("INSERT INTO clients (name, key_hash) VALUES (%s, %s)", (name, hash_key(key)))
    return key


def current_client(x_api_key: str | None = Header(default=None), conn=Depends(get_conn)) -> Client:
    if not x_api_key:
        raise HTTPException(401, "Missing X-API-Key header")
    row = conn.execute("SELECT id, name FROM clients WHERE key_hash = %s", (hash_key(x_api_key),)).fetchone()
    if not row:
        raise HTTPException(401, "Invalid API key")
    return Client(*row)
