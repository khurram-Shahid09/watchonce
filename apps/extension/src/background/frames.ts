// Screenshots: captureVisibleTab gives JPEG/PNG only; frames are stored as WebP, max 1280 px
// wide (docs/06-ai-pipeline.md key frames). Chrome allows ~2 captures per second per window.
//
// Scheduling, "latest wins": at most one capture runs and at most one waits. A newer request
// replaces the waiting one ("superseded"). Before every attempt the caller confirms the page
// is still the one the capture is for; if the tab has moved on the capture is skipped
// ("stale") instead of spending the budget on a screenshot that would show the wrong page.

import { diag } from "./diag";

const MAX_WIDTH = 1280;
const MIN_GAP_MS = 520; // quota: 2 calls per second
const GLITCH_RETRY_MS = 150; // "image readback failed" while the page is repainting

export type CaptureResult = Blob | "superseded" | "stale" | null;

let lastCaptureAt = 0;
let running: Promise<void> = Promise.resolve();
let waiting: { resolve: (r: CaptureResult) => void } | null = null;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function toWebp(dataUrl: string): Promise<Blob> {
  const bitmap = await createImageBitmap(await (await fetch(dataUrl)).blob());
  const scale = Math.min(1, MAX_WIDTH / bitmap.width);
  const canvas = new OffscreenCanvas(Math.round(bitmap.width * scale), Math.round(bitmap.height * scale));
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return canvas.convertToBlob({ type: "image/webp", quality: 0.7 });
}

async function attempt(windowId: number): Promise<Blob | "quota" | "error"> {
  const wait = lastCaptureAt + MIN_GAP_MS - Date.now();
  if (wait > 0) await sleep(wait);
  lastCaptureAt = Date.now();
  try {
    return await toWebp(await chrome.tabs.captureVisibleTab(windowId, { format: "jpeg", quality: 85 }));
  } catch (err) {
    const message = (err as Error).message;
    diag(`capture failed: ${message}`); // quota, repaint glitch, hidden tab, no activeTab
    return /MAX_CAPTURE_VISIBLE_TAB_CALLS_PER_SECOND/.test(message) ? "quota" : "error";
  }
}

/**
 * Capture the visible area of a window. ``isCurrent`` is checked before each attempt.
 * Null if Chrome refused twice.
 */
export function captureWindow(windowId: number, isCurrent: () => Promise<boolean>): Promise<CaptureResult> {
  waiting?.resolve("superseded");
  return new Promise((resolve) => {
    const me = { resolve };
    waiting = me;
    running = running.then(async () => {
      if (waiting !== me) return; // superseded while queued (already resolved)
      waiting = null;
      for (let tries = 0; tries < 2; tries++) {
        if (!(await isCurrent())) return resolve("stale");
        const result = await attempt(windowId);
        if (result instanceof Blob) return resolve(result);
        if (result === "error") await sleep(GLITCH_RETRY_MS); // quota waits via MIN_GAP_MS
      }
      resolve(null);
    });
  });
}

export async function blobToDataUrl(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return `data:${blob.type};base64,${btoa(binary)}`;
}
