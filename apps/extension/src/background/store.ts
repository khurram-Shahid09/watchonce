// Crash-safe buffer: events and frames go to IndexedDB as they happen; the session record
// lives in chrome.storage.local. A browser crash or worker restart loses nothing.

import type { RecordedEvent, RecordingSession } from "../shared/types";

const DB_NAME = "watchonce-recorder";
const SESSION_KEY = "session";

let dbPromise: Promise<IDBDatabase> | null = null;

function db(): Promise<IDBDatabase> {
  dbPromise ??= new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore("events", { keyPath: ["sessionId", "seq"] });
      req.result.createObjectStore("frames", { keyPath: ["sessionId", "name"] });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

function done(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = tx.onabort = () => reject(tx.error);
  });
}

function all<T>(req: IDBRequest<T[]>): Promise<T[]> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

const range = (sessionId: string) => IDBKeyRange.bound([sessionId], [sessionId, []]);

export async function putEvent(sessionId: string, event: RecordedEvent): Promise<void> {
  const tx = (await db()).transaction("events", "readwrite");
  tx.objectStore("events").put({ sessionId, ...event });
  await done(tx);
}

export async function putFrame(sessionId: string, name: string, blob: Blob): Promise<void> {
  const tx = (await db()).transaction("frames", "readwrite");
  tx.objectStore("frames").put({ sessionId, name, blob });
  await done(tx);
}

export async function getEvents(sessionId: string): Promise<RecordedEvent[]> {
  const tx = (await db()).transaction("events");
  const rows = await all<RecordedEvent & { sessionId?: string }>(tx.objectStore("events").getAll(range(sessionId)));
  return rows.map(({ sessionId: _, ...event }) => event).sort((a, b) => a.seq - b.seq);
}

export async function getFrames(sessionId: string): Promise<{ name: string; blob: Blob }[]> {
  const tx = (await db()).transaction("frames");
  return all<{ name: string; blob: Blob }>(tx.objectStore("frames").getAll(range(sessionId)));
}

export async function countFrames(sessionId: string): Promise<number> {
  const tx = (await db()).transaction("frames");
  return new Promise((resolve, reject) => {
    const req = tx.objectStore("frames").count(range(sessionId));
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function deleteRecording(sessionId: string): Promise<void> {
  const tx = (await db()).transaction(["events", "frames"], "readwrite");
  tx.objectStore("events").delete(range(sessionId));
  tx.objectStore("frames").delete(range(sessionId));
  await done(tx);
}

export async function loadSession(): Promise<RecordingSession | null> {
  const stored = await chrome.storage.local.get(SESSION_KEY);
  return (stored[SESSION_KEY] as RecordingSession | undefined) ?? null;
}

export async function saveSession(session: RecordingSession | null): Promise<void> {
  if (session) await chrome.storage.local.set({ [SESSION_KEY]: session });
  else await chrome.storage.local.remove(SESSION_KEY);
}
