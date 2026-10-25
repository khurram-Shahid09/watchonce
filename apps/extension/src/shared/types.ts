// Recording format v1 (docs/07-recorder-extension.md). Uploaded as events.json and read by the
// compiler (services/core/engine/compiler/recording.py). Keep changes backwards compatible or bump FORMAT_VERSION.

export const FORMAT_VERSION = 1;

export type EventType =
  | "click"
  | "dblclick"
  | "input"
  | "select"
  | "check"
  | "uncheck"
  | "press"
  | "submit"
  | "navigate"
  | "file_input"
  | "warning";

export interface ElementDescriptor {
  tag: string;
  role: string | null;
  accessible_name: string | null;
  text: string | null;
  id: string | null; // null when missing or auto-generated
  classes: string[]; // auto-generated class names removed
  attrs: Record<string, string | null>;
  label_text: string | null;
  css_path: string;
  xpath: string;
  bbox: [number, number, number, number]; // x, y, width, height in CSS px, viewport-relative
  viewport: [number, number];
  nearby_text: string[];
  is_unique: { testid: boolean | null; role_name: boolean | null; text: boolean | null; css: boolean; label: boolean | null };
  shadow_hosts: string[]; // css paths of open shadow-root hosts, outermost first
}

export interface RecordedEvent {
  seq: number;
  ts: number;
  type: EventType;
  url: string;
  frame_path: string[];
  element: ElementDescriptor | null;
  value: string | null;
  value_masked: boolean;
  mask_reason?: string;
  key?: string; // press
  option_label?: string; // select
  nav?: { transition: "link_or_script" | "history" | "reload" | "initial" };
  warning?: string;
  frame_ref: string | null; // "frames/0007.webp", the screenshot taken just before the action
}

/** What the content script sends; the background assigns seq, url check and frame_ref. */
export type CapturedEvent = Omit<RecordedEvent, "seq" | "frame_ref"> & { capture_id: number | null };

export type RecordingStatus = "idle" | "recording" | "paused" | "stopped";

export interface UploadState {
  state: "uploading" | "done" | "failed";
  done: number; // files uploaded
  total: number;
  recordingId: string | null;
  error: string | null;
}

export interface RecordingSession {
  id: string; // local id until uploaded
  status: RecordingStatus;
  tabId: number;
  origin: string;
  startUrl: string;
  startedAt: number;
  stoppedAt: number | null;
  eventCount: number;
  frameCount: number;
  warnings: string[];
  description: string;
  upload?: UploadState;
}

export type Message =
  | { kind: "state.get" }
  | { kind: "recording.start"; tabId: number }
  | { kind: "recording.pause" }
  | { kind: "recording.resume" }
  | { kind: "recording.stop" }
  | { kind: "recording.discard" }
  | { kind: "recording.describe"; description: string }
  | { kind: "recording.export" }
  | { kind: "recording.upload" }
  | { kind: "connection.set"; apiUrl: string; token: string }
  | { kind: "connection.clear" }
  | { kind: "event"; event: CapturedEvent }
  | { kind: "capture.intent"; captureId: number } // sent at pointerdown, before the event itself
  | { kind: "capture"; captureId: number; domChanged: boolean }; // secrets blurred, take it now

export interface StateReply {
  session: RecordingSession | null;
  connection?: { apiUrl: string; email: string; orgId: string; orgName: string } | null;
}

export interface ExportedRecording {
  format_version: number;
  recording: RecordingSession;
  events: RecordedEvent[];
  frames: Record<string, string>; // name → data: URL (export only; upload sends binaries)
}
