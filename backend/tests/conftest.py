"""Test setup.

Unit tests need nothing. Integration tests need PostGIS at DATABASE_URL (docker compose or the
CI service). Without a database they are skipped locally; with REQUIRE_DB=1 (CI) they fail instead.
"""
import os
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
os.environ.setdefault("DATABASE_URL", "postgresql://flood:flood@localhost:5432/flood")
os.environ["GEOCODER"] = "fixture"
os.environ["GEOCODER_FIXTURE"] = str(HERE / "fixtures" / "addresses.json")
os.environ["MAX_BATCH_ROWS"] = "5"
os.environ["LOG_LEVEL"] = "WARNING"

# Nested test zones around Copenhagen harbour, drawn in lon/lat and stored in EPSG:25832
# exactly like the real data: high inside medium inside low.
ZONES = [
    ("test: 20-year event", 3, (12.585, 55.678, 12.595, 55.682)),
    ("test: 100-year event", 2, (12.575, 55.670, 12.600, 55.690)),
    ("test: 1000-year event", 1, (12.500, 55.650, 12.620, 55.700)),
]
COVERAGE = (12.450, 55.620, 12.660, 55.720)  # Copenhagen only; Viborg is outside


def _db_available() -> bool:
    try:
        import psycopg
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3):
            return True
    except Exception:
        return False


DB = _db_available()


def pytest_collection_modifyitems(config, items):
    if DB:
        return
    if os.environ.get("REQUIRE_DB") == "1":
        raise pytest.UsageError(f"REQUIRE_DB=1 but no database at {os.environ['DATABASE_URL']}")
    skip = pytest.mark.skip(reason="no PostGIS database available")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


def pytest_configure(config):
    config.addinivalue_line("markers", "db: needs a PostGIS database")


def box_sql(x1, y1, x2, y2) -> str:
    return (f"ST_Multi(ST_Transform(ST_GeomFromText('POLYGON(({x1} {y1},{x2} {y1},{x2} {y2},{x1} {y2},{x1} {y1}))', 4326), 25832))")


@pytest.fixture
def conn():
    import psycopg
    from app.db import SCHEMA
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
        c.execute(SCHEMA.read_text())
        c.execute("TRUNCATE clients, portfolios, portfolio_rows, geocode_cache, flood_zones, coverage_areas "
                  "RESTART IDENTITY CASCADE")
        c.execute(f"INSERT INTO coverage_areas (name, geom) VALUES ('test: Copenhagen', {box_sql(*COVERAGE)})")
        for scenario, level, box in ZONES:
            c.execute(f"INSERT INTO flood_zones (scenario, risk_level, source, geom) VALUES (%s, %s, 'test', {box_sql(*box)})",
                      (scenario, level))
        yield c


@pytest.fixture
def api(conn):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as client:
        yield client


@pytest.fixture
def keys(conn):
    from app.auth import create_client
    return {"a": create_client(conn, "Client A"), "b": create_client(conn, "Client B")}
