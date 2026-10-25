# ADR-0003: Deterministic runtime; AI only for compile and heal

- **Status:** Accepted · 2026-10-25

## Context
AI browser agents decide every action at run time with an LLM. That's flexible, but slow, costly per run, and non-deterministic, which is a poor fit for finance/HR operations that need repeatability and audits.

## Decision
Normal runs execute the spec with **zero LLM calls**. The LLM is used (1) once to understand a recording, (2) to write the SOP, and (3) only when a step can't be located, after cheaper deterministic fallbacks (L1 fallback locators, L2 fingerprint matching) fail. AI repairs are constrained to choosing among real page elements and are verified deterministically.

## Consequences
- ✅ $0 AI cost per normal run. Fast, predictable runs.
- ✅ Clear audit story: every AI-influenced change is a logged, approvable heal event.
- ✅ Smaller prompt-injection surface (the model never chooses actions or values at run time)
- ❌ Can't handle unexpected new screens (e.g. a new pop-up) without failing. Mitigation: v0.3 adds an optional "agentic recovery" mode using computer use, off by default.
