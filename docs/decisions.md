# Decision log

Short notes written while building, so the README only claims what actually happened.

## 2026-10-27 — Address lookup: DAWA is gone
The original plan used DAWA (Danmarks Adressers Web API). Checking before building showed that
DAWA closed on 1 October 2026; its replacements (Adressevælger, Datafordeleren) need a registered
token. Decision: use OpenStreetMap Nominatim (no account), behind a `Geocoder` interface, with a
database cache and a 1 request/second limiter to follow Nominatim's usage policy. Batches are capped
at 100 rows for the same reason.

## 2026-10-27 — Flood data: contour lines are not flood areas
First candidate: Miljøstyrelsen's MiljøGIS "kyst" download (2012), which has storm-surge layers
for 20/50/100-year events. Inspecting the shapefiles showed they are POLYLINEZ contour lines at the
flood water level, not polygons. About 70% are closed rings, but a ring can enclose either a
low-lying basin (flooded) or higher ground (dry), and without terrain data there is no way to tell.
Decision: do not turn the lines into polygons; look for a layer that is published as polygons.

## 2026-10-27 — Same lines from the web service
The MiljøGIS WFS (`wfs2-miljoegis.mim.dk/klima`, access constraints and fees: NONE) serves the same
storm-surge layers. Its DescribeFeatureType says `GeometryPropertyType`, and the SHAPE-ZIP download
is `POLYLINE` again (2,452 features for the 20-year event, `kote` = water level in cm). So the
official storm-surge data is published as contour lines only.

## 2026-10-27 — "No risk" vs "no data"
Real data will only be loaded for part of Denmark. An address outside the loaded area must not be
reported as "none", because "we have no data" is not "it is safe". Added a coverage area: points
outside it get `not_covered`.

## 2026-10-28 — First `docker compose up`: Permission denied
The API container exited with `PermissionError: /app/app/__init__.py`. The source files on disk
were mode 600, `COPY` kept that with root as owner, and the app runs as the unprivileged `appuser`.
Fix: `COPY --chown=appuser:appuser`, so the image no longer depends on the permissions of the
checkout. (Running as root would also have "fixed" it; not done on purpose.)

## 2026-10-28 — Nominatim answered 403 Forbidden
First real lookup failed with an unhandled 500. Two problems: `CONTACT_EMAIL` was empty, so the
User-Agent had no contact details (Nominatim's usage policy asks for them), and the code let the
HTTP error escape. Fix: a `GeocoderUnavailable` error that becomes a clear 503, rolls back the
request (nothing half-saved, nothing cached as "not found"), plus a start-up warning when
`CONTACT_EMAIL` is missing. Covered by a unit test and an integration test.

## 2026-10-28 — First real portfolio: what the demo showed
Uploading `examples/portfolio_copenhagen.csv` (11 rows) gave: 0 high, 0 medium, 1 low, 6 no flood
area, 1 outside coverage (Aarhus), 3 not found. Three findings, kept visible rather than tuned away:
- The map zoomed out to half of Denmark because the Aarhus point was included when fitting the
  view. Fixed: the view fits the addresses inside the coverage area.
- Nominatim did not find two real addresses (Amagerbrogade 1, Østerbrogade 1). Free OSM geocoding
  misses some Danish house numbers; the official address register would fix this but needs a token.
- Most addresses get "no flood area": depressions are small (median ~230 m²) and the check is
  point-in-polygon on the geocoded point. A building next to a depression is not flagged. A
  distance-based check (e.g. within N metres) is the obvious next step; not done, because choosing
  N needs domain input rather than a guess.
