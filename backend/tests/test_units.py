"""Unit tests: no database, no network."""
import json
import logging
import time

import httpx
import pytest

from app import logs
from app.auth import hash_key, new_key
from app.csvio import CsvError, parse
from app.geocode import NominatimGeocoder, normalise


# ---------- CSV parsing ----------

def test_csv_comma_with_reference():
    rows = parse(b"reference,address\nA1,Nyhavn 1\nA2,Havnegade 10\n", 10)
    assert [(r.row_no, r.reference, r.address) for r in rows] == [(2, "A1", "Nyhavn 1"), (3, "A2", "Havnegade 10")]


def test_csv_semicolon_bom_and_danish_header():
    # Danish Excel exports use ';' and often add a BOM
    rows = parse("﻿ID;Adresse\n7;Nyhavn 1, 1051 København K\n".encode("utf-8"), 10)
    assert rows[0].reference == "7" and rows[0].address == "Nyhavn 1, 1051 København K"


def test_csv_skips_blank_rows_and_keeps_spreadsheet_row_numbers():
    rows = parse(b"address\nA\n\n,\nB\n", 10)
    assert [(r.row_no, r.address) for r in rows] == [(2, "A"), (5, "B")]  # header is row 1


@pytest.mark.parametrize("data, message", [
    (b"", "empty"),
    (b"name\nx\n", "'address' column"),
    (b"address\n\n", "No addresses"),
    (b"address\na\nb\nc\n", "limit is 2"),
    ("address\nø\n".encode("latin-1"), "UTF-8"),
])
def test_csv_errors_are_explained(data, message):
    with pytest.raises(CsvError, match=message):
        parse(data, 2)


# ---------- API keys ----------

def test_keys_are_random_and_only_hashes_are_compared():
    a, b = new_key(), new_key()
    assert a != b and a.startswith("fk_") and len(a) > 30
    assert hash_key(a) == hash_key(a) and hash_key(a) != a and len(hash_key(a)) == 64


# ---------- Nominatim geocoder ----------

def _nominatim(handler, interval=0.0):
    client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": "test-agent"})
    return NominatimGeocoder("https://nominatim.example/search", "", min_interval=interval, client=client)


def test_nominatim_request_and_parsing():
    seen = {}

    def handler(request: httpx.Request):
        seen["params"] = dict(request.url.params)
        seen["ua"] = request.headers["user-agent"]
        return httpx.Response(200, json=[{"display_name": "Nyhavn 1, København", "lon": "12.59", "lat": "55.68"}])

    res = _nominatim(handler).lookup("Nyhavn 1")
    assert res.found and (res.lon, res.lat) == (12.59, 55.68)
    assert seen["params"] == {"q": "Nyhavn 1", "format": "jsonv2", "countrycodes": "dk", "limit": "1"}
    assert seen["ua"] == "test-agent"


def test_nominatim_refusal_is_reported_not_treated_as_not_found():
    import pytest
    from app.geocode import GeocoderUnavailable
    with pytest.raises(GeocoderUnavailable, match="403"):
        _nominatim(lambda r: httpx.Response(403, text="Forbidden")).lookup("Nyhavn 1")


def test_nominatim_not_found():
    assert not _nominatim(lambda r: httpx.Response(200, json=[])).lookup("nowhere").found


def test_nominatim_is_rate_limited():
    g = _nominatim(lambda r: httpx.Response(200, json=[]), interval=0.2)
    start = time.monotonic()
    for _ in range(3):
        g.lookup("x")
    assert time.monotonic() - start >= 0.4  # 3 calls -> at least 2 waits


def test_default_user_agent_identifies_the_app():
    g = NominatimGeocoder("https://x", "me@example.com")
    assert g.client.headers["user-agent"] == "dk-flood-risk-demo/0.1 (me@example.com)"


def test_normalise():
    assert normalise("  Nyhavn   1,\t1051 KØBENHAVN K ") == "nyhavn 1, 1051 københavn k"


# ---------- logging ----------

def test_logs_are_json_with_request_id_and_fields():
    logs.new_request_id("abc123")
    record = logging.LogRecord("api", logging.INFO, __file__, 1, "request", None, None)
    record.fields = {"status": 200, "client_id": 7}
    entry = json.loads(logs.JsonFormatter().format(record))
    assert entry["msg"] == "request" and entry["request_id"] == "abc123"
    assert entry["status"] == 200 and entry["client_id"] == 7 and entry["level"] == "INFO"


# ---------- flood-zone classification ----------

def test_classify_by_attribute_uses_first_matching_rule_and_skips_the_rest():
    from app.admin import classify
    layer = {"classify": {"field": "opfyld_mm", "rules": [
        {"max": 15, "risk_level": 3, "scenario": "one cloudburst"},
        {"max": 30, "risk_level": 2, "scenario": "double cloudburst"},
        {"max": 100, "risk_level": 1, "scenario": "extreme"}]}}
    assert classify(layer, {"opfyld_mm": 9.0}) == ("one cloudburst", 3)
    assert classify(layer, {"opfyld_mm": 15.0}) == ("one cloudburst", 3)   # the limit is inclusive
    assert classify(layer, {"opfyld_mm": 15.5}) == ("double cloudburst", 2)
    assert classify(layer, {"opfyld_mm": 100.0}) == ("extreme", 1)
    assert classify(layer, {"opfyld_mm": 5060.0}) is None                  # needs more rain than any rule
    assert classify(layer, {"opfyld_mm": None}) is None


def test_classify_fixed_level_layer():
    from app.admin import classify
    assert classify({"scenario": "s", "risk_level": 2}, {"x": 1}) == ("s", 2)
