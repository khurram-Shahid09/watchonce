// Content script: listens to user actions on the page being recorded and reports them to the
// background worker. Injected only into the origin the user chose to record.

import type { CapturedEvent, EventType, Message, RecordingStatus } from "../shared/types";
import { actionTarget, collapse, describe } from "./descriptor";
import { isSecretField, maskValue } from "./masking";
import { Pill } from "./pill";

declare global {
  interface Window {
    __watchonceRecorder?: boolean;
  }
}

const TEXT_INPUT_TYPES = new Set(["text", "email", "tel", "url", "search", "password", "number", "date", "datetime-local", "time", "month", "week", ""]);
const INPUT_IDLE_MS = 500;

if (!window.__watchonceRecorder) {
  window.__watchonceRecorder = true;
  start();
}

function start(): void {
  let status: RecordingStatus = "idle";
  let captureSeq = 0;
  let pendingCapture: { id: number; el: Element } | null = null;
  let domChanged = true;
  let pendingInput: { el: Element; event: CapturedEvent; timer: number } | null = null;
  const typed = new WeakSet<Element>(); // fields we saw being typed into

  const pill = new Pill({
    pause: () => send({ kind: "recording.pause" }),
    resume: () => send({ kind: "recording.resume" }),
    stop: () => send({ kind: "recording.stop" }),
  });

  const active = () => status === "recording";

  function send(message: Message): Promise<unknown> {
    return chrome.runtime.sendMessage(message).catch(() => undefined); // worker restarting: drop
  }

  function setStatus(next: RecordingStatus): void {
    status = next;
    if (next === "recording" || next === "paused") pill.show(next);
    else {
      flushInput();
      pill.hide();
    }
  }

  new MutationObserver(() => {
    domChanged = true;
  }).observe(document, { subtree: true, childList: true, attributes: true, characterData: true });

  // --- Screenshot just before an action: blur secrets, hide the pill, ask the worker ---

  const blurStyle = document.createElement("style");
  blurStyle.textContent =
    "input[type=password],[autocomplete~='one-time-code'],[autocomplete~='cc-number'],[autocomplete~='cc-csc'],[data-wo-sensitive]{filter:blur(8px)!important}";

  /**
   * ``forAction``: the screenshot belongs to the action about to happen on ``el`` (its event
   * claims it). Otherwise it just refreshes the page's latest frame, e.g. after typing, so a
   * later action whose own capture can't happen in time falls back to an up-to-date picture.
   */
  async function requestCapture(el: Element, forAction = true): Promise<void> {
    const id = ++captureSeq;
    if (forAction) {
      pendingCapture = { id, el };
      // Announce first, synchronously: the action's own event is sent right after this
      // handler and must find the capture already registered in the worker.
      void send({ kind: "capture.intent", captureId: id });
    }
    const changed = domChanged;
    domChanged = false;
    (document.head ?? document.documentElement).appendChild(blurStyle);
    pill.setHidden(true);
    // Let the blur paint. Animation frames stop once the page starts navigating away (e.g. a
    // link was clicked), so cap the wait: ~60 ms is several frames at normal refresh rates.
    await Promise.race([
      new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))),
      new Promise((r) => setTimeout(r, 60)),
    ]);
    try {
      await send({ kind: "capture", captureId: id, domChanged: changed });
    } finally {
      blurStyle.remove();
      pill.setHidden(false);
    }
  }

  function captureIdFor(el: Element): number | null {
    if (pendingCapture && (pendingCapture.el === el || pendingCapture.el.contains(el) || el.contains(pendingCapture.el))) {
      const id = pendingCapture.id;
      pendingCapture = null;
      return id;
    }
    return null;
  }

  // --- Event construction ---

  function base(type: EventType, el: Element | null, captureId: number | null): CapturedEvent {
    return {
      ts: Date.now(),
      type,
      url: location.href,
      frame_path: [],
      element: el ? describe(el) : null,
      value: null,
      value_masked: false,
      capture_id: captureId,
    };
  }

  function emit(event: CapturedEvent): void {
    void send({ kind: "event", event });
  }

  function warn(message: string, el: Element | null = null): void {
    emit({ ...base("warning", el, null), warning: message });
  }

  function flushInput(): void {
    if (!pendingInput) return;
    window.clearTimeout(pendingInput.timer);
    emit(pendingInput.event);
    pendingInput = null;
  }

  const fromPill = (e: Event) => e.composedPath().includes(pill.host);
  const realTarget = (e: Event): Element | null => {
    const t = e.composedPath()[0];
    return t instanceof Element ? t : null;
  };
  const isTextLike = (el: Element) =>
    (el.tagName === "INPUT" && TEXT_INPUT_TYPES.has((el.getAttribute("type") ?? "").toLowerCase())) ||
    el.tagName === "TEXTAREA" ||
    (el as HTMLElement).isContentEditable;
  const isToggle = (el: Element) =>
    el.tagName === "INPUT" && ["checkbox", "radio"].includes((el.getAttribute("type") ?? "").toLowerCase());
  const labelledToggle = (el: Element): boolean => {
    const label = el.closest("label");
    const control = label ? ((label as HTMLLabelElement).control ?? null) : null;
    return control !== null && isToggle(control);
  };

  // --- Listeners (capture phase, so page handlers can't hide events from us) ---

  const on = <K extends keyof DocumentEventMap>(type: K, handler: (e: DocumentEventMap[K]) => void) =>
    document.addEventListener(type, (e) => {
      if (active() && e.isTrusted && !fromPill(e)) handler(e);
    }, true);

  on("pointerdown", (e) => {
    if (e.button !== 0) return;
    const el = realTarget(e);
    if (el) void requestCapture(actionTarget(el));
  });

  on("focusin", (e) => {
    const el = realTarget(e);
    if (el && isTextLike(el) && pendingCapture?.el !== el) void requestCapture(el);
  });

  // Values that reached a form without typing: browser autofill, or text already there when
  // recording started. Without them the replay would submit an empty login form. Recorded
  // just before the click / Enter that submits, masked like typed values.
  function recordUntypedFields(trigger: Element | null): void {
    const form = trigger?.closest("form");
    if (!form) return;
    for (const field of Array.from(form.querySelectorAll("input, textarea"))) {
      if (!isTextLike(field) || typed.has(field)) continue;
      const input = field as HTMLInputElement;
      if (!input.value || input.disabled || input.readOnly || !(input.offsetWidth || input.offsetHeight)) continue;
      typed.add(field);
      const masked = maskValue(field, input.value);
      const event = base("input", field, null);
      event.value = masked.value;
      event.value_masked = masked.masked;
      event.mask_reason = masked.reason;
      event.prefilled = true;
      emit(event);
    }
  }

  on("click", (e) => {
    if (e.button !== 0) return;
    const raw = realTarget(e);
    if (!raw) return;
    const el = actionTarget(raw);
    if (isToggle(el) || labelledToggle(el)) return; // recorded from "change" instead
    flushInput();
    recordUntypedFields(el);
    const event = base("click", el, captureIdFor(el));
    if (el.tagName === "CANVAS") event.warning = "Canvas clicks replay by position only (better support in v0.3).";
    if (el.tagName === "IFRAME") event.warning = "Actions inside embedded frames aren't recorded yet.";
    emit(event);
  });

  on("dblclick", (e) => {
    const el = realTarget(e);
    if (el) emit(base("dblclick", actionTarget(el), null));
  });

  on("input", (e) => {
    const el = realTarget(e);
    if (!el || !isTextLike(el)) return;
    typed.add(el);
    const raw = (el as HTMLElement).isContentEditable ? (el as HTMLElement).innerText : (el as HTMLInputElement).value;
    const masked = maskValue(el, raw);
    if (masked.masked && !isSecretField(el)) el.setAttribute("data-wo-sensitive", "");

    if (pendingInput && pendingInput.el !== el) flushInput();
    if (pendingInput) {
      window.clearTimeout(pendingInput.timer);
      pendingInput.event.value = masked.value;
      pendingInput.event.value_masked = masked.masked;
      pendingInput.event.mask_reason = masked.reason;
      pendingInput.event.ts = Date.now();
    } else {
      const event = base("input", el, captureIdFor(el));
      event.value = masked.value;
      event.value_masked = masked.masked;
      event.mask_reason = masked.reason;
      pendingInput = { el, event, timer: 0 };
    }
    pendingInput.timer = window.setTimeout(() => {
      flushInput();
      void requestCapture(el, false); // typing paused: refresh the page's latest frame
    }, INPUT_IDLE_MS);
  });

  on("focusout", () => flushInput());

  on("change", (e) => {
    const el = realTarget(e);
    if (!el) return;
    if (el.tagName === "SELECT") {
      flushInput();
      const select = el as HTMLSelectElement;
      const option = select.selectedOptions[0];
      const event = base("select", el, captureIdFor(el));
      event.value = select.value;
      event.option_label = collapse(option?.textContent);
      emit(event);
    } else if (isToggle(el)) {
      flushInput();
      const checked = (el as HTMLInputElement).checked;
      emit(base(checked ? "check" : "uncheck", el, captureIdFor(el)));
    } else if (el.tagName === "INPUT" && (el.getAttribute("type") ?? "").toLowerCase() === "file") {
      emit({ ...base("file_input", el, null), warning: "File uploads are recorded but can't be replayed until v0.2." });
    }
  });

  on("keydown", (e) => {
    if (!["Enter", "Tab", "Escape"].includes(e.key)) return;
    const el = realTarget(e);
    if (e.key === "Enter" && el?.tagName === "TEXTAREA") return; // a newline, not an action
    flushInput();
    if (e.key === "Enter") recordUntypedFields(el);
    const target = el && el !== document.body ? el : null;
    const event = base("press", target, null);
    event.key = e.key;
    emit(event);
  });

  on("submit", (e) => {
    flushInput();
    const el = realTarget(e);
    emit(base("submit", el, null));
  });

  on("dragstart", (e) => warn("Drag and drop isn't supported yet; this step won't replay.", realTarget(e)));

  window.addEventListener("pagehide", flushInput, true);

  // --- State from the worker ---

  chrome.runtime.onMessage.addListener((message: { kind: string; status?: RecordingStatus }) => {
    if (message.kind === "state.changed" && message.status) setStatus(message.status);
  });

  void chrome.runtime
    .sendMessage({ kind: "state.get" } satisfies Message)
    .then((reply: { session: { status: RecordingStatus; tabId: number } | null; tabId?: number }) => {
      if (reply?.session) setStatus(reply.session.status);
    })
    .catch(() => undefined);
}
