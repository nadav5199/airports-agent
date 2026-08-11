# Airport Investment Intelligence Agent

## Project Summary
This is a Forward Deployed Engineer take-home exam (Deloitte Digital, July 2026, 24-hour timeframe).
We are building an AI-powered agent for a firm that invests in US airport modernization projects.
The agent helps analysts identify airports where renovations/expansions will be most profitable,
based on increased flight and passenger capacity — i.e., which airports are strong investment
candidates for terminal expansion or other modernization.

**Status:** Not yet started — no source code exists in this directory yet. This file is the
requirements reference for building the project.

## Example Queries the Agent Must Support
- "Which airports in New England are strong candidates for terminal expansion?"
- "Compare LA and Santa Ana airport congestion levels."
- "What is the percentage of long haul flights out of Anchorage airport?"
- "What is the unmet flight demand in SFO airport and why?"

## Functional Requirements
- **Data sourcing:** Use public APIs to gather airport/aviation data (flights, capacity, traffic, etc.).
- **Ranking/scoring:** Rank or compare airports using a defined scoring logic or KPI.
- **Explainability:** Clearly explain the reasoning behind rankings/comparisons.
- **Conversational:** Support conversational follow-up questions (multi-turn chat).
- **Interface:** Provide a chat interface to interact with the agent. Voice support is a bonus,
  not required.

## Hard Requirements
- **Deterministic logic required:** Scoring/ranking must include deterministic logic — not
  LLM output alone. The LLM should reason over and explain results produced by real
  calculations, not invent rankings itself.
- **Transparency:** Clearly communicate assumptions, uncertainty, and scoping limitations to
  the user (e.g., what data wasn't available, what's approximated, what's out of scope).

## Deliverables
1. **Source code** for the agent (data pipeline, scoring logic, chat interface).
2. **Short design/architecture document** covering:
   - Scoring methodology (how airports are ranked/compared, what KPIs and why).
   - Key tradeoffs made given the time constraint.
   - Where and how AI/LLM is used in the system (vs. deterministic logic).

## Data Sources (decided)
Public/free sources, chosen to fit the 24h build window (no paid/login-gated APIs):
- **OurAirports** (free CSV, no key, nightly updates) — airport reference data: location, state/region, runways, elevation. Used for regional filtering (e.g., "New England") and as a rough physical-capacity proxy.
- **BTS T-100 Segment** (`datahub.transportation.gov`, free, no key) — route-level passengers, seats, departures, distance, carrier. Distance buckets flights into long-haul/short-haul; volume feeds demand metrics.
- **FAA ATADS** (public, no login, monthly) — airport operations counts (takeoffs/landings, itinerant vs. local) over time. Core input for congestion and traffic-growth scoring.
- **BTS Airline On-Time Performance / ASQP** (free download) — delays, cancellations, and causes. Drives an "unmet demand" signal (e.g., % of flights delayed/cancelled for capacity-related reasons).
- **FAA Airport Capacity Profiles** (PDF per airport, ~30-35 major airports, not an API) — hourly runway throughput capacity under VMC/IMC. Hardcoded into a small lookup table for airports in our demo set to compute utilization = operations ÷ capacity.

**Explicitly excluded:** FAA ASPM (login-gated), FlightAware AeroAPI (pay-per-call, no free tier), AviationStack/OpenSky (real-time trackers with thin free tiers; not needed since our questions are about structural capacity vs. demand trends, not live flight positions).

**Implication:** Data is batch-downloaded/cached from these public datasets ahead of time rather than queried live per chat turn — the LLM reasons over precomputed deterministic metrics. Freshness is monthly/quarterly, not real-time. State this as an explicit assumption in the design doc.

## Scoring Methodology (decided)
Deterministic, reproducible, not LLM-adjusted — satisfies the "deterministic logic required" hard requirement. The LLM explains these numbers; it does not invent or reweight them.

**Composite "Expansion Candidate Score" (0-100)** = weighted sum of four KPIs, each independently normalized to 0-100 via **percentile rank across the current comparison set** (e.g. all New England airports, or just the two airports being compared). Percentile rank is used over min-max because it's robust to outliers and stays meaningful even for small (e.g. 2-airport) comparisons.

| KPI | Weight | Formula | Source |
|---|---|---|---|
| Capacity Utilization | 35% | peak-period operations ÷ FAA hourly runway capacity | FAA ATADS ÷ FAA Airport Capacity Profiles |
| Traffic Growth Rate | 25% | multi-year CAGR of operations and/or passengers | FAA ATADS, BTS T-100 |
| Delay Burden | 25% | % flights delayed 15+ min and/or avg delay minutes, weighted toward volume/NAS-attributed causes | BTS On-Time/ASQP |
| Passenger/Seat Load Factor | 15% | passengers ÷ seats | BTS T-100 |

`Score = 0.35×CapacityUtilization + 0.25×TrafficGrowth + 0.25×DelayBurden + 0.15×LoadFactor`

**"Unmet demand" (e.g. SFO question):** not a separate KPI — it's the combination of high Capacity Utilization + high volume-attributed Delay Burden. Where BTS cause codes are available, unmet demand can be quantified as estimated ops/passengers delayed specifically due to volume/capacity constraints (excluding weather and carrier-caused delays).

**Long-haul share (standalone stat, not part of the composite score):** % of flights or seats with great-circle distance over the industry-standard long-haul threshold (~2,100+ nm / ~2,400+ statute miles, roughly 6+ hour flights), computed directly from the BTS T-100 distance field. Answers "% long-haul out of Anchorage" literally — it's descriptive, not a congestion/investment signal, so it isn't weighted into the ranking.

**FAA Capacity Profile coverage gap:** only ~30-35 major airports have an FAA Capacity Profile. For airports outside that set, Capacity Utilization falls back to a lower-confidence proxy (operations ÷ a rough capacity estimate derived from OurAirports runway count), and this is explicitly labeled as "estimated" in responses.

**Missing-data policy:** if any KPI can't be computed for an airport, it's labeled "unavailable"/"estimated" rather than silently defaulted to 0, and the composite score reweights across only the available KPIs — keeps the "communicate uncertainty" requirement honest instead of masking gaps with a fabricated number.

## Explainability (decided)
Satisfies the "explain its reasoning clearly" and "communicate assumptions/uncertainty" requirements as first-class design elements, not an afterthought.

- **Dual output per answer:** every chat response that cites a score/KPI returns two things from
  the backend: (1) the LLM's natural-language prose answer, and (2) a structured JSON payload —
  per-airport KPI raw values, percentile ranks, weights, contribution to the composite score,
  data vintage/as-of date, and a confidence flag (`actual` vs `estimated`) per KPI. The React UI
  renders the prose plus a collapsible "show the math" breakdown table/panel built from that JSON,
  so the user can audit every number without trusting the LLM's summary alone.
- **Grounding rule:** the system prompt requires the model to only state figures that came from
  tool results, and to cite which KPI/source backs any number it mentions. It's permitted to do
  light derived arithmetic on tool-returned numbers for follow-ups (e.g. a delta or ratio between
  two already-returned figures), but may never introduce a number that didn't originate from a
  tool call or a simple calculation on tool output — no estimating from general knowledge. If a
  KPI is unavailable, the model must say so rather than fill the gap itself (ties to the
  missing-data policy above).
- **Uncertainty surfaced consistently:** any KPI computed via the lower-confidence proxy (e.g.
  Capacity Utilization for airports without an FAA Capacity Profile) is labeled `estimated` in
  the structured payload and the UI visually distinguishes it (e.g. a badge/asterisk) from
  `actual` figures — not just mentioned once in passing text.

## Tech Stack (decided)
- **Backend:** Python + FastAPI. Exposes REST endpoints for chat and for the underlying scoring
  data. Hosts the data ingestion pipeline, the deterministic scoring engine, and LLM orchestration
  (tool-calling into the scoring functions).
- **Frontend:** React chat UI, calling the FastAPI backend. Voice is out of scope (bonus only, per
  the exam brief).
- **LLM:** OpenAI (GPT) via the OpenAI API, used for conversational Q&A and explaining/reasoning
  over the deterministic scores — not for producing the scores themselves. Wired via tool-calling
  so the model invokes real scoring functions rather than inventing numbers.
- **Agent orchestration:** Raw `openai` Python SDK function/tool calling — no agent framework
  (LangChain, OpenAI Agents SDK, etc). The scoring/query functions are exposed as tools; a simple
  manual loop handles tool calls and conversation history. Chosen for transparency, minimal
  dependencies, and lowest risk of framework quirks eating the 24h budget — easy to explain and
  debug in the design doc.
- **Data storage:** No database. Ingestion scripts pull from the five public sources (see Data
  Sources above) and write cleaned CSV/Parquet files; the scoring engine loads these with pandas
  at query time. Fits the batch-refreshed (not live) data model already decided.

## Scoping Guidance
- Timeframe is ~24 hours. Prioritize **clarity, reasoning, and thoughtful design** over
  completeness or polish. It's acceptable (and expected) to scope down data sources, airport
  coverage, or feature breadth as long as assumptions are stated explicitly.
