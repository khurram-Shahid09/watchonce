# ADR-0002: A JSON workflow spec is the source of truth; code is an export

- **Status:** Accepted · 2026-10-25

## Context
The obvious approach is "AI writes a Playwright script". But generated code is hard to edit safely in a UI, hard to validate, hard to patch one step at a time (healing), and running LLM-written code on a server is a security risk.

## Decision
The compiler produces a **declarative JSON spec** (see [05](../05-workflow-spec.md)) validated by JSON Schema. A trusted runner interprets it. Playwright scripts and SOPs are **generated deterministically from the spec** (templates, not LLM).

## Consequences
- ✅ No arbitrary code execution. Templating is restricted to filters.
- ✅ Step-level editing, diffing, versioning and healing
- ✅ The same spec drives the SOP, the live view, analytics and exports
- ❌ Less expressive than code. Branching/loops must be added to the spec deliberately (v0.3).
