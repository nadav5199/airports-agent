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
- `docs/` — contracts and the design/architecture document

## Status
Scaffolding in progress — see `CLAUDE.md` for full status and plan.
