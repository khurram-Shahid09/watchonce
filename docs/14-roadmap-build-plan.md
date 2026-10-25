# 14 · Roadmap & Build Plan

## Phases

| Phase | Goal | Duration (est.) | Exit criteria |
|---|---|---|---|
| **MVP (v0.1)** | Record → compile → run → checkpoint → self-heal, deployed | **~3 weeks** (15 working days) | Demo video + live demo link. Evals E1/E2 at targets. |
| **v0.2** | Daily-use features | 2–3 weeks | Scheduling, notifications (Slack/email), multi-tab, file upload/download, screenshot redaction, parallel batch runs |
| **v0.3** | Harder UIs & richer workflows | 3–4 weeks | Computer-use fallback (`computer_toolset_20260801`) for canvas/non-DOM UIs, voice narration, conditional steps, loops over table rows |
| **Pilot** | 1–3 real teams | 4–6 weeks | ≥ 1 workflow running weekly in a real company, measured hours saved |
| **Production / Enterprise** | Sellable to enterprise | ongoing | SSO/SCIM, RBAC, on-prem/VPC runner, Canadian/EU data residency, SOC 2 readiness, usage billing |

## MVP day-by-day plan

A **demo-able cut lands at day 10**. Days 11–15 harden it to "production-shaped".

### Week 1: foundations + recording + compile
| Day | Deliverable |
|---|---|
| **D1** | Monorepo scaffold (pnpm + uv), docker-compose (Postgres, Redis, SeaweedFS S3), Django project + DRF + Channels skeleton, settings split, Django admin, Next.js shell, CI (lint/type/test). `packages/spec` JSON Schema v1 + examples + generated types. |
| **D2** | **Acme Vendor Portal** demo app (login, vendors, invoices list/form, custom dropdown, confirmation, invoice number) + UI-mutation toggle M1–M8 |
| **D3** | Auth (register/login/refresh, PATs), orgs/memberships, audit log helper, tenant scoping + tests |
| **D4** | Chrome extension: content script descriptors, masking, screenshots, IndexedDB buffer, popup Start/Stop/description |
| **D5** | Recording upload (presigned R2 URLs) + `complete` → enqueue. **Normalizer** + locator generator with unit tests. |

### Week 2: AI + runner + dashboard
| Day | Deliverable |
|---|---|
| **D6** | Claude client wrapper (structured outputs, caching, fallbacks, stop_reason, cost logging). **Understand** prompt + schema. Spec assembly + validation + retry. |
| **D7** | SOP generation + dashboard workflow page (steps with screenshots, SOP tab, inputs editor, save new version) |
| **D8** | **Runner**: executor for all MVP actions, domain allowlist, run states, run_steps, artifacts. Run-once form in dashboard. |
| **D9** | Live view (Redis pub/sub → WebSocket → dashboard) + **checkpoints** (pause/approve/reject) |
| **D10** | **Self-healing** L1/L2/L3 + verification + heal events + pending version + approve UI. ✅ **Demo-able cut**: record a first demo video draft. |

### Week 3: batch, evals, hardening, launch
| Day | Deliverable |
|---|---|
| **D11** | CSV batch runs + results CSV + approve-all. Playwright export. |
| **D12** | Golden recordings (12) + eval harness E1, first report. Prompt tuning. |
| **D13** | Mutation suite eval E2 + injection test. Tune fingerprint weights. Fix wrong-element heals. |
| **D14** | Secrets encryption, analytics page (hours saved), Sentry, rate limits, security checklist items |
| **D15** | Deploy to VPS + Vercel, smoke tests, final **2-minute demo video**, README with GIFs, LinkedIn post |

## Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Custom dropdowns/date pickers in real apps are hard to replay | High | Handle the common patterns (click-to-open + option click). Record these as two steps. Warn on unknown widgets. |
| Compile quality varies on long recordings | Medium | Chunking + running summary. Cap MVP recordings at 60 actions. |
| Chrome screenshot rate limits drop frames | Medium | Capture queue + skip-if-no-mutation. Frames are helpful but not required (DOM descriptors carry the semantics). |
| Scope creep (multi-tab, uploads, branching) | High | Strict out-of-scope list in [02](02-prd-mvp.md). Log ideas to the v0.2 backlog. |
| LLM cost surprises | Low | Per-org budget cap, cost logging per call, evals report cost |
| Target sites with bot detection | Medium | Out of scope. Focus on internal/enterprise apps where the customer controls the app. |

## Definition of done (MVP)
- [ ] All P0 user stories in [02](02-prd-mvp.md) pass acceptance criteria
- [ ] E1 replay success ≥ 90%, checkpoint recall 100%
- [ ] E2 heal success ≥ 80%, 0 wrong-element heals, 0 injection picks
- [ ] Security checklist ([11](11-security-privacy.md)) complete
- [ ] Deployed with HTTPS, Sentry, backups
- [ ] Demo video + README + architecture diagram published
