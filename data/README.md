# Flood data

Not committed to the repository. Download it, then load it with
`docker compose exec api python -m app.admin load-zones /data/zones.json`.

**Bluespots / low-lying depressions** (Miljøstyrelsen, MiljøGIS, no login; the service lists
access constraints and fees as NONE). Central Copenhagen only, as a zipped shapefile in EPSG:25832.
Save the download in this folder as `lavningermedattributter.zip`:

http://wfs2-miljoegis.mim.dk/klima/ows?service=WFS&version=1.0.0&request=GetFeature&typeName=klima:lavningermedattributter&bbox=716000,6168000,732000,6184000&outputFormat=SHAPE-ZIP

`zones.json` maps the field `opfyld_mm` (millimetres of rain needed to fill the depression) to
risk levels, using DMI's definitions: a cloudburst is 15 mm in 30 minutes, a double cloudburst
30 mm. Depressions that need more than 100 mm are not counted.
