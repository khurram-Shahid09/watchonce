"""The uploaded ``events.json`` (recording format v1, apps/extension/src/shared/types.ts).

Unknown fields are ignored so a newer extension can add data without breaking older
compilers; a different ``format_version`` is rejected.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FORMAT_VERSION = 1


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


class IsUnique(_Lenient):
    testid: bool | None = None
    role_name: bool | None = None
    text: bool | None = None
    css: bool = False
    label: bool | None = None


class Element(_Lenient):
    tag: str
    role: str | None = None
    accessible_name: str | None = None
    text: str | None = None
    id: str | None = None
    classes: list[str] = Field(default_factory=list)
    attrs: dict[str, str | None] = Field(default_factory=dict)
    label_text: str | None = None
    css_path: str
    xpath: str = ""
    bbox: tuple[float, float, float, float] = (0, 0, 0, 0)
    viewport: tuple[float, float] = (0, 0)
    nearby_text: list[str] = Field(default_factory=list)
    is_unique: IsUnique = Field(default_factory=IsUnique)
    shadow_hosts: list[str] = Field(default_factory=list)


EventType = Literal[
    "click",
    "dblclick",
    "input",
    "select",
    "check",
    "uncheck",
    "press",
    "submit",
    "navigate",
    "file_input",
    "warning",
]


class Nav(_Lenient):
    transition: str = "link_or_script"


class Event(_Lenient):
    seq: int
    ts: int
    type: EventType
    url: str
    frame_path: list[str] = Field(default_factory=list)
    element: Element | None = None
    value: str | None = None
    value_masked: bool = False
    mask_reason: str | None = None
    key: str | None = None
    option_label: str | None = None
    nav: Nav | None = None
    warning: str | None = None
    frame_ref: str | None = None


class RecordingMeta(_Lenient):
    description: str = ""
    startUrl: str = ""  # extension field names
    startedAt: int | None = None
    stoppedAt: int | None = None
    warnings: list[str] = Field(default_factory=list)


class Recording(_Lenient):
    format_version: Literal[1]
    recording: RecordingMeta = Field(default_factory=RecordingMeta)
    events: list[Event] = Field(max_length=5000)
