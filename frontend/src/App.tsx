import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, ApiError, type Portfolio, type PortfolioSummary, type RiskResult } from "./api";
import { RiskBadge } from "./components/RiskBadge";
import { ResultsTable } from "./components/ResultsTable";
import { RiskMap } from "./components/RiskMap";
import { COLOR, LABEL, LEVELS, countByLevel } from "./risk";

// The key lives in sessionStorage: it is forgotten when the tab closes. Storage can be
// unavailable (private mode), so every access is guarded.
const KEY_STORAGE = "flood-risk-api-key";
const loadKey = () => {
  try {
    return sessionStorage.getItem(KEY_STORAGE) ?? "";
  } catch {
    return "";
  }
};
const saveKey = (k: string) => {
  try {
    sessionStorage.setItem(KEY_STORAGE, k);
  } catch {
    /* ignore */
  }
};

const message = (e: unknown) =>
  e instanceof ApiError && e.status === 401 ? "The API key was not accepted." : e instanceof Error ? e.message : String(e);

export default function App() {
  const [apiKey, setApiKey] = useState(loadKey);
  const [address, setAddress] = useState("");
  const [lookup, setLookup] = useState<RiskResult | null>(null);
  const [portfolios, setPortfolios] = useState<PortfolioSummary[]>([]);
  const [selected, setSelected] = useState<Portfolio | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(null);
    }
  };

  const refresh = useCallback(async (key: string) => {
    if (!key) return;
    try {
      setPortfolios(await api.portfolios(key));
      setError(null);
    } catch (e) {
      setPortfolios([]);
      setError(message(e));
    }
  }, []);

  useEffect(() => {
    void refresh(apiKey);
  }, [apiKey, refresh]);

  const onLookup = (e: FormEvent) => {
    e.preventDefault();
    void run("Looking up address…", async () => setLookup(await api.risk(apiKey, address)));
  };

  const onUpload = (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    void run("Geocoding and assessing every row (about one second per new address)…", async () => {
      const p = await api.upload(apiKey, file, name);
      setSelected(p);
      setFile(null);
      setName("");
      (document.getElementById("csv") as HTMLInputElement).value = "";
      await refresh(apiKey);
    });
  };

  const open = (id: number) => void run("Loading portfolio…", async () => setSelected(await api.portfolio(apiKey, id)));

  const counts = selected ? countByLevel(selected.rows) : null;

  return (
    <main>
      <header>
        <h1>Flood risk lookup</h1>
        <p className="muted">Indicative flood hazard for Danish addresses, from public data.</p>
        <label className="key">
          API key
          <input
            type="password"
            value={apiKey}
            placeholder="fk_…"
            autoComplete="off"
            onChange={(e) => {
              setApiKey(e.target.value.trim());
              saveKey(e.target.value.trim());
              setSelected(null);
            }}
          />
        </label>
      </header>

      {error && <p className="error" role="alert">{error}</p>}
      {busy && <p className="busy" role="status">{busy}</p>}

      {apiKey ? (
        <>
          <section>
            <h2>Single address</h2>
            <form onSubmit={onLookup} className="row">
              <input
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder="Nyhavn 1, 1051 København K"
                minLength={3}
                required
              />
              <button disabled={!!busy}>Check</button>
            </form>
            {lookup && (
              <div className="result">
                <RiskBadge level={lookup.risk_level} />
                <span>{lookup.found ? lookup.label : `No match for “${lookup.address}”`}</span>
                {lookup.scenario && <span className="muted">Scenario: {lookup.scenario}</span>}
              </div>
            )}
          </section>

          <section>
            <h2>Portfolio upload</h2>
            <p className="muted">
              CSV with an <code>address</code> (or <code>adresse</code>) column and an optional <code>reference</code>
              column; comma or semicolon separated. Up to 100 rows per file.
            </p>
            <form onSubmit={onUpload} className="row">
              <input id="csv" type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Portfolio name (optional)" />
              <button disabled={!file || !!busy}>Upload and assess</button>
            </form>
          </section>

          <section>
            <h2>Your portfolios</h2>
            {portfolios.length === 0 ? (
              <p className="muted">No portfolios yet.</p>
            ) : (
              <ul className="portfolios">
                {portfolios.map((p) => (
                  <li key={p.id}>
                    <button className={selected?.id === p.id ? "link active" : "link"} onClick={() => open(p.id)}>
                      {p.name}
                    </button>
                    <span className="muted">
                      {" "}
                      {p.row_count} rows · {p.high} high · {p.medium} medium · {p.low} low
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {selected && counts && (
            <section>
              <h2>{selected.name}</h2>
              <div className="summary">
                {LEVELS.map((l) => (
                  <span key={l} className="pill" style={{ borderColor: COLOR[l] }}>
                    {LABEL[l]}: <strong>{counts[l]}</strong>
                  </span>
                ))}
              </div>
              <RiskMap rows={selected.rows} />
              <ResultsTable rows={selected.rows} />
              <p className="muted small">{selected.note}</p>
            </section>
          )}
        </>
      ) : (
        <p className="muted">Enter your API key to start.</p>
      )}

      <footer className="muted small">
        Geocoding and map: © OpenStreetMap contributors. Flood data: Miljøstyrelsen. Demo project, not for real decisions.
      </footer>
    </main>
  );
}
