// Display helpers for spec steps, shared by server and client components.

import type { Step } from "./types";

export const ACTION_LABEL: Record<Step["action"], string> = {
  navigate: "Open page",
  click: "Click",
  fill: "Type",
  select: "Choose",
  check: "Tick",
  uncheck: "Untick",
  press: "Press key",
  wait_for: "Wait",
  assert: "Check",
  extract: "Read value",
};

/** The value part of a step, as written in the spec (templates stay visible). */
export function stepDetail(step: Step): string | null {
  switch (step.action) {
    case "navigate":
      return step.url;
    case "fill":
      return step.value;
    case "select":
      return "label" in step && step.label ? step.label : "value" in step ? (step.value ?? null) : null;
    case "press":
      return step.key;
    case "extract":
      return `→ ${step.output}${step.pattern ? `  (pattern ${step.pattern})` : ""}`;
    case "wait_for":
    case "assert":
      return `${step.condition.type.replace("_", " ")}${"value" in step.condition ? `: ${step.condition.value}` : ""}`;
    default:
      return null;
  }
}

export function screenshotUrl(workflowId: string, ref: string): string {
  return `/bff/workflows/${encodeURIComponent(workflowId)}/screenshots/${ref.split("/").map(encodeURIComponent).join("/")}`;
}

/** Splits "{{amount | number:2}}" style templates so inputs can be highlighted. */
export function templateParts(text: string): { text: string; ref: boolean }[] {
  const parts: { text: string; ref: boolean }[] = [];
  let last = 0;
  for (const m of text.matchAll(/\{\{[^}]*\}\}/g)) {
    if (m.index > last) parts.push({ text: text.slice(last, m.index), ref: false });
    parts.push({ text: m[0], ref: true });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last), ref: false });
  return parts;
}
