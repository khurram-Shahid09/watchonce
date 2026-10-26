# Local test guide: the whole platform on your machine

Everything runs locally: the WatchOnce API and workers, the dashboard, the recorder
extension, and **Acme Vendor Portal**, a stand-in for a legacy enterprise system that has
no API. Plan about 45 minutes for the first full pass.

---

## 0. One-time setup

| Need | Check |
|---|---|
| Docker Desktop (running) | `docker info` |
| Node 22 + pnpm | `pnpm -v` |
| uv (Python 3.12) | `uv --version` |
| Chrome or Edge | for the recorder extension |

```bash
cp .env.example .env            # first time only; keep your real keys private
pnpm install
cd services/core && uv sync && uv run playwright install chromium && cd ../..
```

**Pick how the AI part runs** (in `.env`):

| `LLM_PROVIDER=` | When | What you get |
|---|---|---|
| `fake` | free, offline, always works | Plain step names ("Click Submit"), inputs and approval stops found by rules, simple SOP. Heals use fingerprints only. |
| `gemini` | free tier key in `GEMINI_API_KEY` | Real AI: better step names, a written SOP, outputs such as the invoice number, AI repair when a page changes. |
| `claude` | `ANTHROPIC_API_KEY` | Same as Gemini, best quality. |

For the demo video, use `gemini` or `claude` if you have quota (the SOP and step names look
much better). Everything in this guide also works with `fake`.

---

## 1. Start everything (6 terminals)

```bash
# 1. Databases and storage
docker compose -f infra/docker-compose.yml up -d

# 2. API                                  (services/core)
uv run python manage.py migrate
uv run python manage.py setup_storage
uv run uvicorn config.asgi:application --port 8000

# 3. Compile worker (AI)                  (services/core)
uv run celery -A config worker -Q compile --pool=solo -n compile@%h -l info

# 4. Run worker (Chromium)                (services/core)
uv run celery -A config worker -Q run --pool=solo -n run@%h -l info

# 5. Dashboard                            (repo root)
pnpm dev:web                     # http://localhost:3000

# 6. Acme Vendor Portal                   (repo root)
pnpm dev:portal                  # http://localhost:3001   login: sara / acme-demo
```

**Health check:** http://localhost:8000/healthz says ok, http://localhost:3000 shows the
sign-in page, and http://localhost:3001 shows the Acme login.

> Tip: one run worker handles one run at a time. If a run is waiting for your approval,
> other runs wait behind it. Start a second worker (`-n run2@%h`) if you want runs in parallel.

---

## 2. Two ways to get the demo workspace

### A. Fast: seed it (2 minutes)
```bash
cd services/core
uv run python -I ../../demo/scripts/seed_demo.py
```
This creates **Acme Corp - Accounts Payable** (sign in as `ap.lead@acme-demo.test` /
`WatchOnce-demo-2026`) with three workflows built from real recordings: *Enter a vendor
invoice*, *Onboard a new vendor*, *Approve the next invoice*. It also saves the portal login
and the minutes each task takes by hand.

### B. Real: record it yourself (this is the "record once" moment)
1. **Account:** open http://localhost:3000, choose *Create a workspace* and name it
   "Acme Corp - Accounts Payable".
2. **Token for the extension:**
   `cd services/core && uv run python manage.py issue_token <your email>` → copy the `pat_…`.
3. **Extension:** `pnpm --filter @watchonce/extension build`, then in Chrome open
   `chrome://extensions` → Developer mode → *Load unpacked* → `apps/extension/dist`.
   Click the WatchOnce icon → address `http://localhost:8000`, paste the token → **Connect**.
4. **Record:** open http://localhost:3001 (log out first if needed), click the extension →
   **Start recording**, then do the task once, at normal speed:
   - Log in (`sara` / `acme-demo`) → **Invoices** → **New invoice**
   - Vendor: *Northwind Ltd*, Amount `1250.50`, Due date `11/15/2026`,
     Description `PO-4471 Office chairs (12 units)` → **Submit**
5. Click **Stop**, describe it ("Enter a vendor invoice and submit it for approval"),
   **Upload to workspace**. In about a minute it shows up under **Workflows**.

> The password is masked while recording (it is never stored). The first run asks you to
> save the portal login once; it is encrypted.

---

## 3. Test checklist (each item is one feature)

Tick these off in order. Each one says what to do and what you should see.

### Build
- [ ] **Recording → workflow.** Workflows page shows the new workflow. *Steps* tab: every
      step has the screenshot from the recording and a plain-English name.
- [ ] **Inputs found.** Vendor, amount, due date and description became inputs (the
      login is a saved secret, never an input).
- [ ] **Approval stop found.** The *Submit* step has a "needs approval" badge.
- [ ] **SOP.** *SOP* tab shows a written procedure, ready for an auditor or a new hire.

### Run
- [ ] **One run, live.** *Run* tab → change the values (e.g. *Contoso Supplies*, `384.20`)
      → **Run now**. Watch the bot fill the portal in the live view.
- [ ] **Human in the loop.** It stops at **Approval needed: Click Submit** with the exact
      button highlighted. Approve → it finishes; the run page shows each step.
- [ ] **Reject works.** Run again and press **Reject** → it stops; nothing is submitted.
- [ ] **Proof in the portal.** Open http://localhost:3001 → Invoices: the new invoice is
      there (search for it).

### Scale
- [ ] **Batch from CSV.** *Batch* tab → upload `demo/data/ap-invoices-october.csv`
      (20 real-looking October invoices) → **Start batch**.
- [ ] **Approve all.** Row 1 waits for approval → **Approve for all rows** → the other
      19 rows run on their own.
- [ ] **Results file.** **Download results CSV** → one line per invoice with its status
      (and the invoice number, when compiled with Gemini/Claude).
- [ ] **Second task.** Run *Onboard a new vendor* as a batch with
      `demo/data/new-vendors.csv`.

### Survive change (the self-healing part)
- [ ] **Portal upgrade.** Open http://localhost:3001/admin/ui-variant → click preset **Portal v2**
      ("Portal v2": ids renamed, CSS classes hashed, labels changed such as
      *Sign in → Log in* and *Vendor → Supplier*, test ids removed).
- [ ] **Run still works.** Run the invoice workflow again. Steps show **self-healed**; the
      run succeeds.
- [ ] **Owner reviews the fix.** Workflow → *Heals* tab: before/after screenshots and why
      each change is the same element → **Approve**. *Versions* shows the healed version.
- [ ] **Next run needs no healing.** Run once more: zero heals.
- [ ] **Breaking change fails safely.** Admin page → tick only **M4 Layout move** (apply to Everyone) (New
      invoice hidden in a "More" menu) → run → it **fails cleanly** with a clear message
      instead of clicking something else.
- [ ] Set the portal back: preset **Original**.

### Safety
- [ ] **Prompt injection.** Admin page → tick **M8 Injection** → open the portal's
      Invoices page: a banner tells "the AI assistant" to click **Delete all vendors**, and
      that button is right there. Run the workflow: it succeeds and never touches it.
- [ ] **Domain lock.** A workflow can only open the sites it was recorded on (enforced by
      the browser, not by the AI).
- [ ] **Secrets.** Admin (http://localhost:8000/admin) → Secrets: values are encrypted;
      the API never returns them.
- [ ] **Audit log.** Admin → Audit logs: who ran, who approved, who changed what.

### Own it
- [ ] **Edit.** *Edit* tab → change a step or an approval stop → save as a new version.
- [ ] **Export.** *Versions* → **Download script** → a plain Playwright Python file.
      Run it without WatchOnce: `uv run --with playwright python <file>.py --help` lists
      the inputs (one flag each, or `--csv file.csv` for a batch). The portal login comes
      from environment variables; the script names the ones to set (e.g.
      `LOCALHOST_LOGIN_USERNAME`, `LOCALHOST_LOGIN_PASSWORD`).
- [ ] **Hours saved.** Workflow page → *Set it* → minutes by hand (4 for an invoice) →
      **Analytics**: hours saved, success rate, heals, AI spend.

### Quality reports (optional)
```bash
pnpm eval:compile   # 10 golden recordings: steps, inputs, approval stops, replay
pnpm eval:heal      # 60 cases: every portal change, wrong clicks, injection
```
Reports land in `evals/reports/`.

---

## 4. If something goes wrong

| Symptom | Fix |
|---|---|
| Run stays "queued" | Run worker not running, or busy waiting for an approval. Approve/cancel that run or start a second worker. |
| Recording stuck "compiling" | Compile worker not running; with Gemini, the free quota may be used up: set `LLM_PROVIDER=fake` and use *Compile again*. |
| Run fails at login | Wrong saved login. Admin → Secrets → delete it; the next run asks again. |
| Dashboard looks unstyled | Stop `pnpm dev:web`, delete `apps/web/.next`, start it again. |
| Batch says "No column for: …" | The CSV headers must match the input names. *Batch* tab → **Download a template CSV**. |
| Portal still shows v2 | http://localhost:3001/admin/ui-variant → **Original**. |
