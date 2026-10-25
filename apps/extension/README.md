# WatchOnce Recorder (Chrome extension, MV3)

Records a task demonstration: user actions with rich element descriptors, plus a screenshot before each action. Design: [docs/07-recorder-extension.md](../../docs/07-recorder-extension.md).

## Build and load

```bash
pnpm --filter @watchonce/extension build      # → apps/extension/dist
```

Chrome → `chrome://extensions` → turn on **Developer mode** → **Load unpacked** → pick `apps/extension/dist`. After a rebuild, press the reload icon on the extension card.

## Use

1. Open the web app (e.g. the Acme portal on http://localhost:3001).
2. Click the WatchOnce icon → **Start recording**. Chrome asks for access to that one site.
3. Do the task. A "Recording…" pill shows in the corner (Pause / Stop).
4. **Stop** → describe the task → **Upload to workspace** (or **Download** the JSON).

To upload, connect once: open **Connect your WatchOnce workspace** at the bottom of the popup, enter the
WatchOnce address (locally `http://localhost:8000`) and a personal access token (`pat_…`, from
`uv run python manage.py issue_token <email>` in services/core until the dashboard's token page lands). The upload continues if you close the popup.

Shortcut: `Alt+Shift+R` (stops a running recording; otherwise opens the popup).

## What is never captured

- Password, one-time-code and card fields: the value becomes `__SECRET__`.
- Card numbers (Luhn), CNIC, SSN and SIN typed anywhere, even inside free text: just that part is replaced.
- In screenshots, those fields are blurred and the recording pill is hidden.

## Tests

```bash
pnpm --filter @watchonce/extension test        # unit tests (descriptor, masking, upload) under jsdom

# End-to-end: records the "create invoice" task on the Acme portal in real Chromium
pnpm dev:portal                                # in another terminal
pnpm --filter @watchonce/extension build:e2e   # test build (pre-grants site access); never ship it
cd services/core && uv run --with playwright python -I ../../apps/extension/e2e/record_acme.py
# also upload and check normalization (needs the API, SeaweedFS and a compile worker):
WATCHONCE_PAT=pat_... uv run --with playwright python -I ../../apps/extension/e2e/record_acme.py
pnpm --filter @watchonce/extension build       # restore the normal build afterwards
```

## Debugging

The worker keeps the last 50 diagnostic lines (screenshot outcomes, dropped events) in memory. In `chrome://extensions` → WatchOnce → **service worker** → console:

```js
(await chrome.storage.session.get("diag")).diag
```
