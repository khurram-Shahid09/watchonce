// Builds the element descriptor recorded with each event (docs/07-recorder-extension.md).
// Pure DOM code: unit-tested under jsdom, so no chrome.* here.

import type { ElementDescriptor } from "../shared/types";

const MAX_NAME = 200;
const MAX_TEXT = 100;
const TESTID_ATTRS = ["data-testid", "data-test", "data-qa", "data-cy"] as const;
const KEPT_ATTRS = [...TESTID_ATTRS, "type", "name", "placeholder", "aria-label", "title", "role", "href", "for"] as const;

export const collapse = (s: string | null | undefined): string => (s ?? "").replace(/\s+/g, " ").trim();
const cap = (s: string, n: number) => (s.length > n ? s.slice(0, n) : s);

// --- Auto-generated identifiers (never stable across builds, so never recorded) ---

const GENERATED_ID = [
  /^:[a-z0-9]+:?$/i, // React useId ":r1:"
  /^(ember|react-|radix-|headlessui-|mui-|rc_|__next|yui_|ext-gen|gwt-|j_id|ng-|cdk-)/i,
  /[0-9a-f]{8,}/i, // long hex run
  /\d{4,}/, // long digit run
  /^(?=.*\d)(?=.*[a-z])[a-z0-9]{12,}$/i, // opaque token (letters and digits)
];
// Hash segments in generated class names contain at least one digit; real names
// like "form-control" or BEM "card__title" don't, so they are kept.
const HASH = String.raw`(?=[a-z0-9]*\d)[a-z0-9]`;
const GENERATED_CLASS = [
  /^css-[a-z0-9]+$/i, // emotion
  /^sc-[a-z0-9]+$/i, // styled-components
  /^jsx-\d+$/, // styled-jsx
  /^ng-(tns|star|c\d)/, // angular
  new RegExp(`^_${HASH}{5,}$`, "i"), // css modules short hash
  new RegExp(`^[a-z0-9_-]+__${HASH}{5}$`, "i"), // css modules Name_part__hash
  new RegExp(`^[a-z]+-${HASH}{6,}$`, "i"), // name-hash, e.g. "button-1x2y3z"
];

export const isGeneratedId = (id: string): boolean => GENERATED_ID.some((re) => re.test(id));
export const isGeneratedClass = (c: string): boolean => GENERATED_CLASS.some((re) => re.test(c));

// --- Role (explicit, else implicit per HTML-AAM for the elements we care about) ---

export function roleOf(el: Element): string | null {
  const explicit = el.getAttribute("role");
  if (explicit) return explicit.split(/\s+/)[0] ?? null;
  const tag = el.tagName.toLowerCase();
  switch (tag) {
    case "a":
      return el.hasAttribute("href") ? "link" : null;
    case "button":
      return "button";
    case "select":
      return (el as HTMLSelectElement).multiple || (el as HTMLSelectElement).size > 1 ? "listbox" : "combobox";
    case "textarea":
      return "textbox";
    case "option":
      return "option";
    case "img":
      return el.getAttribute("alt") === "" ? "presentation" : "img";
    case "h1":
    case "h2":
    case "h3":
    case "h4":
    case "h5":
    case "h6":
      return "heading";
    case "li":
      return "listitem";
    case "summary":
      return "button";
    case "input": {
      const type = (el.getAttribute("type") ?? "text").toLowerCase();
      if (["button", "submit", "reset", "image"].includes(type)) return "button";
      if (type === "checkbox") return "checkbox";
      if (type === "radio") return "radio";
      if (type === "range") return "slider";
      if (type === "number") return "spinbutton";
      if (type === "search") return el.hasAttribute("list") ? "combobox" : "searchbox";
      if (["text", "email", "tel", "url", "password", ""].includes(type)) return el.hasAttribute("list") ? "combobox" : "textbox";
      return null;
    }
    default:
      return null;
  }
}

// --- Accessible name (simplified accname: the cases real forms use) ---

function textOf(node: Element, skip?: Element): string {
  let out = "";
  for (const child of Array.from(node.childNodes)) {
    if (child === skip) continue;
    if (child.nodeType === Node.TEXT_NODE) out += child.textContent ?? "";
    else if (child.nodeType === Node.ELEMENT_NODE) {
      const e = child as Element;
      if (e.getAttribute("aria-hidden") === "true" || ["SCRIPT", "STYLE", "TEMPLATE"].includes(e.tagName)) continue;
      if (e.tagName === "IMG") out += ` ${e.getAttribute("alt") ?? ""} `;
      else out += ` ${textOf(e, skip)} `;
    }
  }
  return out;
}

function root(el: Element): Document | ShadowRoot {
  const r = el.getRootNode();
  return r instanceof ShadowRoot ? r : (el.ownerDocument ?? document);
}

function byId(el: Element, id: string): Element | null {
  return root(el).getElementById?.(id) ?? el.ownerDocument?.getElementById(id) ?? null;
}

const LABELABLE = new Set(["INPUT", "SELECT", "TEXTAREA", "BUTTON", "METER", "OUTPUT", "PROGRESS"]);

export function labelTextOf(el: Element): string | null {
  if (!LABELABLE.has(el.tagName)) return null;
  const parts: string[] = [];
  const id = el.getAttribute("id");
  if (id) {
    for (const label of Array.from(root(el).querySelectorAll(`label[for="${CSS.escape(id)}"]`))) parts.push(textOf(label));
  }
  const wrapping = el.closest("label");
  if (wrapping) parts.push(textOf(wrapping, el));
  const text = collapse(parts.join(" "));
  return text || null;
}

export function accessibleName(el: Element): string | null {
  const labelledby = el.getAttribute("aria-labelledby");
  if (labelledby) {
    const text = collapse(
      labelledby
        .split(/\s+/)
        .map((id) => byId(el, id))
        .filter((e): e is Element => e !== null)
        .map((e) => textOf(e))
        .join(" "),
    );
    if (text) return cap(text, MAX_NAME);
  }
  const ariaLabel = collapse(el.getAttribute("aria-label"));
  if (ariaLabel) return cap(ariaLabel, MAX_NAME);

  const tag = el.tagName;
  const type = (el.getAttribute("type") ?? "").toLowerCase();
  if (tag === "INPUT" && ["button", "submit", "reset"].includes(type)) {
    const v = collapse((el as HTMLInputElement).value) || (type === "submit" ? "Submit" : type === "reset" ? "Reset" : "");
    if (v) return cap(v, MAX_NAME);
  }
  if (tag === "INPUT" && type === "image") {
    const alt = collapse(el.getAttribute("alt"));
    if (alt) return cap(alt, MAX_NAME);
  }
  const label = labelTextOf(el);
  if (label) return cap(label, MAX_NAME);

  const role = roleOf(el);
  if (role && ["button", "link", "option", "heading", "tab", "menuitem", "checkbox", "radio", "listitem", "cell", "gridcell"].includes(role)) {
    const content = collapse(textOf(el));
    if (content) return cap(content, MAX_NAME);
  }
  const title = collapse(el.getAttribute("title"));
  if (title) return cap(title, MAX_NAME);
  const placeholder = collapse(el.getAttribute("placeholder"));
  return placeholder ? cap(placeholder, MAX_NAME) : null;
}

// --- Paths ---

const cssIdent = (s: string) => CSS.escape(s);

function isUniqueIn(scope: Document | ShadowRoot, selector: string, el: Element): boolean {
  try {
    const found = scope.querySelectorAll(selector);
    return found.length === 1 && found[0] === el;
  } catch {
    return false;
  }
}

/** Shortest selector unique within the element's root (document or shadow root). */
export function cssPath(el: Element): string {
  const scope = root(el);
  const tag = el.tagName.toLowerCase();

  const id = el.getAttribute("id");
  if (id && !isGeneratedId(id) && isUniqueIn(scope, `#${cssIdent(id)}`, el)) return `#${cssIdent(id)}`;
  for (const attr of TESTID_ATTRS) {
    const v = el.getAttribute(attr);
    if (v && isUniqueIn(scope, `[${attr}="${CSS.escape(v)}"]`, el)) return `[${attr}="${CSS.escape(v)}"]`;
  }
  const name = el.getAttribute("name");
  if (name && isUniqueIn(scope, `${tag}[name="${CSS.escape(name)}"]`, el)) return `${tag}[name="${CSS.escape(name)}"]`;

  const segments: string[] = [];
  let node: Element | null = el;
  while (node && node.nodeType === Node.ELEMENT_NODE) {
    const nodeTag = node.tagName.toLowerCase();
    const nodeId = node.getAttribute("id");
    if (node !== el && nodeId && !isGeneratedId(nodeId) && isUniqueIn(scope, `#${cssIdent(nodeId)}`, node)) {
      segments.unshift(`#${cssIdent(nodeId)}`);
      break;
    }
    const stable = Array.from(node.classList).filter((c) => !isGeneratedClass(c)).slice(0, 2);
    let segment = nodeTag + stable.map((c) => `.${cssIdent(c)}`).join("");
    const parent: Element | null = node.parentElement;
    if (parent) {
      const sameTag = Array.from(parent.children).filter((c) => c.tagName === node!.tagName);
      if (sameTag.length > 1) segment += `:nth-of-type(${sameTag.indexOf(node) + 1})`;
    }
    segments.unshift(segment);
    const candidate = segments.join(" > ");
    if (isUniqueIn(scope, candidate, el)) return candidate;
    node = parent;
  }
  return segments.join(" > ");
}

export function xPath(el: Element): string {
  const parts: string[] = [];
  let node: Element | null = el;
  while (node && node.nodeType === Node.ELEMENT_NODE) {
    const tag = node.tagName.toLowerCase();
    const parent: Element | null = node.parentElement;
    if (!parent) {
      parts.unshift(tag);
      break;
    }
    const same = Array.from(parent.children).filter((c) => c.tagName === node!.tagName);
    parts.unshift(same.length > 1 ? `${tag}[${same.indexOf(node) + 1}]` : tag);
    node = parent;
  }
  return `/${parts.join("/")}`;
}

// --- Uniqueness flags, computed against the live DOM at capture time ---

const INTERACTIVE = "a[href],button,input,select,textarea,summary,[role],[tabindex],[contenteditable='true'],label,option,li,td,th";

function countWhere(scope: Document | ShadowRoot, predicate: (e: Element) => boolean): number {
  let n = 0;
  for (const e of Array.from(scope.querySelectorAll(INTERACTIVE))) if (predicate(e)) n++;
  return n;
}

// --- Nearby text: labels and headings close to the element (helps fuzzy re-matching) ---

const NEARBY = "label,h1,h2,h3,h4,h5,h6,th,legend,dt,[role=heading],.card-title,caption";

function nearbyText(el: Element, rect: DOMRect): string[] {
  const own = collapse(textOf(el));
  const cx = rect.x + rect.width / 2;
  const cy = rect.y + rect.height / 2;
  const found: [number, string][] = [];
  for (const candidate of Array.from(root(el).querySelectorAll(NEARBY))) {
    if (candidate === el || candidate.contains(el)) continue;
    const text = cap(collapse(textOf(candidate)), 60);
    if (!text || text === own) continue;
    const r = candidate.getBoundingClientRect();
    const d = Math.hypot(r.x + r.width / 2 - cx, r.y + r.height / 2 - cy);
    if (d <= 200 || (r.width === 0 && rect.width === 0)) found.push([d, text]);
  }
  found.sort((a, b) => a[0] - b[0]);
  return [...new Set(found.map(([, t]) => t))].slice(0, 5);
}

function shadowHosts(el: Element): string[] {
  const hosts: string[] = [];
  let r = el.getRootNode();
  while (r instanceof ShadowRoot) {
    hosts.unshift(cssPath(r.host));
    r = r.host.getRootNode();
  }
  return hosts;
}

// --- Public ---

export function describe(el: Element): ElementDescriptor {
  const scope = root(el);
  const rect = el.getBoundingClientRect();
  const view = el.ownerDocument?.defaultView;

  const attrs: Record<string, string | null> = {};
  for (const a of KEPT_ATTRS) {
    let v = el.getAttribute(a);
    if (a === "href" && v) v = v.split("#")[0]!.slice(0, 300) || v; // keep path, drop fragments
    attrs[a] = v;
  }

  const role = roleOf(el);
  const name = accessibleName(el);
  const tag = el.tagName.toLowerCase();
  const text = ["input", "select", "textarea"].includes(tag) ? null : cap(collapse(textOf(el)), MAX_TEXT) || null;
  const label = labelTextOf(el);
  const id = el.getAttribute("id");
  const testidAttr = TESTID_ATTRS.find((a) => el.hasAttribute(a));
  const css = cssPath(el);

  return {
    tag,
    role,
    accessible_name: name,
    text,
    id: id && !isGeneratedId(id) ? id : null,
    classes: Array.from(el.classList).filter((c) => !isGeneratedClass(c)),
    attrs,
    label_text: label,
    css_path: css,
    xpath: xPath(el),
    bbox: [Math.round(rect.x), Math.round(rect.y), Math.round(rect.width), Math.round(rect.height)],
    viewport: [view?.innerWidth ?? 0, view?.innerHeight ?? 0],
    nearby_text: nearbyText(el, rect),
    is_unique: {
      testid: testidAttr ? scope.querySelectorAll(`[${testidAttr}="${CSS.escape(el.getAttribute(testidAttr)!)}"]`).length === 1 : null,
      role_name: role && name ? countWhere(scope, (e) => roleOf(e) === role && accessibleName(e) === name) === 1 : null,
      text: text ? countWhere(scope, (e) => e.tagName === el.tagName && cap(collapse(textOf(e)), MAX_TEXT) === text) === 1 : null,
      css: isUniqueIn(scope, css, el),
      label: label ? countWhere(scope, (e) => labelTextOf(e) === label) === 1 : null,
    },
    shadow_hosts: shadowHosts(el),
  };
}

/** The element an action really targeted: walk up from inner spans/icons to the control. */
export function actionTarget(start: Element): Element {
  const control = start.closest(
    "button,a[href],input,select,textarea,summary,label,option,[role=button],[role=link],[role=option],[role=menuitem],[role=tab],[role=checkbox],[role=radio],[role=switch],[role=combobox],[contenteditable='true']",
  );
  return control ?? start;
}
