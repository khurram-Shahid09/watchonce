# ADR-0004: Django + DRF backend, Next.js frontend

- **Status:** Accepted · 2026-10-25 (supersedes the earlier FastAPI proposal)

## Context
The runner needs Playwright and the compiler needs the LLM SDKs. Both have first-class Python support. Most of the backend is business plumbing: users, organizations, roles, workflows, versions, runs, approvals, secrets and an audit log. The owner has production experience with Django/DRF, Celery, Redis, WebSockets and Next.js. FastAPI was considered for native async and WebSockets, but it needs auth, admin and ORM tooling assembled by hand.

## Decision
- Backend: **Django + Django REST Framework** in `services/core`, with **Django Channels** for WebSockets, **Celery + Redis** for the `compile`, `run` and `heal` queues, and **Playwright (Python)** in the runner
- API schema via **drf-spectacular**. Auth via **simplejwt + django-allauth** + a custom PAT authentication class.
- Framework-agnostic core logic (compiler, runner, healer, LLM providers) lives in `services/core/engine/` and is called from Celery tasks
- The workflow spec and AI outputs are validated with **Pydantic** models generated from `packages/spec/workflow.schema.json`
- Frontend: **Next.js + TypeScript**. Extension: **TypeScript**.

## Consequences
- ✅ Fastest path to MVP for this owner: auth, ORM, migrations and admin are built in
- ✅ Django admin gives a free internal back-office for debugging runs, heals and costs
- ✅ Best-in-class Celery integration (`django-celery-beat` for v0.2 scheduling)
- ✅ Highly trusted framework in enterprise settings
- ❌ WebSockets need Channels (an extra component, mitigated by owner experience)
- ❌ Two validation styles (DRF serializers for API I/O, Pydantic for spec/LLM data)
- ❌ Two languages in the repo (mitigated by the shared JSON Schema + generated API client)
