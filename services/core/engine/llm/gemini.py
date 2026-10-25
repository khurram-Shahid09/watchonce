"""Gemini via the Google Gen AI SDK: JSON-schema response mode with inline images.

Local development uses the free tier, which may use inputs to improve Google's products:
only the fake Acme demo data goes here (docs/06-ai-pipeline.md, usage policy).
"""

import json
import time

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from .base import LLMError, load_prompt
from .messages import Part, sop_parts, understand_parts
from .types import (
    Image,
    SopRequest,
    SopResult,
    Understanding,
    UnderstandRequest,
    Usage,
    output_schema,
)

TIMEOUT_MS = 180_000  # a stuck request must not hold the compile worker
BLOCKED = {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}


def _contents(parts: list[Part]) -> list[types.Part]:
    return [
        types.Part.from_bytes(data=p.data, mime_type=p.media_type)
        if isinstance(p, Image)
        else types.Part.from_text(text=p)
        for p in parts
    ]


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str, api_key: str, fallbacks: tuple[str, ...] = ()) -> None:
        if not api_key:
            raise LLMError("llm_auth", "GEMINI_API_KEY is not set.")
        self.model = model
        # Tried in order when a model is overloaded (503) or rate limited (429), the way
        # Claude's server-side fallbacks work. Free-tier capacity varies a lot by model.
        self.models = [model, *(m for m in fallbacks if m != model)]
        self.client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS)
        )

    def understand(self, req: UnderstandRequest) -> tuple[Understanding, Usage]:
        return self._call("understand", understand_parts(req), Understanding)

    def write_sop(self, req: SopRequest) -> tuple[SopResult, Usage]:
        return self._call("sop", sop_parts(req), SopResult)

    def _call[T: BaseModel](
        self, stage: str, parts: list[Part], result_type: type[T]
    ) -> tuple[T, Usage]:
        system, _version = load_prompt(stage, self.name)
        contents = _contents(parts)
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=output_schema(result_type),
            max_output_tokens=32000,
        )
        busy: LLMError | None = None
        for model in self.models:
            usage = Usage(provider=self.name, model=model)
            started = time.monotonic()
            try:
                response = self.client.models.generate_content(
                    model=model, contents=contents, config=config
                )
                break
            except errors.ClientError as exc:
                if exc.code == 429:
                    busy = LLMError("llm_unavailable", "Gemini rate limit reached.", retryable=True)
                    continue
                if exc.code in (401, 403):
                    raise LLMError("llm_auth", "The Gemini API key was rejected.") from exc
                raise LLMError(
                    "llm_bad_request", f"Gemini rejected the request ({exc.code})."
                ) from exc
            except errors.ServerError:
                busy = LLMError("llm_unavailable", "Gemini is busy.", retryable=True)
                continue
            except httpx.TimeoutException:
                busy = LLMError("llm_unavailable", "Gemini didn't answer in time.", retryable=True)
                continue
            except (httpx.TransportError, OSError) as exc:  # network
                raise LLMError("llm_unavailable", "Can't reach Gemini.", retryable=True) from exc
        else:
            raise busy or LLMError("llm_unavailable", "Gemini is unavailable.", retryable=True)

        usage.latency_ms = int((time.monotonic() - started) * 1000)
        meta = response.usage_metadata
        if meta is not None:
            usage.input_tokens = meta.prompt_token_count or 0
            usage.cache_read_tokens = meta.cached_content_token_count or 0
            usage.output_tokens = (meta.candidates_token_count or 0) + (
                meta.thoughts_token_count or 0
            )
        candidate = response.candidates[0] if response.candidates else None
        finish = candidate.finish_reason.value if candidate and candidate.finish_reason else ""
        usage.stop_reason = finish
        if candidate is None or finish in BLOCKED:
            raise LLMError(
                "llm_refusal",
                "The AI declined to process this recording. Review its contents and try again.",
                usage=usage,
            )
        if finish == "MAX_TOKENS":
            raise LLMError("llm_truncated", "The AI answer was cut off (too long).", usage=usage)
        try:
            return result_type.model_validate(json.loads(response.text or "")), usage
        except (ValueError, ValidationError) as exc:
            raise LLMError(
                "llm_invalid_output", f"Unexpected AI answer: {exc}", usage=usage
            ) from exc
