# Evals

Offline checks of the compiler (E1) and the self-healing runner (E2), from
[docs/12-testing-and-evals.md](../docs/12-testing-and-evals.md).

| Path | What |
|---|---|
| `goldens.py` | Golden tasks: how each is performed, and its hand-written answer key |
| `golden/<id>/recording.json` | The recording, as exported by the extension (screenshots included; passwords masked) |
| `golden/<id>/expected.json` | The answer key, copied from `goldens.py` |
| `reports/` | One markdown + JSON report per eval run |

## Run

Needs the Docker stack (Postgres) and the Acme portal on :3001 (`pnpm --filter @watchonce/acme-portal start`).

```
pnpm eval:compile     # E1: compile each golden, score it, replay it
pnpm eval:heal        # E2: replay workflows against portal mutations M1–M8
```

The provider is whatever `LLM_PROVIDER` says (`fake` runs offline at no cost).

## Re-record the goldens

```
pnpm --filter @watchonce/extension build:e2e
cd services/core && uv run --with playwright python -I ../../evals/make_goldens.py [ids...]
pnpm --filter @watchonce/extension build      # back to the normal extension
```
