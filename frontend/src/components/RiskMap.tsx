import { useEffect } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer, useMap } from "react-leaflet";
import type { PortfolioRow } from "../api";
import { COLOR, LABEL, mappable } from "../risk";

const DENMARK: [number, number] = [56.1, 10.4];

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  const key = JSON.stringify(points); // refit only when the set of points changes
  useEffect(() => {
    if (points.length === 1) map.setView(points[0], 14);
    else if (points.length > 1) map.fitBounds(points, { padding: [30, 30] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, key]);
  return null;
}

export function RiskMap({ rows }: { rows: PortfolioRow[] }) {
  const pts = mappable(rows);
  // Frame the map on the addresses that have data. One address far outside the coverage area
  // would otherwise zoom the map out to half the country.
  const covered = pts.filter((r) => r.risk_level !== "not_covered");
  const latlngs = (covered.length ? covered : pts).map((r) => [r.lat, r.lon] as [number, number]);
  return (
    <MapContainer center={DENMARK} zoom={7} className="map" scrollWheelZoom={false}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {pts.map((r) => (
        <CircleMarker
          key={r.row_no}
          center={[r.lat, r.lon]}
          radius={8}
          pathOptions={{ color: "#222", weight: 1, fillColor: COLOR[r.risk_level], fillOpacity: 0.9 }}
        >
          <Popup>
            <strong>{r.reference ?? `Row ${r.row_no}`}</strong>
            <br />
            {r.address}
            <br />
            Risk: {LABEL[r.risk_level]}
            {r.scenario ? ` (${r.scenario})` : ""}
          </Popup>
        </CircleMarker>
      ))}
      <FitBounds points={latlngs} />
    </MapContainer>
  );
}
