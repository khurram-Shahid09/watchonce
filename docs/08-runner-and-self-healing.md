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

## Live view
- After each action (and every 1 s while waiting), a JPEG frame (quality 50, 960 px) goes to Redis pub/sub channel `run:{id}:frames`
- API WebSocket `/ws/runs/{id}` relays frames + step events to authorized viewers
- The dashboard shows the frame, highlights the current step in the step list, and shows heal/checkpoint banners

## Playwright export
`GET /workflows/{id}/versions/{v}/export/playwright` → a standalone Python script generated from the spec with a Jinja template:
- Inputs as CLI args / CSV, secrets from env vars
- Each step uses the primary locator with fallbacks via a tiny helper (`first_working(page, [...])`)
- Checkpoints become `input("Approve step s10? [y/N]")`
- No self-healing in the export (that's the platform's value), clearly commented
