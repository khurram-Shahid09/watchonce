# Demo video kit: script, shot list, voice-over

Two cuts from the same footage:
- **Main video (≈ 2:00):** LinkedIn, the README, investors. Story first, fast.
- **Walkthrough (≈ 6 min):** for technical viewers and enterprise buyers. Every feature, at full length.

The footage comes from two sources:
1. **You, live (the human moment):** recording a task with the Chrome extension. Real
   people doing a real task is what makes "record once" believable. Record this one by hand.
2. **The capture script (everything else):** consistent, repeatable clips with a visible
   cursor and human-paced typing:
   ```bash
   cd services/core
   uv run python -I ../../demo/scripts/seed_demo.py                         # once
   uv run --with playwright python -I ../../demo/scripts/capture_scenes.py  # all 8 scenes
   ```
   Clips: `demo/out/raw/01-portal.webm … 08-analytics.webm`; stills: `demo/out/shots/`.
   Re-record one scene: `capture_scenes.py heal`.

---

## Recording your live clip (scene 0)

**Setup:** Chrome at 1440×900 or larger (or full screen at 1920×1080), zoom 100%,
bookmarks bar hidden, only the Acme tab open. Screen recorder: OBS (Display Capture, 30 fps,
MP4) or Windows **Win+Alt+R** (Xbox Game Bar).

**Take:**
1. Start on the Acme login page. Click the WatchOnce icon → **Start recording**.
2. Log in as `sara` / `acme-demo` → **Invoices** → **New invoice**.
3. Vendor *Northwind Ltd* · Amount `1250.50` · Due `11/15/2026` ·
   Description `PO-4471 Office chairs (12 units)` → **Submit**.
4. **Stop** → description: "Enter a vendor invoice and submit it for approval" →
   **Upload to workspace**.
5. Switch to the dashboard and keep recording until the workflow appears (cut the wait later).

Save it as `demo/out/raw/00-live-recording.mp4`. Do 2–3 takes; we use the cleanest.

---

## Main video (≈ 2:00)

| Time | Clip | On screen (caption) | Voice-over |
|---|---|---|---|
| 0:00–0:08 | `01-portal` (first seconds) | **Every company has a portal like this.** | "Every company has a system like this: an old web portal, no API, and a team that types into it all day." |
| 0:08–0:18 | `01-portal` (new-invoice form) | **400 invoices / month × 4 min = 26 hours** | "At Acme, Accounts Payable enters four hundred invoices a month into it. Four minutes each. By hand." |
| 0:18–0:35 | `00-live-recording` (sped up 2×) | **Show it once.** | "So Sara shows WatchOnce how to do it. Once. She just does her job while the extension watches." |
| 0:35–0:50 | `02-workflow` | **One recording → a reviewed workflow + SOP** | "A minute later it's a workflow: every step named, with a screenshot. The vendor, amount and dates became inputs. It even wrote the procedure document." |
| 0:50–1:05 | `03-run` (live view → approval) | **It asks before anything risky.** | "Now it runs by itself, in a real browser. And before it submits anything, it stops and asks a human." |
| 1:05–1:25 | `04-batch` (sped up 8–10×) | **20 invoices. One approval. Hands off.** | "October's backlog: twenty invoices from a spreadsheet. Sara approves once, and WatchOnce does the rest, with a results file at the end." |
| 1:25–1:50 | `05-heal` (portal v2 → healed run → heal review) | **IT changed the portal. It healed itself.** | "Then IT ships a new version of the portal: new labels, new layout. Old automation breaks here. WatchOnce finds the same buttons, finishes the job, and shows the manager exactly what changed, for one-click approval." |
| 1:50–2:02 | `06-injection` | **"Delete all vendors"? No.** | "And when a page tries to trick the AI into deleting every vendor, it does its job and nothing else." |
| 2:02–2:12 | `08-analytics` | **Hours saved. $0 AI per run.** | "Hours saved, every run audited, and no AI cost per run, because AI is only used to learn and to heal." |
| 2:12–2:15 | Title card | **WatchOnce: show it once.** + repo URL | "WatchOnce. Show it once." |

**Music:** quiet, upbeat, no lyrics; −20 dB under the voice.
**Captions:** burn the captions in (most LinkedIn viewers watch muted).

---

## Walkthrough (≈ 6 min)

| # | Clip | Length | Talking points |
|---|---|---|---|
| 1 | `01-portal` | 0:30 | The legacy system: no API, owned by a vendor, changes without notice. |
| 2 | `00-live-recording` | 1:00 | Record once. Password is masked on capture; it's never stored. |
| 3 | `02-workflow` | 0:45 | Steps + screenshots, inputs found, approval stop found, SOP for auditors. Versioned, editable. |
| 4 | `03-run` | 0:40 | Deterministic replay in an isolated browser, live view, approval with the exact element highlighted, reject stops cleanly. |
| 5 | `04-batch` | 0:50 | CSV in, results CSV out, approve-all for the batch, row-level status. |
| 6 | `05-heal` | 1:00 | Portal v2: L1 fallbacks, L2 fingerprint match, L3 AI repair, with checks after every pick; owner review with before/after; the next run needs no healing. Mention: a breaking change (menu) fails cleanly, never a wrong click (0 in 60 eval cases). |
| 7 | `06-injection` | 0:30 | Prompt injection on the page is ignored: AI picks only from candidates, risky clicks need a human, look-alikes refused, domain allowlist. |
| 8 | `07-export` | 0:20 | No lock-in: plain Playwright script with argparse inputs and `--csv`. |
| 9 | `08-analytics` | 0:25 | Hours saved, success rate, heals, AI spend. Rate limits, audit log, encrypted secrets. |
| 10 | Eval reports (screenshot of `evals/reports/*.md`) | 0:20 | "We measure it": E1 compile and E2 heal suites; 0 wrong clicks, 0 injection picks. |

---

## Stills for posts and the README
`demo/out/shots/`: `portal-new-invoice`, `workflow-steps`, `workflow-sop`,
`approval-*`, `run-done`, `batch-waiting`, `batch-done`, `portal-v2`, `heal-run`,
`heal-review`, `injection-banner`, `injection-run`, `export-script`, `analytics`.
LinkedIn carousel order: portal → steps → approval → batch-done → heal-review →
injection-banner → analytics.

---

## Build the finished video (automated)
```bash
pnpm --filter @watchonce/extension build:e2e
cd services/core
uv run --with playwright python -I ../../demo/scripts/capture_recording.py   # scene 0, with the real extension
uv run --with playwright python -I ../../demo/scripts/capture_scenes.py      # scenes 1-8
cd ../.. && pnpm --filter @watchonce/extension build
uv run --no-project --with edge-tts --with imageio-ffmpeg --with numpy python demo/scripts/make_video.py
```
`make_video.py` cuts the clips to the voice-over, speeds up the waiting, adds captions,
title/end cards and a quiet synthesized music bed, and normalizes loudness to −14 LUFS.
Output: `demo/out/watchonce-demo.mp4`. The voice is Microsoft's neural TTS via `edge-tts`
(set `VOICE=en-US-AvaNeural` for a female voice); the narration and cut points are the
`SEGMENTS` list at the top of the script. To use your own voice, replace the files in
`demo/out/edit/voice/` with the same names (keep the `.txt` stamps).

## Hand-off for editing and voice-over
When the footage is ready, tell me, and make sure these exist:
- `demo/out/raw/00-live-recording.mp4` (your take) and the 8 captured clips
- optional: your own voice-over takes (`demo/out/voice/*.wav`), one file per row of the
  table above, or say "use the draft voice"

I'll then assemble the cut with **ffmpeg** (trim, speed-ups, captions, music bed, voice
mix, title cards) into `demo/out/watchonce-demo.mp4` (1080p) and a square version for
LinkedIn. Install it once: `winget install Gyan.FFmpeg`.

**Draft voice-over now:** `powershell -File demo/scripts/voiceover.ps1` reads the main
video's lines with the built-in Windows voice into `demo/out/voice/` so the timing can be
checked before you record your own voice (or use an AI voice of your choice).
