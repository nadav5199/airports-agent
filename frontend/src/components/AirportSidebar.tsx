import { useMemo, useState } from "react";
import type { Airport } from "../types";

/** Reference sidebar listing every airport the agent can actually answer
 * about. Exists mainly to (a) prove GET /api/airports is wired to a real
 * backend, and (b) surface the real scoping limitation that this demo only
 * covers 62 airports (New England + a handful of major hubs) -- per
 * CLAUDE.md's "communicate scoping" requirement, the UI shouldn't let a user
 * assume coverage that doesn't exist. */
export default function AirportSidebar({
  airports,
  loading,
  error,
}: {
  airports: Airport[];
  loading: boolean;
  error: string | null;
}) {
  const [filter, setFilter] = useState("");

  const regions = useMemo(() => {
    const set = new Set(airports.map((a) => a.region).filter(Boolean));
    return Array.from(set).sort();
  }, [airports]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return airports;
    return airports.filter(
      (a) =>
        a.airport_code.toLowerCase().includes(q) ||
        a.name.toLowerCase().includes(q) ||
        a.city.toLowerCase().includes(q) ||
        a.state.toLowerCase().includes(q) ||
        a.region.toLowerCase().includes(q)
    );
  }, [airports, filter]);

  return (
    <aside className="sidebar">
      <h2>Airports in Scope</h2>
      <p className="sidebar-note">
        The agent can only answer about the {airports.length || "…"} airports below (New
        England + a handful of major hubs). Questions about other airports won't have
        real data behind them.
      </p>
      {regions.length > 0 && (
        <p className="sidebar-regions">
          Regions: {regions.join(", ")}
        </p>
      )}
      <input
        className="sidebar-filter"
        type="text"
        placeholder="Filter by code, city, state, region..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />
      {loading && <p className="sidebar-status">Loading airports...</p>}
      {error && <p className="sidebar-status sidebar-error">Failed to load airports: {error}</p>}
      {!loading && !error && (
        <ul className="airport-list">
          {filtered.map((a) => (
            <li key={a.airport_code}>
              <span className="airport-code">{a.airport_code}</span>
              <span className="airport-name">{a.name}</span>
              <span className="airport-meta">
                {a.city}, {a.state} &middot; {a.region}
              </span>
            </li>
          ))}
          {filtered.length === 0 && <li className="sidebar-status">No matches.</li>}
        </ul>
      )}
    </aside>
  );
}
