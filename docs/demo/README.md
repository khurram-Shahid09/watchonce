# Demo kit

Everything needed to run WatchOnce end to end on one machine, test every feature, and
produce the demo video, built around a real enterprise use case (Accounts Payable on a
legacy portal with no API).

| File | What it's for |
|---|---|
| [01-local-test-guide.md](01-local-test-guide.md) | Start everything locally, then a feature-by-feature test checklist |
| [02-enterprise-use-cases.md](02-enterprise-use-cases.md) | The AP month-end story, "why not an API / agent / RPA", more use cases, FAQ |
| [03-demo-video-script.md](03-demo-video-script.md) | Shot list, voice-over, captions, and the hand-off for editing |

| Script / data | What it does |
|---|---|
| `demo/scripts/seed_demo.py` | Creates the *Acme Corp - Accounts Payable* workspace with three workflows from real recordings |
| `demo/scripts/capture_scenes.py` | Records the 8 demo scenes as videos + stills (`demo/out/`) |
| `demo/scripts/capture_recording.py` | Records scene 0: the task recorded with the real extension |
| `demo/scripts/make_video.py` | Builds the finished video (voice, captions, music, cards) |
| `demo/scripts/voiceover.ps1` | Draft voice-over (Windows voice) + captions for timing |
| `demo/data/ap-invoices-october.csv` | 20 October invoices for the batch run |
| `demo/data/new-vendors.csv` | 5 vendors to onboard |

Quick start (with everything running, see guide section 1):
```bash
cd services/core
uv run python -I ../../demo/scripts/seed_demo.py
uv run --with playwright python -I ../../demo/scripts/capture_scenes.py
```
