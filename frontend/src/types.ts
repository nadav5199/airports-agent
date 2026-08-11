// Types mirroring the real backend response shapes.
// Source of truth: backend/main.py + scoring/schemas.py + backend/tests/test_api.py
// (field names here match the running code, not just docs/contracts.md, per
// the instruction that implementation details take precedence over the spec).

export interface Airport {
  airport_code: string;
  name: string;
  city: string;
  state: string;
  region: string;
  lat: number;
  lon: number;
  runway_count: number | null;
  longest_runway_ft: number | null;
}

export type Confidence = "actual" | "estimated" | "unavailable";

export interface KPIResult {
  name: string; // "capacity_utilization" | "traffic_growth" | "delay_burden" | "load_factor"
  raw_value: number | null;
  normalized_0_100: number | null;
  weight: number;
  confidence: Confidence;
  source: string;
  as_of: string;
}

export interface ScoreBreakdown {
  airport_code: string;
  composite_score: number | null;
  kpis: Record<string, KPIResult>;
}

export interface LongHaulShare {
  airport_code: string;
  threshold_miles: number;
  pct_long_haul_flights: number;
  pct_long_haul_seats: number;
  as_of: string;
}

// The /api/chat `breakdown` array is untyped JSON on the wire (list[dict]);
// each element is either a ScoreBreakdown (has "kpis") or a LongHaulShare
// (has "pct_long_haul_flights"). Narrow with the type guards below.
export type BreakdownItem = ScoreBreakdown | LongHaulShare;

export function isScoreBreakdown(item: BreakdownItem): item is ScoreBreakdown {
  return (item as ScoreBreakdown).kpis !== undefined;
}

export function isLongHaulShare(item: BreakdownItem): item is LongHaulShare {
  return (item as LongHaulShare).pct_long_haul_flights !== undefined;
}

export interface ChatRequest {
  message: string;
  conversation_id: string | null;
}

export interface ChatResponse {
  reply: string;
  conversation_id: string;
  breakdown: BreakdownItem[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  breakdown?: BreakdownItem[];
  error?: boolean;
}
