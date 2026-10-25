# 13 · Deployment & Operations

## Environments

| Env | Purpose | Where |
|---|---|---|
| `local` | Development | `docker compose up` (Postgres, Redis, API, workers, acme-portal, SeaweedFS as local S3/R2) + `pnpm dev` for web/extension |
| `staging` | Demo + evals | VPS #1 (same as prod in MVP, separate compose project + DB) |
| `prod` | Pilot customers / public demo | VPS + Vercel |

## MVP production topology

```
Vercel ─────────────── apps/web (Next.js)          https://watchonce.vercel.app
VPS (4 vCPU / 8 GB, Ubuntu 24.04)
  Caddy (TLS via Let's Encrypt, reverse proxy)       https://api.<vps-ip-dashed>.sslip.io
  ├─ api        (Django on uvicorn ASGI: DRF + Channels, 2 workers)
  ├─ worker-compile (celery -Q compile, concurrency 4)
  ├─ worker-run     (celery -Q run,heal, concurrency 2, Playwright image)
  ├─ postgres 16 (volume + nightly pg_dump → R2)
  └─ redis 7 (AOF on)
Cloudflare R2 ──────── recordings, frames, artifacts, backups
Demo portal ────────── Vercel                         https://watchonce-acme.vercel.app
```

**No domain is purchased for the MVP.** `sslip.io` resolves `api.203-0-113-10.sslip.io` to `203.0.113.10`, so Caddy can obtain a real HTTPS certificate for the VPS without owning a domain. Exact Vercel project names depend on availability at creation time. Moving to a custom domain later means changing `APP_BASE_URL`, `API_BASE_URL`, `CORS_ORIGINS`, the Caddyfile host and the extension's API URL. No code changes.

**Demo portal hosting:** the "Portal v2" switch is held in the portal's server memory (see [demo/acme-portal](../demo/acme-portal/README.md)). On Vercel, serverless instances don't share memory, so the switch may not reach the runner reliably. If that shows up in testing, run the portal as one more small container on the VPS instead (open question D10 in [16](16-open-questions.md)).

Runner concurrency rule of thumb: ~1 GB RAM per concurrent Chromium context under load. Scale `worker-run` horizontally to more VPS nodes later (they only need Redis + DB + R2 access).

## Containers
- `services/core` image (python:3.12-slim) used for `api` and `worker-compile`
- `worker-run` image based on the official Playwright Python image (browsers preinstalled), non-root user, `--init`, shared memory `shm_size: 1gb`

## Environment variables

```dotenv
# core
APP_ENV=production
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_SECRET_KEY=***         # 50+ random chars; also signs JWTs (simplejwt)
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=api.<vps-ip-dashed>.sslip.io
APP_BASE_URL=https://watchonce.vercel.app
API_BASE_URL=https://api.<vps-ip-dashed>.sslip.io
DATABASE_URL=postgres://watchonce:***@postgres:5432/watchonce
REDIS_URL=redis://redis:6379/0
SECRETS_MASTER_KEY=***        # base64 32 bytes; move to KMS later
CORS_ORIGINS=https://watchonce.vercel.app

# storage (R2)
S3_ENDPOINT=https://<account>.r2.cloudflarestorage.com
S3_BUCKET=watchonce-prod
S3_ACCESS_KEY_ID=***
S3_SECRET_ACCESS_KEY=***

# AI
LLM_PROVIDER=claude           # claude | gemini (gemini free tier: local dev with demo data only)
# LLM_PROVIDER_REPAIR=        # optional per-stage override
ANTHROPIC_API_KEY=***
CLAUDE_MODEL=claude-opus-5-5
GEMINI_API_KEY=***
GEMINI_MODEL=                 # set to the current Gemini vision model when implementing
CLAUDE_EFFORT_UNDERSTAND=high
CLAUDE_EFFORT_SOP=medium
CLAUDE_EFFORT_REPAIR=high
LLM_MONTHLY_BUDGET_USD=50     # hard stop for AI calls per org/plan

# auth
GOOGLE_CLIENT_ID=***
GOOGLE_CLIENT_SECRET=***

# observability
SENTRY_DSN_API=***
SENTRY_DSN_WEB=***
```

All secrets in a `.env` on the server with `chmod 600`, never committed. `gitleaks` in CI.

## Deploy process (MVP)
1. PR → CI green → merge to `main`
2. GitHub Actions builds and pushes images to GHCR (tag = git SHA)
3. Action SSHes to the VPS: `docker compose pull && docker compose up -d` + `python manage.py migrate` (migrations are backward-compatible; expand → migrate → contract)
4. Vercel deploys web automatically from `main`
5. Smoke test job: health endpoints + one canary run against the demo portal

Rollback: `docker compose` with the previous SHA tag. DB migrations are designed to be forward-compatible for one release.

## Monitoring & alerting

| Signal | Tool | Alert |
|---|---|---|
| Exceptions | Sentry | New issue → email |
| API health | `/healthz`, `/readyz` + UptimeRobot | Down > 2 min |
| Queue depth | Celery/Redis metrics → simple `/metrics` endpoint | `run` queue > 50 for 10 min |
| Run failure rate | Daily SQL report | > 20% failures/day on any workflow |
| LLM spend | `llm_calls` table | Org > 80% of monthly budget |
| Disk | node exporter / VPS panel | > 80% |

## Backups & DR
- Postgres: nightly `pg_dump` → R2 (30-day retention). Weekly restore test into staging.
- R2: versioning on. Lifecycle rules for retention.
- RPO 24 h / RTO 4 h for the MVP (documented honestly to pilots)

## Runbooks (to write as incidents occur)
- Runner stuck / Chromium zombie processes → restart worker, check `shm_size`
- Claude API errors spike → check status page. Heals degrade to L2-only automatically after 5 consecutive API failures.
- A customer's target site blocks the runner → document the IP of the VPS for their allowlist
