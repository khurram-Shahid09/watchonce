"""Provider-neutral requests and results for the three AI stages (docs/06-ai-pipeline.md).

The output models double as the structured-output schema sent to the providers, so every
field is required and objects are closed: that is what JSON-schema response modes accept.
Use "" or [] for "not applicable" instead of null.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Understand ---


class ValueSource(_Closed):
    kind: Literal["input", "constant", "secret", "none"]
    input_name: str  # kind=input: snake_case name declared in inputs[]
    secret_name: str  # kind=secret: e.g. "acme_login"
    secret_field: str  # kind=secret: e.g. "password"


class StepUnderstanding(_Closed):
    candidate_id: str
    keep: bool
    drop_reason: str
    intent: str  # imperative, human readable: "Choose the vendor"
    value_source: ValueSource
    checkpoint: bool
    checkpoint_reason: str
    assert_text_after: str  # text that proves the step worked, or ""


class InputUnderstanding(_Closed):
    name: str
    type: Literal["string", "number", "integer", "boolean", "date"]
    example: str
    description: str
    format_hint: str  # how the app expects it, e.g. "MM/DD/YYYY", or ""


class OutputUnderstanding(_Closed):
    name: str
    type: Literal["string", "number"]
    description: str
    after_candidate_id: str  # read once this step has run
    from_candidate_id: str  # element holding the value, or "" to search the page text
    pattern: str  # regex for the value, e.g. "INV-\\d+", or ""


class Understanding(_Closed):
    workflow_name: str
    summary: str
    steps: list[StepUnderstanding]
    inputs: list[InputUnderstanding]
    outputs: list[OutputUnderstanding]
    warnings: list[str]


# --- SOP ---


class SopResult(_Closed):
    markdown: str


# --- Requests ---


@dataclass(frozen=True)
class Image:
    label: str  # e.g. "c7" (screenshot before candidate c7) or "final"
    data: bytes
    media_type: Literal["image/jpeg", "image/png", "image/gif", "image/webp"] = "image/webp"


@dataclass
class UnderstandRequest:
    description: str
    candidates: list[dict[str, Any]]  # compact candidates (engine/compiler/prompting.py)
    images: list[Image] = field(default_factory=list)
    feedback: list[str] = field(default_factory=list)  # validator errors from a previous try


@dataclass
class SopRequest:
    spec: dict[str, Any]
    images: list[Image] = field(default_factory=list)


@dataclass
class Usage:
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    latency_ms: int = 0
    stop_reason: str = ""


def output_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON schema with ``$defs`` inlined and titles removed (both providers accept it)."""
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(deepcopy(defs[node["$ref"].rsplit("/", 1)[-1]]))
            return {k: walk(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


# --- Repair (self-healing L3) ---


class RepairResult(_Closed):
    decision: Literal["match", "no_match", "page_state_wrong"]
    candidate_id: str  # one of the given ids, or "" when there is no match
    confidence: float
    explanation: str


class AuthorAction(_Closed):
    """The authoring agent's next move (engine/author). Every field is required; use "" when
    it doesn't apply."""

    status: Literal["act", "done", "stuck"]
    action: Literal[
        "click",
        "fill",
        "select",
        "check",
        "uncheck",
        "press",
        "navigate",
        "wait_for",
        "extract",
        "",
    ]
    candidate_id: str  # one of the given ids; "" for navigate, wait_for and a page-wide press
    intent: str  # imperative, human readable: "Enter the reference number"
    value_kind: Literal["literal", "input", "secret", "none"]
    value: str  # literal text, or the example value of an input
    input_name: str  # value_kind=input: snake_case name
    input_type: Literal["string", "number", "date", ""]
    secret_name: str  # value_kind=secret: a saved login's name
    secret_field: str  # value_kind=secret: e.g. "password"
    key: str  # press: e.g. "Enter"
    url: str  # navigate: absolute URL
    wait_text: str  # wait_for: text that shows the page is ready
    output_name: str  # extract: snake_case name of the value read
    output_type: Literal["string", "number", ""]
    pattern: str  # extract: optional regex for the value
    risky: bool  # submits, pays, deletes, sends or posts something
    explanation: str  # one sentence: why this step, or why done / stuck
    workflow_name: str  # done: a short name for the whole task
    summary: str  # done: one sentence on what the workflow does


@dataclass
class AuthorRequest:
    instructions: str
    start_url: str
    page_url: str
    page_title: str
    candidates: list[dict[str, Any]]  # compact descriptors of visible interactive elements
    page_text: str  # visible text of the page, trimmed
    history: list[dict[str, Any]]  # steps done so far: intent, action, result
    secrets: list[dict[str, Any]]  # saved logins usable here: name and field names only
    images: list[Image] = field(default_factory=list)  # "now": the current page


@dataclass
class RepairRequest:
    intent: str
    action: str
    fingerprint: dict[str, Any]
    candidates: list[dict[str, Any]]  # compact, pre-ranked by fingerprint score
    previous_intent: str = ""
    next_intent: str = ""
    page_url: str = ""
    images: list[Image] = field(default_factory=list)  # "recorded" frame, "now" screenshot
