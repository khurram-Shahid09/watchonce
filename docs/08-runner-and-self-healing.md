# 08 · Runner & Self-Healing

## Runner overview

The runner is a Celery worker (queue `run`) that executes one workflow version with given inputs inside an **isolated Playwright browser context**.

```
load spec (pinned version) → validate → resolve inputs/secrets → new browser context
  → for each step: locate → (heal?) → checkpoint? → act → post-condition → stream frame
  → collect outputs → save artifacts → close context
```

### Isolation
- One Chromium **browser** per worker process, a **fresh context per run** (no shared cookies/storage)
- Request interception: block any navigation or XHR to hosts not in `allowed_domains` (plus their CDN subdomains declared in settings)
- Downloads disabled in MVP. Geolocation/notifications/camera permissions denied.
- Hard limits per run: max duration (default 10 min), max steps executed (spec length × 2)

### Step execution
1. **Locate** the target: try `locators[]` in order. Each must resolve to **exactly one visible, enabled** element within `timeout_ms`.
2. **Act** with Playwright's actionability checks (auto-wait for visible/stable/enabled).
3. **Post-condition**: if the step has `assert_after`, check it. Otherwise wait for network idle (short cap, 2 s) or DOM stability.
4. **Record**: step status, timings, locator used, screenshot (after action) → DB + R2, frame to live view.

### Run states
`queued → running → awaiting_approval → running → succeeded | failed | rejected | cancelled | timed_out`

### Checkpoints
- At a checkpoint step, the runner locates the target first (so the screenshot shows exactly what will be clicked, with a highlight box), then sets `awaiting_approval` and **blocks on a Redis key** `run:{id}:decision` (BLPOP with timeout, default 30 min → `timed_out`)
- API writes `approve`/`reject` after an authorized user decides, and logs it to the audit log
- Batch (CSV) runs: option to **approve once for the whole batch** after reviewing the first row's checkpoint screenshot (owner-only, audit-logged)

### Batch runs
- One parent `batch` record + N child runs, executed sequentially per batch in MVP (configurable concurrency later)
- A failed row doesn't stop the batch (configurable "stop on first failure")
- Results CSV = input columns + `status`, `error`, all outputs, `run_id`

### Implementation notes (MVP)
- Code: `engine/runner/` (`executor.py`, `locate.py`, `browser.py`, `tasks.py`), `runs/` (models, API, `live.py` Redis glue), `secrets_vault/` (encrypted logins).
- **Run workers listen on the `run` queue only** (`celery -A config worker -Q run`), so a run waiting at a checkpoint never blocks compiles. Run tasks are acknowledged on receipt and never retried: a run that died may already have submitted something.
- **Locating**: each locator counts only if exactly one *visible* element matches; locators are tried in order, repeatedly, until the step timeout. `rung` is `L0` (primary) or `L1` (a fallback). Custom dropdowns: open the combobox, then click the option by its accessible name (`option`, `menuitem`, then exact text).
- **Domain allowlist** on every request via Playwright routing (`allowed_domains` + `RUNNER_EXTRA_ALLOWED_HOSTS`); a blocked navigation fails the step with `domain_blocked`, blocked sub-resources are just dropped.
- **Checkpoints**: the target is located first and outlined, the screenshot is taken, the run goes `awaiting_approval`, and the worker `BLPOP`s `run:{id}:decision` (`RUN_CHECKPOINT_TIMEOUT_S`, 30 min → `timed_out`). Waiting time doesn't count toward `RUN_MAX_SECONDS`. Cancel sets `run:{id}:cancel` and also wakes a waiting runner.
- **Secrets** are decrypted in the worker only, typed into the page, and scrubbed (`•••`) from every error message and event.
- **Artifacts**: one JPEG after every step under `org/{org}/runs/{run}/`, plus the approval screenshot (kept on the checkpoint decision). Each screenshot is also published as a live frame.
- Playwright's sync API runs an event loop in the worker thread, so the runner process sets `DJANGO_ALLOW_ASYNC_UNSAFE` (it's genuinely synchronous) and closes its DB connections after each run.

## Self-healing ladder

When locating fails, the runner climbs the ladder. It stops at the first rung that succeeds.

| Rung | Method | Cost | Needs approval? |
|---|---|---|---|
| **L0** | Primary locator | free | – |
| **L1** | Fallback locators (rest of `locators[]`) | free | No (logged as "fallback used") |
| **L2** | **Fingerprint match**: score every interactive element on the page against the stored fingerprint | free | Yes if score < 0.9 or checkpoint step |
| **L3** | **AI repair**: Claude picks from top-40 candidates using intent + screenshot + anchor image | ~$0.05 | Per heal policy (always on checkpoint steps) |
| **L4** | Fail the step: screenshot + DOM snapshot saved, user notified, run → `failed` | – | – |

### L2 fingerprint scoring
Weighted similarity (weights tuned with the eval suite):

| Signal | Weight |
|---|---|
| Role equal | 0.20 |
| Accessible name similarity (normalized Levenshtein / token overlap) | 0.25 |
| Text similarity | 0.15 |
| Stable attributes overlap (`name`, `type`, `data-*`, non-generated id) | 0.15 |
| Nearby text overlap (labels, headings within 200 px) | 0.15 |
| Position proximity (normalized bbox distance) | 0.10 |

Accept if top score ≥ 0.75 **and** (top − second) ≥ 0.1 (an unambiguous winner).

### L3 verification (before using an AI pick)
1. Candidate resolves to exactly one element, visible and enabled
2. Role is compatible with the action (e.g. `fill` → textbox/combobox)
3. Fingerprint score ≥ 0.4 (sanity floor: blocks a "completely different" element)
4. Model `confidence` ≥ 0.6
5. If fails → L4

### Persisting a heal
- New locators are generated for the healed element (same algorithm as compile) and **prepended** to the step's `locators[]`. Old locators are kept as fallbacks.
- A `heal_event` is stored (step id, rung, before/after locators, screenshots, scores, model explanation, cost)
- A new workflow version is created with status `pending_heal`:
  - `heal_policy: approve` → owner approves in the dashboard → becomes `active`
  - `heal_policy: auto` → auto-activates if confidence ≥ threshold **and** the step isn't a checkpoint
- The **current run continues** with the healed locator, except on checkpoint steps, where the approval screen shows the heal explanation clearly.

### Self-healing implementation notes (MVP)
- **Page agent**: `engine/runner/static/page-agent.js` is built from the recorder's own descriptor code (`apps/extension/src/runner/page-agent.ts`, `pnpm --filter @watchonce/extension build`), so candidates on the live page are described exactly like recorded elements and healed locators are built by the same `build_locators` as compile.
- **Fallbacks are verified**: a `text`, `css` or `xpath` fallback (not the primary locator) is only used if the element it found has the recorded role and scores ≥ 0.5 against the fingerprint. Otherwise the step goes to L2/L3. Found in testing: a text fallback "Sign in" matched the page heading, and a positional fallback matched an injected "Delete all records" button.
- **Scoring**: empty text on both sides counts as a match (input fields); attribute and nearby-text overlap are measured against the smaller set, so stripped test ids or a removed heading don't count against a match twice.
- **A heal only counts if the step then works**: if a healed step's post-condition fails, the heal is marked `rejected` and is not saved.
- **One pending version per run** holds all its heals (new locators first, old kept as fallbacks); the dashboard's Heals tab decides them together.
- With `LLM_PROVIDER=fake`, L3 is a deterministic "closest match ≥ 0.5" rule, still subject to every L3 check.
- Tested on "Portal v2" (M1+M2+M3+M6+M7): 6 steps healed in one run; after approval the next run needed none (`apps/web/e2e/heal_workflow.py`).

## Live view
- After each step a JPEG frame goes to Redis pub/sub channel `run:{id}:events` with the step events (`step`, `checkpoint`, `approved`, `frame`, `done`); the latest frame is also kept in `run:{id}:frame` for late viewers
- `GET /runs/{id}/events` (Server-Sent Events) sends a snapshot, the latest frame, then live events; the dashboard relays it (decision D11)
- The dashboard shows the frame, highlights the current step in the step list, and shows heal/checkpoint banners

## Playwright export
`GET /workflows/{id}/versions/{v}/export/playwright` → a standalone Python script generated from the spec with a Jinja template:
- Inputs as CLI args / CSV, secrets from env vars
- Each step uses the primary locator with fallbacks via a tiny helper (`first_working(page, [...])`)
- Checkpoints become `input("Approve step s10? [y/N]")`
- No self-healing in the export (that's the platform's value), clearly commented
