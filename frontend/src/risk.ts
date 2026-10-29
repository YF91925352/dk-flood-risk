import type { PortfolioRow, RiskLevel } from "./api";

export const LEVELS: RiskLevel[] = ["high", "medium", "low", "none", "not_covered", "unknown"];

export const LABEL: Record<RiskLevel, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
  none: "No flood area found",
  not_covered: "Outside data coverage",
  unknown: "Address not found",
};

// Colour-blind-safe order (dark red → orange → yellow), with grey for "nothing found".
export const COLOR: Record<RiskLevel, string> = {
  high: "#b2182b",
  medium: "#ef8a62",
  low: "#e6c229",
  none: "#4d9221",
  not_covered: "#c9c9c9",
  unknown: "#8c8c8c",
};

export function countByLevel(rows: PortfolioRow[]): Record<RiskLevel, number> {
  const out = { high: 0, medium: 0, low: 0, none: 0, not_covered: 0, unknown: 0 } as Record<RiskLevel, number>;
  for (const r of rows) out[r.risk_level] += 1;
  return out;
}

/** Rows that can go on a map: geocoded and with coordinates. */
export function mappable(rows: PortfolioRow[]): (PortfolioRow & { lon: number; lat: number })[] {
  return rows.filter((r): r is PortfolioRow & { lon: number; lat: number } => r.lon !== null && r.lat !== null);
}

/** Sort worst risk first, then by row number, so a reviewer sees what matters at the top. */
export function byRisk(rows: PortfolioRow[]): PortfolioRow[] {
  return [...rows].sort((a, b) => LEVELS.indexOf(a.risk_level) - LEVELS.indexOf(b.risk_level) || a.row_no - b.row_no);
}
