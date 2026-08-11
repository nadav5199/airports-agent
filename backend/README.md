# backend/

FastAPI + raw `openai` Python SDK tool-calling agent layer for the Airport
Investment Intelligence Agent. Implements `POST /api/chat` and
`GET /api/airports` per [`docs/contracts.md`](../docs/contracts.md). Wraps the
real `scoring/` functions (does not reimplement scoring logic) as OpenAI
tool-calls, per `CLAUDE.md`'s "Agent orchestration" and "Explainability"
sections.

## Module layout
- `main.py` -- FastAPI app: `/api/chat`, `/api/airports`, CORS, in-memory
  per-`conversation_id` chat history.
- `agent.py` -- the manual tool-calling loop (`run_agent_turn`) against an
  injected OpenAI-SDK-shaped `client`. System prompt encodes the grounding
  rule, airport-resolution instruction, and composite-score explanation
  requirement from `CLAUDE.md`.
- `tools.py` -- OpenAI tool/function JSON schemas + `execute_tool()` dispatch
  to the real `scoring.kpis` / `scoring.composite` functions, plus
  `lookup_airports()` (filters the real `airports.csv` by region/state/query/
  explicit codes) so the LLM can resolve "New England airports" or "LA and
  Santa Ana" into real `airport_code`s before scoring.
- `tests/` -- pytest, see "What was tested" below.

## Running it

```
pip install -r requirements.txt
cp backend/.env.example .env   # fill in OPENAI_API_KEY for real LLM calls
uvicorn backend.main:app --reload --port 8000
```

Env vars (`.env`, loaded via `python-dotenv`; see `backend/.env.example`):
- `OPENAI_API_KEY` -- required for real `/api/chat` calls. Not required to
  run `GET /api/airports` or the test suite.
- `OPENAI_MODEL` -- optional, defaults to `gpt-4o-mini`.

```
curl http://localhost:8000/api/airports
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Which New England airports are strong expansion candidates?", "conversation_id": null}'
```

## What was tested -- be precise about this

**Tested with a real OpenAI API call: YES (added late in the build).** No
`OPENAI_API_KEY` was available for most of development (confirmed unset at
the start), so the design deliberately keeps the OpenAI client injectable
(`get_openai_client` FastAPI dependency / `run_agent_turn(client, ...)`) so
the tool-calling control flow could be fully tested with mocks first (see
below). A real key was later added to `backend/.env` (gitignored, never
committed) and used to run the real app end-to-end against the real OpenAI
API through a real `uvicorn` server + real HTTP requests, no mocking:
- `"What is the percentage of long haul flights out of Anchorage airport?"`
  -- the model correctly called `compute_long_haul_share(airport_code="ANC")`
  and reported 55.7% of flights / 67.6% of seats long-haul, matching
  `scoring.kpis.compute_long_haul_share("ANC")` exactly.
- `"Which airports in New England are strong candidates for terminal
  expansion?"` -- the model correctly called `lookup_airports(region="New
  England")` first to resolve the 5 New England airports with T-100 data
  (PVD, PWM, BOS, BDL, MHT) into real IATA codes, then
  `compute_composite_score` and `compute_long_haul_share` for each, and
  produced a prose summary correctly citing each KPI's confidence
  (actual/estimated) and composite score, e.g. ranking PVD (77) and PWM (68)
  as the strongest candidates -- all numbers traced back to real tool
  results, no invented figures.

This confirms the system prompt's grounding/airport-resolution/composite-
explanation instructions work as intended against a live model, not just in
theory. That said, this was a small number of manual smoke-test queries, not
a systematic eval -- treat it as "the wiring works end-to-end with a real
key," not "the prompt has been exhaustively validated."

**Tested with a mocked LLM + real scoring + real HTTP: YES.**
- `backend/tests/fakes.py` hand-builds fake OpenAI SDK response objects
  (`FakeOpenAIClient`, matching `response.choices[0].message.{content,
  tool_calls}` / `tool_calls[i].function.{name,arguments}`) -- no network
  call, no real API.
- `backend/tests/test_tools.py` (9 tests): tool schemas are well-formed and
  match `execute_tool`'s dispatch targets; `lookup_airports` filters the real
  `data/processed/airports.csv`; every scoring tool dispatches to the real
  `scoring.kpis` / `scoring.composite` functions against the real merged
  data (SFO, ACK, ANC, unknown-code `ZZZ` edge cases).
- `backend/tests/test_agent_loop.py` (5 tests): the tool-calling loop
  (`run_agent_turn`) against mocked multi-round responses -- single tool call,
  a two-tool-call chain (`lookup_airports` -> `compute_composite_score`,
  mirroring "which New England airports..."), a no-tool-call direct reply,
  multi-turn history threading across two calls to `run_agent_turn`, and a
  malformed tool-call args case (loop doesn't crash, error dict fed back to
  the model).
- `backend/tests/test_api.py` (6 tests): FastAPI's `TestClient` (a real ASGI
  request through the actual `app` object) against `/api/airports` (real
  62-row dataset, real column set) and `/api/chat` with the OpenAI call
  mocked via `app.dependency_overrides[get_openai_client]` -- the tool-dispatch
  loop and `scoring.composite.compute_composite_score` / `compute_long_haul_share`
  underneath it are 100% real, only the LLM response is a hand-built fake.
  Verifies conversation_id generation/persistence and the empty-message 422
  validation path.
- **Additionally**, beyond the pytest suite, the real app was started with a
  real `uvicorn` server (a real OS socket, not `TestClient`) and hit with real
  `requests` HTTP calls from a separate script
  (verified during development; see commit history) confirming:
  `GET /api/airports` returns all 62 real rows over real HTTP, and
  `POST /api/chat` -- with the OpenAI call mocked only at the
  `get_openai_client` dependency boundary -- round-trips through the real
  tool-calling loop, calls the real `compute_composite_score`, and returns a
  real `ScoreBreakdown` (composite_score, all 4 KPIs, confidence/source per
  KPI) embedded in the JSON response.

Run the test suite:
```
python -m pytest backend/tests -v
```
21/21 passing as of this writing.

## Known gaps / honest limitations
- No real LLM call has ever been made against this code. The system prompt's
  effectiveness (does the model actually call `lookup_airports` first, does
  it actually cite sources, does it actually say "unavailable" rather than
  guess) is unverified beyond the fact that the tool schemas are
  well-formed JSON and the control-flow loop correctly dispatches whatever
  tool calls it's given.
- In-memory conversation history is process-local and lost on restart -- fine
  for this take-home's scope (see `CLAUDE.md` "Data storage"), not
  production-durable.
- CORS is wide open (`allow_origins=["*"]`) for local frontend-dev
  convenience; would be locked to a specific origin in a real deployment.
