"""Address -> coordinates.

Production uses OpenStreetMap Nominatim, which needs no account. Its usage policy allows at
most one request per second, requires an identifying User-Agent and asks clients to cache
results, so every lookup goes through a database cache and a process-wide rate limiter.
The Danish official address services (Adressevælger / Datafordeleren) need a registered
token; swapping one in means writing one more class with the same ``lookup`` method.
"""
import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from .config import settings


class GeocoderUnavailable(RuntimeError):
    """The geocoding service refused or failed. Never cached, never reported as "not found"."""


@dataclass(frozen=True)
class GeocodeResult:
    found: bool
    label: str | None = None
    lon: float | None = None
    lat: float | None = None


def normalise(address: str) -> str:
    return re.sub(r"\s+", " ", address.strip().lower())


class NominatimGeocoder:
    name = "nominatim"

    def __init__(self, url: str, contact: str, min_interval: float = 1.0, client: httpx.Client | None = None):
        self.url = url
        self.min_interval = min_interval
        ua = "dk-flood-risk-demo/0.1" + (f" ({contact})" if contact else "")
        self.client = client or httpx.Client(timeout=10, headers={"User-Agent": ua})
        self._lock = threading.Lock()
        self._last = 0.0

    def lookup(self, address: str) -> GeocodeResult:
        with self._lock:  # one request at a time, at most one per min_interval seconds
            wait = self._last + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            try:
                r = self.client.get(self.url, params={
                    "q": address, "format": "jsonv2", "countrycodes": "dk", "limit": 1,
                })
                r.raise_for_status()
                hits = r.json()
            except (httpx.HTTPError, ValueError) as e:
                raise GeocoderUnavailable(f"{type(e).__name__}: {e}") from e
            finally:
                self._last = time.monotonic()
        if not hits:
            return GeocodeResult(False)
        h = hits[0]
        return GeocodeResult(True, h.get("display_name"), float(h["lon"]), float(h["lat"]))


class FixtureGeocoder:
    """Deterministic geocoder for tests and offline demos: a JSON file {address: [lon, lat]}."""
    name = "fixture"

    def __init__(self, path: str):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        self.table = {normalise(k): v for k, v in raw.items()}

    def lookup(self, address: str) -> GeocodeResult:
        hit = self.table.get(normalise(address))
        return GeocodeResult(True, address.strip(), hit[0], hit[1]) if hit else GeocodeResult(False)


def make_geocoder():
    if settings.geocoder == "fixture":
        return FixtureGeocoder(settings.geocoder_fixture)
    return NominatimGeocoder(settings.nominatim_url, settings.contact_email)


def geocode(conn, geocoder, address: str) -> GeocodeResult:
    """Cached lookup: the cache stores misses too, so a bad address is not retried on every upload."""
    key = normalise(address)
    row = conn.execute("SELECT found, label, lon, lat FROM geocode_cache WHERE query = %s", (key,)).fetchone()
    if row:
        return GeocodeResult(*row)
    res = geocoder.lookup(address)
    conn.execute(
        "INSERT INTO geocode_cache (query, found, label, lon, lat, provider) VALUES (%s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (query) DO NOTHING",
        (key, res.found, res.label, res.lon, res.lat, geocoder.name),
    )
    return res
