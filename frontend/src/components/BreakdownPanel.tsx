import { useState } from "react";
import type { BreakdownItem } from "../types";
import { isLongHaulShare, isScoreBreakdown } from "../types";
import ConfidenceBadge from "./ConfidenceBadge";

const KPI_LABELS: Record<string, string> = {
  capacity_utilization: "Capacity Utilization",
  traffic_growth: "Traffic Growth",
  delay_burden: "Delay Burden",
  load_factor: "Load Factor",
};

function fmt(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

function fmtPct(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

/** Collapsible "show the math" panel rendered under an agent reply whenever
 * that reply's `breakdown` array is non-empty. Renders one card per
 * ScoreBreakdown (KPI table + composite score) or LongHaulShare (stat card). */
export default function BreakdownPanel({ items }: { items: BreakdownItem[] }) {
  const [open, setOpen] = useState(false);

  if (!items || items.length === 0) return null;

  return (
    <div className="breakdown-panel">
      <button
        type="button"
        className="breakdown-toggle"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        {open ? "▾" : "▸"} Show the math ({items.length} airport
        {items.length === 1 ? "" : "s"})
      </button>
      {open && (
        <div className="breakdown-body">
          {items.map((item, idx) =>
            isScoreBreakdown(item) ? (
              <ScoreBreakdownCard key={`${item.airport_code}-score-${idx}`} item={item} />
            ) : isLongHaulShare(item) ? (
              <LongHaulCard key={`${item.airport_code}-lh-${idx}`} item={item} />
            ) : null
          )}
        </div>
      )}
    </div>
  );
}

function ScoreBreakdownCard({ item }: { item: Extract<BreakdownItem, { kpis: unknown }> }) {
  const kpiEntries = Object.entries(item.kpis);
  // Most recent as_of across KPIs, for a card-level summary label.
  const asOfValues = kpiEntries.map(([, k]) => k.as_of).filter(Boolean);
  const asOf = asOfValues.length ? asOfValues.sort().at(-1) : "—";

  return (
    <div className="breakdown-card">
      <div className="breakdown-card-header">
        <strong>{item.airport_code}</strong>
        <span className="composite-score">
          Composite Score: {item.composite_score === null ? "N/A" : fmt(item.composite_score, 1)}
        </span>
        <span className="as-of">as of {asOf}</span>
      </div>
      <div className="table-scroll">
        <table className="kpi-table">
          <thead>
            <tr>
              <th>KPI</th>
              <th>Raw Value</th>
              <th>Weight</th>
              <th>Percentile Score</th>
              <th>Confidence</th>
              <th>Source</th>
              <th>As Of</th>
            </tr>
          </thead>
          <tbody>
            {kpiEntries.map(([key, kpi]) => (
              <tr key={key}>
                <td>{KPI_LABELS[key] ?? key}</td>
                <td>{fmt(kpi.raw_value)}</td>
                <td>{fmtPct(kpi.weight, 0)}</td>
                <td>{kpi.normalized_0_100 === null ? "—" : fmt(kpi.normalized_0_100, 1)}</td>
                <td>
                  <ConfidenceBadge confidence={kpi.confidence} />
                </td>
                <td className="source-cell">{kpi.source}</td>
                <td>{kpi.as_of}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LongHaulCard({
  item,
}: {
  item: Extract<BreakdownItem, { pct_long_haul_flights: unknown }>;
}) {
  return (
    <div className="breakdown-card">
      <div className="breakdown-card-header">
        <strong>{item.airport_code}</strong>
        <span className="composite-score">Long-Haul Share</span>
        <span className="as-of">as of {item.as_of}</span>
      </div>
      <div className="table-scroll">
        <table className="kpi-table">
          <thead>
            <tr>
              <th>Threshold (miles)</th>
              <th>% Long-Haul Flights</th>
              <th>% Long-Haul Seats</th>
              <th>As Of</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>{fmt(item.threshold_miles, 0)}</td>
              <td>{fmtPct(item.pct_long_haul_flights)}</td>
              <td>{fmtPct(item.pct_long_haul_seats)}</td>
              <td>{item.as_of}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
