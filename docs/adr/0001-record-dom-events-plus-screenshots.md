# ADR-0001: Record DOM events + screenshots, not video only

- **Status:** Accepted · 2026-10-25

## Context
The product promise is "screen-record a task once". A pure video recording (screen capture → vision model) works on any app, but it has to *guess* which element was clicked, can't see hidden attributes (ids, roles, labels), and produces brittle coordinate-based replays.

## Decision
For the MVP, record through a **browser extension** that captures structured DOM events (with rich element descriptors and uniqueness flags) **plus** a screenshot before each action. Video-only/desktop recording is deferred to v0.3, where it pairs with a computer-use executor.

## Consequences
- ✅ Accurate targets and robust multi-strategy locators, the foundation of self-healing
- ✅ Far fewer tokens than processing a video (one frame per step, not 30 fps)
- ✅ Masking of password fields at the source
- ❌ Limited to Chromium browsers and DOM-based web apps in the MVP
- ❌ Users install an extension (acceptable: enterprise IT can deploy it by policy)
