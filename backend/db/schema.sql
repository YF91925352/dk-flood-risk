-- Applied on API start-up. Every statement is idempotent.
CREATE EXTENSION IF NOT EXISTS postgis;

-- Customers. Only a SHA-256 hash of each API key is stored; the key itself is shown once.
CREATE TABLE IF NOT EXISTS clients (
    id         serial PRIMARY KEY,
    name       text NOT NULL UNIQUE,
    key_hash   text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Flood hazard areas in the Danish national grid (ETRS89 / UTM 32N, EPSG:25832).
-- risk_level: 3 = high, 2 = medium, 1 = low.
CREATE TABLE IF NOT EXISTS flood_zones (
    id         bigserial PRIMARY KEY,
    scenario   text NOT NULL,
    risk_level smallint NOT NULL CHECK (risk_level BETWEEN 1 AND 3),
    source     text NOT NULL,
    geom       geometry(MultiPolygon, 25832) NOT NULL
);
CREATE INDEX IF NOT EXISTS flood_zones_geom_idx ON flood_zones USING gist (geom);

-- Where flood data has been loaded. Outside these areas the answer is "not_covered", never "none".
CREATE TABLE IF NOT EXISTS coverage_areas (
    id   serial PRIMARY KEY,
    name text NOT NULL,
    geom geometry(MultiPolygon, 25832) NOT NULL
);

-- Geocoding results are cached (also "not found"), to respect the geocoder's usage policy.
CREATE TABLE IF NOT EXISTS geocode_cache (
    query      text PRIMARY KEY,          -- normalised address text
    found      boolean NOT NULL,
    label      text,
    lon        double precision,
    lat        double precision,
    provider   text NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS portfolios (
    id         bigserial PRIMARY KEY,
    client_id  integer NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    name       text NOT NULL,
    row_count  integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS portfolios_client_idx ON portfolios (client_id);

CREATE TABLE IF NOT EXISTS portfolio_rows (
    portfolio_id bigint  NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    row_no       integer NOT NULL,
    reference    text,
    address      text NOT NULL,
    status       text NOT NULL CHECK (status IN ('ok', 'not_found')),
    label        text,
    geom         geometry(Point, 4326),
    risk_level   text NOT NULL CHECK (risk_level IN ('high', 'medium', 'low', 'none', 'not_covered', 'unknown')),
    scenario     text,
    PRIMARY KEY (portfolio_id, row_no)
);
