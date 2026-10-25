// WatchOnce API client for the extension. Signs in with a personal access token (pat_…),
// which is pinned to one workspace (docs/10-api-spec.md). The token lives in
// chrome.storage.local, which only this extension can read.

export interface Connection {
  apiUrl: string; // e.g. http://localhost:8000, no trailing slash
  token: string;
  email: string;
  orgId: string;
  orgName: string;
}

/** What the popup may see: never the token. */
export type PublicConnection = Omit<Connection, "token">;

const KEY = "connection";

export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export function normalizeApiUrl(raw: string): string {
  let url: URL;
  try {
    url = new URL(raw.trim());
  } catch {
    throw new ApiError("invalid_url", "Enter the WatchOnce address, e.g. https://app.watchonce.dev", 0);
  }
  if (!["http:", "https:"].includes(url.protocol)) throw new ApiError("invalid_url", "The address must start with http:// or https://", 0);
  return url.origin;
}

export async function apiFetch<T>(conn: Pick<Connection, "apiUrl" | "token">, path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${conn.apiUrl}/api/v1${path}`, {
      ...init,
      headers: { Authorization: `Bearer ${conn.token}`, "Content-Type": "application/json", ...init.headers },
    });
  } catch {
    throw new ApiError("network_error", `Can't reach ${conn.apiUrl}. Is WatchOnce running?`, 0);
  }
  const body = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const error = (body as { error?: { code?: string; message?: string } } | null)?.error;
    throw new ApiError(error?.code ?? "http_error", error?.message ?? `Request failed (${response.status}).`, response.status);
  }
  return body as T;
}

interface MeResponse {
  email: string;
  token: { org: { id: string; name: string } } | null;
}

/** Check the token against the API and return the connection to store. */
export async function connect(rawUrl: string, rawToken: string): Promise<Connection> {
  const apiUrl = normalizeApiUrl(rawUrl);
  const token = rawToken.trim();
  if (!token.startsWith("pat_")) {
    throw new ApiError("invalid_token", "Paste a personal access token (it starts with pat_).", 0);
  }
  const me = await apiFetch<MeResponse>({ apiUrl, token }, "/me");
  if (!me.token) throw new ApiError("invalid_token", "That isn't a personal access token.", 0);
  return { apiUrl, token, email: me.email, orgId: me.token.org.id, orgName: me.token.org.name };
}

export async function loadConnection(): Promise<Connection | null> {
  const stored = await chrome.storage.local.get(KEY);
  return (stored[KEY] as Connection | undefined) ?? null;
}

export async function saveConnection(conn: Connection | null): Promise<void> {
  if (conn) await chrome.storage.local.set({ [KEY]: conn });
  else await chrome.storage.local.remove(KEY);
}

export function publicView(conn: Connection | null): PublicConnection | null {
  if (!conn) return null;
  const { token: _, ...rest } = conn;
  return rest;
}
