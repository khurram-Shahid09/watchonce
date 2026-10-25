# 07 · Recorder Extension (Chrome MV3)

## Responsibilities
1. Authenticate to the user's workspace (personal access token from the dashboard, stored in `chrome.storage.local`)
2. Capture user actions with rich element descriptors
3. Capture a screenshot before each action
4. Mask sensitive values
5. Upload the recording reliably

## Architecture

| Part | File | Job |
|---|---|---|
| Popup | `src/popup/` | Sign-in status, Start/Pause/Stop, task description form, upload progress |
| Service worker | `src/background.ts` | Recording session state, `chrome.tabs.captureVisibleTab` screenshots, buffering, upload with retry |
| Content script | `src/content.ts` | DOM event listeners (capture phase), element descriptor builder, masking, DOM snapshot on demand |

Permissions: `activeTab`, `scripting`, `storage`, `tabs`; `host_permissions` requested **at recording time for the current site only** (optional permissions). This is least privilege, and enterprise IT reviewers will check it.

- The site permission lets the worker register the content script for that origin (`scripting.registerContentScripts`), so it follows the user across pages of the site.
- Screenshots (`tabs.captureVisibleTab`) need **activeTab**, which Chrome grants when the user clicks the extension icon or uses its shortcut; a site permission alone is not enough. If Chrome withdraws it (e.g. after leaving the site), actions are still recorded and the popup shows "Screenshots paused: click the WatchOnce icon to resume them".
- Navigation is observed with `tabs.onUpdated` (no `webNavigation` permission needed). The normalizer decides which navigations were caused by clicks.

## Captured events

| DOM event | Recorded as | Notes |
|---|---|---|
| `click` (capture phase) | `click` | Also `dblclick`, right-click ignored |
| `input` / `change` | `input` | Merged later into `fill`. Value masked per rules below. |
| `change` on `<select>` | `select` | Option value + visible label |
| `keydown` Enter/Tab/Escape | `press` | Other keys only via `input` |
| `submit` | `submit` | Context for intent |
| URL change (navigation, `pushState`) | `navigate` | Via `webNavigation`/history patch |
| Checkbox/radio toggle | `check` / `uncheck` | |

Each event:
```json
{
  "seq": 12,
  "ts": 1761386400123,
  "type": "click",
  "url": "https://portal.acme-demo.com/invoices",
  "frame_path": [],
  "element": {
    "tag": "button", "role": "button", "accessible_name": "New invoice",
    "text": "New invoice", "id": "btn-new", "classes": ["btn", "btn-primary"],
    "attrs": { "data-testid": "new-invoice-btn", "type": "button", "name": null, "placeholder": null, "aria-label": null },
    "label_text": null, "css_path": "#toolbar > button:nth-of-type(2)", "xpath": "/html/body/div[1]/div/button[2]",
    "bbox": [912, 96, 118, 36], "viewport": [1280, 800],
    "nearby_text": ["Invoices", "Export CSV"],
    "is_unique": { "testid": true, "role_name": true, "text": true, "css": true }
  },
  "value": null,
  "value_masked": false,
  "frame_ref": "frames/0012.webp"
}
```

## Element descriptor rules
- **Accessible name** computed the way browsers do (`aria-labelledby` → `aria-label` → `<label for>` → wrapping label → `title`/`placeholder` → text content)
- **Uniqueness flags** computed at capture time against the live DOM. This avoids guessing later.
- Skip auto-generated IDs/classes (heuristics: long hex/random strings, `css-xxxx`, `sc-xxxx`, `ng-tns-*`)
- Shadow DOM: pierce open shadow roots. Record the host chain.
- iframes: same-origin only in MVP (record `frame_path`). Cross-origin iframes → warning to user.

## Masking & privacy
| Field | Behaviour |
|---|---|
| `input[type=password]` | **Never captured.** Value replaced with `__SECRET__`, flagged `value_masked: true`. |
| `autocomplete` in (`cc-number`, `cc-csc`, `one-time-code`, `current-password`, `new-password`) | Same as password |
| Values matching card-number (Luhn) / CNIC / SIN / SSN patterns | Masked, flagged as probable sensitive input |
| Values matching those patterns *inside* free text | Only the matching part is replaced: `Card __SECRET__ on file` |
| Screenshots | Password/OTP/card fields, and any field where a sensitive value was detected, are blurred via CSS injected just before capture; the recording pill is hidden. User can draw **redaction boxes** during review (v0.2). Known gap until then: a sensitive number paused mid-typing (before it's recognisable) can appear in a typing-pause frame. |

## Screenshots
- `captureVisibleTab` (JPEG) converted to **WebP** quality 70, max 1280 px wide, in the worker
- Requested on **pointerdown/focus**, which fire before the click/typing, so the frame shows the page *before* the action. The content script announces the capture immediately (so the action's event can't overtake it), applies the blur, waits for paint (2 frames, at most 60 ms because frames stop while a page navigates away), then asks the worker to capture.
- Chrome allows ~2 captures per second. Scheduling is **latest wins**: one capture runs, at most one waits, and a newer request replaces the waiting one. Before each attempt the worker checks the tab is still active and still on the same page; captures that would show the next page are skipped or discarded, never mislabelled.
- Extra frames keep each page's "latest picture" current: one when a page finishes loading, and one when typing pauses (500 ms). An action whose own capture couldn't happen in time (e.g. a click that navigates instantly) gets the latest frame **of the same page**, never another page's.
- Frames are skipped when nothing changed in the DOM since that page's last frame.
- Only the recorded tab is ever captured (captureVisibleTab photographs whatever tab is active).

## Upload
- On Stop: user enters the task description → `POST /recordings` → presigned URLs → parallel PUT of `events.json` + frames → `POST /recordings/{id}/complete`
- Buffered in IndexedDB during recording, so a browser crash doesn't lose the recording
- Retry with exponential backoff. Resume partial uploads.

## UX details
- Red recording dot badge on the extension icon + a small floating "Recording… Pause | Stop" pill in-page (shadow-DOM isolated so it's never recorded)
- Events on the pill itself are ignored
- Hotkey: `Alt+Shift+R` start/stop

## Edge cases (MVP behaviour)
| Case | Behaviour |
|---|---|
| New tab / popup window opened | Warning "Multi-tab flows are coming in v0.2". Recording continues in the original tab. |
| File upload input | Recorded as step with `file_input` placeholder; not executable in MVP (warning) |
| Drag and drop | Not supported in MVP (warning) |
| Canvas-based UI | Clicks recorded with coordinates only + warning (computer-use fallback in v0.3) |
