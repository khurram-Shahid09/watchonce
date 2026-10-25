# 02 · MVP Product Requirements (PRD)

## Goal

Ship a working, production-shaped MVP that a person can use end to end on a real web app:
**record → review SOP & workflow → run (single / CSV) with live view → approve checkpoint → see self-healing after a UI change.**

"Production-shaped" means real auth, multi-tenant data model, encrypted secrets, audit log, containerized deploy, error tracking and tests. It doesn't mean every enterprise feature.

## In scope (MVP)

### A. Recording
- **R1** Chrome extension with Start / Stop / Pause, signed in to the user's workspace.
- **R2** Captures, per user action: action type, target element descriptor (tag, role, accessible name, text, id, `data-*` test attributes, CSS path, bounding box), URL, timestamp, and a screenshot.
- **R3** Password fields are **never** captured in plain text. The value is replaced with a `{{secret}}` placeholder.
- **R4** At stop, the user writes a 1–2 sentence description of the task ("Create a vendor invoice from an email").
- **R5** Upload to backend, with progress indicator and retry if offline.

### B. Compilation (AI)
- **C1** Clean up the noise: merge keystrokes, drop stray scrolls/mouse moves, collapse double clicks.
- **C2** Claude produces: step intents, **detected inputs** (variables) with names/types/examples, constants, **checkpoint steps** (submit/delete/pay), suggested assertions, and output extractions.
- **C3** Generates a **workflow spec** (validated against JSON Schema, see [05](05-workflow-spec.md)).
- **C4** Generates an **SOP** (Markdown + screenshots) viewable in the dashboard and exportable as PDF.
- **C5** Compile status visible in the UI (queued → processing → ready / failed with reason).

### C. Review & edit
- **E1** Dashboard shows the steps side by side with their screenshots.
- **E2** User can rename/retype inputs, toggle a step as checkpoint, delete a step, edit a literal value.
- **E3** Every save creates a new **workflow version** (immutable history).
- **E4** "Export as Playwright script" (Python). It's generated deterministically from the spec.

### D. Running
- **X1** Run once with an input form auto-generated from the workflow inputs.
- **X2** Run in batch from a CSV upload (column → input mapping, preview first 5 rows).
- **X3** **Live view**: streamed screenshots + current step highlighted (WebSocket).
- **X4** Checkpoint steps pause the run and request approval in the dashboard (Approve / Reject), with a screenshot of the exact page state.
- **X5** Run results: status per step, extracted outputs (e.g. invoice number), duration, final screenshot; CSV batch results downloadable.
- **X6** Credentials: store a named secret (username/password) per workflow. It's injected at runtime and never shown again.
- **X7** Domain allowlist: runner refuses navigation outside the workflow's recorded domains.

### E. Self-healing
- **H1** Each step stores multiple locator strategies. If the primary fails, the runner tries the fallbacks.
- **H2** If all fail, the AI repair is called with step intent + current DOM snapshot + screenshot and proposes a new locator. It's verified before use.
- **H3** Every repair is logged as a **heal event** (before/after locator, screenshots, confidence).
- **H4** Repairs create a **pending workflow version**. The owner approves it so future runs use it. Optional per-workflow setting: auto-approve repairs above a confidence threshold.

### F. Platform
- **P1** Email/password auth + Google sign-in. Workspaces (org) with Owner and Member roles.
- **P2** Audit log of key actions (recording uploaded, workflow edited, run started, checkpoint approved, heal approved, secret created).
- **P3** Usage dashboard: runs, success rate, estimated hours saved (manual duration × successful runs).
- **P4** Demo target app ("Acme Vendor Portal") with a **"UI change" toggle** that renames IDs, moves buttons and changes labels, to demonstrate healing.

## Out of scope (MVP), planned later
- Desktop apps, Citrix/RDP, PDFs-in-browser canvas interaction → **v0.3 via computer-use fallback**
- Scheduling (cron) and Slack/Teams/email notifications → **v0.2**
- Voice narration during recording → **v0.3**
- Branching logic (if/else), loops inside a workflow → **v0.3** (CSV batch covers the common "loop" case)
- SSO (SAML/OIDC), fine-grained RBAC, on-prem runner → **production phase**
- Multi-tab and popup-window flows, file downloads/uploads → **v0.2**

## Explicit non-goals (never)
- Bypassing CAPTCHAs, bot detection, or any site's terms of service
- Automating MFA by defeating it. (A supported path later is a customer-provided TOTP secret or a human-in-the-loop code prompt.)
- Scraping sites the customer doesn't have rights to use

## User stories & acceptance criteria

| ID | Story | Acceptance criteria |
|---|---|---|
| US-1 | As Sara, I record creating an invoice in the Acme portal. | Recording of ~15 actions uploads in < 10 s on normal broadband. Password never appears in stored data (verified by test). |
| US-2 | As Sara, I get an SOP and workflow from my recording. | Compile completes in < 90 s for ≤ 50 actions. ≥ 90% of steps have correct intents on the golden set. Inputs detected for every value that differs across golden examples. |
| US-3 | As Sara, I run it for 50 invoices from a CSV. | Batch runs sequentially with per-row status. Failed rows don't stop the batch. Results CSV includes extracted invoice numbers. |
| US-4 | As Imran, I approve the "Submit" step before money moves. | The run pauses at the checkpoint and shows a screenshot. Reject ends the run as `rejected`. All approvals are audit-logged with user + timestamp. |
| US-5 | As Imran, the portal changed and the automation fixed itself. | After the UI-change toggle, ≥ 80% of the eval mutations are healed. A heal event shows before/after. The new version is pending until approved. |
| US-6 | As a Manager, I see hours saved. | The dashboard shows runs, success rate and hours saved for the last 7/30 days. |

## Success metrics (MVP)
- Golden-set replay success after compile: **≥ 90%**
- Heal success on the UI-mutation suite: **≥ 80%**, with **0 wrong-element heals** on checkpoint steps
- Median compile cost **≤ $0.30**, median heal cost **≤ $0.08**
- Time from "start recording" to "first successful run": **< 10 minutes**
