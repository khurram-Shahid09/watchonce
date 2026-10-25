// Service worker: owns the recording session. Content scripts report actions; this worker
// numbers them, attaches the screenshot taken just before each one, and buffers everything
// in IndexedDB. When stopped, the recording is uploaded to the connected workspace.

import {
  FORMAT_VERSION,
  type CapturedEvent,
  type ExportedRecording,
  type Message,
  type RecordedEvent,
  type RecordingSession,
  type RecordingStatus,
  type UploadState,
} from "../shared/types";
import { ApiError, connect, loadConnection, publicView, saveConnection } from "./api";
import { diag } from "./diag";
import { blobToDataUrl, captureWindow } from "./frames";
import { countFrames, deleteRecording, getEvents, getFrames, loadSession, putEvent, putFrame, saveSession } from "./store";
import { uploadRecording } from "./upload";

const CONTENT_SCRIPT_ID = "watchonce-recorder";
const FRAME_WAIT_MS = 1500;

// Frames requested by content scripts. Keyed by document + capture id (ids restart on every
// page load). In memory only: if the worker restarts mid-recording an event may lose its
// frame, which the compiler tolerates.
interface PendingFrame {
  promise: Promise<string | null>;
  resolve: (name: string | null) => void;
}
const frameByCapture = new Map<string, PendingFrame>();
const captureKey = (sender: chrome.runtime.MessageSender, id: number) => `${sender.documentId ?? sender.tab?.id}:${id}`;

function announceCapture(key: string): PendingFrame {
  let resolve!: (name: string | null) => void;
  const promise = new Promise<string | null>((r) => (resolve = r));
  const pending = { promise, resolve };
  frameByCapture.set(key, pending);
  setTimeout(() => {
    resolve(null); // never captured (page left first); no-op if already resolved
    frameByCapture.delete(key);
  }, 15_000);
  return pending;
}
// Latest frame of each page (URL without fragment). An action whose own screenshot didn't
// arrive in time falls back to the latest frame *of the same page*, never another page's.
const framesByUrl = new Map<string, string>();
const pageOf = (url: string | undefined) => (url ?? "").split("#")[0]!;
const frameFor = (url: string | undefined) => framesByUrl.get(pageOf(url)) ?? null;

// All session mutations go through one chain so seq numbers never collide and events keep
// arrival order. Frames use a separate chain: an event waits for its frame while holding the
// session chain, so frame writes must never need that chain (that would deadlock).
let chain: Promise<unknown> = Promise.resolve();
function serialized<T>(fn: () => Promise<T>): Promise<T> {
  const next = chain.then(fn, fn);
  chain = next.catch(() => undefined);
  return next;
}
let frameChain: Promise<unknown> = Promise.resolve();
let frameCounter: { sessionId: string; next: number } | null = null;
function writeFrame(sessionId: string, blob: Blob): Promise<string> {
  const run = async () => {
    if (frameCounter?.sessionId !== sessionId) frameCounter = { sessionId, next: (await countFrames(sessionId)) + 1 };
    const name = `frames/${String(frameCounter.next++).padStart(4, "0")}.webp`;
    await putFrame(sessionId, name, blob);
    return name;
  };
  const next = frameChain.then(run, run);
  frameChain = next.catch(() => undefined);
  return next;
}

async function withFrameCount(session: RecordingSession | null): Promise<RecordingSession | null> {
  return session ? { ...session, frameCount: await countFrames(session.id) } : null;
}

// --- Session lifecycle ---

async function broadcast(session: RecordingSession | null): Promise<void> {
  const status: RecordingStatus = session?.status ?? "idle";
  const badge: Record<RecordingStatus, [string, string]> = {
    idle: ["", "#000000"],
    recording: ["REC", "#dc2626"],
    paused: ["II", "#d97706"],
    stopped: ["✓", "#2563eb"],
  };
  await chrome.action.setBadgeText({ text: badge[status][0] });
  await chrome.action.setBadgeBackgroundColor({ color: badge[status][1] });
  if (session) {
    await chrome.tabs.sendMessage(session.tabId, { kind: "state.changed", status }).catch(() => undefined);
  }
}

async function startRecording(tabId: number): Promise<RecordingSession> {
  const existing = await loadSession();
  if (existing && existing.status !== "idle") throw new Error("A recording is already in progress or waiting to be saved.");

  const tab = await chrome.tabs.get(tabId);
  const url = new URL(tab.url ?? "");
  if (!["http:", "https:"].includes(url.protocol)) throw new Error("Open the web app you want to automate first.");
  const origin = url.origin;
  if (!(await chrome.permissions.contains({ origins: [`${origin}/*`] }))) {
    throw new Error(`WatchOnce needs permission to record on ${origin}.`);
  }

  await chrome.scripting.unregisterContentScripts({ ids: [CONTENT_SCRIPT_ID] }).catch(() => undefined);
  await chrome.scripting.registerContentScripts([
    { id: CONTENT_SCRIPT_ID, matches: [`${origin}/*`], js: ["content.js"], runAt: "document_start", allFrames: false, persistAcrossSessions: false },
  ]);

  const session: RecordingSession = {
    id: `local_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
    status: "recording",
    tabId,
    origin,
    startUrl: url.href,
    startedAt: Date.now(),
    stoppedAt: null,
    eventCount: 0,
    frameCount: 0,
    warnings: [],
    description: "",
  };
  await saveSession(session);
  framesByUrl.clear();
  frameCounter = null;
  frameByCapture.clear();

  // The page is already loaded: inject now (later navigations use the registration above).
  await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
  await appendEvent(session, {
    ts: Date.now(),
    type: "navigate",
    url: url.href,
    frame_path: [],
    element: null,
    value: null,
    value_masked: false,
    nav: { transition: "initial" },
    capture_id: null,
  });
  await broadcast(session);
  // The page as it was when recording started: if the first action leaves the page at once
  // (e.g. an autofilled login's Sign in), it still has a picture to fall back on.
  if (tab.windowId !== undefined) void capturePage(session, tab.windowId, url.href, "recording start");
  return session;
}

async function setStatus(status: RecordingStatus): Promise<RecordingSession | null> {
  return serialized(async () => {
    const session = await loadSession();
    if (!session) return null;
    session.status = status;
    if (status === "stopped") {
      session.stoppedAt = Date.now();
      await chrome.scripting.unregisterContentScripts({ ids: [CONTENT_SCRIPT_ID] }).catch(() => undefined);
    }
    await saveSession(session);
    await broadcast(session);
    return session;
  });
}

async function discard(): Promise<void> {
  await serialized(async () => {
    const session = await loadSession();
    if (session?.upload?.state === "uploading") throw new Error("Wait for the upload to finish.");
    if (session) {
      await chrome.tabs.sendMessage(session.tabId, { kind: "state.changed", status: "idle" }).catch(() => undefined);
      await deleteRecording(session.id);
    }
    await chrome.scripting.unregisterContentScripts({ ids: [CONTENT_SCRIPT_ID] }).catch(() => undefined);
    await saveSession(null);
    await broadcast(null);
  });
}

// --- Events and frames ---

async function warn(session: RecordingSession, message: string): Promise<void> {
  if (!session.warnings.includes(message)) session.warnings.push(message);
  await saveSession(session);
}

/** Append one event (caller holds the serialized chain or owns the session object). */
async function appendEvent(session: RecordingSession, captured: CapturedEvent, frameKey: string | null = null): Promise<void> {
  const { capture_id: _, ...rest } = captured;
  let frame_ref: string | null = null;
  if (frameKey) {
    const pending = frameByCapture.get(frameKey);
    if (pending) {
      frame_ref = await Promise.race([pending.promise, new Promise<null>((r) => setTimeout(() => r(null), FRAME_WAIT_MS))]);
    }
    frame_ref ??= frameFor(captured.url); // e.g. the page navigated before its capture ran
  }
  const event: RecordedEvent = { ...rest, seq: session.eventCount + 1, frame_ref };
  await putEvent(session.id, event);
  session.eventCount = event.seq;
  if (event.warning) await warn(session, event.warning);
  await saveSession(session);
}

function onEvent(sender: chrome.runtime.MessageSender, captured: CapturedEvent): Promise<void> {
  const frameKey = captured.capture_id !== null ? captureKey(sender, captured.capture_id) : null;
  return serialized(async () => {
    const session = await loadSession();
    if (!session || session.status !== "recording" || session.tabId !== sender.tab?.id) return;
    await appendEvent(session, captured, frameKey);
  });
}

const SCREENSHOT_WARNING = "Screenshots paused: click the WatchOnce icon to resume them. Actions are still recorded.";

function setScreenshotWarning(sessionId: string, failing: boolean): Promise<void> {
  return serialized(async () => {
    const session = await loadSession();
    if (session?.id !== sessionId || session.warnings.includes(SCREENSHOT_WARNING) === failing) return;
    // Usually a failure means Chrome withdrew the activeTab grant (e.g. after leaving the site).
    session.warnings = failing
      ? [...session.warnings, SCREENSHOT_WARNING]
      : session.warnings.filter((w) => w !== SCREENSHOT_WARNING);
    await saveSession(session);
  });
}

/**
 * Screenshot of ``pageUrl`` as it is now, or the latest earlier frame of that page.
 * Never awaits the session chain (events hold it while waiting for frames).
 */
async function capturePage(session: RecordingSession, windowId: number, pageUrl: string, label: string): Promise<string | null> {
  // captureVisibleTab photographs the window's *active* tab: never capture unless that is
  // the tab being recorded, or we could save a screenshot of some other page.
  const isCurrent = async () => {
    const live = await chrome.tabs.get(session.tabId).catch(() => null);
    return Boolean(live?.active) && pageOf(live?.url) === pageOf(pageUrl);
  };
  const result = await captureWindow(windowId, isCurrent);
  diag(`${label}: ${result instanceof Blob ? "ok" : String(result)}`);
  // A newer action took the slot, or the tab already moved on: use this page's latest frame.
  if (result === "superseded" || result === "stale") return frameFor(pageUrl);
  void setScreenshotWarning(session.id, result === null);
  if (result === null) return frameFor(pageUrl);
  // A capture that ran after the tab moved on shows the *next* page: never label it as this one.
  const after = await chrome.tabs.get(session.tabId).catch(() => null);
  if (pageOf(after?.url) !== pageOf(pageUrl)) {
    diag(`${label}: page changed during capture, discarded`);
    return frameFor(pageUrl);
  }
  const name = await writeFrame(session.id, result);
  framesByUrl.set(pageOf(pageUrl), name);
  return name;
}

function onCapture(sender: chrome.runtime.MessageSender, captureId: number, domChanged: boolean): Promise<boolean> {
  const tab = sender.tab;
  const key = captureKey(sender, captureId);
  const pending = frameByCapture.get(key) ?? announceCapture(key);
  const capture = (async (): Promise<string | null> => {
    const session = await loadSession();
    if (!session || session.status !== "recording" || tab?.id !== session.tabId || tab.windowId === undefined) return null;
    // Nothing changed since this page's last frame: reuse it instead of spending the budget.
    if (!domChanged && frameFor(tab.url)) return frameFor(tab.url);
    return capturePage(session, tab.windowId, tab.url ?? "", `capture ${captureId}`);
  })();
  return capture.then((name) => {
    pending.resolve(name);
    return name !== null;
  });
}

// --- Navigation and tabs ---

chrome.tabs.onUpdated.addListener((tabId, change, tab) => {
  if (change.status === "complete" && tab.url) {
    // One frame per loaded page, so every screen has at least one true picture of itself.
    void loadSession().then((session) => {
      if (session?.status === "recording" && session.tabId === tabId && !frameFor(tab.url)) {
        return capturePage(session, tab.windowId, tab.url!, "page load");
      }
    });
  }
  if (!change.url) return;
  const ts = Date.now(); // when it happened, not when the queue gets to it
  void serialized(async () => {
    const session = await loadSession();
    if (!session || session.status !== "recording" || session.tabId !== tabId) return;
    const url = new URL(change.url!);
    await appendEvent(session, {
      ts,
      type: "navigate",
      url: url.href,
      frame_path: [],
      element: null,
      value: null,
      value_masked: false,
      nav: { transition: "link_or_script" },
      capture_id: null,
      ...(url.origin !== session.origin
        ? { warning: `Left the recorded site (${session.origin}). Actions on ${url.origin} aren't recorded.` }
        : {}),
    });
  });
});

// Back on the recorded tab (e.g. after the popup or another tab had focus): make sure its
// current page has a picture before the next action needs one.
chrome.tabs.onActivated.addListener(({ tabId, windowId }) => {
  void (async () => {
    const session = await loadSession();
    if (session?.status !== "recording" || session.tabId !== tabId) return;
    const tab = await chrome.tabs.get(tabId).catch(() => null);
    if (tab?.url && !frameFor(tab.url)) await capturePage(session, windowId, tab.url, "tab activated");
  })();
});

chrome.tabs.onCreated.addListener((tab) => {
  void serialized(async () => {
    const session = await loadSession();
    if (session?.status === "recording" && tab.openerTabId === session.tabId) {
      await warn(session, "Multi-tab flows are coming in v0.2. Recording continues in the original tab.");
    }
  });
});

chrome.tabs.onRemoved.addListener((tabId) => {
  void loadSession().then((s) => (s && s.tabId === tabId && s.status !== "stopped" ? setStatus("stopped") : undefined));
});

// --- Export (Day 4 stand-in for upload) ---

async function exportRecording(): Promise<ExportedRecording | null> {
  const session = await loadSession();
  if (!session) return null;
  const frames: Record<string, string> = {};
  for (const f of await getFrames(session.id)) frames[f.name] = await blobToDataUrl(f.blob);
  return {
    format_version: FORMAT_VERSION,
    recording: { ...session, frameCount: Object.keys(frames).length },
    events: await getEvents(session.id),
    frames,
  };
}

// --- Upload ---

function setUpload(sessionId: string, upload: UploadState): Promise<void> {
  return serialized(async () => {
    const session = await loadSession();
    if (session?.id !== sessionId) return;
    session.upload = upload;
    await saveSession(session);
  });
}

async function startUpload(): Promise<RecordingSession> {
  const conn = await loadConnection();
  if (!conn) throw new Error("Connect your WatchOnce workspace first.");
  const session = await serialized(async () => {
    const s = await loadSession();
    if (!s || s.status !== "stopped") throw new Error("Stop the recording before uploading.");
    if (s.upload?.state === "uploading") throw new Error("Already uploading.");
    if (s.upload?.state === "done") throw new Error("This recording is already uploaded.");
    if (!s.description.trim()) throw new Error("Describe what this task does first.");
    s.upload = { state: "uploading", done: 0, total: 0, recordingId: null, error: null };
    await saveSession(s);
    return s;
  });

  // Runs on after the reply; the popup follows progress through state.get.
  void (async () => {
    let progress = { done: 0, total: 0 };
    let reported = 0;
    try {
      const [events, frames] = await Promise.all([getEvents(session.id), getFrames(session.id)]);
      const id = await uploadRecording(conn, { session, events, frames }, (done, total) => {
        progress = { done, total };
        if (done === total || Date.now() - reported > 300) {
          reported = Date.now();
          void setUpload(session.id, { state: "uploading", ...progress, recordingId: null, error: null });
        }
      });
      await setUpload(session.id, { state: "done", ...progress, recordingId: id, error: null });
      diag(`upload: ${id} done (${progress.total} files)`);
    } catch (err) {
      const message =
        err instanceof ApiError && err.status === 401
          ? "Your access token was revoked or has expired. Connect again."
          : err instanceof Error
            ? err.message
            : String(err);
      diag(`upload failed: ${message}`);
      await setUpload(session.id, { state: "failed", ...progress, recordingId: null, error: message });
    }
  })();
  return session;
}

// --- Messages ---

async function handle(message: Message, sender: chrome.runtime.MessageSender): Promise<unknown> {
  // Our own pages (popup) vs content scripts. The popup can also be open in a tab (tests),
  // so look at the sender's URL, not at whether it has a tab.
  const fromExtension = sender.id === chrome.runtime.id && (sender.url ?? "").startsWith(chrome.runtime.getURL(""));
  const fromTab = fromExtension ? undefined : sender.tab?.id;
  switch (message.kind) {
    case "state.get": {
      const session = await loadSession();
      // Content scripts in other tabs of the same site must stay inert.
      if (fromTab !== undefined && session?.tabId !== fromTab) return { session: null };
      return { session: await withFrameCount(session), connection: fromExtension ? publicView(await loadConnection()) : null };
    }
    case "recording.start":
      return { session: await startRecording(message.tabId) };
    case "recording.pause":
      return { session: await setStatus("paused") };
    case "recording.resume":
      return { session: await setStatus("recording") };
    case "recording.stop":
      return { session: await setStatus("stopped") };
    case "recording.discard":
      await discard();
      return { session: null };
    case "recording.describe":
      return serialized(async () => {
        const session = await loadSession();
        if (session) {
          session.description = message.description.slice(0, 1000);
          await saveSession(session);
        }
        return { session };
      });
    case "recording.export":
      return exportRecording();
    case "recording.upload":
      return { session: await startUpload() };
    case "connection.set": {
      if (!fromExtension) throw new Error("Not allowed.");
      const conn = await connect(message.apiUrl, message.token);
      await saveConnection(conn);
      return { connection: publicView(conn) };
    }
    case "connection.clear":
      if (!fromExtension) throw new Error("Not allowed.");
      await saveConnection(null);
      return { connection: null };
    case "capture.intent":
      announceCapture(captureKey(sender, message.captureId)); // synchronous: before any await
      return { ok: true };
    case "event":
      await onEvent(sender, message.event);
      return { ok: true };
    case "capture":
      return { ok: await onCapture(sender, message.captureId, message.domChanged) };
  }
}

chrome.runtime.onMessage.addListener((message: Message, sender, sendResponse) => {
  handle(message, sender).then(sendResponse, (err: Error) => sendResponse({ error: err.message }));
  return true; // async response
});

// Alt+Shift+R: stop when recording, otherwise open the popup to start (permission prompts need it).
chrome.commands.onCommand.addListener((command) => {
  if (command !== "toggle-recording") return;
  void (async () => {
    const s = await loadSession();
    if (s?.status === "recording" || s?.status === "paused") await setStatus("stopped");
    else await chrome.action.openPopup().catch(() => undefined);
  })();
});

// Restore the badge after a browser restart. An upload can't survive a worker restart.
void loadSession().then(async (session) => {
  if (session?.upload?.state === "uploading") {
    await setUpload(session.id, { ...session.upload, state: "failed", error: "The upload was interrupted. Try again." });
  }
  await broadcast(session);
});
