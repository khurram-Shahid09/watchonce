"""Self-healing for the runner: rungs L2 (fingerprint) and L3 (AI repair), then persisting
the fixes as a pending workflow version (docs/08 "Self-healing ladder").

Called by the executor only after every recorded locator failed (L0/L1). The run goes on
with the healed element; the workflow itself only changes when someone approves the
pending version (or heal_policy=auto allows it).
"""

import contextlib
import copy
import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from engine.compiler.locators import build_locators
from engine.compiler.recording import Element

from .healing import Ranked, action_fits, describe_change, l2_pick, l3_verify, rank, score
from .locate import ElementNotFound, Found, find

if TYPE_CHECKING:
    from .executor import Executor

log = logging.getLogger(__name__)

AGENT_JS = (Path(__file__).parent / "static" / "page-agent.js").read_text(encoding="utf-8")
MAX_AI_CANDIDATES = 40
HIGHLIGHT = "3px solid #2563eb"


class HealFailed(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Heal:
    step_id: str
    rung: str
    new_locators: list[dict[str, Any]]
    score: float
    confidence: float | None
    explanation: str
    is_checkpoint: bool
    event_id: str


# Fallbacks that say *where* or *what text*, not *what kind of element*: after a redesign
# they can land on something else (another button, a heading with the same words).
UNVERIFIED_KINDS = ("text", "css", "xpath")
FALLBACK_MIN = 0.5  # such a fallback must still look like the recorded element


def fallback_ok(found: Found, fingerprint: dict[str, Any] | None) -> bool:
    """A text / CSS / XPath fallback is only trusted if the element it found resembles the
    recorded one; otherwise the step goes to self-healing and its safety checks."""
    if found.index == 0 or found.spec.get("kind") not in UNVERIFIED_KINDS or not fingerprint:
        return True
    try:
        descriptor = found.locator.evaluate(
            f"el => {{ {AGENT_JS}\n return __watchonceAgent.describeOne(el); }}"
        )
        element = Element.model_validate(descriptor)
        if fingerprint.get("role") and element.role != fingerprint["role"]:
            return False  # a heading is never a stand-in for a button
        return score(fingerprint, element) >= FALLBACK_MIN
    except (PlaywrightError, ValueError):
        return False


def _candidates(page: Page) -> list[dict[str, Any]]:
    page.evaluate(f"() => {{ {AGENT_JS}\n window.__watchonceAgent = __watchonceAgent; }}")
    return page.evaluate("limit => window.__watchonceAgent.candidates(limit)", 150)


def _compact(r: Ranked, action: str) -> dict[str, Any]:
    el = r.element
    attrs = {
        k: v
        for k, v in el.attrs.items()
        if v and k in ("type", "name", "placeholder", "href", "aria-label", "title")
    }
    return {
        "id": r.id,
        "tag": el.tag,
        "role": el.role,
        "name": el.accessible_name,
        "text": el.text,
        "label": el.label_text,
        "attributes": attrs,
        "nearby_text": el.nearby_text[:4],
        "bbox": list(el.bbox),
        "score": r.score,
        "fits_action": action_fits(action, r.element),
    }


def _ask_ai(
    ex: "Executor", page: Page, step: dict[str, Any], ranked: list[Ranked]
) -> tuple[Ranked, float, str, Decimal]:
    from engine.llm import LLMError, get_provider, load_prompt
    from engine.llm.types import Image, RepairRequest
    from metering.service import budget_left, cost_of, record_call

    run = ex.run
    if not budget_left(run.org):
        raise HealFailed(
            "element_not_found",
            "the AI repair was skipped: this workspace reached its monthly AI budget",
        )
    index = next((n for n, s in enumerate(ex.steps) if s["id"] == step["id"]), 0)
    images = []
    recorded = step.get("screenshot_ref")
    recording = run.workflow.recording
    if recorded and recording is not None:
        with contextlib.suppress(Exception):
            from common.storage import get_storage

            images.append(
                Image(label="recorded", data=get_storage().get_bytes(recording.key(recorded)))
            )
    with contextlib.suppress(PlaywrightError):
        images.append(
            Image(
                label="now", data=page.screenshot(type="jpeg", quality=60), media_type="image/jpeg"
            )
        )

    provider = get_provider("repair")
    _, prompt_version = load_prompt("repair", provider.name)
    request = RepairRequest(
        intent=step["intent"],
        action=step["action"],
        fingerprint=step["target"]["fingerprint"],
        candidates=[_compact(r, step["action"]) for r in ranked[:MAX_AI_CANDIDATES]],
        previous_intent=ex.steps[index - 1]["intent"] if index > 0 else "",
        next_intent=ex.steps[index + 1]["intent"] if index + 1 < len(ex.steps) else "",
        page_url=page.url,
        images=images,
    )
    try:
        result, usage = provider.repair(request)
    except LLMError as exc:
        if exc.usage is not None:
            record_call(
                org=run.org,
                purpose="repair",
                usage=exc.usage,
                entity_id=run.id,
                prompt_version=prompt_version,
                error_code=exc.code,
            )
        raise HealFailed("element_not_found", f"the AI repair failed ({exc.message})") from None
    record_call(
        org=run.org, purpose="repair", usage=usage, entity_id=run.id, prompt_version=prompt_version
    )
    cost = cost_of(usage)

    if result.decision == "page_state_wrong":
        raise HealFailed(
            "page_state_wrong", f"the page isn't what this step expects: {result.explanation}"
        )
    if result.decision != "match":
        raise HealFailed(
            "element_not_found", f"no matching element on the page ({result.explanation})"
        )
    pick = next((r for r in ranked if r.id == result.candidate_id), None)
    if pick is None:  # the model must pick from the list; anything else is ignored
        raise HealFailed("heal_rejected", "the AI suggested an element that wasn't on the list")
    recorded_name = step["target"]["fingerprint"].get("accessible_name") or ""
    reason = l3_verify(step["action"], pick, result.confidence, ranked, recorded_name)
    if reason:
        name = pick.element.accessible_name or pick.element.text or pick.element.tag
        raise HealFailed("heal_rejected", f"the AI suggested “{name}” but {reason}")
    return pick, result.confidence, result.explanation, cost


def heal(ex: "Executor", page: Page, step: dict[str, Any]) -> Found:
    """Find the step's element on a changed page, or raise HealFailed."""
    from runs.models import HealEvent

    fingerprint = step["target"].get("fingerprint")
    if not fingerprint:
        raise HealFailed("element_not_found", "the step has no recorded fingerprint to heal from")
    try:
        ranked = rank(fingerprint, _candidates(page))
    except PlaywrightError as exc:
        raise HealFailed(
            "element_not_found", f"couldn't inspect the page ({str(exc).splitlines()[0]})"
        ) from None

    pick = l2_pick(step["action"], ranked)
    rung, confidence, cost = "L2", None, Decimal(0)
    explanation = describe_change(fingerprint, pick.element) if pick else ""
    if pick is None:
        pick, confidence, explanation, cost = _ask_ai(ex, page, step, ranked)
        rung = "L3"
        ex.run.llm_cost_usd = (ex.run.llm_cost_usd or Decimal(0)) + cost
        ex.run.save(update_fields=["llm_cost_usd", "updated_at"])

    # Locate it with freshly built locators (the same way compile does), so what gets saved
    # is known to work; fall back to the agent's mark if none is unique yet.
    new_locators = build_locators(pick.element)
    try:
        found = find(page, new_locators, 2000)
        found.healed = rung
    except ElementNotFound:
        found = Found(
            page.locator(f'[data-wo-candidate="{pick.id}"]'), 0, new_locators[0], healed=rung
        )

    with contextlib.suppress(PlaywrightError):
        found.locator.evaluate(
            f"e => {{ e.dataset.woHeal = e.style.outline; e.style.outline = '{HIGHLIGHT}'; }}"
        )
    after_ref = ex._screenshot(page, f"{ex.seq:03d}-{step['id']}-heal.jpg", step["id"])
    with contextlib.suppress(PlaywrightError):
        found.locator.evaluate(
            "e => { e.style.outline = e.dataset.woHeal || ''; delete e.dataset.woHeal; }"
        )

    event = HealEvent.objects.create(
        org_id=ex.run.org_id,
        run=ex.run,
        workflow_id=ex.run.workflow_id,
        step_id=step["id"],
        rung=rung,
        before_locators=step["target"]["locators"],
        after_locators=new_locators,
        score=pick.score,
        model_confidence=confidence,
        explanation=explanation[:2000],
        before_image_ref=step.get("screenshot_ref", "")[:64],
        after_image_ref=after_ref,
        cost_usd=cost,
    )
    ex.heals.append(
        Heal(
            step_id=step["id"],
            rung=rung,
            new_locators=new_locators,
            score=pick.score,
            confidence=confidence,
            explanation=explanation,
            is_checkpoint=(step.get("checkpoint") or {}).get("type") == "approval",
            event_id=event.id,
        )
    )
    ex.publish(
        {
            "type": "heal",
            "step_id": step["id"],
            "rung": rung,
            "score": pick.score,
            "explanation": explanation,
            "screenshot_ref": after_ref,
        }
    )
    log.info("run %s healed %s via %s (score %.2f)", ex.run.id, step["id"], rung, pick.score)
    return found


def persist(ex: "Executor") -> None:
    """One new workflow version with every heal of this run: pending approval, or active
    straight away when heal_policy=auto and every heal is confident and off checkpoints."""
    from django.utils import timezone

    from runs.models import HealEvent
    from workflows.models import WorkflowVersion
    from workflows.service import activate_version, create_version

    if not ex.heals:
        return
    base = ex.run.version
    spec = copy.deepcopy(base.spec)
    healed = {h.step_id: h for h in ex.heals}
    for step in spec["steps"]:
        h = healed.get(step["id"])
        if h is None:
            continue
        old = [loc for loc in step["target"]["locators"] if loc not in h.new_locators]
        step["target"]["locators"] = h.new_locators + old  # new first; old kept as fallbacks

    settings_ = spec.get("settings", {})
    threshold = settings_.get("auto_approve_heal_min_confidence", 0.9)
    auto = settings_.get("heal_policy") == "auto" and all(
        not h.is_checkpoint and (h.confidence if h.confidence is not None else h.score) >= threshold
        for h in ex.heals
    )
    version = create_version(
        base.workflow,
        spec,
        created_by="healer",
        sop_markdown=base.sop_markdown,
        warnings=[f"Self-healed {h.step_id} ({h.rung}): {h.explanation}" for h in ex.heals],
        parent=base,
        change_note=f"Self-healed {len(ex.heals)} step(s) in run {ex.run.id[-6:]}",
    )
    if auto:
        activate_version(version)
        decision = HealEvent.Decision.AUTO
    else:
        version.status = WorkflowVersion.Status.PENDING_HEAL
        version.save(update_fields=["status", "updated_at"])
        decision = HealEvent.Decision.PENDING
    HealEvent.objects.filter(id__in=[h.event_id for h in ex.heals]).update(
        resulting_version=version,
        decision=decision,
        decided_at=timezone.now() if auto else None,
    )


def discard_last(ex: "Executor", step_id: str, reason: str) -> None:
    """The healed step didn't do what the recording did: never save that heal."""
    from runs.models import HealEvent

    if ex.heals and ex.heals[-1].step_id == step_id:
        heal = ex.heals.pop()
        HealEvent.objects.filter(pk=heal.event_id).update(
            decision=HealEvent.Decision.REJECTED,
            explanation=f"{heal.explanation} Rejected: {reason}"[:2000],
        )
