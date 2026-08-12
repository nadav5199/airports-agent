import { useState } from "react";
import type { BreakdownItem, Confidence } from "../types";
import { isLongHaulShare, isScoreBreakdown } from "../types";
import ConfidenceBadge from "./ConfidenceBadge";

const KPI_INFO: Record<string, { label: string; description: string }> = {
  capacity_utilization: {
    label: "Capacity Utilization",
    description: "Peak-period operations ÷ FAA hourly runway capacity",
  },
  traffic_growth: {
    label: "Traffic Growth",
    description: "Multi-year CAGR of operations/passengers",
  },
  delay_burden: {
    label: "Delay Burden",
    description: "% of flights delayed 15+ min, weighted toward volume-caused delays",
  },
  load_factor: {
    label: "Load Factor",
    description: "Passengers ÷ seats",
  },
};

const CONFIDENCE_LEGEND: { confidence: Confidence; description: string }[] = [
  { confidence: "actual", description: "measured directly from source data" },
  {
    confidence: "estimated",
    description: "computed via a lower-confidence proxy (e.g. no FAA Capacity Profile for this airport)",
  },
  {
    confidence: "unavailable",
    description: "could not be computed; excluded from the composite score",
  },
];

function fmt(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

function fmtPct(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(digits)}%`;
}

/** Tier a 0-100 value into low/mid/high for at-a-glance color coding. */
function tierOf(n: number | null | undefined): "low" | "mid" | "high" | null {
  if (n === null || n === undefined || Number.isNaN(n)) return null;
  if (n < 33) return "low";
  if (n < 66) return "mid";
  return "high";
}

/** Collapsible "show the math" panel rendered under an agent reply whenever
 * that reply's `breakdown` array is non-empty. Renders one card per
 * ScoreBreakdown (KPI table + composite score) or LongHaulShare (stat card). */
export default function BreakdownPanel({ items }: { items: BreakdownItem[] }) {
  const [open, setOpen] = useState(false);

  if (!items || items.length === 0) return null;

  const hasScoreCard = items.some(isScoreBreakdown);

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
          {hasScoreCard && <ConfidenceLegend />}
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

function ConfidenceLegend() {
  return (
    <div className="breakdown-legend">
      {CONFIDENCE_LEGEND.map(({ confidence, description }) => (
        <span key={confidence} className="breakdown-legend-item">
          <ConfidenceBadge confidence={confidence} />
          {description}
        </span>
      ))}
    </div>
  );
}

function ScoreBreakdownCard({ item }: { item: Extract<BreakdownItem, { kpis: unknown }> }) {
  const kpiEntries = Object.entries(item.kpis);
  // Most recent as_of across KPIs, for a card-level summary label.
  const asOfValues = kpiEntries.map(([, k]) => k.as_of).filter(Boolean);
  const asOf = asOfValues.length ? asOfValues.sort().at(-1) : "—";
  const compositeTier = tierOf(item.composite_score);

  // weight * normalized_0_100 / 100, summed, should equal the composite score --
  // shown per-row and totaled so the table visibly reconstructs the composite.
  const contributions = kpiEntries.map(([, kpi]) =>
    kpi.normalized_0_100 === null || kpi.weight === null ? null : (kpi.weight * kpi.normalized_0_100) / 100
  );
  const totalContribution = contributions.some((c) => c !== null)
    ? contributions.reduce((sum: number, c) => sum + (c ?? 0), 0)
    : null;

  return (
    <div className="breakdown-card">
      <div className="breakdown-card-header">
        <strong>{item.airport_code}</strong>
        <span className={`composite-score${compositeTier ? ` composite-score--${compositeTier}` : ""}`}>
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
              <th>Contribution</th>
              <th>Confidence</th>
              <th>Source</th>
              <th>As Of</th>
            </tr>
          </thead>
          <tbody>
            {kpiEntries.map(([key, kpi], i) => {
              const info = KPI_INFO[key];
              const tier = tierOf(kpi.normalized_0_100);
              return (
                <tr key={key}>
                  <td>
                    {info ? (
                      <span className="kpi-name-cell">
                        <span className="kpi-name">{info.label}</span>
                        <span className="kpi-description">{info.description}</span>
                      </span>
                    ) : (
                      key
                    )}
                  </td>
                  <td>{fmt(kpi.raw_value)}</td>
                  <td>{fmtPct(kpi.weight, 0)}</td>
                  <td>
                    {kpi.normalized_0_100 === null ? (
                      "—"
                    ) : (
                      <span className="percentile-cell">
                        <span className="percentile-bar">
                          <span
                            className={`percentile-bar-fill${tier ? ` percentile-bar-fill--${tier}` : ""}`}
                            style={{ width: `${Math.max(0, Math.min(100, kpi.normalized_0_100))}%` }}
                          />
                        </span>
                        {fmt(kpi.normalized_0_100, 1)}
                      </span>
                    )}
                  </td>
                  <td className="kpi-contribution">{contributions[i] === null ? "—" : fmt(contributions[i], 1)}</td>
                  <td>
                    <ConfidenceBadge confidence={kpi.confidence} />
                  </td>
                  <td className="source-cell">{kpi.source}</td>
                  <td>{kpi.as_of}</td>
                </tr>
              );
            })}
          </tbody>
          {totalContribution !== null && (
            <tfoot>
              <tr className="kpi-table-total">
                <td colSpan={4}>Sum of contributions</td>
                <td className="kpi-contribution">{fmt(totalContribution, 1)}</td>
                <td colSpan={3} />
              </tr>
            </tfoot>
          )}
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
