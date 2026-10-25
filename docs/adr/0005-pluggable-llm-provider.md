# ADR-0005: Pluggable LLM provider (Claude and Gemini)

- **Status:** Accepted · 2026-10-25

## Context
Development and evals make many AI calls. A free Gemini tier makes development cost nothing, while Claude is the preferred production model. Free tiers may allow the provider to use inputs to improve its products, which is unacceptable for real customer screenshots. Enterprise buyers also ask which model is used and why.

## Decision
All AI calls (understand, write SOP, repair) go through one `LLMProvider` interface with `ClaudeProvider` and `GeminiProvider` implementations, selected by `LLM_PROVIDER` (overridable per stage). Outputs are validated into the same Pydantic types regardless of provider. Policy: the free tier is used only with fake demo data. Demos, pilots and real data use a paid tier (Claude by default). Eval E4 compares providers side by side.

## Consequences
- ✅ Zero-cost development; no vendor lock-in
- ✅ A published model comparison (quality, cost, latency) strengthens the engineering story
- ✅ Per-stage choice (e.g. a different provider for SOP writing) if evals support it
- ❌ Two integrations to maintain; provider-specific features (prompt caching, refusal fallbacks) are implemented per provider
- ❌ Prompts may need small per-provider overlays
