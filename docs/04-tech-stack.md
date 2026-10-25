# 04 · Tech Stack

The choices favour **what Khurram already ships in production** (Next.js, Django/FastAPI, Celery, Redis, Postgres, WebSockets, Cloudflare R2). That keeps the time to MVP short while staying credible for enterprise.

| Layer | Choice | Why |
|---|---|---|
| Recorder | **Chrome Extension, Manifest V3, TypeScript, Vite** | Records real DOM semantics, which video alone can't give. Chrome/Edge cover most enterprise desktops. |
| Dashboard | **Next.js (App Router) + TypeScript + Tailwind + shadcn/ui** | Known stack, fast to build. Check the installed version's docs for breaking changes before coding. |
| API | **FastAPI (Python 3.12) + Pydantic v2** | Same language as the Playwright runner and the Anthropic Python SDK. Async. OpenAPI generated for free. |
| ORM / migrations | **SQLAlchemy 2.0 + Alembic** | Standard, typed |
| Background jobs | **Celery + Redis** | Already used at Enigmatix. Separate queues: `compile`, `run`, `heal`. |
| Browser automation | **Playwright (Python) + Chromium** | Best-in-class locators (role/text/test-id), auto-wait, tracing |
| AI | **Pluggable `LLMProvider` interface** with two implementations: Claude (official `anthropic` Python SDK) and Gemini (official Google Gen AI SDK). Selected with `LLM_PROVIDER`. | Free Gemini tier for development; paid provider for demos and real data. Lets us compare models with evals. See [ADR-0005](adr/0005-pluggable-llm-provider.md). |
| Default production model | **`claude-opus-5-5`** ($4 / $20 per 1M input/output tokens) | Best quality for understanding demonstrations and safe repair |
| Database | **PostgreSQL 16** | JSONB for specs, relational for everything else |
| Object storage | **Cloudflare R2** (S3-compatible) | Zero egress fees. Khurram already migrated PetX media to it. |
| Realtime | **WebSockets (FastAPI) + Redis pub/sub** | Live run view, approval prompts |
| Auth | **FastAPI-issued JWT (access + refresh) + Google OAuth; personal access tokens for the extension** | One auth system for web + extension. SSO via WorkOS later. |
| Secrets at rest | **Envelope encryption (AES-GCM data keys; master key from env/KMS)** | Credentials are never stored in plaintext |
| Spec validation | **JSON Schema (draft 2020-12)** → generated Pydantic + TS types | One schema, three consumers |
| Error tracking | **Sentry** (web, API, workers, extension) | Free tier is enough for the MVP |
| Logs / metrics | Structured JSON logs; OpenTelemetry later | |
| Packaging | **Docker + docker-compose**; `uv` for Python; `pnpm` workspaces for TS | |
| Hosting (MVP) | **Web + demo portal → Vercel (free `*.vercel.app` URLs); API + workers + Postgres + Redis → one VPS (Hetzner/DigitalOcean, 4 vCPU/8 GB) with HTTPS via an `sslip.io` hostname** | No domain purchase needed. Chromium needs a real VM, not serverless. A custom domain is a config change later. |
| CI | **GitHub Actions**: lint, type-check, unit tests, spec-schema tests, build images | |
| Tests | pytest, Vitest, Playwright Test (dashboard E2E) | |

## Claude API usage specifics
These apply when `LLM_PROVIDER=claude`. The Gemini implementation maps the same three calls onto its own structured-output and image APIs (see [06](06-ai-pipeline.md#llm-provider-abstraction)).

- **Model:** `claude-opus-5-5` for compile, SOP and repair. It's the default and current Opus. Switching some calls (e.g. SOP writing) to a cheaper model is an **owner decision**. See [16](16-open-questions.md).
- **Effort:** set `output_config.effort` explicitly. Opus 5.5's default is `medium`. Plan: `high` for compile/understand and repair, `medium` for SOP writing. Tune with evals.
- **Thinking:** adaptive (always on for Opus 5.5; don't send `disabled` or `budget_tokens`, both return 400).
- **Structured outputs:** `output_config.format` with our JSON Schema for the "understand" and "repair" calls, so we never parse free text.
- **Tool use:** no forced `tool_choice` (`any`/`tool` returns 400 on Opus 5.5). Use structured outputs instead.
- **Prompt caching:** the system prompt + output schema + few-shot examples are large and stable, so put them first and mark them with `cache_control`. The volatile recording goes last.
- **Refusal fallbacks:** enable server-side fallback (`fallbacks: "default"` with beta `server-side-fallback-2026-07-01`) and always check `stop_reason` before reading content.
- **Streaming:** use streaming + `get_final_message()` for compile calls (long input/output) to avoid HTTP timeouts.
- **Computer use (v0.3, not MVP):** for non-DOM UIs (canvas, remote desktops), use `computer_toolset_20260801` on Opus 5.5 as a last-resort executor.

## Versions policy
Pin exact versions in lockfiles (`uv.lock`, `pnpm-lock.yaml`). Renovate/Dependabot weekly. Don't adopt a release younger than 2 weeks.
