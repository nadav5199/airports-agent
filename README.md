# Airport Investment Intelligence Agent

AI agent that helps analysts identify US airports where terminal/capacity expansion is most
likely to pay off, using public aviation data and a deterministic scoring model. See
[CLAUDE.md](CLAUDE.md) for the full requirements, data sources, scoring methodology, tech
stack, and explainability design, and [docs/contracts.md](docs/contracts.md) for the concrete
data schemas / function signatures / API shape that the ingestion, scoring, backend, and
frontend layers are built against.

## Layout
- `ingestion/` — pulls/cleans public aviation data into `data/processed/*.csv`
- `scoring/` — deterministic KPI + composite scoring engine over the processed data
- `backend/` — FastAPI app + OpenAI tool-calling agent exposing `/api/chat` and `/api/airports`
- `frontend/` — React chat UI with a "show the math" score-breakdown panel
- `docs/` — contracts (`docs/contracts.md`)

## Status
Core implementation complete — ingestion, scoring, backend, and frontend are built and verified
end-to-end against all four example questions from the exam brief. See `CLAUDE.md` for full
status and plan.

## Design / Architecture

**Airport Investment Intelligence Agent** — Deloitte Digital FDE take-home exam, July 2026.

### 1. Overview

An AI agent that helps analysts identify US airports where terminal/capacity-expansion
investment is most likely to pay off. It combines a deterministic scoring engine (real
formulas over real/semi-real public data) with an LLM (OpenAI GPT) that resolves natural-language
questions into tool calls, explains the resulting numbers, and supports conversational
follow-ups. The deterministic engine produces every number the user sees; the LLM never invents
a figure.

**Stack:** Python ingestion scripts → pandas/CSV data layer → deterministic `scoring/` engine →
FastAPI backend with raw OpenAI SDK tool-calling → React (Vite/TypeScript) chat UI. No database,
no agent framework (LangChain, etc.) — see §3 for why.

**Scope actually built:** 62 airports (all New England airports with scheduled service + the
exam's named airports LAX/SNA/ANC/SFO + ~35 other major US hubs), 24 months of operations/route
data, 2 months of real delay data. All four example questions from the exam brief work
end-to-end against the real running system.

### 2. Scoring Methodology

#### 2.1 Composite "Expansion Candidate Score"

A 0-100 score per airport, computed as a weighted sum of four independently-normalized KPIs:

| KPI | Weight | Formula | Rationale |
|---|---|---|---|
| Capacity Utilization | 35% | peak-hour operations ÷ FAA hourly runway capacity | Direct measure of how congested an airport already is relative to its physical ceiling — the single strongest "needs expansion" signal |
| Traffic Growth Rate | 25% | multi-year trend in operations/passengers | High growth means today's slack disappears — expansion pays off where demand is *rising*, not just where it's already high |
| Delay Burden | 25% | % flights delayed 15+ min, weighted toward volume/NAS-attributed causes | A visible symptom of congestion and the primary proxy for **unmet demand** |
| Passenger/Seat Load Factor | 15% | passengers ÷ seats | How saturated *already-scheduled* capacity is, independent of runway/terminal physical limits |

Each KPI is normalized to 0-100 via **percentile rank within the current comparison set** (e.g.
just the airports in a "New England" query, or just two airports in a head-to-head comparison) —
not a fixed global population. This was a deliberate choice: percentile rank is robust to
outliers and stays meaningful even for a 2-airport comparison, where min-max normalization would
be degenerate (one airport is trivially 0, the other trivially 100).

```
Score = 0.35×CapacityUtilization + 0.25×TrafficGrowth + 0.25×DelayBurden + 0.15×LoadFactor
```

If a KPI is unavailable for an airport (see §2.3), the score reweights across only the
*available* KPIs rather than treating the missing one as 0 — a data gap should never silently
drag a score down.

#### 2.2 "Unmet demand" and "long-haul share" are not separate scores

- **Unmet demand** (e.g. "why is SFO's demand unmet?") is not its own KPI — it's the
  *combination* of high Capacity Utilization and high volume-attributed Delay Burden, which the
  LLM is instructed to explain together rather than as independent facts.
- **Long-haul share** ("% long-haul out of Anchorage") is a direct descriptive statistic —
  % of flights/seats over a 2,400-statute-mile threshold — computed straight from route distance
  data. It answers a literal question and isn't a congestion/investment signal, so it's reported
  standalone rather than folded into the composite score.

#### 2.2b Which KPIs rest on synthetic data

To be explicit rather than requiring this to be traced through §3.1's source-by-source table,
here is the same information mapped onto the four KPIs that feed the composite score:

| KPI | Data behind it | Real or synthetic |
|---|---|---|
| Capacity Utilization | operations (FAA ATADS) ÷ runway capacity (FAA Capacity Profiles) | **Both synthetic** — ATADS operations are generated; Capacity Profile figures are hand-transcribed approximations, not pulled from each airport's actual published PDF |
| Traffic Growth Rate | multi-year trend in operations (ATADS) and/or passengers (BTS T-100) | **Synthetic** |
| Delay Burden | BTS On-Time Performance | **Real** — actual downloaded monthly files, 2 months, 50/62 airports |
| Passenger/Seat Load Factor | passengers ÷ seats (BTS T-100) | **Synthetic** |
| Long-haul share (standalone stat, not in composite score) | route distance (BTS T-100) | **Real** — computed via haversine from real lat/lon in `airports.csv`; only the passenger/seat *volumes* riding on top of those routes are synthetic |

**Net effect: 3 of the 4 composite-score KPIs (Capacity Utilization, Traffic Growth, Load
Factor) rest on synthetic data; only Delay Burden is real.** This is a bigger exposure than
"two of five sources are synthetic" sounds like at the source level, and is called out here
explicitly rather than left for the reader to derive.

**Why these two sources ended up synthetic — access mechanics, not cost.** Both FAA ATADS and
BTS T-100 are free, unlike the sources CLAUDE.md excludes outright for being paywalled
(FlightAware AeroAPI, FAA ASPM). They ended up synthetic because neither is programmatically
reachable within a 24h scope in practice:
- **FAA ATADS** is served through a session/ViewState-driven ASP.NET report generator with no
  stable bulk-CSV or REST endpoint — there's no fixed URL to script against, paid or free.
- **BTS T-100** bulk files sit behind a stateful web form that generates unpredictable,
  per-request hashed filenames (e.g. `896816367_T_T100D_SEGMENT_ALL_CARRIER.zip`), unlike the
  On-Time Performance files (used for real, see above), which have a stable, predictable URL
  pattern.

#### 2.3 Honesty about data confidence — two separate axes

Every KPI result carries **two independent trust signals**, both surfaced to the user rather than
collapsed into one:

1. **`confidence`** (`actual` / `estimated` / `unavailable`) — describes the *method*. Did we use
   the primary formula, a documented fallback/proxy, or could we compute nothing at all?
   - Capacity Utilization falls back to a runway-count-based proxy for the ~40 airports outside
     the ~20-airport FAA Capacity Profile set (`confidence="estimated"`).
   - Delay Burden is `unavailable` (not a fabricated 0) for the 12 small New England airports
     with zero rows in the real 2-month BTS delay extract.
   - Traffic Growth degrades gracefully for short data histories, downgrading to `estimated`
     rather than crashing or over-claiming precision.
2. **`source`** (free text) — discloses whether the *underlying data file itself* is real,
   synthetic-fallback, or hand-transcribed-approximate (see §3.1). A KPI can be
   `confidence="actual"` (the primary formula ran cleanly) while its `source` honestly notes the
   input file is synthetic — these are genuinely different questions, and conflating them would
   hide the real limitation from an analyst relying on this for investment decisions.

Missing/low-confidence data is never silently defaulted to a number — this is the concrete
implementation of the exam's "communicate uncertainty" requirement, not just a sentence in a
prompt.

### 3. Key Tradeoffs

#### 3.1 Real data where feasible; clearly-labeled synthetic fallback where not

Of the five data sources, two turned out to have no practically-reachable free bulk/API access
within scope, despite being public:

| Source | Status | Why |
|---|---|---|
| OurAirports (airport reference) | **Real** | Plain CSV over HTTPS, no auth |
| BTS On-Time Performance (delays) | **Real** (2 months, 50/62 airports) | Real bulk extracts, but each monthly file is a ~25-30MB national download with no filterable query API — bounded to 2 months to keep one-time ingestion runtime reasonable |
| FAA ATADS (operations) | **Synthetic fallback** | No stable bulk/REST endpoint — it's a session/ViewState-gated report generator, not a data feed |
| BTS T-100 (routes/passengers/seats) | **Synthetic fallback** (route distances are real) | Bulk files sit behind a stateful form with non-predictable per-request filenames |
| FAA Capacity Profiles (runway throughput) | **Hardcoded lookup, by design** | PDF-only documents, no API exists at all — not a shortcut, a structural fact about this data source |

**Tradeoff:** this is the single biggest deviation from "use public APIs to gather data." It was
accepted deliberately rather than silently, because a demo built on nothing (blocked entirely by
FAA ATADS/T-100's access barriers) is worse than a demo built on a transparently-labeled,
internally-consistent, deterministically-seeded synthetic dataset that exercises the same
scoring logic the real data would. Every synthetic value is disclosed at the file level
(`data/processed/README.md`) and the KPI level (`source` field) — nothing is presented as more
authoritative than it is. In a production version, closing this gap (e.g. FAA ATADS via
scraping/vendor data, T-100 via a paid data provider) would be the top priority.

#### 3.2 Batch-cached data, not live API calls per chat turn

Ingestion runs once (or on manual re-run) and writes static CSVs; the chat app only ever reads
those files with pandas. **Tradeoff:** data freshness is "as of last ingestion run," not
real-time — acceptable for an investment-analysis tool reasoning about structural capacity
trends (monthly/quarterly cadence), not for live flight-status use cases. This also makes scoring
fast and fully reproducible, which matters for a *deterministic* scoring requirement — a live API
dependency would make the same question answerable differently minute to minute.

#### 3.3 No agent framework

Tool-calling is a manual loop against the raw OpenAI SDK, not LangChain or the OpenAI Agents SDK.
**Tradeoff:** more boilerplate than a framework would save, in exchange for full transparency
(every tool dispatch is inspectable Python, not framework internals), minimal dependency
surface, and lower risk of framework quirks consuming the build's time budget. For a
single-agent, well-scoped tool-calling use case, the framework's abstractions weren't earning
their cost.

#### 3.4 No database

Processed data lives in CSV files loaded by pandas; conversation history is in-memory,
process-local. **Tradeoff:** simple to build and reason about, fits the batch-refreshed data
model, but conversation history doesn't survive a backend restart, and CSV-scale performance
wouldn't hold up much beyond hundreds of airports. Both are acceptable for a 62-airport, 24-hour
scope and would be the first things to change for a production system.

#### 3.5 Sequential, not parallel, agent build

The four implementation layers (ingestion → scoring → backend → frontend) were built by separate
agents *sequentially*, each merging real, tested work into `main` before the next started,
instead of in parallel against a stubbed/mocked contract. **Tradeoff:** slower wall-clock time
than parallel execution, in exchange for each layer being built and tested against the *actual*
upstream output rather than an interface assumption that could have drifted from reality (e.g.
the scoring engine was written against the real 62-airport dataset's real column values and real
data sparsity, not an imagined one).

### 4. Where and How AI Is Used

**The LLM (OpenAI GPT, via the raw `openai` SDK with tool-calling) is used for exactly three
things — and explicitly not for a fourth:**

1. **Resolving natural language into structured queries.** "Which airports in New England..." or
   "LA and Santa Ana" have to become real `airport_code`s before anything deterministic can run.
   A `lookup_airports` tool (filtering the real `airports.csv` by region/state/query/explicit
   codes) handles this resolution step.
2. **Orchestrating tool calls.** The model decides which scoring functions to call and with what
   arguments (e.g. call `compute_composite_score` for a list of resolved airport codes, then
   `compute_long_haul_share` per airport if the question asks about long-haul share).
3. **Explaining results in natural language.** Given the real tool outputs, the model writes the
   prose answer — citing specific numbers, their confidence level, and their source — and
   supports multi-turn follow-ups via threaded conversation history.

**What the LLM never does: produce a score, a ranking, or any numeric figure from its own
knowledge.** This is enforced by:
- **Tool-only grounding.** The system prompt requires every stated number to originate from a
  tool result (light derived arithmetic on tool-returned numbers — e.g. a delta between two
  already-fetched figures — is permitted; inventing or "recalling" a number is not).
- **Mandatory source citation.** The model must say which KPI/source backs any number it states.
- **Explicit "unavailable" over guessing.** If a tool returns `confidence="unavailable"`, the
  model must say so, not fill the gap from general knowledge.
- **Dual output, not prose-only.** Every chat response that touches scored data returns both the
  LLM's prose *and* the raw structured tool results (`ScoreBreakdown`/`LongHaulShare` JSON). The
  frontend renders this as a collapsible "show the math" panel with a KPI table and
  actual/estimated/unavailable confidence badges — so a user can audit every number without
  trusting the LLM's summary. This was treated as core to "explain its reasoning clearly," not a
  nice-to-have.

All ranking/scoring logic itself — the formulas, weights, normalization, and missing-data
handling in §2 — is plain deterministic Python with no LLM involvement, satisfying the exam's
"deterministic logic required, not only LLM output" requirement directly.

### 5. Voice (bonus)

Voice support is called out in the exam brief as a bonus, not a requirement. Implemented via the
browser-native **Web Speech API** (`SpeechRecognition` for speech-to-text, `speechSynthesis` for
text-to-speech) rather than a third-party platform (e.g. Vapi):

- **Mic input**: a 🎤 button next to the chat input (left of Send) transcribes speech and sends it
  immediately — it goes through the exact same `/api/chat` call as typed messages, no new backend
  code.
- **Spoken replies**: an opt-in **"Read replies aloud" checkbox, off by default, sitting directly
  under the page header/description** (above the airport sidebar and chat panel — easy to miss on
  first glance since it's small and unchecked by default). Check it to have the LLM's prose reply
  spoken via `speechSynthesis` — never the structured breakdown JSON.
- **Why this over a hosted voice platform**: zero new accounts/API keys/services, works entirely
  client-side, and reuses the existing chat endpoint unchanged — fit the 24h budget for a bonus
  feature better than integrating an external voice pipeline.
- **Known limitation**: Web Speech API is Chromium-only (Chrome/Edge) — no Safari/Firefox
  support. The mic button and toggle detect support and hide themselves gracefully when
  unavailable, rather than erroring.

### 6. Known Limitations (honest accounting)

- FAA ATADS and BTS T-100 volumes are synthetic fallback data, not real (see §3.1) — route
  distances and delay data are real; operations/passenger/seat *volumes* are not.
- FAA Capacity Profile figures are representative/approximate, hand-transcribed from public
  knowledge rather than verified line-by-line against each airport's current official PDF.
- Real delay data covers only April-May 2026 for 50 of 62 airports; the rest report
  `confidence="unavailable"` for Delay Burden rather than a guessed number.
- Capacity Utilization's peak-hour figure is estimated from monthly totals via a documented
  8%-of-daily-volume planning assumption, since FAA ATADS's free product has no hourly
  granularity.
- The system prompt's real-world effectiveness was validated with a small number of manual
  live-model smoke tests (the four example questions), not a systematic eval suite.
- Conversation history and all data are process-local/in-memory or flat-file — no database, no
  persistence across restarts.
- 62 airports total; questions about airports outside this set won't have real data behind them
  (surfaced via the frontend's airport reference sidebar).
