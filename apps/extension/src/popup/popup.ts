import type { ExportedRecording, Message, RecordingSession, StateReply } from "../shared/types";

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;

async function call<T>(message: Message): Promise<T> {
  const reply = (await chrome.runtime.sendMessage(message)) as T & { error?: string };
  if (reply && typeof reply === "object" && "error" in reply && reply.error) throw new Error(reply.error);
  return reply;
}

function showError(err: unknown): void {
  const el = $("error");
  el.textContent = err instanceof Error ? err.message : String(err);
  el.hidden = false;
}

let session: RecordingSession | null = null;
let ticker: number | undefined;

function render(): void {
  const status = session?.status ?? "idle";
  for (const view of ["idle", "recording", "stopped"]) {
    $(`view-${view}`).hidden = view !== (status === "paused" ? "recording" : status);
  }
  const chip = $("status-chip");
  chip.textContent = { idle: "Idle", recording: "Recording", paused: "Paused", stopped: "Ready to save" }[status];
  chip.className = `chip ${status}`;

  if (session) {
    $("events").textContent = String(session.eventCount);
    $("frames").textContent = String(session.frameCount);
    $("pause").textContent = status === "paused" ? "Resume" : "Pause";
    $("summary").textContent = `${session.eventCount} actions and ${session.frameCount} screenshots on ${session.origin}.`;
    const description = $<HTMLTextAreaElement>("description");
    if (document.activeElement !== description) description.value = session.description;
  }
  const warnings = $("warnings");
  warnings.replaceChildren(
    ...(session?.warnings ?? []).map((w) => Object.assign(document.createElement("li"), { textContent: w })),
  );

  window.clearInterval(ticker);
  if (session && (status === "recording" || status === "paused")) {
    const tick = () => {
      const s = Math.floor((Date.now() - session!.startedAt) / 1000);
      $("elapsed").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    };
    tick();
    ticker = window.setInterval(tick, 1000);
  }
}

async function refresh(): Promise<void> {
  session = (await call<StateReply>({ kind: "state.get" })).session;
  render();
}

async function activeTab(): Promise<chrome.tabs.Tab | undefined> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function init(): Promise<void> {
  const tab = await activeTab();
  const url = tab?.url ? new URL(tab.url) : null;
  const recordable = url !== null && ["http:", "https:"].includes(url.protocol);
  $("site").textContent = recordable ? url.origin : "Open the web app you want to automate, then click Start.";
  $<HTMLButtonElement>("start").disabled = !recordable;

  $("start").addEventListener("click", async () => {
    try {
      // Least privilege: ask for this one site only, at the moment recording starts.
      const granted = await chrome.permissions.request({ origins: [`${url!.origin}/*`] });
      if (!granted) throw new Error("WatchOnce needs access to this site to record it.");
      session = (await call<StateReply>({ kind: "recording.start", tabId: tab!.id! })).session;
      render();
      window.close();
    } catch (err) {
      showError(err);
    }
  });

  $("pause").addEventListener("click", () =>
    call<StateReply>({ kind: session?.status === "paused" ? "recording.resume" : "recording.pause" })
      .then((r) => ((session = r.session), render()))
      .catch(showError),
  );
  $("stop").addEventListener("click", () =>
    call<StateReply>({ kind: "recording.stop" }).then((r) => ((session = r.session), render())).catch(showError),
  );
  $("description").addEventListener("change", (e) =>
    call<StateReply>({ kind: "recording.describe", description: (e.target as HTMLTextAreaElement).value }).catch(showError),
  );
  $("discard").addEventListener("click", async () => {
    if (!confirm("Discard this recording? This can't be undone.")) return;
    await call<StateReply>({ kind: "recording.discard" }).catch(showError);
    await refresh();
  });
  $("download").addEventListener("click", async () => {
    try {
      await call<StateReply>({ kind: "recording.describe", description: $<HTMLTextAreaElement>("description").value });
      const data = await call<ExportedRecording>({ kind: "recording.export" });
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const a = Object.assign(document.createElement("a"), {
        href: URL.createObjectURL(blob),
        download: `watchonce-recording-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.json`,
      });
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (err) {
      showError(err);
    }
  });

  await refresh();
  window.setInterval(() => void refresh().catch(() => undefined), 1000);
}

void init().catch(showError);
