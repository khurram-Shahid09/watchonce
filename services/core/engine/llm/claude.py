"""Claude via the Anthropic SDK: structured outputs, prompt caching on the stable system
prompt, server-side refusal fallbacks, and stop_reason checks (docs/06-ai-pipeline.md)."""

import base64
import json
import time

import anthropic
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaOutputConfigParam,
)
from pydantic import BaseModel, ValidationError

from .base import LLMError, load_prompt
from .messages import Part, author_parts, repair_parts, sop_parts, understand_parts
from .types import (
    AuthorAction,
    AuthorRequest,
    Image,
    RepairRequest,
    RepairResult,
    SopRequest,
    SopResult,
    Understanding,
    UnderstandRequest,
    Usage,
    output_schema,
)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
EFFORTS = ("low", "medium", "high", "xhigh", "max")


def _content(parts: list[Part]) -> list[BetaContentBlockParam]:
    blocks: list[BetaContentBlockParam] = []
    for part in parts:
        if isinstance(part, Image):
            data = base64.standard_b64encode(part.data).decode()
            blocks.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": part.media_type, "data": data},
                }
            )
        else:
            blocks.append({"type": "text", "text": part})
    return blocks


class ClaudeProvider:
    name = "claude"

    def __init__(
        self, model: str, api_key: str = "", efforts: dict[str, str] | None = None
    ) -> None:
        self.model = model
        self.efforts = {
            "understand": "high",
            "sop": "medium",
            "author": "medium",
            **(efforts or {}),
        }
        # No key: the SDK falls back to ANTHROPIC_AUTH_TOKEN / an `ant auth login` profile.
        self.client = anthropic.Anthropic(api_key=api_key or None, timeout=300.0)

    def understand(self, req: UnderstandRequest) -> tuple[Understanding, Usage]:
        return self._call("understand", understand_parts(req), Understanding)

    def write_sop(self, req: SopRequest) -> tuple[SopResult, Usage]:
        return self._call("sop", sop_parts(req), SopResult)

    def repair(self, req: RepairRequest) -> tuple[RepairResult, Usage]:
        return self._call("repair", repair_parts(req), RepairResult)

    def author(self, req: AuthorRequest) -> tuple[AuthorAction, Usage]:
        return self._call("author", author_parts(req), AuthorAction)

    def _call[T: BaseModel](
        self, stage: str, parts: list[Part], result_type: type[T]
    ) -> tuple[T, Usage]:
        system, _version = load_prompt(stage, self.name)
        usage = Usage(provider=self.name, model=self.model)
        effort = self.efforts[stage]
        if effort not in EFFORTS:
            raise LLMError("llm_config", f"Unknown Claude effort {effort!r} for {stage}.")
        output_config: BetaOutputConfigParam = {
            "effort": effort,  # type: ignore[typeddict-item]  # checked against EFFORTS above
            "format": {"type": "json_schema", "schema": output_schema(result_type)},
        }
        started = time.monotonic()
        try:
            with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=32000,
                betas=[FALLBACK_BETA],
                fallbacks="default",
                # Stable prefix first so repeat compiles hit the cache.
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": _content(parts)}],
                output_config=output_config,
            ) as stream:
                message = stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise LLMError("llm_auth", "The Claude API key was rejected.") from exc
        except anthropic.BadRequestError as exc:
            raise LLMError(
                "llm_bad_request", f"Claude rejected the request: {exc.message}"
            ) from exc
        except (anthropic.RateLimitError, anthropic.InternalServerError) as exc:
            raise LLMError("llm_unavailable", "Claude is busy.", retryable=True) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("llm_unavailable", "Can't reach Claude.", retryable=True) from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(
                "llm_error",
                f"Claude API error {exc.status_code}.",
                retryable=exc.status_code >= 500,
            ) from exc

        usage.latency_ms = int((time.monotonic() - started) * 1000)
        usage.model = message.model  # the fallback model if one served the request
        usage.input_tokens = message.usage.input_tokens + (
            message.usage.cache_creation_input_tokens or 0
        )
        usage.cache_read_tokens = message.usage.cache_read_input_tokens or 0
        usage.output_tokens = message.usage.output_tokens
        usage.stop_reason = str(message.stop_reason)

        if message.stop_reason == "refusal":
            raise LLMError(
                "llm_refusal",
                "The AI declined to process this recording. Review its contents and try again.",
                usage=usage,
            )
        if message.stop_reason == "max_tokens":
            raise LLMError("llm_truncated", "The AI answer was cut off (too long).", usage=usage)

        text = "".join(block.text for block in message.content if block.type == "text")
        try:
            return result_type.model_validate(json.loads(text)), usage
        except (ValueError, ValidationError) as exc:
            raise LLMError(
                "llm_invalid_output", f"Unexpected AI answer: {exc}", usage=usage
            ) from exc
