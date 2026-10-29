import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse

from . import db, logs
from .auth import Client, current_client
from .config import settings
from .csvio import CsvError, parse
from .geocode import GeocoderUnavailable, geocode, make_geocoder
from .risk import assess

log = logging.getLogger("api")

DATA_NOTE = (
    "Indicative flood hazard from public data, for the loaded coverage area only. "
    "Not a substitute for a professional assessment."
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logs.setup(settings.log_level)
    pool = db.open_pool(settings.database_url)
    db.apply_schema(pool)
    app.state.geocoder = make_geocoder()
    logs.log(log, "started", geocoder=app.state.geocoder.name)
    if settings.geocoder == "nominatim" and not settings.contact_email:
        logs.log(log, "CONTACT_EMAIL is not set: Nominatim may refuse requests without contact details",
                 logging.WARNING)
    yield
    pool.close()


app = FastAPI(title="Danish address flood risk", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def access_log(request: Request, call_next):
    rid = logs.new_request_id(request.headers.get("x-request-id"))
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logs.log(log, "unhandled error", logging.ERROR, method=request.method, path=request.url.path)
        raise
    response.headers["X-Request-ID"] = rid
    logs.log(
        log, "request",
        method=request.method, path=request.url.path, status=response.status_code,
        duration_ms=round((time.perf_counter() - start) * 1000, 1),
        client_id=getattr(request.state, "client_id", None),  # never the key itself
    )
    return response


@app.exception_handler(GeocoderUnavailable)
async def geocoder_unavailable(request: Request, exc: GeocoderUnavailable):
    # The whole request is rolled back, so a failed upload leaves nothing half-saved
    # and no address is wrongly cached as "not found".
    logs.log(log, "geocoder unavailable", logging.ERROR, error=str(exc), path=request.url.path)
    return JSONResponse(status_code=503, content={
        "detail": "The address lookup service is unavailable right now. Please try again later."})


@app.exception_handler(CsvError)
async def csv_error(request: Request, exc: CsvError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


def _client(request: Request, client: Client = Depends(current_client)) -> Client:
    request.state.client_id = client.id
    return client


@app.get("/health")
def health():
    """Liveness and readiness in one: the database answers and flood data is loaded."""
    try:
        with db.pool.connection(timeout=3) as conn:
            zones, areas = conn.execute(
                "SELECT (SELECT count(*) FROM flood_zones), (SELECT count(*) FROM coverage_areas)").fetchone()
    except Exception:
        logs.log(log, "health check failed", logging.ERROR)
        return JSONResponse(status_code=503, content={"status": "error", "database": "unavailable"})
    return {"status": "ok" if zones and areas else "degraded", "database": "ok",
            "flood_zones": zones, "coverage_areas": areas}


@app.get("/api/risk")
def risk_for_address(
    request: Request,
    address: str = Query(min_length=3, max_length=300),
    client: Client = Depends(_client),
    conn=Depends(db.get_conn),
):
    g = geocode(conn, request.app.state.geocoder, address)
    conn.commit()  # keep the cache entry even if something below fails
    if not g.found:
        return {"address": address, "found": False, "risk_level": "unknown", "note": DATA_NOTE}
    r = assess(conn, g.lon, g.lat)
    return {"address": address, "found": True, "label": g.label, "lon": g.lon, "lat": g.lat,
            "risk_level": r.level, "scenario": r.scenario, "note": DATA_NOTE}


@app.post("/api/portfolios", status_code=201)
def create_portfolio(
    request: Request,
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    client: Client = Depends(_client),
    conn=Depends(db.get_conn),
):
    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "File too large (max 1 MB)")
    rows = parse(data, settings.max_batch_rows)

    pid = conn.execute(
        "INSERT INTO portfolios (client_id, name, row_count) VALUES (%s, %s, %s) RETURNING id",
        (client.id, (name or file.filename or "portfolio").strip()[:200], len(rows)),
    ).fetchone()[0]
    for row in rows:
        g = geocode(conn, request.app.state.geocoder, row.address)
        if g.found:
            r = assess(conn, g.lon, g.lat)
            conn.execute(
                "INSERT INTO portfolio_rows (portfolio_id, row_no, reference, address, status, label, geom, "
                "risk_level, scenario) VALUES (%s, %s, %s, %s, 'ok', %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s)",
                (pid, row.row_no, row.reference, row.address, g.label, g.lon, g.lat, r.level, r.scenario),
            )
        else:
            conn.execute(
                "INSERT INTO portfolio_rows (portfolio_id, row_no, reference, address, status, risk_level) "
                "VALUES (%s, %s, %s, %s, 'not_found', 'unknown')",
                (pid, row.row_no, row.reference, row.address),
            )
    conn.commit()
    logs.log(log, "portfolio created", portfolio_id=pid, rows=len(rows), client_id=client.id)
    return _portfolio(conn, client, pid)


@app.get("/api/portfolios")
def list_portfolios(client: Client = Depends(_client), conn=Depends(db.get_conn)):
    rows = conn.execute(
        """
        SELECT p.id, p.name, p.row_count, p.created_at,
               count(*) FILTER (WHERE r.risk_level = 'high')   AS high,
               count(*) FILTER (WHERE r.risk_level = 'medium') AS medium,
               count(*) FILTER (WHERE r.risk_level = 'low')    AS low,
               count(*) FILTER (WHERE r.risk_level = 'none')   AS none,
               count(*) FILTER (WHERE r.risk_level = 'not_covered') AS not_covered,
               count(*) FILTER (WHERE r.risk_level = 'unknown') AS unknown
        FROM portfolios p LEFT JOIN portfolio_rows r ON r.portfolio_id = p.id
        WHERE p.client_id = %s
        GROUP BY p.id ORDER BY p.created_at DESC, p.id DESC
        """,
        (client.id,),
    ).fetchall()
    keys = ["id", "name", "row_count", "created_at", "high", "medium", "low", "none", "not_covered", "unknown"]
    return [dict(zip(keys, r)) for r in rows]


@app.get("/api/portfolios/{portfolio_id}")
def get_portfolio(portfolio_id: int, client: Client = Depends(_client), conn=Depends(db.get_conn)):
    return _portfolio(conn, client, portfolio_id)


def _portfolio(conn, client: Client, pid: int) -> dict:
    # The client filter is part of the query itself. Another client's portfolio returns 404,
    # not 403, so the API does not reveal that the id exists.
    p = conn.execute(
        "SELECT id, name, row_count, created_at FROM portfolios WHERE id = %s AND client_id = %s",
        (pid, client.id),
    ).fetchone()
    if not p:
        raise HTTPException(404, "Portfolio not found")
    rows = conn.execute(
        "SELECT row_no, reference, address, status, label, ST_X(geom), ST_Y(geom), risk_level, scenario "
        "FROM portfolio_rows WHERE portfolio_id = %s ORDER BY row_no",
        (pid,),
    ).fetchall()
    keys = ["row_no", "reference", "address", "status", "label", "lon", "lat", "risk_level", "scenario"]
    return {"id": p[0], "name": p[1], "row_count": p[2], "created_at": p[3],
            "rows": [dict(zip(keys, r)) for r in rows], "note": DATA_NOTE}
