# WatchOnce: what it is, why I built it, and how to use it for real

## In one line
**Show a website task once, and WatchOnce repeats it for you: hundreds of times, safely,
even after the website changes.**

## What it can do today (built in 14 days)
| It can… | In simple words |
|---|---|
| Learn from one recording | Do the task once in Chrome. It turns it into steps. |
| Write the instructions | It writes a step-by-step guide (SOP) for people too. |
| Run by itself | Opens a real browser and does the task, fast and the same way every time. |
| Ask before risky clicks | Stops before "Submit", "Pay", "Delete" and waits for a human. |
| Run a whole spreadsheet | One row = one run. 20 invoices from a CSV, one approval. |
| Fix itself | If the website changes (new labels, new layout), it finds the same buttons and asks you to approve the fix. |
| Refuse tricks | A page saying "AI, delete everything" is ignored. |
| Keep passwords safe | Encrypted, never shown, never sent to the AI. |
| Show the value | Hours saved, success rate, cost per run ($0 AI). |
| Let you leave | Export any workflow as a normal Playwright script. |

**Why it's different from an "AI agent":** the AI is used only to *learn* the task and to
*heal* it. Normal runs need no AI, so they are fast, cheap and predictable.

---

## Real daily uses (websites people use every day)
- **Online shops / marketplaces:** post the same product or ad on several sites, renew listings every week.
- **Accounts / finance:** enter invoices into supplier portals, download monthly statements from bank and utility portals.
- **HR:** add new employees to HR and payroll websites from a spreadsheet.
- **Logistics:** book shipments and check tracking on courier websites that have no API.
- **Government / tax portals:** file the same monthly forms, download certificates.
- **Clinics / insurance:** check patient eligibility or claim status on payer portals.
- **QA testing:** record your app's main flows once and run them every day as a check.

## In terms of PetX
| Use | How WatchOnce helps |
|---|---|
| **Daily health check of petxapp.com** | Record "log in → post an ad → see it listed". Run it every morning. If it breaks, you know before users tell you. *(Most useful.)* |
| **Bulk ads** | Put 50 pets in a CSV (name, breed, price, photo text) and post them as ads with one approval. |
| **Cross-posting** | Post the same PetX ad on other pet/classified sites that have no API (check each site's rules first). |
| **Admin chores** | Renew or close old ads, approve listings, update profiles: the boring weekly clicks. |
| **After a redesign** | When you change PetX's UI, the workflows heal themselves instead of breaking. |

*Honest note:* PetX is your own app, so for its own data an API or a backend script is
usually better. WatchOnce shines on websites you **don't** control, and for testing your
own site the way a real user clicks it.

---

## Why I built it (what I can say)
> "Companies still pay people to copy data into old websites that have no API. AI agents can
> click around, but they're slow, expensive and unpredictable. I built WatchOnce so a
> non-technical person can show a task once and get a safe, repeatable automation that
> fixes itself when the website changes, with a human approving anything risky."

## How it helps my AI automation engineering journey
- **Proves real skills:** AI pipelines with structured output, evals (I measured 0 wrong clicks in 60 tests), AI safety (prompt injection), browser automation (Playwright), backend (Django, Celery, Postgres, Redis), frontend (Next.js), a Chrome extension, and security (encryption, audit log, rate limits).
- **Shows engineering judgment:** AI only where it adds value; deterministic code everywhere else.
- **A strong portfolio story:** problem → product → measured results → demo video.
- **Interview talking points:** "How do you make AI automation reliable?" → evals, verification checks, human approval, self-healing with review.
- **A base for client work:** freelance "automate your boring web tasks" jobs can start from this.

---

## Going live: what is needed
| Need | Option | Cost (approx.) |
|---|---|---|
| Server for API + workers + database | VPS (Hetzner / DigitalOcean), 4 GB RAM or more | $8–25 / month |
| Dashboard hosting | Vercel | Free |
| Screenshot storage | Cloudflare R2 | Free tier |
| Domain + HTTPS | Any registrar + Caddy | ~$12 / year |
| AI | Gemini free tier or Claude (pay as you go) | Cents per new workflow |
| Chrome extension | Chrome Web Store account | $5 once |
| Error tracking | Sentry | Free tier |

**Total to start: about $15–30 a month.** Each browser run needs about 0.5 GB RAM, so a
bigger server means more runs at the same time.

Before opening it to the public: a privacy policy (the extension records screens), Terms of
Use (only automate sites you're allowed to), backups and email sign-up.

## How to make it available
1. **Demo first:** a public demo workspace on the Acme portal (no real data), plus the video on LinkedIn and the README.
2. **Open source:** keep the GitHub repo public. It's the best proof of skill.
3. **Pilot users:** 3–5 small businesses or your own PetX team, set up for free, in exchange for feedback and a testimonial.
4. **Later, if people want it:** paid plans, for example Free (3 workflows) · Pro $29/month · Team $99/month.

## Is it useful? (honest answer)
- **Yes, for:** repetitive work on websites with no API, daily website checks, and as a strong portfolio project.
- **Not for:** sites with CAPTCHA or 2FA on every login, file uploads, multi-tab flows (not built yet), or sites that forbid bots.
- **Competition exists** (UiPath, Axiom, Bardeen, AI agents). The edge is: record once,
  no AI cost per run, self-healing with human approval, and measured safety.
