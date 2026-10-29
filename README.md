# dk-flood-risk

[![CI](https://github.com/YF91925352/dk-flood-risk/actions/workflows/ci.yml/badge.svg)](https://github.com/YF91925352/dk-flood-risk/actions/workflows/ci.yml)

A small service that answers one question: **is this Danish address in a known flood-prone spot?**
Look up one address, or upload a CSV portfolio and get a risk level per row, on a map and in a
table. Each customer has an API key and only ever sees their own portfolios.

![Portfolio view: risk summary, map and table](docs/screenshot-portfolio.png)

## What it does

- `GET /api/risk?address=…`: geocode one address and return its risk level.
- `POST /api/portfolios`: upload a CSV (up to 100 rows) and get every row assessed.
- `GET /api/portfolios`, `GET /api/portfolios/{id}`: list or open your own portfolios.
- `GET /health`: database reachable, how many flood polygons and coverage areas are loaded.
- A React page with a Leaflet map and a results table, sorted worst risk first.

Every answer is one of six levels, and the difference between the last three matters:

| Level | Meaning |
|---|---|
| `high` / `medium` / `low` | The address lies in a mapped depression (see [Data](#data-and-risk-method)) |
| `none` | Inside the area where data is loaded, and not in any depression |
| `not_covered` | Outside the loaded area. **No data is not the same as no risk**, so this is never reported as `none` |
| `unknown` | The address could not be geocoded |

## Run it

Requires Docker.

```bash
cp .env.example .env              # set CONTACT_EMAIL: Nominatim's usage policy requires contact details
docker compose up -d --build      # PostGIS + API + web
# download the flood data once, see data/README.md, then:
docker compose exec api python -m app.admin load-zones /data/zones.json
docker compose exec api python -m app.admin create-client "Demo A"   # prints an API key once
open http://localhost:8080        # paste the key, try examples/portfolio_copenhagen.csv
```

```bash
curl -H "X-API-Key: fk_…" "http://localhost:8080/api/risk?address=Islands%20Brygge%2014,%202300%20København%20S"
```

## Architecture

```
browser ── nginx (web) ──/api──► FastAPI (api) ──► PostgreSQL + PostGIS (db)
                                     │
                                     └──► Nominatim (OpenStreetMap geocoder), cached in the db
```

- **One SQL query per address.** The geocoded point is transformed once from WGS84 to the Danish
  grid (EPSG:25832) and tested with `ST_Intersects` against GiST-indexed polygons. The worst
  matching level wins.
- **Plain SQL with psycopg**, no ORM: the queries are short, and the spatial SQL is the core of the service.
- **Same origin for UI and API** (nginx proxies `/api`), so there is no CORS configuration to get wrong.

## Data and risk method

**Source:** Miljøstyrelsen, MiljøGIS web service `klima:lavningermedattributter` ("bluespots": terrain
depressions where rainwater collects). It is public, needs no login, and the service lists access
constraints and fees as *none*. Only central Copenhagen is loaded (a 16 × 16 km box), which is the
coverage area. The data is downloaded by the user ([data/README.md](data/README.md)) and not
redistributed in this repository.

**Risk levels** use the field `opfyld_mm` (millimetres of rain needed to fill the depression) and
DMI's definitions of a cloudburst (15 mm in 30 minutes) and a double cloudburst (30 mm):

| Level | Rule | Depressions loaded |
|---|---|---:|
| high | fills with ≤ 15 mm (one cloudburst) | 14,910 |
| medium | fills with ≤ 30 mm (double cloudburst) | 4,552 |
| low | fills with ≤ 100 mm (extreme event) | 3,826 |
| — | needs more than 100 mm: not counted | 2,321 |

The rules live in [`data/zones.json`](data/zones.json), not in code. The loader replaces all zones
in one transaction, so a failed load never leaves half a dataset behind.

**This is an indicative screening, not an assessment.** It covers cloudburst depressions only (no
storm surge or river flooding), ignores sewers and local defences, and uses one point per address.

## Security and access control

- **API keys** are random (`secrets.token_urlsafe`) and only their SHA-256 hash is stored. A key is
  shown once, when the client is created.
- **Every customer query filters on the client id inside the SQL itself.** Another client's
  portfolio returns **404, not 403**, so the API does not even confirm that it exists. Tests check this.
- The API runs as an unprivileged user in the container. Ports are bound to `127.0.0.1` only.
- Secrets (`POSTGRES_PASSWORD`, `CONTACT_EMAIL`) come from `.env`, which is git-ignored.

## Operations

- **Health check:** `/health` checks the database and reports `degraded` when no flood data is
  loaded. Docker Compose uses it: the web container starts only after the API is healthy.
- **Structured logs:** one JSON line per request (`request_id`, method, path, status, duration,
  client id, never the key). The request id is returned in the `X-Request-ID` header.
- **Geocoder etiquette:** a database cache (misses included), one request per second at most, and an
  identifying User-Agent. If the geocoder fails, the API returns a clear **503** and rolls back, so
  nothing is saved half-done and no address is wrongly cached as "not found".
- **CI (GitHub Actions):** backend tests against a real PostGIS service container, front-end tests
  and type-checked build, then the whole stack is started with Docker Compose and `/health` is
  called through nginx.

## Tests

```bash
docker compose --profile test up -d testdb      # throwaway PostGIS in memory, port 5433
cd backend && pip install -r requirements-dev.txt
DATABASE_URL=postgresql://flood:flood@localhost:5433/flood REQUIRE_DB=1 pytest -q   # 36 tests
cd ../frontend && npm ci && npm test                                                # 5 tests
```

The integration tests use invented polygons around Copenhagen harbour and a fixture geocoder, so
they need no network. They cover the spatial lookup for every level, coverage, client isolation,
CSV edge cases (`;` separators, BOM, Danish headers, row limits), geocoder outages and the
shapefile loader. Without a database they are skipped locally; in CI (`REQUIRE_DB=1`) they must run.

## Demo result

`examples/portfolio_copenhagen.csv`, 11 addresses, run against the real data:

| high | medium | low | none | not_covered | unknown |
|---:|---:|---:|---:|---:|---:|
| 0 | 0 | 1 | 6 | 1 | 3 |

What this shows, and what I did about it:

- **The map zoomed out to half of Denmark,** because the Aarhus address (outside coverage) was
  included when fitting the view. *Fixed:* the map now fits the covered addresses.
- **Two real addresses were not found** (Amagerbrogade 1, Østerbrogade 1), plus one deliberately
  fake address. Free OSM geocoding misses some Danish house numbers. *Not fixed:* the official
  Danish address register would solve it, but it requires a registered token.
- **Most addresses get "none".** Depressions are small (median ≈ 230 m²), and the check is
  point-in-polygon on one point, so a building next to a depression is not flagged. *Not fixed on
  purpose:* a distance rule ("within N metres") is the obvious next step, but N should come from
  domain experts, not from me guessing.

## What I deliberately did not build

Kept small and simple on purpose. Each item below is a real next step, not an oversight:

- **No cloud deployment yet.** It runs with Docker Compose; Azure Container Apps would take the same images.
- **No background job queue.** Batches are capped at 100 rows (about 100 s with a cold cache), because the free geocoder allows one request per second. A larger product would need a queue and a paid or self-hosted geocoder.
- **No ORM or migration tool.** One idempotent `schema.sql` is enough at this size. Alembic would come with the first real schema change.
- **No user accounts or OAuth.** API keys per client match how B2B data APIs are usually consumed.
- **No Postgres row-level security.** Isolation is enforced in every query and covered by tests. RLS would be defence in depth.
- **No storm-surge or river flooding.** The official storm-surge layers are published as contour lines, not areas (see below).

## How I used AI

This project was built together with an AI coding assistant (Claude): it wrote most of the code
and tests, and I made the scope and data decisions, ran everything on my machine and checked the
results. The [decision log](docs/decisions.md) has the details. These are the points where the
first plan or the first output turned out wrong and was changed:

- **The planned address API no longer exists.** The plan said DAWA; checking before building showed DAWA closed on 1 October 2026. Its official replacements need a registered token, which I chose not to use, so the geocoder is Nominatim behind an interface that can be swapped.
- **The first flood dataset was the wrong shape.** The storm-surge layers turned out to be contour lines, not polygons, both in the download and in the web service. Turning closed lines into polygons was rejected, because a ring can enclose a basin (flooded) or a hill (dry), and that would produce confident wrong answers. We switched to a layer published as polygons.
- **"No data" was first reported as "no risk".** Fixed with an explicit coverage area and a `not_covered` level.
- **The first `docker compose up` failed** with `Permission denied`: the app ran as a non-root user but the copied files were not readable. Fixed with `COPY --chown` rather than running as root.
- **The first real lookup returned a raw 500.** Nominatim refused requests without contact details, and the code did not handle a geocoder failure. Fixed with a clear 503, a rollback and a start-up warning, and covered by tests.
- **The demo map was framed badly,** and the limitations above were found by looking at real output rather than trusting the tests.

## Data credits

Flood data: Miljøstyrelsen (MiljøGIS). Geocoding and base map: © OpenStreetMap contributors (Nominatim, tile.openstreetmap.org).
Demo project, not for real decisions.
