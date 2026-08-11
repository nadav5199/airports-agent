# frontend/

React (Vite + TypeScript) chat UI for the Airport Investment Intelligence
Agent. Calls the real FastAPI backend's `POST /api/chat` and
`GET /api/airports` per [`docs/contracts.md`](../docs/contracts.md). Field
names in `src/types.ts` were matched against the actual running backend
(`backend/main.py`, `backend/tests/test_api.py`, `scoring/schemas.py`), not
just the abstract contract.

## Module layout
- `src/api.ts` -- thin `fetch` wrappers for the two endpoints; reads the
  configurable backend base URL.
- `src/types.ts` -- TypeScript types mirroring `Airport`, `KPIResult`,
  `ScoreBreakdown`, `LongHaulShare`, and the chat request/response shapes,
  plus type guards (`isScoreBreakdown` / `isLongHaulShare`) to narrow the
  untyped `breakdown` array returned by `/api/chat`.
- `src/App.tsx` -- top-level layout: header, airport sidebar, chat panel.
  Owns chat message state and the `conversation_id` threaded across turns.
- `src/components/ChatThread.tsx` -- message list + input box.
- `src/components/BreakdownPanel.tsx` -- the collapsible "show the math"
  panel rendered under any agent reply whose `breakdown` array is non-empty.
  Renders one card per airport: a KPI table (raw value, weight, percentile
  score, confidence badge, source, as-of) for `ScoreBreakdown` entries, or a
  stat table (threshold, % long-haul flights/seats, as-of) for
  `LongHaulShare` entries.
- `src/components/ConfidenceBadge.tsx` -- visually distinct badge for
  `confidence: "actual" | "estimated" | "unavailable"` (green / amber / red).
- `src/components/AirportSidebar.tsx` -- reference list of every airport in
  `GET /api/airports`, with a text filter. Exists mainly to prove the
  endpoint is wired to real data and to make the ~62-airport scoping
  limitation visible to the user (per `CLAUDE.md`'s "communicate scoping"
  requirement) -- questions about airports not in this list won't have real
  data behind them.

## Running it

```
cd frontend
npm install
npm run dev       # starts Vite dev server, default http://localhost:5173
```

In a separate terminal, run the real backend (see `backend/README.md`):
```
uvicorn backend.main:app --reload --port 8000
```

Build for production:
```
npm run build      # tsc -b && vite build -> frontend/dist/
npm run preview    # serve the production build locally
```

Lint:
```
npm run lint       # oxlint
```

## Configuration

`VITE_API_BASE_URL` -- backend base URL. Defaults to `http://localhost:8000`
if unset. Set it in `frontend/.env` (copy `frontend/.env.example`) to point
at a different backend, e.g.:
```
VITE_API_BASE_URL=http://localhost:8000
```

CORS: the backend's `CORSMiddleware` is wide open (`allow_origins=["*"]`) for
local dev, so no proxy config is needed.

## What was verified live (not mocked)

Both the real backend (`uvicorn backend.main:app --port 8000`, real
`data/processed/*.csv`, real `scoring/` functions) and the real Vite dev
server (`npm run dev`, port 5173) were started, and the app was driven with a
headless Chrome instance (via `puppeteer-core` against the system-installed
Chrome) doing actual clicks/typing -- not a static render check:

1. **`GET /api/airports` over real HTTP, rendered in the UI.** The sidebar
   loaded and displayed all **62 real airports** (verified count and sample
   rows both via direct `curl` and via the rendered DOM/screenshot), with
   working client-side text filtering by code/city/state/region.
2. **A real `OPENAI_API_KEY` was present in `backend/.env`** (gitignored,
   pre-existing from the backend agent's build -- not fabricated by this
   agent), so `/api/chat` was exercised end-to-end against the real OpenAI
   API through real HTTP from the browser, for three of the example queries
   from `CLAUDE.md`:
   - *"What is the percentage of long haul flights out of Anchorage
     airport?"* -- reply correctly cited 55.7% of flights / 67.6% of seats
     long-haul (matches the figures documented in `backend/README.md`'s own
     smoke test); the "Show the math" panel rendered a `LongHaulShare` card
     with threshold/pct fields.
   - *"Which airports in New England are strong candidates for terminal
     expansion?"* -- reply ranked PVD (77.0) and BOS (71.0) highest; the
     breakdown panel rendered one `ScoreBreakdown` card per airport with all
     4 KPIs, correctly showing `estimated` (amber badge) for
     capacity-utilization-via-runway-proxy airports and `actual` (green
     badge) for the rest.
   - *"Compare LA and Santa Ana airport congestion levels."* -- reply
     compared LAX vs. SNA capacity utilization and delay burden with a
     4-airport breakdown underneath.
3. **Confidence badges are visually distinct**: computed styles confirmed
   `actual` renders green (`rgb(220,245,226)` bg), `estimated` renders amber
   (`rgb(255,242,204)` bg); `unavailable` is styled red in the same
   component (not hit by these particular smoke queries, but same code
   path).
4. Multi-turn `conversation_id` threading is wired (state carried in
   `App.tsx`, sent on every `POST /api/chat`) but the interactive smoke test
   above only drove single-turn exchanges (one message per browser session);
   it was **not** re-verified with a live follow-up question referencing
   prior context in this pass -- the request/response wiring is the same
   code path exercised by `backend/tests/test_api.py`'s
   `test_post_chat_conversation_id_persists_history`, which does test it
   (with a mocked LLM), so multi-turn plumbing is covered, just not with a
   second live OpenAI call in the browser.

`npm run build` (TypeScript project build + Vite production build) and
`npx oxlint` both pass with zero errors/warnings as of this writing.

## Known gaps / honest limitations
- No automated frontend test suite (no Vitest/RTL tests) -- given the 24h
  scope, verification leaned on the live browser-driven smoke test above
  instead. Manual/scripted verification, not CI-enforced regression
  coverage.
- The airport sidebar is a flat filterable list, not a true autocomplete
  wired into the chat input -- CLAUDE.md marks the picker as optional
  ("nice to have, mainly to prove the endpoint is wired"), so this was kept
  simple per the "prioritize clarity over polish" scoping guidance.
- If `/api/chat` fails (network error, backend down, no API key), the UI
  surfaces the error inline as a distinct red chat bubble rather than
  failing silently -- but there's no retry/backoff logic.
- In-memory conversation history lives entirely in React state; a page
  refresh loses the thread (matches the backend's own in-memory,
  process-local history, so nothing durable is lost that wasn't already
  ephemeral).
