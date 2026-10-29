export type RiskLevel = "high" | "medium" | "low" | "none" | "not_covered" | "unknown";

export interface RiskResult {
  address: string;
  found: boolean;
  label?: string;
  lon?: number;
  lat?: number;
  risk_level: RiskLevel;
  scenario?: string | null;
  note: string;
}

export interface PortfolioRow {
  row_no: number;
  reference: string | null;
  address: string;
  status: "ok" | "not_found";
  label: string | null;
  lon: number | null;
  lat: number | null;
  risk_level: RiskLevel;
  scenario: string | null;
}

export interface PortfolioSummary {
  id: number;
  name: string;
  row_count: number;
  created_at: string;
  high: number;
  medium: number;
  low: number;
  none: number;
  not_covered: number;
  unknown: number;
}

export interface Portfolio {
  id: number;
  name: string;
  row_count: number;
  created_at: string;
  rows: PortfolioRow[];
  note: string;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** Every call sends the client's API key; the server decides what that key may see. */
export async function request<T>(path: string, apiKey: string, init: RequestInit = {}, fetchFn = fetch): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-API-Key", apiKey);
  const res = await fetchFn(path, { ...init, headers });
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* not JSON: keep the status text */
    }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

export const api = {
  risk: (key: string, address: string) =>
    request<RiskResult>(`/api/risk?address=${encodeURIComponent(address)}`, key),
  portfolios: (key: string) => request<PortfolioSummary[]>("/api/portfolios", key),
  portfolio: (key: string, id: number) => request<Portfolio>(`/api/portfolios/${id}`, key),
  upload: (key: string, file: File, name: string) => {
    const form = new FormData();
    form.append("file", file);
    if (name.trim()) form.append("name", name.trim());
    return request<Portfolio>("/api/portfolios", key, { method: "POST", body: form });
  },
};
