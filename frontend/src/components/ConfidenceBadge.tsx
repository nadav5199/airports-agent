import type { Confidence } from "../types";

const LABELS: Record<Confidence, string> = {
  actual: "actual",
  estimated: "estimated",
  unavailable: "unavailable",
};

export default function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  return (
    <span className={`badge badge-${confidence}`} title={`Confidence: ${confidence}`}>
      {LABELS[confidence] ?? confidence}
    </span>
  );
}
