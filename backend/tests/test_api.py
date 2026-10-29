"""Integration tests against a real PostGIS database."""
import json

import pytest

pytestmark = pytest.mark.db

H = lambda key: {"X-API-Key": key}  # noqa: E731


def test_health_reports_database_and_zone_count(api):
    r = api.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok", "flood_zones": 3, "coverage_areas": 1}
    assert r.headers["X-Request-ID"]


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "fk_not_a_real_key"}])
def test_risk_needs_a_valid_key(api, headers):
    assert api.get("/api/risk", params={"address": "Nyhavn 1, 1051 København K"}, headers=headers).status_code == 401


@pytest.mark.parametrize("address, level, scenario", [
    ("Nyhavn 1, 1051 København K", "high", "test: 20-year event"),        # inside all three zones: worst wins
    ("Havnegade 10, 1058 København K", "medium", "test: 100-year event"),
    ("Frederiksberg Allé 1, 1820 Frederiksberg C", "low", "test: 1000-year event"),
    ("Valby Langgade 1, 2500 Valby", "none", None),          # inside coverage, outside all zones
    ("Viborgvej 1, 8800 Viborg", "not_covered", None),        # no data loaded there: not "none"
])
def test_risk_levels_from_spatial_lookup(api, keys, address, level, scenario):
    body = api.get("/api/risk", params={"address": address}, headers=H(keys["a"])).json()
    assert (body["found"], body["risk_level"], body["scenario"]) == (True, level, scenario)
    assert "coverage" in body["note"]


def test_unknown_address_is_reported_not_guessed(api, keys):
    body = api.get("/api/risk", params={"address": "Ikke en adresse 999"}, headers=H(keys["a"])).json()
    assert body["found"] is False and body["risk_level"] == "unknown"


def test_geocoding_is_cached_including_misses(api, keys, conn):
    calls = []
    real = api.app.state.geocoder
    api.app.state.geocoder = type("Counting", (), {
        "name": "counting", "lookup": lambda self, a: calls.append(a) or real.lookup(a)})()
    try:
        for _ in range(2):
            api.get("/api/risk", params={"address": "Nyhavn 1, 1051 København K"}, headers=H(keys["a"]))
            api.get("/api/risk", params={"address": "Ikke en adresse 999"}, headers=H(keys["a"]))
    finally:
        api.app.state.geocoder = real
    assert len(calls) == 2  # each address looked up once; the second round came from the cache
    assert conn.execute("SELECT count(*) FROM geocode_cache WHERE NOT found").fetchone()[0] == 1


CSV = (
    "reference;adresse\n"
    "P1;Nyhavn 1, 1051 København K\n"
    "P2;Havnegade 10, 1058 København K\n"
    "P3;Valby Langgade 1, 2500 Valby\n"
    "P5;Viborgvej 1, 8800 Viborg\n"
    "P4;Ikke en adresse 999\n"
).encode("utf-8")


def upload(api, key, data=CSV, name="Harbour portfolio"):
    return api.post("/api/portfolios", headers=H(key), data={"name": name},
                    files={"file": ("portfolio.csv", data, "text/csv")})


def test_portfolio_upload_assesses_every_row(api, keys):
    r = upload(api, keys["a"])
    assert r.status_code == 201
    p = r.json()
    assert p["name"] == "Harbour portfolio" and p["row_count"] == 5
    assert [(x["row_no"], x["reference"], x["status"], x["risk_level"]) for x in p["rows"]] == [
        (2, "P1", "ok", "high"), (3, "P2", "ok", "medium"), (4, "P3", "ok", "none"),
        (5, "P5", "ok", "not_covered"), (6, "P4", "not_found", "unknown")]
    assert p["rows"][0]["lon"] == pytest.approx(12.59)


def test_portfolio_list_has_counts_per_level(api, keys):
    upload(api, keys["a"])
    [p] = api.get("/api/portfolios", headers=H(keys["a"])).json()
    assert {k: p[k] for k in ("row_count", "high", "medium", "low", "none", "not_covered", "unknown")} == {
        "row_count": 5, "high": 1, "medium": 1, "low": 0, "none": 1, "not_covered": 1, "unknown": 1}


def test_clients_only_see_their_own_portfolios(api, keys):
    pid = upload(api, keys["a"]).json()["id"]
    assert api.get("/api/portfolios", headers=H(keys["b"])).json() == []
    # 404, not 403: client B cannot even learn that portfolio exists
    assert api.get(f"/api/portfolios/{pid}", headers=H(keys["b"])).status_code == 404
    assert api.get(f"/api/portfolios/{pid}", headers=H(keys["a"])).status_code == 200


@pytest.mark.parametrize("data, status, message", [
    (b"name\nx\n", 422, "'address' column"),
    (b"address\n" + b"Nyhavn 1\n" * 6, 422, "limit is 5"),
])
def test_bad_uploads_are_rejected_with_a_reason(api, keys, conn, data, status, message):
    r = upload(api, keys["a"], data)
    assert r.status_code == status and message in r.json()["detail"]
    assert conn.execute("SELECT count(*) FROM portfolios").fetchone()[0] == 0  # nothing half-saved


def test_api_keys_are_stored_hashed(conn, keys):
    stored = [r[0] for r in conn.execute("SELECT key_hash FROM clients").fetchall()]
    assert keys["a"] not in stored and len(stored[0]) == 64


def test_load_zones_from_shapefile(conn, tmp_path):
    """The loader reads a shapefile in EPSG:25832, filters by attribute and replaces the zones."""
    import shapefile
    from app.admin import load_zones

    ring = json.loads(conn.execute(
        "SELECT ST_AsGeoJSON(ST_Transform(ST_GeomFromText("
        "'POLYGON((12.585 55.678,12.595 55.678,12.595 55.682,12.585 55.682,12.585 55.678))', 4326), 25832))"
    ).fetchone()[0])["coordinates"]
    w = shapefile.Writer(str(tmp_path / "zones"), shapeType=shapefile.POLYGON)
    w.field("SCENARIE", "C")
    w.poly(ring)
    w.record("2050")
    w.poly(ring)
    w.record("2100")
    w.close()
    (tmp_path / "zones.json").write_text(json.dumps({"source": "unit test",
        "coverage": {"name": "test area", "bbox": [700000, 6150000, 750000, 6200000]}, "layers": [
        {"file": "zones.shp", "scenario": "2100 storm surge", "risk_level": 2, "where": {"SCENARIE": "2100"}}]}))

    counts = load_zones(conn, tmp_path / "zones.json")
    assert counts == {"2100 storm surge": 1}
    rows = conn.execute("SELECT scenario, risk_level, ST_SRID(geom), GeometryType(geom) FROM flood_zones").fetchall()
    assert rows == [("2100 storm surge", 2, 25832, "MULTIPOLYGON")]
    hit = conn.execute("SELECT count(*) FROM flood_zones WHERE ST_Intersects(geom, "
                       "ST_Transform(ST_SetSRID(ST_MakePoint(12.59, 55.68), 4326), 25832))").fetchone()[0]
    assert hit == 1
    assert conn.execute("SELECT name FROM coverage_areas").fetchall() == [("test area",)]


def test_geocoder_outage_returns_503_and_caches_nothing(api, keys, conn):
    from app.geocode import GeocoderUnavailable

    class Down:
        name = "down"

        def lookup(self, address):
            raise GeocoderUnavailable("HTTPStatusError: 403 Forbidden")

    real, api.app.state.geocoder = api.app.state.geocoder, Down()
    try:
        r = api.get("/api/risk", params={"address": "Nyhavn 1, 1051 København K"}, headers=H(keys["a"]))
        u = upload(api, keys["a"])
    finally:
        api.app.state.geocoder = real
    assert r.status_code == 503 and "unavailable" in r.json()["detail"]
    assert u.status_code == 503
    assert conn.execute("SELECT count(*) FROM geocode_cache").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM portfolios").fetchone()[0] == 0
