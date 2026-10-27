# LinkedIn launch: WatchOnce

A ready-to-use plan: what to post, how it should look, and the exact words.

**The angle:** not "AI automates everything forever". The posts show **a real problem, a working
solution, proof that it's safe, and an honest line about where it doesn't fit.** That is what makes
engineers, hiring managers and operations leads trust it.

---

## 1. The plan: two posts, one week apart

| | Post 1: the launch | Post 2: the proof |
|---|---|---|
| **Format** | Native video (upload the MP4, don't paste a YouTube link) | PDF carousel ("document" post), 12 slides |
| **Story** | "Show it once, or just describe it" | "Here's why you can trust it" (approvals, healing, injection, evals) |
| **Upload** | `demo/out/linkedin/post1-video.mp4` (2:38, captions burned in) + `post1-thumbnail.png` | `demo/out/linkedin/post2-carousel.pdf` |
| **When** | Tue–Thu, 8–10 am in your audience's time zone | 5–7 days later, same time |

Why this works:
- **Native video** plays in the feed. A YouTube link sends people away, and posts with outside links tend to reach fewer people.
- **Carousels** keep people swiping, and each slide gets a few seconds of attention, which suits a step-by-step story.
- Two posts tell two stories without cramming everything into one.

**All media is generated:** `demo/scripts/make_linkedin.py` builds every file below from the
real screenshots and videos (no AI involved). Re-run it after changing any words.

| File | What it is |
|---|---|
| `post1-video.mp4` | The main demo (1:50) followed by the "describe it" clip (0:48) |
| `post1-thumbnail.png` | 1920×1080 cover for the video |
| `post2-carousel.pdf` | The 12 slides as one document |
| `post2-slide-01.png … 12.png` | The same slides as images (for other posts or the portfolio) |

---

## 2. What makes a post look professional

1. **Hook in the first 2 lines.** LinkedIn cuts the text after about 210 characters (about 140 on mobile). Lead with the problem, not your product name.
2. **Short lines and white space.** One idea per line. No walls of text.
3. **Specific numbers, honestly labelled.** "0 wrong clicks in 60 UI-change tests" beats "very reliable".
4. **Show the limits.** One line on when *not* to use it. This is what separates engineers from hype.
5. **Links in the first comment,** not in the post.
6. **End with a real question** that people can answer from their own work.
7. **3–5 hashtags** at the end. No more.
8. **No emoji walls.** At most 1–2 arrows or pointers.
9. **Reply to every comment in the first hour.** Early replies help the post reach more people.

---

## 3. Post 1: the launch (copy-paste ready)

```
Every company has one: a web portal with no API, and a team that types into it all day.

Supplier invoices. Carrier bookings. Government forms. Insurance portals.

I built WatchOnce to take that work off people's desks.

How it works:
→ Show it once: do the task in Chrome and the extension records it.
→ Or just describe it: an agent does the task once in a live browser while you watch.
→ Either way you get a reviewed workflow with inputs and a written SOP.
→ It runs a whole spreadsheet: 20 invoices, one approval.
→ It stops before anything risky (Submit, Pay, Delete) and waits for a human.
→ When the website changes, it finds the same buttons, finishes the job and asks the owner to approve the fix.

The question I cared about wasn't "can AI click buttons?"
It was "would you trust it with real work on a Monday morning?"

So I measured it:
• 60 tests where the website changes under it: renamed buttons, new layouts, look-alike buttons, even a page telling the AI to "delete all vendors"
• 0 wrong clicks. When it can't be sure, it stops and says why.
• $0 AI cost per run. AI learns the task and repairs it; normal runs are plain, repeatable steps.

Where it doesn't fit: if a good API exists, use the API. This is for the long tail of work that will never get one.

Built with Django, Celery, Playwright, Next.js, a Chrome extension, and Gemini / Claude.

Demo below. Code and full write-up in the first comment.

What's the one portal your team still types into by hand?

#AIAutomation #AIEngineering #Automation #Playwright #BuildInPublic
```

**First comment (post it yourself right after publishing; use it on both posts):**
```
Full case study: https://khurramshahid.vercel.app/watchonce
Code: https://github.com/khurram-Shahid09/watchonce
Demo on YouTube: https://youtu.be/gKPZ_yQvJnU
```

### Other hooks to choose from (first 2 lines)
- "AI agents that click around websites are impressive in demos. I wanted one I'd trust with an accounts-payable team's invoices."
- "I tried to break my own automation 60 ways. It made 0 wrong clicks. Here's what I built and how I tested it."
- "Most 'AI automation' runs a language model on every click. Mine uses it to learn the task and to fix it when the website changes. Nothing else."

### Uploading the video
1. Start a post → **Video** → `post1-video.mp4`.
2. **Edit** (pencil) → **Thumbnail** → upload `post1-thumbnail.png`.
3. Captions are burned into the video, so no subtitle file is needed.
4. Paste the text, post, then add the first comment.

---

## 4. Post 2: the proof (12-slide carousel)

**Upload:** start a post → **Add a document** (the "+" or "…" menu) → `post2-carousel.pdf`.
**Document title** (LinkedIn asks for one): `How I made AI automation you can trust`

| # | Slide |
|---|---|
| 1 | **I tried to break my own AI automation 60 ways.** Zero wrong clicks. |
| 2 | **Every company has a website it can't plug into.** 400 invoices × 4 minutes = 26 hours a month. |
| 3 | **Scripts break. AI agents guess.** What I wanted: learn once, replay exactly, use AI only to repair. |
| 4 | **Show it once.** The extension records; passwords are masked. |
| 5 | **AI turns it into a workflow.** Named steps, inputs, a written SOP. |
| 6 | **It asks before anything risky.** You see exactly which button it will press. |
| 7 | **20 invoices. One approval.** $0 in AI per run. |
| 8 | **The portal got a redesign. The job still finished.** Owner approves the fix. |
| 9 | **A page told the AI to delete every vendor.** Ignored. |
| 10 | **Or just describe it.** An agent does it once in a live browser and asks before Submit. |
| 11 | **When a run fails: tell it what changed.** It redoes the task as a new version. |
| 12 | **Measured, not claimed.** 0 / 100% / $0 / 1, then "What would you automate first?" |

**Post 2 text (copy-paste ready, the slides do the talking):**
```
"Can I trust it?" matters more than "can it do it?" when AI touches real business systems.

So before showing WatchOnce to anyone, I tried to break it 60 ways: renamed buttons, new layouts, look-alike buttons, and a page that told the AI to delete every vendor.

Result: 0 wrong clicks. When it couldn't be sure, it stopped and said why.

The slides walk through it: one recording (or a plain-English description) becomes a workflow, 20 invoices run with one approval, and a failed run gets fixed from a one-line hint 👉

Case study, code and demo in the first comment.

What would you automate first?

#AIAutomation #AIEngineering #Automation #QualityEngineering
```

---

## 5. Checklist before you press Post

- [ ] Post 1: video uploaded natively, custom thumbnail set
- [ ] Post 2: PDF uploaded as a document, title filled in
- [ ] The hook reads well when cut after 2 lines on a phone
- [ ] No links in the post body; links ready to paste in the first comment
- [ ] Portfolio page and GitHub README open correctly from a phone
- [ ] You're free for the next hour to reply to comments

## 6. After posting

- Reply to every comment with something specific, not just "Thanks!".
- If someone asks "why not just use the API?", answer with "Why not just use the API?" from `02-enterprise-use-cases.md`.
- If someone asks "is the agent just an LLM clicking around?": no. It does the task once while you watch, then every run replays fixed, reviewed steps with no AI (`docs/17-authoring-agent.md`).
- Share the post to relevant groups a day later with one new line of context, not a copy.
- Pin Post 1 to your profile's Featured section.
