# 05 · Workflow Spec (v1)

The **workflow spec** is a JSON document that fully describes an automation. It is:

- **Produced** by the compiler from a recording
- **Edited** by users in the dashboard
- **Executed** by the runner (deterministically)
- **Patched** by the healer (as a new pending version)
- **Exported** to a Playwright Python script and an SOP

The canonical schema lives at `packages/spec/workflow.schema.json`. This document is the human-readable reference.

## Top-level shape

```json
{
  "spec_version": "1.0",
  "name": "Create vendor invoice in Acme Portal",
  "description": "Creates a new invoice for an existing vendor and records the invoice number.",
  "allowed_domains": ["portal.acme-demo.com"],
  "start_url": "https://portal.acme-demo.com/login",
  "inputs": [
    { "name": "vendor_name", "type": "string", "required": true, "example": "Northwind Ltd", "description": "Vendor as shown in the vendor dropdown" },
    { "name": "amount", "type": "number", "required": true, "example": 1250.5 },
    { "name": "due_date", "type": "date", "required": true, "example": "2026-11-15", "format_hint": "MM/DD/YYYY in the portal" }
  ],
  "secrets": [
    { "name": "acme_login", "fields": ["username", "password"] }
  ],
  "outputs": [
    { "name": "invoice_number", "type": "string" }
  ],
  "steps": [ ... ],
  "settings": {
    "default_timeout_ms": 15000,
    "heal_policy": "approve",
    "auto_approve_heal_min_confidence": 0.9,
    "slow_mo_ms": 0
  },
  "source": { "recording_id": "rec_01J...", "compiled_by": "claude-opus-5-5", "compiled_at": "2026-10-25T10:00:00Z" }
}
```

## Steps

Every step has: `id` (stable, e.g. `s7`), `action`, `intent` (plain-English purpose: used by the SOP, live view and healer), optional `checkpoint`, optional `timeout_ms`, optional `screenshot_ref` (the recorded frame).

### Actions (MVP)

| `action` | Fields | Notes |
|---|---|---|
| `navigate` | `url` (templated) | Must match `allowed_domains` |
| `click` | `target` | |
| `fill` | `target`, `value` (templated) | Clears the field first |
| `select` | `target`, `value` or `label` | Native `<select>` and common custom dropdowns (click + option) |
| `check` / `uncheck` | `target` | |
| `press` | `key` (e.g. `Enter`) and optional `target` | |
| `wait_for` | `condition`: `url_matches`, `element_visible`, `text_visible`, `network_idle` | |
| `assert` | `condition` (same as `wait_for`) | Fails the run if false. Generated after key steps. |
| `extract` | `target`, `attribute` (`text` default), `output` (name), optional `pattern` (regex) | Fills a workflow output |

### Templating
`{{input_name}}`, `{{secrets.acme_login.username}}`, `{{outputs.invoice_number}}`, plus a few filters: `{{due_date | date:"MM/DD/YYYY"}}`, `{{amount | number:2}}`. No arbitrary expressions (security + determinism).

### Target (the self-healing foundation)

```json
"target": {
  "locators": [
    { "kind": "testid", "value": "new-invoice-btn" },
    { "kind": "role", "role": "button", "name": "New invoice" },
    { "kind": "text", "value": "New invoice", "exact": true },
    { "kind": "label", "value": "Vendor" },
    { "kind": "css", "value": "#toolbar > button.btn-primary:nth-of-type(2)" }
  ],
  "fingerprint": {
    "tag": "button",
    "role": "button",
    "accessible_name": "New invoice",
    "text": "New invoice",
    "attributes": { "id": "btn-new", "class": "btn btn-primary", "type": "button" },
    "nearby_text": ["Invoices", "Export CSV"],
    "bbox_norm": [0.71, 0.12, 0.09, 0.04],
    "frame_path": []
  },
  "anchor_image_ref": "frames/rec_01J/s2_crop.webp"
}
```

- `locators` are ordered **most robust → least robust**. The runner tries them in order.
- `fingerprint` is used for fuzzy re-matching when all locators fail (see [08](08-runner-and-self-healing.md)).
- `anchor_image_ref` is a crop of the element from the recording, used for visual verification during repair.

### Checkpoints

```json
{ "id": "s11", "action": "click", "intent": "Submit the invoice for payment",
  "target": { ... },
  "checkpoint": { "type": "approval", "reason": "Submits a payment request (irreversible)" } }
```

`checkpoint.type`: `approval` (pause for a human) or `none`. The compiler proposes checkpoints for submit/pay/delete/send/approve-like intents. Users can add or remove them, but removing one is audit-logged.

## Full example step list (abridged)

```json
[
  { "id": "s1", "action": "navigate", "intent": "Open the portal login page", "url": "https://portal.acme-demo.com/login" },
  { "id": "s2", "action": "fill", "intent": "Enter username", "target": { "locators": [{ "kind": "label", "value": "Username" }] }, "value": "{{secrets.acme_login.username}}" },
  { "id": "s3", "action": "fill", "intent": "Enter password", "target": { "locators": [{ "kind": "label", "value": "Password" }] }, "value": "{{secrets.acme_login.password}}" },
  { "id": "s4", "action": "click", "intent": "Sign in", "target": { "locators": [{ "kind": "role", "role": "button", "name": "Sign in" }] } },
  { "id": "s5", "action": "wait_for", "intent": "Dashboard loaded", "condition": { "type": "url_matches", "value": "/dashboard" } },
  { "id": "s6", "action": "click", "intent": "Open new invoice form", "target": { "locators": [{ "kind": "testid", "value": "new-invoice-btn" }, { "kind": "role", "role": "button", "name": "New invoice" }] } },
  { "id": "s7", "action": "select", "intent": "Choose the vendor", "target": { "locators": [{ "kind": "label", "value": "Vendor" }] }, "label": "{{vendor_name}}" },
  { "id": "s8", "action": "fill", "intent": "Enter invoice amount", "target": { "locators": [{ "kind": "label", "value": "Amount" }] }, "value": "{{amount | number:2}}" },
  { "id": "s9", "action": "fill", "intent": "Enter due date", "target": { "locators": [{ "kind": "label", "value": "Due date" }] }, "value": "{{due_date | date:\"MM/DD/YYYY\"}}" },
  { "id": "s10", "action": "click", "intent": "Submit the invoice", "target": { "locators": [{ "kind": "role", "role": "button", "name": "Submit" }] }, "checkpoint": { "type": "approval", "reason": "Creates a payable invoice" } },
  { "id": "s11", "action": "assert", "intent": "Confirmation shown", "condition": { "type": "text_visible", "value": "Invoice created" } },
  { "id": "s12", "action": "extract", "intent": "Read the new invoice number", "target": { "locators": [{ "kind": "testid", "value": "invoice-number" }] }, "output": "invoice_number", "pattern": "INV-\\d+" }
]
```

## Versioning rules
- Specs are immutable once saved. Every edit or heal creates `workflow_versions.version + 1`.
- A version is `draft` | `active` | `pending_heal` | `archived`. Exactly one `active` version per workflow.
- `spec_version` (the format version) is separate from workflow version. Migrations are written for format changes.

## Validation (before save and before run)
1. JSON Schema validation
2. Every `{{input}}` referenced exists in `inputs`. Every output is produced by exactly one `extract`.
3. `navigate.url` hosts ⊆ `allowed_domains`
4. Every step with a `target` has ≥ 2 locators where possible (warning, not error)
5. At least one checkpoint if any step intent matches the risky-verb list (warning)
