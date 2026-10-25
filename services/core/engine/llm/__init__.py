"""AI providers behind one interface (docs/06-ai-pipeline.md "LLM provider abstraction").

``get_provider("understand")`` reads ``LLM_PROVIDER`` (claude | gemini | fake), overridable
per stage with ``LLM_PROVIDER_<STAGE>`` (e.g. ``LLM_PROVIDER_SOP=fake``).
"""

from django.conf import settings

from .base import LLMError, LLMProvider, load_prompt

__all__ = ["LLMError", "LLMProvider", "get_provider", "load_prompt"]


def get_provider(stage: str) -> LLMProvider:
    name = (getattr(settings, f"LLM_PROVIDER_{stage.upper()}", "") or settings.LLM_PROVIDER).lower()
    if name == "claude":
        from .claude import ClaudeProvider

        return ClaudeProvider(
            settings.CLAUDE_MODEL,
            settings.ANTHROPIC_API_KEY,
            {
                "understand": settings.CLAUDE_EFFORT_UNDERSTAND,
                "sop": settings.CLAUDE_EFFORT_SOP,
                "repair": settings.CLAUDE_EFFORT_REPAIR,
            },
        )
    if name == "gemini":
        from .gemini import GeminiProvider

        return GeminiProvider(
            settings.GEMINI_MODEL, settings.GEMINI_API_KEY, tuple(settings.GEMINI_FALLBACK_MODELS)
        )
    if name == "fake":
        from .fake import FakeProvider

        return FakeProvider()
    raise LLMError("llm_config", f"Unknown LLM_PROVIDER {name!r} (claude, gemini or fake).")
