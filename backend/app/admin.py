"""Operator commands.

    python -m app.admin create-client "Acme Insurance"     # prints a new API key once
    python -m app.admin load-zones data/zones.json          # (re)load flood hazard polygons
"""
import argparse
import json
import sys
from pathlib import Path

import psycopg
import shapefile  # pyshp: pure Python, no GDAL needed

from .auth import create_client
from .config import settings
from .db import SCHEMA

INSERT = """
INSERT INTO flood_zones (scenario, risk_level, source, geom)
VALUES (%s, %s, %s, ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 25832)), 3)))
"""


def classify(layer: dict, attrs: dict):
    """(scenario, risk_level) for one feature, or None to skip it."""
    if "classify" not in layer:
        return layer["scenario"], layer["risk_level"]
    c = layer["classify"]
    value = attrs.get(c["field"])
    if value is None:
        return None
    for rule in c["rules"]:
        if value <= rule["max"]:
            return rule["scenario"], rule["risk_level"]
    return None


def load_zones(conn, config_path: Path) -> dict:
    """Replace all flood zones with the layers listed in the config file, in one transaction.

    Config: {"source": "...",
             "coverage": {"name": "...", "bbox": [minx, miny, maxx, maxy]},
             "layers": [ one of:
                 {"file": "x.shp", "scenario": "...", "risk_level": 3, "where": {"FIELD": "value"}},
                 {"file": "x.zip", "classify": {"field": "opfyld_mm", "rules": [
                     {"max": 15, "risk_level": 3, "scenario": "..."}, ...]}} ]}
    With "classify", each feature gets the first rule whose "max" its field value does not exceed;
    features above every rule are skipped. "where" is optional. Files (.shp or a zipped shapefile)
    and coordinates are in EPSG:25832.
    """
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    base = config_path.parent
    counts = {}
    conn.execute("DELETE FROM flood_zones")
    conn.execute("DELETE FROM coverage_areas")
    cov = cfg["coverage"]
    conn.execute("INSERT INTO coverage_areas (name, geom) VALUES (%s, ST_Multi(ST_MakeEnvelope(%s, %s, %s, %s, 25832)))",
                 (cov["name"], *cov["bbox"]))
    for layer in cfg["layers"]:
        reader = shapefile.Reader(str(base / layer["file"]), encoding="latin-1")
        where = layer.get("where", {})
        batch = []
        for rec in reader.iterShapeRecords():
            attrs = rec.record.as_dict()
            if any(str(attrs.get(k)) != str(v) for k, v in where.items()):
                continue
            if rec.shape.shapeType == shapefile.NULL:
                continue
            target = classify(layer, attrs)
            if target is None:
                continue
            scenario, level = target
            batch.append((scenario, level, cfg["source"], json.dumps(rec.shape.__geo_interface__)))
            counts[scenario] = counts.get(scenario, 0) + 1
        with conn.cursor() as cur:
            cur.executemany(INSERT, batch)
    # empty geometries can appear after ST_MakeValid on degenerate input
    conn.execute("DELETE FROM flood_zones WHERE ST_IsEmpty(geom)")
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="app.admin")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-client")
    c.add_argument("name")
    z = sub.add_parser("load-zones")
    z.add_argument("config", type=Path)
    a = ap.parse_args(argv)

    with psycopg.connect(settings.database_url) as conn:
        conn.execute(SCHEMA.read_text())
        if a.cmd == "create-client":
            key = create_client(conn, a.name)
            print(f"Client '{a.name}' created. API key (shown once, store it safely):\n{key}")
        elif a.cmd == "load-zones":
            counts = load_zones(conn, a.config)
            for scenario, n in counts.items():
                print(f"  {scenario}: {n:,} polygons")
    return 0


if __name__ == "__main__":
    sys.exit(main())
