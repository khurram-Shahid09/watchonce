// Injected by the runner (services/core/engine/runner) when a step's locators all fail.
// Lists the page's interactive elements in the same descriptor format the recorder
// captured, so self-healing compares like with like and healed locators are built the
// same way as compiled ones. Built as an IIFE into engine/runner/static/page-agent.js.

import type { ElementDescriptor } from "../shared/types";
import { actionTarget, describe } from "../content/descriptor";

const INTERACTIVE = [
  "a[href]",
  "button",
  "input:not([type=hidden])",
  "select",
  "textarea",
  "summary",
  "[role=button]",
  "[role=link]",
  "[role=checkbox]",
  "[role=radio]",
  "[role=combobox]",
  "[role=option]",
  "[role=menuitem]",
  "[role=tab]",
  "[role=switch]",
  "[role=textbox]",
  "[contenteditable='true']",
  "[onclick]",
].join(",");
const MARK = "data-wo-candidate";

export interface Candidate {
  id: string;
  descriptor: ElementDescriptor;
  enabled: boolean;
}

function visible(el: Element): boolean {
  const rect = el.getBoundingClientRect();
  if (rect.width < 2 || rect.height < 2) return false;
  const style = getComputedStyle(el);
  return style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity) > 0.05;
}

/** Visible interactive elements, each marked with ``data-wo-candidate`` so the runner can
 * address the one it picks. Earlier marks are cleared first. */
export function candidates(limit = 150): Candidate[] {
  for (const old of Array.from(document.querySelectorAll(`[${MARK}]`))) old.removeAttribute(MARK);
  const seen = new Set<Element>();
  const out: Candidate[] = [];
  for (const raw of Array.from(document.querySelectorAll(INTERACTIVE))) {
    const el = actionTarget(raw);
    if (seen.has(el) || !visible(el)) continue;
    seen.add(el);
    const id = `e${out.length + 1}`;
    el.setAttribute(MARK, id);
    out.push({
      id,
      descriptor: describe(el),
      enabled: !(el as HTMLButtonElement).disabled && el.getAttribute("aria-disabled") !== "true",
    });
    if (out.length >= limit) break;
  }
  return out;
}

/** Remove the marks again once a candidate has been chosen (or none was). */
export function clearMarks(): void {
  for (const el of Array.from(document.querySelectorAll(`[${MARK}]`))) el.removeAttribute(MARK);
}

/** The descriptor of one element (to check a positional fallback against the fingerprint). */
export function describeOne(el: Element): ElementDescriptor {
  return describe(el);
}
