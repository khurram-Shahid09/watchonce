# 17. Authoring agent: workflows from plain instructions

Recording a task with the extension is one way to build a workflow. The authoring agent is
the other: you write the task in plain words, and an AI agent does it once in a real browser
while you watch. Every step it takes is saved exactly like a compiled recording (locators +
fingerprint), so later runs replay without AI, self-heal and export like any other workflow.

The same agent also **fixes** a workflow whose run failed: you describe what to do
differently, it redoes the task live and saves the result as a new version.

## Using it

| Where | What |
|---|---|
| Workflows → **New from instructions** | Start link + instructions → live build → saved workflow |
| A failed run → **Fix this workflow** | A hint → live rebuild → new version (the old one is kept) |
| A failed run → **edit the steps yourself** | The workflow's Edit tab |

Good instructions are short and concrete, one step per line:

```
Log in with my saved login petx_login
Open My Ads
Read the number of views of the first ad as views
```

- **Inputs:** values that change from run to run (names, amounts, reference numbers) become
  workflow inputs, with the value used while building as the example.
- **Outputs:** "Read … as name" becomes an extract step; the value shows on every run and in
  batch results.
- **Logins:** never write a password in the instructions. Save it (the form has a
  "Save a login" link) and say "log in with my saved login *name*".
- **Risky steps** (submit, pay, delete, send, post…) pause with the element highlighted:
  **Do it now** performs it on the site; **Keep without doing** saves the step with an
  approval checkpoint and finishes there, without doing it.

## How it works

```
POST /authoring {start_url, instructions}        → AuthoringSession (queued)
  run worker: engine.runner.author_session
    open start_url in an isolated context (allowed hosts: the start URL's and any URL in the instructions)
    loop (≤ 40 steps, ≤ 60 AI calls):
      page agent marks the visible interactive elements (e1, e2, …)
      AI "author" stage: instructions + steps so far + elements + page text + screenshot → next action
      check it: the element id must be in the list; a secret must exist; navigation must stay on allowed hosts
      risky? → pause for the person (Redis decision, like run checkpoints)
      do it in the browser (pointer glides to the element first) → save the step
      failed? → the AI hears why and tries another way (3 failures in a row stop it)
    done → validate the spec → new workflow (or new version) with a basic SOP
```

Live view: the browser is streamed with Chromium's screencast (about 4 frames a second while
something moves), plus `agent_step`, `thinking`, `checkpoint` and `done` events on the same
Redis channel scheme as runs (`run:{id}:events`). Normal runs now use the same screencast and
pointer, so every run shows what it is doing as it happens.

## Safety

The agent keeps every guarantee of the rest of the system:

| Risk | Control |
|---|---|
| Prompt injection from the page | The AI can only answer with an element id from the list; anything else is refused. Page text is marked as data in the prompt. |
| Leaking credentials | The AI sees saved logins' names and field names only. Values are typed from the vault; they're scrubbed from page text, URLs, titles and the step log before anything is sent or stored. |
| Doing something irreversible | Deterministic risky-verb check on the element's name plus the AI's own flag; both pause for a person. |
| Wandering off | Navigation and network requests are limited to the hosts in the start URL and instructions. |
| Runaway cost | ≤ 60 AI calls per session, the workspace's monthly AI budget, and the hourly compile quota (an authoring session counts as one). |
| Busy AI | Rate limits and overloads are retried after 10, 20 and 40 seconds before giving up. |

## Providers

The stage is `author` (prompt `engine/llm/prompts/author.md`). Gemini and Claude answer with
JSON-schema output (`AuthorAction`). `LLM_PROVIDER_AUTHOR` overrides the provider for this
stage only. The fake provider follows one-line instructions mechanically ("Type X in Field",
"Click Name", "Select X in Field", "Wait for Text", "Read Label as name", "Log in with my
saved login name"), which is what the tests and offline demos use.

## Limits

- One browser tab; no file uploads, CAPTCHAs or 2FA prompts (same as runs).
- An authoring session holds a run worker while it waits for your approval: run a second
  run worker if you build and run at the same time.
- The free Gemini tier allows only a few calls a minute and a daily cap; a long build can hit
  it. The agent waits and retries, but a used-up daily quota stops it until the next day.
