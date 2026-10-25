"""Parser for spec templates: ``{{name}}``, ``{{secrets.s.field}}``, ``{{outputs.o}}`` and filters.

Grammar (docs/05-workflow-spec.md#templating). No arbitrary expressions, by design:

    template  := text ( "{{" ws ref ( ws "|" ws filter )* ws "}}" text )*
    ref       := identifier | "secrets." identifier "." identifier | "outputs." identifier
    filter    := "date:" quoted-string | "number:" digits

``render`` fills a template for the runner; inputs are validated before a run starts.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

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


_DATE_TOKENS = re.compile(r"YYYY|YY|MM|M|DD|D")


def format_date(value: date, fmt: str) -> str:
    """``MM/DD/YYYY``-style formats: YYYY, YY, MM, M, DD, D; anything else is literal."""
    parts = {
        "YYYY": f"{value.year:04d}",
        "YY": f"{value.year % 100:02d}",
        "MM": f"{value.month:02d}",
        "M": str(value.month),
        "DD": f"{value.day:02d}",
        "D": str(value.day),
    }
    return _DATE_TOKENS.sub(lambda m: parts[m.group(0)], fmt)


def _apply(value: Any, flt: Filter) -> str:
    if flt.name == "date":
        when = value if isinstance(value, date) else date.fromisoformat(str(value))
        return format_date(when, str(flt.arg))
    return f"{float(value):.{int(flt.arg)}f}"


def render(
    template: str,
    inputs: dict[str, Any],
    secrets: dict[str, dict[str, str]] | None = None,
    outputs: dict[str, Any] | None = None,
) -> str:
    """Fill every ``{{ }}`` in ``template``. Missing values raise TemplateError."""
    parse(template)  # validates the whole template first

    def repl(m: re.Match[str]) -> str:
        ref_part, *filter_parts = m.group(1).split("|")
        kind, name, field = _parse_ref(ref_part)
        if kind == "secret":
            try:
                return (secrets or {})[name][field or ""]
            except KeyError:
                raise TemplateError(f"secret {name}.{field} is not available") from None
        source = inputs if kind == "input" else (outputs or {})
        if name not in source:
            raise TemplateError(f'{"input" if kind == "input" else "output"} "{name}" has no value')
        value: Any = source[name]
        try:
            for raw in filter_parts:
                value = _apply(value, _parse_filter(raw))
        except ValueError as exc:
            raise TemplateError(f"can't format {name!r}: {exc}") from None
        return str(value)

    return _EXPR_RE.sub(repl, template)
