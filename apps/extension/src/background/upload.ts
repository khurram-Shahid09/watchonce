// Upload a finished recording (docs/10-api-spec.md "Recordings"):
// create → PUT events.json and frames straight to object storage → complete.

import { FORMAT_VERSION, type RecordedEvent, type RecordingSession } from "../shared/types";
import { apiFetch, ApiError, type Connection } from "./api";

const PARALLEL_PUTS = 4;
const PUT_ATTEMPTS = 3;

interface Created {
  id: string;
  upload: { events_url: string; frames: { name: string; url: string }[] };
}

export interface UploadInput {
  session: RecordingSession;
  events: RecordedEvent[];
  frames: { name: string; blob: Blob }[];
}

async function put(url: string, body: Blob, contentType: string): Promise<void> {
  for (let attempt = 1; ; attempt++) {
    try {
      const response = await fetch(url, { method: "PUT", body, headers: { "Content-Type": contentType } });
      if (response.ok) return;
      if (response.status < 500 || attempt >= PUT_ATTEMPTS) {
        throw new ApiError("upload_failed", `Storage refused a file (${response.status}).`, response.status);
      }
    } catch (err) {
      if (err instanceof ApiError || attempt >= PUT_ATTEMPTS) {
        throw err instanceof ApiError ? err : new ApiError("upload_failed", "Lost the connection while uploading.", 0);
      }
    }
    await new Promise((r) => setTimeout(r, 500 * attempt));
  }
}

/** Returns the new recording id. ``onProgress`` gets files done / total. */
export async function uploadRecording(
  conn: Connection,
  { session, events, frames }: UploadInput,
  onProgress: (done: number, total: number) => void,
): Promise<string> {
  const created = await apiFetch<Created>(conn, "/recordings", {
    method: "POST",
    body: JSON.stringify({
      description: session.description,
      start_url: session.startUrl,
      event_count: events.length,
      duration_ms: session.stoppedAt ? session.stoppedAt - session.startedAt : undefined,
      frames: frames.map((f) => f.name),
    }),
  });

  const total = 1 + frames.length;
  let done = 0;
  const tick = () => onProgress(++done, total);
  onProgress(0, total);

  const { upload: _upload, ...meta } = session;
  const eventsJson = JSON.stringify({ format_version: FORMAT_VERSION, recording: meta, events });
  await put(created.upload.events_url, new Blob([eventsJson], { type: "application/json" }), "application/json");
  tick();

  const blobs = new Map(frames.map((f) => [f.name, f.blob]));
  const queue = [...created.upload.frames];
  const worker = async () => {
    for (let next = queue.shift(); next; next = queue.shift()) {
      await put(next.url, blobs.get(next.name)!, "image/webp");
      tick();
    }
  };
  await Promise.all(Array.from({ length: PARALLEL_PUTS }, worker));

  await apiFetch(conn, `/recordings/${created.id}/complete`, { method: "POST" });
  return created.id;
}
