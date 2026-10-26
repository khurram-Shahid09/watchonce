"""E1 · compile quality (docs/12-testing-and-evals.md).

For every golden recording: compile it, compare the steps with the answer key, then replay
the compiled workflow (checkpoints auto-approved) against the unmodified site.
"""

import json
import statistics
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from .harness import (
    REPORT_DIR,
    Golden,
    align,
    chromium,
    compile_golden,
    eval_workspace,
    load_goldens,
    replay,
    replay_inputs,
    save_logins,
    set_portal_variant,
    step_name,
    uses_input,
)


@dataclass
class CaseResult:
    id: str
    compiled_by: str = ""
    compile_error: str = ""
    expected_steps: int = 0
    compiled_steps: int = 0
    matched_steps: int = 0
    input_tp: int = 0
    input_fp: int = 0
    input_fn: int = 0
    checkpoints_expected: int = 0
    checkpoints_found: int = 0
    checkpoints_extra: int = 0
    replay_status: str = ""
    replay_error: str = ""
    compile_seconds: float = 0.0
    replay_seconds: float = 0.0
    cost_usd: float = 0.0
    tokens: int = 0
    notes: list[str] = field(default_factory=list)


def evaluate(golden: Golden, org, browser, *, run_replay: bool = True) -> CaseResult:
    expected = golden.expected
    result = CaseResult(golden.id, expected_steps=len(expected["steps"]))
    compiled = compile_golden(org, golden)
    result.compile_seconds = round(compiled.seconds, 2)
    result.cost_usd, result.tokens = compiled.cost_usd, compiled.tokens
    if compiled.error:
        result.compile_error = compiled.error
        result.input_fn = len(expected["input_steps"])
        result.checkpoints_expected = len(expected["checkpoints"])
        return result

    result.compiled_by = compiled.by
    steps = compiled.spec["steps"]
    result.compiled_steps = len(steps)
    pairs = align(expected["steps"], steps)
    result.matched_steps = len(pairs)
    matched = {j: expected["steps"][i][1] for i, j in pairs}
    for j, step in enumerate(steps):
        if j not in matched:
            result.notes.append(f"extra step {step['id']}: {step['action']} {step_name(step)!r}")
    for i, exp in enumerate(expected["steps"]):
        if i not in {i for i, _ in pairs}:
            result.notes.append(f"missing step: {exp[0]} {exp[1]!r}")

    truth = {n.lower() for n in expected["input_steps"]}
    predicted = {
        (matched.get(j) or step_name(step) or step["id"]).lower()
        for j, step in enumerate(steps)
        if uses_input(step)
    }
    result.input_tp = len(predicted & truth)
    result.input_fp = len(predicted - truth)
    result.input_fn = len(truth - predicted)
    for name in sorted(predicted - truth):
        result.notes.append(f"made an input that should be fixed: {name!r}")
    for name in sorted(truth - predicted):
        result.notes.append(f"kept a fixed value that should be an input: {name!r}")

    guarded = {
        (matched.get(j) or step_name(step) or "").lower()
        for j, step in enumerate(steps)
        if (step.get("checkpoint") or {}).get("type") == "approval"
    }
    wanted = {n.lower() for n in expected["checkpoints"]}
    result.checkpoints_expected = len(wanted)
    result.checkpoints_found = len(wanted & guarded)
    result.checkpoints_extra = len(guarded - wanted)
    for name in sorted(wanted - guarded):
        result.notes.append(f"MISSED CHECKPOINT: {name!r}")

    if run_replay:
        save_logins(org, compiled.spec, expected.get("login", {}))
        inputs = replay_inputs(compiled.spec, expected.get("replay", {}))
        outcome = replay(org, compiled.workflow.active_version, inputs, browser)
        result.replay_status = outcome.status
        result.replay_error = outcome.error
        result.replay_seconds = round(outcome.seconds, 2)
    return result


def _ratio(a: int, b: int) -> float | None:
    return a / b if b else None


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    ok = [r for r in results if not r.compile_error]
    matched = sum(r.matched_steps for r in ok)
    precision = _ratio(matched, sum(r.compiled_steps for r in ok))
    recall = _ratio(matched, sum(r.expected_steps for r in results))
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else 0.0
    tp, fp, fn = (sum(getattr(r, k) for r in results) for k in ("input_tp", "input_fp", "input_fn"))
    replayed = [r for r in results if r.replay_status]
    compile_times = sorted(r.compile_seconds for r in results)
    return {
        "cases": len(results),
        "compiled": len(ok),
        "step_precision": precision,
        "step_recall": recall,
        "step_f1": f1,
        "input_precision": _ratio(tp, tp + fp),
        "input_recall": _ratio(tp, tp + fn),
        "checkpoint_recall": _ratio(
            sum(r.checkpoints_found for r in results), sum(r.checkpoints_expected for r in results)
        ),
        "extra_checkpoints": sum(r.checkpoints_extra for r in results),
        "replay_success": _ratio(
            sum(r.replay_status == "succeeded" for r in replayed), len(replayed)
        ),
        "compile_p50_s": round(statistics.median(compile_times), 2) if compile_times else None,
        "compile_max_s": compile_times[-1] if compile_times else None,
        "cost_usd_total": round(sum(r.cost_usd for r in results), 4),
        "cost_usd_per_compile": round(sum(r.cost_usd for r in results) / len(results), 4)
        if results
        else None,
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def _verdict(value: float | None, target: float) -> str:
    return "n/a" if value is None else ("pass" if value >= target else "**FAIL**")


def render(summary: dict[str, Any], results: list[CaseResult], provider: str) -> str:
    s = summary
    lines = [
        f"# E1 · Compile eval, {date.today().isoformat()}",
        "",
        f"Provider: `{provider}`. {s['cases']} golden recordings, {s['compiled']} compiled.",
        "Replays run against the unmodified sites with new input values; checkpoints are",
        "approved automatically.",
        "",
        "| Metric | Result | Target |",
        "|---|---|---|",
        f"| Step alignment F1 | {_pct(s['step_f1'])} (precision {_pct(s['step_precision'])}, "
        f"recall {_pct(s['step_recall'])}) | — |",
        f"| Input detection | precision {_pct(s['input_precision'])}, "
        f"recall {_pct(s['input_recall'])} | — |",
        f"| Checkpoint recall | {_pct(s['checkpoint_recall'])} "
        f"({s['extra_checkpoints']} extra) | 100%: {_verdict(s['checkpoint_recall'], 1.0)} |",
        f"| Replay success | {_pct(s['replay_success'])} | ≥ 90%: "
        f"{_verdict(s['replay_success'], 0.9)} |",
        f"| Compile time | p50 {s['compile_p50_s']}s, max {s['compile_max_s']}s | — |",
        f"| AI cost | ${s['cost_usd_total']} total, ${s['cost_usd_per_compile']} per compile | — |",
        "",
        "## Cases",
        "",
        "| Golden | Steps (matched / expected / compiled) | Inputs TP·FP·FN | Checkpoints | Replay |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        if r.compile_error:
            lines.append(f"| {r.id} | compile failed: {r.compile_error} | | | |")
            continue
        replay_cell = r.replay_status or "skipped"
        if r.replay_error:
            replay_cell += f" ({r.replay_error[:80]})"
        lines.append(
            f"| {r.id} | {r.matched_steps} / {r.expected_steps} / {r.compiled_steps} | "
            f"{r.input_tp}·{r.input_fp}·{r.input_fn} | "
            f"{r.checkpoints_found}/{r.checkpoints_expected}"
            f"{f' (+{r.checkpoints_extra})' if r.checkpoints_extra else ''} | {replay_cell} |"
        )
    notes = [(r.id, n) for r in results for n in r.notes]
    if notes:
        lines += ["", "## Notes", ""]
        lines += [f"- `{case}`: {note}" for case, note in notes]
    return "\n".join(lines) + "\n"


def run_compile_eval(
    only: list[str] | None = None, *, run_replay: bool = True, keep: bool = False
) -> tuple[dict[str, Any], list[CaseResult], str]:
    from django.conf import settings

    goldens = load_goldens(only)
    if run_replay and any(
        "localhost:3001" in g.recording["recording"]["startUrl"] for g in goldens
    ):
        set_portal_variant("original")
    results: list[CaseResult] = []
    with eval_workspace("Evals: compile", keep=keep) as org, chromium() as browser:
        for golden in goldens:
            print(f"  {golden.id} ...", flush=True)
            results.append(evaluate(golden, org, browser, run_replay=run_replay))
    summary = summarize(results)
    provider = settings.LLM_PROVIDER
    report = render(summary, results, provider)
    REPORT_DIR.mkdir(exist_ok=True)
    stem = REPORT_DIR / f"compile-{date.today().isoformat()}"
    stem.with_suffix(".md").write_text(report, encoding="utf-8")
    stem.with_suffix(".json").write_text(
        json.dumps(
            {"provider": provider, "summary": summary, "cases": [asdict(r) for r in results]},
            indent=2,
        ),
        encoding="utf-8",
    )
    return summary, results, str(stem.with_suffix(".md"))
