// In-page "Recording… Pause | Stop" pill. Lives in a closed shadow root so page styles
// can't touch it and the recorder can recognise (and ignore) events on it.

import type { RecordingStatus } from "../shared/types";

const CSS = `
:host{all:initial}
.pill{position:fixed;right:16px;bottom:16px;z-index:2147483647;display:flex;align-items:center;gap:8px;
  font:600 12px/1 system-ui,-apple-system,Segoe UI,sans-serif;color:#fff;background:#111827;border-radius:999px;
  padding:6px 6px 6px 12px;box-shadow:0 4px 16px rgba(0,0,0,.3);user-select:none}
.dot{width:8px;height:8px;border-radius:50%;background:#ef4444;animation:blink 1.2s infinite}
.paused .dot{background:#f59e0b;animation:none}
button{font:inherit;color:#111827;background:#fff;border:0;border-radius:999px;padding:5px 10px;cursor:pointer}
button.stop{background:#ef4444;color:#fff}
@keyframes blink{50%{opacity:.25}}
`;

export class Pill {
  readonly host: HTMLElement;
  private readonly root: ShadowRoot;
  private readonly label: HTMLSpanElement;
  private readonly toggle: HTMLButtonElement;
  private status: RecordingStatus = "idle";

  constructor(actions: { pause(): void; resume(): void; stop(): void }) {
    this.host = document.createElement("watchonce-recorder");
    this.root = this.host.attachShadow({ mode: "closed" });
    const style = document.createElement("style");
    style.textContent = CSS;
    const pill = document.createElement("div");
    pill.className = "pill";
    pill.setAttribute("role", "status");
    const dot = document.createElement("span");
    dot.className = "dot";
    this.label = document.createElement("span");
    this.toggle = document.createElement("button");
    this.toggle.addEventListener("click", () => (this.status === "paused" ? actions.resume() : actions.pause()));
    const stop = document.createElement("button");
    stop.className = "stop";
    stop.textContent = "Stop";
    stop.addEventListener("click", () => actions.stop());
    pill.append(dot, this.label, this.toggle, stop);
    this.root.append(style, pill);
  }

  show(status: RecordingStatus): void {
    this.status = status;
    const paused = status === "paused";
    this.label.textContent = paused ? "Paused" : "Recording…";
    this.toggle.textContent = paused ? "Resume" : "Pause";
    this.root.querySelector(".pill")!.classList.toggle("paused", paused);
    if (!this.host.isConnected) {
      const attach = () => document.documentElement.appendChild(this.host);
      if (document.documentElement) attach();
      else document.addEventListener("DOMContentLoaded", attach, { once: true });
    }
  }

  hide(): void {
    this.host.remove();
  }

  /** Hidden (not removed) while a screenshot is taken, so it never appears in frames. */
  setHidden(hidden: boolean): void {
    this.host.style.setProperty("display", hidden ? "none" : "", "important");
  }
}
