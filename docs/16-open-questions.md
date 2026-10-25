# 16 · Open Questions & Owner Inputs

## Needed from Khurram

| # | Item | Needed by | Status / notes |
|---|---|---|---|
| N1 | **Gemini API key** (free tier, Google AI Studio) | Day 6 | Paste into `GEMINI_API_KEY` in the local `.env`. For local development with fake demo data only. |
| N2 | **Anthropic API key** with billing enabled (console.anthropic.com) | Before demo recording / evals (~Day 12) | Set a monthly spend limit (e.g. $30–50 for evals + demo) |
| N3 | **Cloudflare R2** bucket + access keys | Day 5 (SeaweedFS S3 locally until then) | Can reuse the existing Cloudflare account, in a separate bucket |
| N4 | **GitHub repo** | Day 1 | ✅ Done: `github.com/khurram-Shahid09/watchonce` (private) |
| N5 | **Domain** | – | ✅ Not needed for the MVP: free `*.vercel.app` + `sslip.io` (see [13](13-deployment-ops.md)) |
| N6 | **VPS** (Hetzner CX32 / DigitalOcean 4 vCPU 8 GB, ~US$15–30/mo) | Day 15 | Or start on a free trial credit |
| N7 | **Vercel** account linked to GitHub | Day 15 | Already in use for the portfolio |
| N8 | **Google OAuth client** (Google Cloud console) | Day 3 (optional, email login works without it) | |
| N9 | **Sentry** account (free tier) | Day 14 | |
| N10 | **Chrome Web Store developer account** ($5 one-time) | Only if publishing the extension publicly | For the MVP demo, "load unpacked" is fine |

## Decisions

| # | Question | Decision / default | Alternatives |
|---|---|---|---|
| D1 | Product name | ✅ **WatchOnce** | – |
| D2 | Backend framework | ✅ **Django + DRF + Channels + Celery + Playwright (Python)** ([ADR-0004](adr/0004-python-backend-nextjs-frontend.md)) | – |
| D3 | AI provider | ✅ **Pluggable**: Gemini free tier for development, Claude (`claude-opus-5-5`) for demo and real data, both in evals ([ADR-0005](adr/0005-pluggable-llm-provider.md)) | Final per-stage choice after E4 eval results |
| D4 | Hosting | ✅ **Vercel (web + demo portal) + one VPS (API, workers, DB, Redis)**, no custom domain | Railway/Render, AWS |
| D5 | Auth | **Own JWT + Google OAuth** | Clerk/Auth.js |
| D6 | Demo target | **Our own Acme Vendor Portal** | Also one real public app (e.g. OrangeHRM demo) |
| D7 | Data region | Default (US/EU) for MVP | Canadian region when a Canadian pilot asks |
| D8 | License | ✅ **No license, private repo** (all rights reserved) | Revisit before making the repo public |
| D9 | Timeline | 15 working days (demo-able cut at day 10) | Faster cut: skip batch + Google OAuth → demo at ~day 8 |
| D10 | Demo portal hosting | Vercel as planned; move it to a container on the VPS if the "Portal v2" switch is unreliable there (it's held in server memory) | VPS from the start |

## Open product questions (answer during the pilot, not blocking)
- Pricing unit: per workflow, per run, or per seat?
- Will pilot customers accept a cloud runner, or do they need it to run inside their network (on-prem runner)?
- Which first vertical: AP/finance ops, logistics back-office, or BPOs?
- Do customers want the SOP export more than the automation itself? (Possible free wedge product.)
