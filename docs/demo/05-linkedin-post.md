# LinkedIn launch: WatchOnce

A ready-to-use plan: what to post, how it should look, and the exact words.

**The angle:** not "AI automates everything forever". The post shows **a real problem, a working
solution, proof that it's safe, and an honest line about where it doesn't fit.** That is what makes
engineers, hiring managers and operations leads trust it.

---

## 1. The plan: two posts, one week apart

| | Post 1: the launch | Post 2: the proof |
|---|---|---|
| **Format** | Native video (upload the MP4, don't paste a YouTube link) | PDF carousel ("document" post), 10 slides |
| **Story** | "Here's what it does" | "Here's why you can trust it" (safety, healing, evals) |
| **Media** | `demo/out/watchonce-demo.mp4` (1:50, captions burned in) + a custom thumbnail | Slides built from `demo/out/shots/` |
| **When** | Tue–Thu, 8–10 am in your audience's time zone | 5–7 days later, same time |

Why this works:
- **Native video** plays in the feed. A YouTube link sends people away, and posts with outside links tend to reach fewer people.
- **Carousels** keep people swiping, and each slide gets a few seconds of attention, which suits a step-by-step story.
- Two posts tell two stories without cramming everything into one.

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

Over 14 days I built WatchOnce to take that work off people's desks.

How it works:
→ Someone does the task once in Chrome. The extension records it.
→ AI turns the recording into a reviewed workflow, with inputs and a written SOP.
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

2-minute demo below. Code and full write-up in the first comment.

What's the one portal your team still types into by hand?

#AIAutomation #AIEngineering #Automation #Playwright #BuildInPublic
```

**First comment (post it yourself right after publishing):**
```
Full case study: https://khurramshahid.vercel.app/watchonce
Code: https://github.com/khurram-Shahid09/watchonce
Demo on YouTube: https://youtu.be/gKPZ_yQvJnU
```

### Other hooks to choose from (first 2 lines)
- "AI agents that click around websites are impressive in demos. I wanted one I'd trust with an accounts-payable team's invoices."
- "I tried to break my own automation 60 ways. It made 0 wrong clicks. Here's what I built and how I tested it."
- "Most 'AI automation' runs a language model on every click. Mine uses it twice: to learn the task and to fix it when the website changes."

---

## 4. The video thumbnail (Post 1)

LinkedIn lets you upload a custom thumbnail. Without one, it picks a random frame.

| | Spec |
|---|---|
| Size | 1920×1080 (same as the video) |
| Background | Dark navy `#0b1220`, a soft blue glow top-right |
| Headline (left half) | **"20 invoices. 1 approval. 0 wrong clicks."** in white, large (about 96 px), 2–3 lines |
| Sub-line | "WatchOnce: AI automation for websites with no API" in light grey |
| Visual (right half) | The approval screen (`approval-*.png`) in a browser frame, slightly tilted, with a badge: "Asks before it clicks Submit" |
| Footer | Your name + "khurramshahid.vercel.app" small, bottom-left |
| Font | Space Grotesk (headings) + Inter (text), the same as your portfolio |

Rule: readable on a phone at thumbnail size. If you squint and can't read the headline, it's too small.

---

## 5. Post 2: the carousel script (10 slides, 1080×1350 PDF)

**Style for every slide:** same dark navy background, white headline (max 8 words), one
screenshot or one number, slide number "3/10" top-right, your name bottom-left. Keep 80 px
margins so nothing touches the edge.

| # | Headline | Visual | Small text (optional) |
|---|---|---|---|
| 1 | **I tried to break my own AI automation 60 ways.** | Heal review in a browser frame + 3 stat chips | "It made zero wrong clicks. Here's what I built…" |
| 2 | **Every company has a website it can't plug into.** | "26 hours" stat card | "Example: 400 invoices × 4 minutes, for one form" |
| 3 | **Scripts break. AI agents guess.** | Three cards: Scripts & RPA / AI agents / What I wanted | "Learn once. Replay exactly. Use AI only to repair." |
| 4 | **Show it once.** | Portal form + red "● Recording" pill | "Passwords are masked before anything is saved" |
| 5 | **AI turns it into a workflow.** | Workflow steps and inputs | "Named steps, inputs and a written SOP" |
| 6 | **It asks before anything risky.** | Approval screen + "Waiting for you" pill | "You see exactly which button it will press" |
| 7 | **20 invoices. One approval.** | Batch results + "20 of 20 succeeded" | "Every run replays the same steps, so $0 in AI" |
| 8 | **The portal got a redesign. The job still finished.** | Portal v2 behind, heal review in front | "Found the same fields by meaning, owner approves the fix" |
| 9 | **A page told the AI to delete every vendor.** | The trap text quoted large + the page | "It never takes orders from page text" |
| 10 | **Measured, not claimed.** | 4 numbers: 0 / 100% / $0 / 1 | "When it isn't sure, it stops and tells you why. What would you automate first?" |

**Ready-made files** (rebuild any time with `demo/scripts/make_linkedin.py`):
- `demo/out/linkedin/post1-thumbnail.png`: the video thumbnail for Post 1
- `demo/out/linkedin/post2-carousel.pdf`: upload this for Post 2 (LinkedIn → Add a document)
- `demo/out/linkedin/post2-slide-01.png … 10.png`: the same slides as images

**Post 2 text (copy-paste ready):**
```
"Can I trust it?" matters more than "can it do it?" when AI touches real business systems.

So before showing WatchOnce to anyone, I tried to break it 60 ways: renamed buttons, new layouts, look-alike buttons, and a page that told the AI to delete every vendor.

Result: 0 wrong clicks. When it couldn't be sure, it stopped and said why.

The slides walk through how it works, from one recording to 20 invoices with one approval 👉

Case study, code and demo in the first comment.

What would you automate first?

#AIAutomation #AIEngineering #Automation #QualityEngineering
```
**Document title** (LinkedIn asks for one): `How I made AI automation you can trust`

---

## 6. Checklist before you press Post

- [ ] Video uploaded natively, custom thumbnail added, captions on (they're burned in)
- [ ] Hook reads well when cut after 2 lines on a phone
- [ ] No links in the post body; links ready to paste in the first comment
- [ ] Numbers match the eval reports (0 wrong clicks / 60 cases, $0 AI per run)
- [ ] Portfolio page and GitHub README open correctly from a phone
- [ ] You're free for the next hour to reply to comments

## 7. After posting

- Reply to every comment with something specific, not just "Thanks!".
- If someone asks "why not just use the API?", answer with section "Why not just use the API?" from `02-enterprise-use-cases.md`.
- Share the post to relevant groups a day later with one new line of context, not a copy.
- Pin the post to your profile's Featured section.
