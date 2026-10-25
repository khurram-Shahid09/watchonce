import { afterEach, describe, expect, it, vi } from "vitest";

import type { RecordedEvent, RecordingSession } from "../shared/types";
import { ApiError, connect, normalizeApiUrl } from "./api";
import { uploadRecording } from "./upload";

const conn = { apiUrl: "http://api.test", token: "pat_secret", email: "sara@acme.test", orgId: "org_1", orgName: "Acme" };

const session: RecordingSession = {
  id: "local_1",
  status: "stopped",
  tabId: 1,
  origin: "http://acme.test",
  startUrl: "http://acme.test/login",
  startedAt: 1_000,
  stoppedAt: 31_000,
  eventCount: 2,
  frameCount: 2,
  warnings: [],
  description: "Create an invoice",
  upload: { state: "uploading", done: 0, total: 0, recordingId: null, error: null },
};

const event = (seq: number): RecordedEvent => ({
  seq,
  ts: seq,
  type: "click",
  url: "http://acme.test/",
  frame_path: [],
  element: null,
  value: null,
  value_masked: false,
  frame_ref: null,
});

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

interface Call {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: unknown;
}

function mockFetch(handler: (call: Call) => Response | Promise<Response>): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const call = { url, method: init.method ?? "GET", headers: (init.headers ?? {}) as Record<string, string>, body: init.body };
      calls.push(call);
      return handler(call);
    }),
  );
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe("uploadRecording", () => {
  const created = {
    id: "rec_1",
    upload: {
      events_url: "http://s3.test/events.json?sig",
      frames: [
        { name: "frames/0001.webp", url: "http://s3.test/0001?sig" },
        { name: "frames/0002.webp", url: "http://s3.test/0002?sig" },
      ],
    },
  };
  const frames = [
    { name: "frames/0001.webp", blob: new Blob(["a"], { type: "image/webp" }) },
    { name: "frames/0002.webp", blob: new Blob(["b"], { type: "image/webp" }) },
  ];

  it("creates, uploads every file to storage, then completes", async () => {
    const calls = mockFetch(({ url }) =>
      url.endsWith("/recordings") ? json(201, created) : url.endsWith("/complete") ? json(202, {}) : new Response(null, { status: 200 }),
    );
    const progress: [number, number][] = [];
    const id = await uploadRecording(conn, { session, events: [event(1), event(2)], frames }, (d, t) => progress.push([d, t]));

    expect(id).toBe("rec_1");
    const create = calls[0]!;
    expect(create.headers.Authorization).toBe("Bearer pat_secret");
    expect(JSON.parse(create.body as string)).toEqual({
      description: "Create an invoice",
      start_url: "http://acme.test/login",
      event_count: 2,
      duration_ms: 30_000,
      frames: ["frames/0001.webp", "frames/0002.webp"],
    });

    const puts = calls.filter((c) => c.method === "PUT");
    expect(puts.map((c) => [c.url, c.headers["Content-Type"]])).toEqual([
      ["http://s3.test/events.json?sig", "application/json"],
      ["http://s3.test/0001?sig", "image/webp"],
      ["http://s3.test/0002?sig", "image/webp"],
    ]);
    expect(puts.every((c) => !("Authorization" in c.headers))).toBe(true); // the token never goes to storage
    const uploaded = JSON.parse(await (puts[0]!.body as Blob).text());
    expect(uploaded.format_version).toBe(1);
    expect(uploaded.events).toHaveLength(2);
    expect(uploaded.recording.upload).toBeUndefined();

    expect(calls.at(-1)!.url).toBe("http://api.test/api/v1/recordings/rec_1/complete");
    expect(progress.at(-1)).toEqual([3, 3]);
  });

  it("retries a storage hiccup, then succeeds", async () => {
    let failures = 1;
    mockFetch(({ url }) => {
      if (url.endsWith("/recordings")) return json(201, { ...created, upload: { ...created.upload, frames: [] } });
      if (url.endsWith("/complete")) return json(202, {});
      return failures-- > 0 ? new Response(null, { status: 503 }) : new Response(null, { status: 200 });
    });
    await expect(uploadRecording(conn, { session, events: [event(1)], frames: [] }, () => undefined)).resolves.toBe("rec_1");
  });

  it("surfaces API errors with their code", async () => {
    mockFetch(() => json(409, { error: { code: "upload_incomplete", message: "1 file(s) haven't been uploaded yet.", details: {} } }));
    const failure = uploadRecording(conn, { session, events: [], frames: [] }, () => undefined);
    await expect(failure).rejects.toMatchObject({ code: "upload_incomplete", status: 409 });
  });
});

describe("connect", () => {
  it("checks the token and remembers the workspace", async () => {
    const calls = mockFetch(() => json(200, { email: "sara@acme.test", token: { org: { id: "org_1", name: "Acme" } } }));
    const result = await connect("http://localhost:8000/some/path ", " pat_abc ");
    expect(result).toEqual({ apiUrl: "http://localhost:8000", token: "pat_abc", email: "sara@acme.test", orgId: "org_1", orgName: "Acme" });
    expect(calls[0]!.url).toBe("http://localhost:8000/api/v1/me");
  });

  it("rejects things that aren't access tokens before calling the API", async () => {
    const calls = mockFetch(() => json(200, {}));
    await expect(connect("http://localhost:8000", "eyJhbGciOi...")).rejects.toBeInstanceOf(ApiError);
    expect(calls).toHaveLength(0);
  });

  it("explains an unreachable server", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(connect("http://localhost:8000", "pat_abc")).rejects.toMatchObject({ code: "network_error" });
  });

  it("only accepts http(s) addresses", () => {
    expect(() => normalizeApiUrl("javascript:alert(1)")).toThrow(ApiError);
    expect(normalizeApiUrl("https://app.watchonce.dev/")).toBe("https://app.watchonce.dev");
  });
});
