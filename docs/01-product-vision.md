# 01 · Product Vision

## Problem

Knowledge workers in operations, finance, HR, logistics and support spend hours a week on **repetitive browser tasks inside tools that have no API**, or whose API their team can't access:

- Copying invoice data from emails or spreadsheets into a vendor or ERP portal
- Updating order status across two internal admin panels
- Downloading monthly reports from 6 different supplier portals
- Filing the same insurance or government form for each case
- Onboarding a new employee across 5 SaaS admin consoles

Today's options are all bad:

1. **Keep doing it by hand.** It's slow and error-prone, and good people burn out.
2. **Buy RPA** (UiPath, Power Automate Desktop). Expensive licenses, specialist developers, and the bots break when the UI changes. Industry surveys repeatedly put RPA maintenance at a large share of total RPA cost.
3. **Ask engineering to build an integration.** That means a months-long backlog, and often there's no API at all.
4. **Use an AI browser agent on every run.** Slow, costly per run, and non-deterministic. Hard to trust for finance or HR data.

## Insight

> The person who does the task already knows exactly how to do it. We just need to **watch them once**.

AI is very good at *understanding* a demonstration: what each click means, which typed values are inputs and which are constants, which step is the risky "Submit". It's also good at *repairing* a broken step when a page changes. It isn't needed to *repeat* a known-good path. So we use AI where it adds value (understanding and repair) and plain deterministic code for execution.

## Product

**WatchOnce** turns a single recorded demonstration into:

1. **An SOP**: a readable, screenshot-illustrated procedure. Useful on its own for training and audits.
2. **A workflow**: a parameterized, deterministic automation with named inputs (e.g. `vendor_name`, `amount`).
3. **A runner**: run it once, run it over 500 CSV rows, or put it on a schedule, with a live view.
4. **Self-healing**: when the target app's UI changes, the workflow repairs the broken step, logs what changed, and asks for approval.
5. **Guardrails**: human-approval checkpoints before destructive steps, domain allowlists, encrypted credentials, and a full audit log.

## Target users (MVP)

| Persona | Role | What they want |
|---|---|---|
| **Sara, Ops Analyst** (primary) | Does the repetitive task daily | "Let me show it once and stop doing it by hand." |
| **Imran, Automation Owner / IT** | Approves and maintains automations | "I need it to be reliable, auditable and safe." |
| **Manager** | Owns the team's KPIs | "How many hours did we save? Did anything go wrong?" |

## Initial target segments

- Mid-size companies (50–2,000 staff) that run on many SaaS and legacy web tools and have no RPA team
- Accounts payable/receivable, logistics back-office, insurance claims, HR ops
- Agencies and BPOs (outsourcing firms) doing the same portal work for many clients. This is a strong fit for Pakistan- and Canada-based BPO networks.

## Value proposition (the numbers we'll demo)

- A 4-minute manual task × 40 times/day = **~2.7 hours/day saved** for one person
- Time to automate: **under 10 minutes** (record + review), compared with days or weeks for RPA
- Run-time AI cost: **$0 per run**. Typical compile cost is about $0.10–$0.30 once, and a repair is a few cents (see [06](06-ai-pipeline.md#cost-model)).

## Positioning statement

> For operations teams stuck doing repetitive work in web apps without APIs, **WatchOnce** is a record-once automation tool that turns a single demonstration into a documented, self-healing workflow. Unlike traditional RPA, it needs no developer and survives UI changes. Unlike AI browser agents, it's deterministic, auditable, and costs nothing per run.

## What success looks like

- **MVP (portfolio):** A 2-minute demo video plus a live demo link that makes an engineering manager say "wait, how did it do that?", especially the self-healing moment.
- **Pilot:** 1–3 real teams (via network or Fiverr) automating 1 real task each, with measured hours saved.
- **Product:** Paid tiers per workflow or per run volume. Enterprise features: SSO, RBAC, on-prem runner.
