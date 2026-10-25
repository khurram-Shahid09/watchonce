# GENERATED from packages/spec/workflow.schema.json by scripts/gen_spec_models.py. Do not edit.

from __future__ import annotations

from typing import Annotated, Literal
from pydantic import AnyUrl, AwareDatetime, BaseModel, ConfigDict, Field, RootModel


class Identifier(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="snake_case name used in templates, e.g. vendor_name.",
            pattern="^[a-z][a-z0-9_]{0,63}$",
        ),
    ]


class Domain(RootModel[str]):
    root: Annotated[
        str,
        Field(
            description="Hostname (optionally with port), no scheme or path.",
            pattern="^(\\*\\.)?[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*(:[0-9]{1,5})?$",
        ),
    ]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[
        str,
        Field(
            description="snake_case name used in templates, e.g. vendor_name.",
            pattern="^[a-z][a-z0-9_]{0,63}$",
        ),
    ]
    type: Literal["string", "number", "integer", "boolean", "date"]
    required: bool | None = True
    example: str | float | int | bool | None = None
    description: Annotated[str | None, Field(max_length=500)] = None
    format_hint: Annotated[str | None, Field(max_length=200)] = None


class SecretRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[
        str,
        Field(
            description="snake_case name used in templates, e.g. vendor_name.",
            pattern="^[a-z][a-z0-9_]{0,63}$",
        ),
    ]
    fields: Annotated[list[Identifier], Field(min_length=1)]


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[
        str,
        Field(
            description="snake_case name used in templates, e.g. vendor_name.",
            pattern="^[a-z][a-z0-9_]{0,63}$",
        ),
    ]
    type: Literal["string", "number"]
    description: Annotated[str | None, Field(max_length=500)] = None


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_timeout_ms: Annotated[int | None, Field(ge=100, le=300000)] = 15000
    heal_policy: Literal["approve", "auto"] | None = "approve"
    auto_approve_heal_min_confidence: Annotated[float | None, Field(ge=0.0, le=1.0)] = 0.9
    slow_mo_ms: Annotated[int | None, Field(ge=0, le=10000)] = 0


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recording_id: str | None = None
    compiled_by: str | None = None
    compiled_at: AwareDatetime | None = None


class TestIdLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["testid"]
    value: Annotated[str, Field(min_length=1)]


class RoleLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["role"]
    role: Annotated[str, Field(min_length=1)]
    name: str | None = None
    exact: bool | None = None


class TextLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["text"]
    value: Annotated[str, Field(min_length=1)]
    exact: bool | None = None


class LabelLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["label"]
    value: Annotated[str, Field(min_length=1)]
    exact: bool | None = None


class PlaceholderLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["placeholder"]
    value: Annotated[str, Field(min_length=1)]
    exact: bool | None = None


class CssLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["css"]
    value: Annotated[str, Field(min_length=1)]


class XPathLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["xpath"]
    value: Annotated[str, Field(min_length=1)]


class Fingerprint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tag: str | None = None
    role: str | None = None
    accessible_name: str | None = None
    text: str | None = None
    attributes: dict[str, str | None] | None = None
    nearby_text: list[str] | None = None
    bbox_norm: Annotated[
        list[float] | None,
        Field(
            description="[x, y, width, height] normalized to the viewport (0..1).",
            max_length=4,
            min_length=4,
        ),
    ] = None
    frame_path: list[str] | None = None


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid")
    locators: Annotated[
        list[
            TestIdLocator
            | RoleLocator
            | TextLocator
            | LabelLocator
            | PlaceholderLocator
            | CssLocator
            | XPathLocator
        ],
        Field(description="Ordered most robust to least robust.", min_length=1),
    ]
    fingerprint: Fingerprint | None = None
    anchor_image_ref: str | None = None


class UrlMatchesCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["url_matches"]
    value: Annotated[str, Field(min_length=1)]


class ElementVisibleCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["element_visible"]
    target: Target


class TextVisibleCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["text_visible"]
    value: Annotated[
        str,
        Field(
            description="String that may contain {{input}}, {{secrets.name.field}}, {{outputs.name}} and filters.",
            max_length=4000,
        ),
    ]


class NetworkIdleCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["network_idle"]


class Checkpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["approval", "none"]
    reason: Annotated[str | None, Field(max_length=500)] = None


class NavigateStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Annotated[
        str, Field(description="Stable step id, e.g. s7.", pattern="^[a-z][a-z0-9_-]{0,31}$")
    ]
    action: Literal["navigate"]
    intent: Annotated[str, Field(max_length=300, min_length=1)]
    url: Annotated[
        str,
        Field(
            description="String that may contain {{input}}, {{secrets.name.field}}, {{outputs.name}} and filters.",
            max_length=4000,
        ),
    ]
    checkpoint: Checkpoint | None = None
    timeout_ms: Annotated[int | None, Field(ge=100, le=300000)] = None
    screenshot_ref: str | None = None
    assert_after: (
        UrlMatchesCondition
        | ElementVisibleCondition
        | TextVisibleCondition
        | NetworkIdleCondition
        | None
    ) = None


class ClickStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Annotated[
        str, Field(description="Stable step id, e.g. s7.", pattern="^[a-z][a-z0-9_-]{0,31}$")
    ]
    action: Literal["click"]
    intent: Annotated[str, Field(max_length=300, min_length=1)]
    target: Target
    checkpoint: Checkpoint | None = None
    timeout_ms: Annotated[int | None, Field(ge=100, le=300000)] = None
    screenshot_ref: str | None = None
    assert_after: (
        UrlMatchesCondition
        | ElementVisibleCondition
        | TextVisibleCondition
        | NetworkIdleCondition
        | None
    ) = None


class FillStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Annotated[
        str, Field(description="Stable step id, e.g. s7.", pattern="^[a-z][a-z0-9_-]{0,31}$")
    ]
    action: Literal["fill"]
    intent: Annotated[str, Field(max_length=300, min_length=1)]
    target: Target
    value: Annotated[
        str,
        Field(
            description="String that may contain {{input}}, {{secrets.name.field}}, {{outputs.name}} and filters.",
            max_length=4000,
        ),
    ]
    checkpoint: Checkpoint | None = None
    timeout_ms: Annotated[int | None, Field(ge=100, le=300000)] = None
    screenshot_ref: str | None = None
    assert_after: (
        UrlMatchesCondition
        | ElementVisibleCondition
        | TextVisibleCondition
        | NetworkIdleCondition
        | None
    ) = None


class SelectStep1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Annotated[
        str, Field(description="Stable step id, e.g. s7.", pattern="^[a-z][a-z0-9_-]{0,31}$")
    ]
    action: Literal["select"]
    intent: Annotated[str, Field(max_length=300, min_length=1)]
    target: Target
    value: Annotated[
        str,
        Field(
            description="String that may contain {{input}}, {{secrets.name.field}}, {{outputs.name}} and filters.",
            max_length=4000,
        ),
    ]
    label: Annotated[
        str | None,
        Field(
            description="String that may contain {{input}}, {{secrets.name.field}}, {{outputs.name}} and filters.",
            max_length=4000,
        ),
    ] = None
    checkpoint: Checkpoint | None = None
    timeout_ms: Annotated[int | None, Field(ge=100, le=300000)] = None
    screenshot_ref: str | None = None
    assert_after: (
        UrlMatchesCondition
        | ElementVisibleCondition
        | TextVisibleCondition
        | NetworkIdleCondition
        | None
    ) = None


class SelectStep2(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Annotated[
        str, Field(description="Stable step id, e.g. s7.", pattern="^[a-z][a-z0-9_-]{0,31}$")
    ]
    action: Literal["select"]
    intent: Annotated[str, Field(max_length=300, min_length=1)]
    target: Target
    value: Annotated[
        str | None,
        Field(
            description="String that may contain {{input}}, {{secrets.name.field}}, {{outputs.name}} and filters.",
            max_length=4000,
        ),
    ] = None
    label: Annotated[
        str,
        Field(
            description="String that may contain {{input}}, {{secrets.name.field}}, {{outputs.name}} and filters.",
            max_length=4000,
        ),
    ]
    checkpoint: Checkpoint | None = None
    timeout_ms: Annotated[int | None, Field(ge=100, le=300000)] = None
    screenshot_ref: str | None = None
    assert_after: (
        UrlMatchesCondition
        | ElementVisibleCondition
        | TextVisibleCondition
        | NetworkIdleCondition
        | None
    ) = None


class CheckStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Annotated[
        str, Field(description="Stable step id, e.g. s7.", pattern="^[a-z][a-z0-9_-]{0,31}$")
    ]
    action: Literal["check", "uncheck"]
    intent: Annotated[str, Field(max_length=300, min_length=1)]
    target: Target
    checkpoint: Checkpoint | None = None
    timeout_ms: Annotated[int | None, Field(ge=100, le=300000)] = None
    screenshot_ref: str | None = None
    assert_after: (
        UrlMatchesCondition
        | ElementVisibleCondition
        | TextVisibleCondition
        | NetworkIdleCondition
        | None
    ) = None


class PressStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Annotated[
        str, Field(description="Stable step id, e.g. s7.", pattern="^[a-z][a-z0-9_-]{0,31}$")
    ]
    action: Literal["press"]
    intent: Annotated[str, Field(max_length=300, min_length=1)]
    key: Annotated[str, Field(max_length=50, min_length=1)]
    target: Target | None = None
    checkpoint: Checkpoint | None = None
    timeout_ms: Annotated[int | None, Field(ge=100, le=300000)] = None
    screenshot_ref: str | None = None
    assert_after: (
        UrlMatchesCondition
        | ElementVisibleCondition
        | TextVisibleCondition
        | NetworkIdleCondition
        | None
    ) = None


class WaitForStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Annotated[
        str, Field(description="Stable step id, e.g. s7.", pattern="^[a-z][a-z0-9_-]{0,31}$")
    ]
    action: Literal["wait_for"]
    intent: Annotated[str, Field(max_length=300, min_length=1)]
    condition: (
        UrlMatchesCondition | ElementVisibleCondition | TextVisibleCondition | NetworkIdleCondition
    )
    checkpoint: Checkpoint | None = None
    timeout_ms: Annotated[int | None, Field(ge=100, le=300000)] = None
    screenshot_ref: str | None = None


class AssertStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Annotated[
        str, Field(description="Stable step id, e.g. s7.", pattern="^[a-z][a-z0-9_-]{0,31}$")
    ]
    action: Literal["assert"]
    intent: Annotated[str, Field(max_length=300, min_length=1)]
    condition: (
        UrlMatchesCondition | ElementVisibleCondition | TextVisibleCondition | NetworkIdleCondition
    )
    checkpoint: Checkpoint | None = None
    timeout_ms: Annotated[int | None, Field(ge=100, le=300000)] = None
    screenshot_ref: str | None = None


class ExtractStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Annotated[
        str, Field(description="Stable step id, e.g. s7.", pattern="^[a-z][a-z0-9_-]{0,31}$")
    ]
    action: Literal["extract"]
    intent: Annotated[str, Field(max_length=300, min_length=1)]
    target: Target
    attribute: Annotated[str | None, Field(min_length=1)] = "text"
    output: Annotated[
        str,
        Field(
            description="snake_case name used in templates, e.g. vendor_name.",
            pattern="^[a-z][a-z0-9_]{0,63}$",
        ),
    ]
    pattern: str | None = None
    checkpoint: Checkpoint | None = None
    timeout_ms: Annotated[int | None, Field(ge=100, le=300000)] = None
    screenshot_ref: str | None = None


class WorkflowSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec_version: Literal["1.0"]
    name: Annotated[str, Field(max_length=200, min_length=1)]
    description: Annotated[str | None, Field(max_length=2000)] = None
    allowed_domains: Annotated[list[Domain], Field(min_length=1)]
    start_url: AnyUrl
    inputs: list[Input]
    secrets: list[SecretRef]
    outputs: list[Output]
    steps: Annotated[
        list[
            NavigateStep
            | ClickStep
            | FillStep
            | CheckStep
            | PressStep
            | WaitForStep
            | AssertStep
            | ExtractStep
            | SelectStep1
            | SelectStep2
        ],
        Field(min_length=1),
    ]
    settings: Settings
    source: Source | None = None
