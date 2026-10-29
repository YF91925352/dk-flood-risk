import { describe, expect, it, vi } from "vitest";
import { ApiError, request, type PortfolioRow } from "./api";
import { byRisk, countByLevel, mappable } from "./risk";

const row = (row_no: number, risk_level: PortfolioRow["risk_level"], lon: number | null = 12.5): PortfolioRow => ({
  row_no, reference: null, address: `a${row_no}`, status: lon === null ? "not_found" : "ok",
  label: null, lon, lat: lon === null ? null : 55.6, risk_level, scenario: null,
});

describe("risk helpers", () => {
  const rows = [row(2, "none"), row(3, "high"), row(4, "unknown", null), row(5, "high"), row(6, "low")];

  it("counts every level, including zero", () => {
    expect(countByLevel(rows)).toEqual({ high: 2, medium: 0, low: 1, none: 1, not_covered: 0, unknown: 1 });
  });

  it("sorts worst risk first, then by row", () => {
    expect(byRisk(rows).map((r) => r.row_no)).toEqual([3, 5, 6, 2, 4]);
  });

  it("only maps rows with coordinates", () => {
    expect(mappable(rows).map((r) => r.row_no)).toEqual([2, 3, 5, 6]);
  });
});

describe("api request", () => {
  it("sends the API key header", async () => {
    const fetchFn = vi.fn(async (_url: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify({ ok: 1 }), { status: 200 }));
    await request("/api/x", "fk_abc", {}, fetchFn);
    const init = fetchFn.mock.calls[0][1] as RequestInit;
    expect(new Headers(init.headers).get("X-API-Key")).toBe("fk_abc");
  });

  it("turns the server's error detail into the message", async () => {
    const fetchFn = vi.fn(async () => new Response(JSON.stringify({ detail: "CSV needs an 'address' column" }), { status: 422 }));
    await expect(request("/api/x", "k", {}, fetchFn)).rejects.toEqual(new ApiError(422, "CSV needs an 'address' column"));
  });
});
