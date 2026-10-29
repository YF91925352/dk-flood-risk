import type { PortfolioRow } from "../api";
import { byRisk } from "../risk";
import { RiskBadge } from "./RiskBadge";

export function ResultsTable({ rows }: { rows: PortfolioRow[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Row</th>
            <th>Reference</th>
            <th>Address</th>
            <th>Risk</th>
            <th>Scenario</th>
          </tr>
        </thead>
        <tbody>
          {byRisk(rows).map((r) => (
            <tr key={r.row_no}>
              <td className="num">{r.row_no}</td>
              <td>{r.reference ?? "–"}</td>
              <td title={r.label ?? undefined}>{r.address}</td>
              <td>
                <RiskBadge level={r.risk_level} />
              </td>
              <td>{r.scenario ?? "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
