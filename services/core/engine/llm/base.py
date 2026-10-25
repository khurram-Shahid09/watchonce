"""The provider interface. Nothing outside engine/llm imports a vendor SDK."""

from pathlib import Path
from typing import Protocol

from .types import SopRequest, SopResult, Understanding, UnderstandRequest, Usage

PROMPTS = Path(__file__).parent / "prompts"


class LLMError(Exception):
    """``code`` is stable and shown to users; ``retryable`` drives the Celery retry."""

    def __init__(
        self, code: str, message: str, *, retryable: bool = False, usage: Usage | None = None
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.usage = usage


class LLMProvider(Protocol):
    name: str
    model: str

    def understand(self, req: UnderstandRequest) -> tuple[Understanding, Usage]: ...
    def write_sop(self, req: SopRequest) -> tuple[SopResult, Usage]: ...


def load_prompt(stage: str, provider: str) -> tuple[str, str]:
    """(prompt text, version). Version is the first line: ``<!-- version: understand-v1 -->``.
    A provider overlay (``<stage>.<provider>.md``) is appended when present."""
    text = (PROMPTS / f"{stage}.md").read_text(encoding="utf-8")
    first, _, body = text.partition("\n")
    version = first.removeprefix("<!-- version:").removesuffix("-->").strip()
    overlay = PROMPTS / f"{stage}.{provider}.md"
    if overlay.exists():
        body += "\n\n" + overlay.read_text(encoding="utf-8")
    return body.strip(), version
