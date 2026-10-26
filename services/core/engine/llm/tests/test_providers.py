import json
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from google.genai import errors as genai_errors

from engine.llm import LLMError, load_prompt
from engine.llm.claude import FALLBACK_BETA, ClaudeProvider
from engine.llm.fake import FakeProvider
from engine.llm.gemini import GeminiProvider
from engine.llm.types import Image, SopRequest, Understanding, UnderstandRequest, output_schema

CANDIDATES: list[dict[str, Any]] = [
    {"id": "c1", "action": "navigate", "url": "http://acme.test/login"},
    {"id": "c2", "action": "fill", "url": "http://acme.test/login", "element": {"role": "textbox", "label": "Password"}, "value": "__SECRET__", "value_masked": True},
    {"id": "c3", "action": "fill", "url": "http://acme.test/inv", "element": {"role": "textbox", "label": "Due date"}, "value": "11/15/2026"},
    {"id": "c4", "action": "click", "url": "http://acme.test/inv", "element": {"role": "button", "name": "Submit"}},
]  # fmt: skip
ANSWER = {
    "workflow_name": "W",
    "summary": "S",
    "steps": [
        {"candidate_id": "c1", "keep": True, "drop_reason": "", "intent": "Open", "value_source": {"kind": "none", "input_name": "", "secret_name": "", "secret_field": ""}, "checkpoint": False, "checkpoint_reason": "", "assert_text_after": ""}
    ],
    "inputs": [],
    "outputs": [],
    "warnings": [],
}  # fmt: skip


def walk(node: Any):
    yield node
    if isinstance(node, dict):
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


def test_output_schema_is_closed_and_self_contained() -> None:
    schema = output_schema(Understanding)
    text = json.dumps(schema)
    assert "$ref" not in text and "$defs" not in text
    objects = [n for n in walk(schema) if isinstance(n, dict) and n.get("type") == "object"]
    assert len(objects) >= 5
    for obj in objects:  # what structured-output modes require
        assert obj["additionalProperties"] is False
        assert sorted(obj["required"]) == sorted(obj["properties"])


def test_prompts_have_versions() -> None:
    for stage in ("understand", "sop"):
        text, version = load_prompt(stage, "claude")
        assert version == {"understand": "understand-v2", "sop": "sop-v1"}[stage]
        assert "data" in text and "instructions" in text  # the injection guard is present


def test_fake_provider_follows_the_rules() -> None:
    result, usage = FakeProvider().understand(UnderstandRequest("Create invoice", CANDIDATES))
    by_id = {s.candidate_id: s for s in result.steps}
    assert by_id["c2"].value_source.kind == "secret"
    assert by_id["c3"].value_source.input_name == "due_date"
    assert result.inputs[0].type == "date" and result.inputs[0].example == "2026-11-15"
    assert by_id["c4"].checkpoint
    assert usage.provider == "fake"


def test_fake_provider_only_takes_a_username_from_the_login_page() -> None:
    candidates = [
        *CANDIDATES[:2],
        {"id": "c5", "action": "fill", "url": "http://acme.test/login", "element": {"role": "textbox", "label": "Email"}, "value": "sara@acme.test"},
        {"id": "c6", "action": "fill", "url": "http://acme.test/vendors", "element": {"role": "textbox", "label": "Email"}, "value": "ap@globex.example"},
        {"id": "c7", "action": "click", "url": "http://acme.test/approvals", "element": {"role": "button", "name": "Reject"}},
    ]  # fmt: skip
    result, _ = FakeProvider().understand(UnderstandRequest("Add vendor", candidates))
    by_id = {s.candidate_id: s for s in result.steps}
    assert by_id["c5"].value_source.secret_field == "username"
    assert by_id["c6"].value_source.kind == "input"  # a form's email, not the login
    assert by_id["c7"].checkpoint  # rejecting is a decision, too


def test_fake_repair_never_guesses_between_look_alikes() -> None:
    from engine.llm.types import RepairRequest

    def ask(*scores: float) -> str:
        candidates = [
            {"id": f"e{n}", "score": s, "fits_action": True} for n, s in enumerate(scores)
        ]
        request = RepairRequest(intent="Click New invoice", action="click", fingerprint={},
                                candidates=candidates, previous_intent="", next_intent="",
                                page_url="http://acme.test/", images=[])  # fmt: skip
        return FakeProvider().repair(request)[0].decision

    assert ask(0.7, 0.4) == "match"
    assert ask(0.61, 0.59) == "no_match"  # too close to call
    assert ask(0.45) == "no_match"


# --- Claude (SDK mocked at the client boundary) ---


class FakeStream:
    def __init__(self, message: Any) -> None:
        self.message = message

    def __enter__(self) -> "FakeStream":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def get_final_message(self) -> Any:
        return self.message


def claude_message(stop_reason: str, text: str = "") -> Any:
    return SimpleNamespace(
        model="claude-opus-5-5",
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=text)] if text else [],
        usage=SimpleNamespace(input_tokens=1000, output_tokens=200, cache_creation_input_tokens=0, cache_read_input_tokens=500),
    )  # fmt: skip


def claude_with(message: Any) -> tuple[ClaudeProvider, dict[str, Any]]:
    provider = ClaudeProvider("claude-opus-5-5", api_key="sk-test")
    sent: dict[str, Any] = {}

    def stream(**kwargs: Any) -> FakeStream:
        sent.update(kwargs)
        return FakeStream(message)

    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream)))  # type: ignore[assignment]
    return provider, sent


def test_claude_request_shape_and_parsing() -> None:
    provider, sent = claude_with(claude_message("end_turn", json.dumps(ANSWER)))
    image = Image(label="c1", data=b"RIFFxxxxWEBP")
    result, usage = provider.understand(UnderstandRequest("Do it", CANDIDATES[:1], images=[image]))

    assert result.workflow_name == "W"
    assert usage.input_tokens == 1000 and usage.cache_read_tokens == 500
    assert sent["model"] == "claude-opus-5-5"
    assert sent["fallbacks"] == "default" and FALLBACK_BETA in sent["betas"]
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert sent["output_config"]["effort"] == "high"
    assert sent["output_config"]["format"]["type"] == "json_schema"
    content = sent["messages"][0]["content"]
    assert any(b["type"] == "image" and b["source"]["media_type"] == "image/webp" for b in content)
    assert "temperature" not in sent


def test_claude_refusal_and_truncation_are_errors_with_usage() -> None:
    provider, _ = claude_with(claude_message("refusal"))
    with pytest.raises(LLMError) as exc:
        provider.understand(UnderstandRequest("x", CANDIDATES[:1]))
    assert exc.value.code == "llm_refusal" and exc.value.usage is not None

    provider, _ = claude_with(claude_message("max_tokens", '{"workflow_'))
    with pytest.raises(LLMError, match="cut off"):
        provider.write_sop(SopRequest(spec={"steps": []}))


def test_claude_rate_limit_is_retryable() -> None:
    provider = ClaudeProvider("claude-opus-5-5", api_key="sk-test")
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.RateLimitError(
        "slow down", response=httpx2.Response(429, request=request), body=None
    )

    def stream(**_: Any) -> FakeStream:
        raise error

    provider.client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream)))  # type: ignore[assignment]
    with pytest.raises(LLMError) as exc:
        provider.understand(UnderstandRequest("x", CANDIDATES[:1]))
    assert exc.value.retryable


# --- Gemini ---


def gemini_response(text: str, finish: str = "STOP") -> Any:
    return SimpleNamespace(
        text=text,
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(value=finish))],
        usage_metadata=SimpleNamespace(prompt_token_count=900, candidates_token_count=100, thoughts_token_count=50, cached_content_token_count=0),
    )  # fmt: skip


def test_gemini_falls_back_to_the_next_model_when_overloaded() -> None:
    provider = GeminiProvider("gemini-new", "key", fallbacks=("gemini-steady",))
    tried: list[str] = []

    def generate_content(*, model: str, contents: Any, config: Any) -> Any:
        tried.append(model)
        if model == "gemini-new":
            raise genai_errors.ServerError(
                503, {"error": {"message": "high demand", "status": "UNAVAILABLE"}}
            )
        assert config.response_json_schema == output_schema(Understanding)
        return gemini_response(json.dumps(ANSWER))

    provider.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))  # type: ignore[assignment]
    result, usage = provider.understand(UnderstandRequest("x", CANDIDATES[:1]))
    assert tried == ["gemini-new", "gemini-steady"]
    assert usage.model == "gemini-steady" and usage.output_tokens == 150
    assert result.summary == "S"


def test_gemini_safety_block_is_a_refusal() -> None:
    provider = GeminiProvider("gemini-new", "key")
    provider.client = SimpleNamespace(
        models=SimpleNamespace(generate_content=lambda **_: gemini_response("", "SAFETY"))
    )  # type: ignore[assignment]
    with pytest.raises(LLMError) as exc:
        provider.understand(UnderstandRequest("x", CANDIDATES[:1]))
    assert exc.value.code == "llm_refusal"


def test_gemini_all_models_busy_is_retryable() -> None:
    provider = GeminiProvider("a", "key", fallbacks=("b",))

    def generate_content(**_: Any) -> Any:
        raise genai_errors.ServerError(503, {"error": {"message": "busy", "status": "UNAVAILABLE"}})

    provider.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))  # type: ignore[assignment]
    with pytest.raises(LLMError) as exc:
        provider.understand(UnderstandRequest("x", CANDIDATES[:1]))
    assert exc.value.retryable


def test_gemini_timeout_moves_on_to_the_next_model() -> None:
    import httpx

    provider = GeminiProvider("slow", "key", fallbacks=("fast",))

    def generate_content(*, model: str, contents: Any, config: Any) -> Any:
        if model == "slow":
            raise httpx.ReadTimeout("no answer")
        return gemini_response(json.dumps(ANSWER))

    provider.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))  # type: ignore[assignment]
    _, usage = provider.understand(UnderstandRequest("x", CANDIDATES[:1]))
    assert usage.model == "fast"
