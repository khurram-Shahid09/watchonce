# ADR-0004: Python (FastAPI + Celery + Playwright) backend, Next.js frontend

- **Status:** Proposed (confirm with owner, see [16 D2](../16-open-questions.md)) · 2026-10-25

## Context
The runner needs Playwright and the compiler needs the Anthropic SDK. Both have first-class Python and TypeScript SDKs. The owner has production experience with Django/DRF, FastAPI, Celery, Redis, and Next.js.

## Decision
- Backend: **FastAPI + SQLAlchemy + Celery + Redis + Playwright (Python)** in one `services/core` package with separate worker queues
- Frontend: **Next.js + TypeScript**. Extension: **TypeScript**.
- One JSON Schema in `packages/spec` generates both Pydantic and TS types.

## Consequences
- ✅ Matches existing expertise → faster MVP
- ✅ Celery gives mature retries, queues and routing for compile/run/heal
- ❌ Two languages in the repo (mitigated by the shared schema + generated API client)
