# 03 · System Architecture

## High-level view

```mermaid
flowchart LR
  subgraph Browser["User's browser"]
    EXT["Recorder extension<br/>(Chrome MV3)"]
    WEB["Dashboard<br/>(Next.js)"]
  end

  subgraph Backend["Backend (Docker)"]
    API["API<br/>(Django + DRF + Channels)"]
    Q[("Redis<br/>queue + pub/sub")]
    COMP["Compiler worker<br/>(Celery)"]
    RUN["Runner worker<br/>(Celery + Playwright)"]
    DB[("PostgreSQL")]
  end

  OBJ[("Object storage<br/>Cloudflare R2")]
  LLM["LLM provider<br/>(Claude / Gemini)"]
  TARGET["Target web app<br/>(e.g. Acme Portal)"]

  EXT -- "upload recording" --> API
  WEB -- "REST + WebSocket" --> API
  API --> DB
  API -- "presigned URLs" --> OBJ
  API -- "enqueue" --> Q
  Q --> COMP
  Q --> RUN
  COMP -- "understand + SOP" --> LLM
  RUN -- "repair only" --> LLM
  COMP --> DB
  COMP --> OBJ
  RUN --> DB
  RUN --> OBJ
  RUN -- "headless Chromium" --> TARGET
  RUN -- "live frames" --> Q
  Q -- "pub/sub → WS" --> API
```

## Components

| Component | Responsibility | Scaling unit |
|---|---|---|
| **Recorder extension** | Capture events + screenshots, mask secrets, upload | Per user |
| **Dashboard (web)** | Review/edit workflows, run, live view, approvals, analytics | Stateless, CDN |
| **API** | Auth, CRUD, presigned uploads, enqueue jobs, WebSocket fan-out, audit log | Stateless replicas |
| **Compiler worker** | Normalize events → Claude → spec + SOP → validate | Horizontal, CPU-light |
| **Runner worker** | Execute spec in isolated Chromium; checkpoints; self-heal; stream frames | Horizontal, **1 browser per concurrent run** |
| **PostgreSQL** | System of record (tenants, workflows, versions, runs, audit) | Managed DB |
| **Redis** | Celery broker, run-control signals (approve/cancel), live-frame pub/sub | Single instance (MVP) |
| **R2** | Screenshots, raw recordings, SOP PDFs, run artifacts | Managed |
| **LLM provider** (Claude / Gemini) | Compile (vision + structured output) and repair | External |

## Core flows

### 1. Record → compile

```mermaid
sequenceDiagram
  participant U as User
  participant X as Extension
  participant A as API
  participant S as R2
  participant C as Compiler
  participant L as Claude
  U->>X: Start recording, do task, Stop + description
  X->>A: POST /recordings (metadata)
  A-->>X: recording_id + presigned upload URLs
  X->>S: PUT events.json, frames/*.webp
  X->>A: POST /recordings/{id}/complete
  A->>C: enqueue compile(recording_id)
  C->>S: fetch events + frames
  C->>C: normalize (deterministic)
  C->>L: understand(steps, key frames, description) → structured JSON
  C->>C: build locators, validate spec (JSON Schema)
  C->>L: write SOP (Markdown)
  C->>A: workflow v1 + SOP saved; status=ready
  A-->>U: dashboard shows workflow (WS event)
```

### 2. Run with checkpoint and heal

```mermaid
sequenceDiagram
  participant U as User
  participant A as API
  participant R as Runner
  participant T as Target app
  participant L as Claude
  U->>A: POST /workflows/{id}/runs (inputs)
  A->>R: enqueue run
  loop each step
    R->>T: locate + act (primary locator)
    alt locator fails
      R->>R: try fallback locators / fingerprint match
      alt still failing
        R->>L: repair(intent, pruned DOM, screenshot)
        L-->>R: candidate locator (from provided candidates)
        R->>R: verify (unique, visible, fingerprint similarity)
        R->>A: heal_event (pending approval)
      end
    end
    opt step.checkpoint
      R->>A: run.status = awaiting_approval (+ screenshot)
      U->>A: approve
      A->>R: signal continue (Redis)
    end
    R-->>A: frame + step status (pub/sub → WS)
  end
  R->>A: run finished (outputs, artifacts)
```

## Key design principles

1. **The spec is the source of truth.** Code (Playwright export) and the SOP are generated *from* it. See [ADR-0002](adr/0002-workflow-spec-as-source-of-truth.md).
2. **AI at authoring and repair time, never in the normal run path.** See [ADR-0003](adr/0003-deterministic-runtime-ai-only-for-compile-and-heal.md).
3. **Record structured DOM events + screenshots, not just video.** See [ADR-0001](adr/0001-record-dom-events-plus-screenshots.md).
4. **Untrusted page content.** Text from the target app is data, never instructions to the AI (prompt-injection defense). See [11](11-security-privacy.md).
5. **Isolation per run.** A fresh browser context per run. No cookies are shared across workflows or tenants.
6. **Everything is versioned and audited.**

## Repository layout

```
watchonce/
├─ apps/
│  ├─ web/                    # Next.js (App Router) + TS + Tailwind + shadcn/ui
│  │  ├─ app/(auth)/ app/(dashboard)/workflows/[id]/ runs/[id]/ ...
│  │  └─ lib/api-client.ts    # generated from OpenAPI
│  └─ extension/              # Chrome MV3 + TS + Vite
│     ├─ src/background.ts    # service worker: session, screenshots, upload
│     ├─ src/content.ts       # event capture + element descriptors
│     └─ src/popup/           # start/stop UI
├─ services/core/             # Python 3.12, uv-managed Django project
│  ├─ manage.py
│  ├─ config/                 # settings/ (base, dev, prod), urls.py, asgi.py (Channels), celery.py
│  ├─ accounts/               # Django app: users, orgs, memberships, API tokens, auth views
│  ├─ recordings/             # Django app: recordings, presigned uploads
│  ├─ workflows/              # Django app: workflows, versions, secret bindings, exports
│  ├─ runs/                   # Django app: runs, batches, steps, checkpoints, consumers.py (WebSockets)
│  ├─ heals/                  # Django app: heal events + decisions
│  ├─ vault/                  # Django app: encrypted secrets
│  ├─ audit/                  # Django app: append-only audit log
│  └─ engine/                 # framework-agnostic core used by Celery tasks
│     ├─ compiler/            # normalize.py, understand.py, locators.py, sop.py
│     ├─ runner/              # executor.py, healer.py, checkpoints.py, live.py
│     └─ llm/                 # LLMProvider interface, Claude + Gemini providers, prompts/, schemas/
├─ packages/spec/
│  ├─ workflow.schema.json    # single source; TS types + Pydantic models generated
│  └─ examples/
├─ demo/acme-portal/          # mock legacy portal with a UI-mutation toggle
├─ evals/                     # golden recordings, heal mutation suite, runner scripts
├─ infra/                     # docker-compose.yml, Dockerfiles, Caddyfile
└─ docs/
```
