"""Point-in-polygon against the flood hazard areas, done by PostGIS with a spatial index."""
from dataclasses import dataclass

LEVELS = {3: "high", 2: "medium", 1: "low"}

# Addresses come in as WGS84 lon/lat; the zones are stored in the Danish grid (EPSG:25832),
# so the point is transformed once rather than transforming every polygon.
SQL = """
WITH p AS (SELECT ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 25832) AS geom)
SELECT
    EXISTS (SELECT 1 FROM coverage_areas c, p WHERE ST_Intersects(c.geom, p.geom)) AS covered,
    (SELECT z.risk_level FROM flood_zones z, p WHERE ST_Intersects(z.geom, p.geom)
     ORDER BY z.risk_level DESC, z.scenario LIMIT 1) AS level,
    (SELECT z.scenario FROM flood_zones z, p WHERE ST_Intersects(z.geom, p.geom)
     ORDER BY z.risk_level DESC, z.scenario LIMIT 1) AS scenario
"""


@dataclass(frozen=True)
class Risk:
    level: str            # high | medium | low | none | not_covered
    scenario: str | None  # the most severe scenario whose flood area contains the point


def assess(conn, lon: float, lat: float) -> Risk:
    covered, level, scenario = conn.execute(SQL, (lon, lat)).fetchone()
    if not covered:
        return Risk("not_covered", None)  # no data here: never claim "no risk"
    return Risk(LEVELS[level], scenario) if level else Risk("none", None)
