// Last 50 diagnostic lines in chrome.storage.session (memory only, cleared with the browser).
// Read them from the worker console: await chrome.storage.session.get("diag")
const KEY = "diag";
let pending: Promise<void> = Promise.resolve();

export function diag(message: string): void {
  const line = `${new Date().toISOString().slice(11, 23)} ${message}`;
  pending = pending.then(async () => {
    const lines = ((await chrome.storage.session.get(KEY))[KEY] as string[] | undefined) ?? [];
    await chrome.storage.session.set({ [KEY]: [...lines, line].slice(-50) });
  }).catch(() => undefined);
}
