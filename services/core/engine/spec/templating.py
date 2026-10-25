"""Parser for spec templates: ``{{name}}``, ``{{secrets.s.field}}``, ``{{outputs.o}}`` and filters.

Grammar (docs/05-workflow-spec.md#templating). No arbitrary expressions, by design:

    template  := text ( "{{" ws ref ( ws "|" ws filter )* ws "}}" text )*
    ref       := identifier | "secrets." identifier "." identifier | "outputs." identifier
    filter    := "date:" quoted-string | "number:" digits

Rendering lands with the runner (D8); this module only parses so specs can be validated.
"""

import re
from dataclasses import dataclass
from typing import Literal

IDENT = r"[a-z][a-z0-9_]{0,63}"
_EXPR_RE = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_REF_RE = re.compile(rf"^(?:(?P<ns>secrets|outputs)\.)?(?P<name>{IDENT})(?:\.(?P<field>{IDENT}))?$")
_FILTER_RE = re.compile(r'^(?P<name>date|number)\s*:\s*(?P<arg>"[^"\\]{1,40}"|\d{1,2})$')

RefKind = Literal["input", "secret", "output"]


class TemplateError(ValueError):
    pass


@dataclass(frozen=True)
class Filter:
    name: Literal["date", "number"]
    arg: str | int


@dataclass(frozen=True)
class Ref:
    kind: RefKind
    name: str
    field: str | None = None
    filters: tuple[Filter, ...] = ()


def _parse_filter(raw: str) -> Filter:
    m = _FILTER_RE.match(raw.strip())
    if not m:
        raise TemplateError(f'unsupported filter "{raw.strip()}" (allowed: date:"FMT", number:N)')
    name, arg = m["name"], m["arg"]
    if name == "date":
        if not arg.startswith('"'):
            raise TemplateError('date filter needs a quoted format, e.g. date:"MM/DD/YYYY"')
        return Filter("date", arg[1:-1])
    if arg.startswith('"'):
        raise TemplateError("number filter needs an integer, e.g. number:2")
    return Filter("number", int(arg))


def _parse_ref(raw: str) -> tuple[RefKind, str, str | None]:
    m = _REF_RE.match(raw.strip())
    if not m:
        raise TemplateError(f'invalid reference "{raw.strip()}"')
    ns, name, field = m["ns"], m["name"], m["field"]
    if ns == "secrets":
        if field is None:
            raise TemplateError(f'secret reference needs a field: "secrets.{name}.<field>"')
        return "secret", name, field
    if field is not None:
        raise TemplateError(f'invalid reference "{raw.strip()}"')
    return ("output" if ns == "outputs" else "input"), name, None


def parse(template: str) -> list[Ref]:
    """Return every reference in ``template``. Raises TemplateError on malformed expressions."""
    stripped = _EXPR_RE.sub("", template)
    if "{{" in stripped or "}}" in stripped:
        raise TemplateError("unbalanced {{ }} in template")

    refs: list[Ref] = []
    for m in _EXPR_RE.finditer(template):
        ref_part, *filter_parts = m.group(1).split("|")
        kind, name, field = _parse_ref(ref_part)
        filters = tuple(_parse_filter(f) for f in filter_parts)
        if kind == "secret" and filters:
            raise TemplateError("filters cannot be applied to secrets")
        refs.append(Ref(kind, name, field, filters))
    return refs


def has_expressions(template: str) -> bool:
    return bool(_EXPR_RE.search(template))
