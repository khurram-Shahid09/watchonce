"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { refresh } from "next/cache";

import { accessToken, api, ApiError } from "@/lib/api";
import { API_URL, REFRESH_COOKIE, clearSession } from "@/lib/session";
import type { Version, WorkflowSpec } from "@/lib/types";

// Server Functions are reachable by POST from anywhere: every one re-checks the session
// through api(), which redirects to /login without a valid token.

export async function logout(): Promise<void> {
  const store = await cookies();
  const refreshToken = store.get(REFRESH_COOKIE)?.value;
  if (refreshToken) {
    await fetch(`${API_URL}/api/v1/auth/logout`, {
      method: "POST",
      headers: { Cookie: `${REFRESH_COOKIE}=${encodeURIComponent(refreshToken)}` },
    }).catch(() => undefined);
  }
  clearSession(store);
  redirect("/login");
}

export interface SaveResult {
  ok: boolean;
  version?: number;
  message?: string;
  errors?: { path: string; message: string }[];
}

export async function saveVersion(
  workflowId: string,
  spec: WorkflowSpec,
  changeNote: string,
  baseVersion: number,
  activate: boolean,
): Promise<SaveResult> {
  try {
    const version = await api<Version>(`/workflows/${encodeURIComponent(workflowId)}/versions`, {
      method: "POST",
      body: JSON.stringify({ spec, change_note: changeNote, base_version: baseVersion, activate }),
    });
    refresh();
    return { ok: true, version: version.version };
  } catch (err) {
    if (err instanceof ApiError) {
      const errors = (err.details.errors as SaveResult["errors"]) ?? [];
      return { ok: false, message: err.message, errors };
    }
    throw err;
  }
}

export async function activateVersion(workflowId: string, version: number): Promise<SaveResult> {
  try {
    await api(`/workflows/${encodeURIComponent(workflowId)}/versions/${version}/activate`, { method: "POST" });
    refresh();
    return { ok: true, version };
  } catch (err) {
    if (err instanceof ApiError) return { ok: false, message: err.message };
    throw err;
  }
}

export async function regenerateSop(workflowId: string, version: number): Promise<SaveResult> {
  try {
    await api(`/workflows/${encodeURIComponent(workflowId)}/versions/${version}/sop`, { method: "POST" });
    refresh();
    return { ok: true, version };
  } catch (err) {
    if (err instanceof ApiError) return { ok: false, message: err.message };
    throw err;
  }
}

export async function recompile(recordingId: string): Promise<SaveResult> {
  try {
    await api(`/recordings/${encodeURIComponent(recordingId)}/compile`, { method: "POST" });
    refresh();
    return { ok: true };
  } catch (err) {
    if (err instanceof ApiError) return { ok: false, message: err.message };
    throw err;
  }
}

export async function setManualDuration(workflowId: string, seconds: number | null): Promise<SaveResult> {
  try {
    await api(`/workflows/${encodeURIComponent(workflowId)}`, {
      method: "PATCH",
      body: JSON.stringify({ manual_duration_sec: seconds }),
    });
    refresh();
    return { ok: true };
  } catch (err) {
    if (err instanceof ApiError) return { ok: false, message: err.message };
    throw err;
  }
}

export interface StartResult extends SaveResult {
  runId?: string;
  inputErrors?: Record<string, string>;
  missing?: string[];
}

export async function startRun(workflowId: string, inputs: Record<string, unknown>, version?: number): Promise<StartResult> {
  try {
    const run = await api<{ id: string }>(`/workflows/${encodeURIComponent(workflowId)}/runs`, {
      method: "POST",
      body: JSON.stringify({ inputs, ...(version ? { version } : {}) }),
    });
    return { ok: true, runId: run.id };
  } catch (err) {
    if (err instanceof ApiError) {
      return {
        ok: false,
        message: err.message,
        inputErrors: err.details.inputs as Record<string, string> | undefined,
        missing: err.details.missing as string[] | undefined,
      };
    }
    throw err;
  }
}

export async function saveSecret(name: string, values: Record<string, string>): Promise<SaveResult> {
  try {
    await api("/secrets", { method: "POST", body: JSON.stringify({ name, values }) });
    refresh();
    return { ok: true };
  } catch (err) {
    if (err instanceof ApiError) {
      const details = Object.values(err.details ?? {}).flat().map(String);
      return { ok: false, message: details[0] ?? err.message };
    }
    throw err;
  }
}

export async function decideCheckpoint(runId: string, stepId: string, decision: "approve" | "reject", note = ""): Promise<SaveResult> {
  try {
    await api(`/runs/${encodeURIComponent(runId)}/checkpoints/${encodeURIComponent(stepId)}`, {
      method: "POST",
      body: JSON.stringify({ decision, note }),
    });
    return { ok: true };
  } catch (err) {
    if (err instanceof ApiError) return { ok: false, message: err.message };
    throw err;
  }
}

export async function cancelRun(runId: string): Promise<SaveResult> {
  try {
    await api(`/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" });
    return { ok: true };
  } catch (err) {
    if (err instanceof ApiError) return { ok: false, message: err.message };
    throw err;
  }
}

export async function decideHeal(healId: string, decision: "approve" | "reject"): Promise<SaveResult> {
  try {
    await api(`/heals/${encodeURIComponent(healId)}/decision`, { method: "POST", body: JSON.stringify({ decision }) });
    refresh();
    return { ok: true };
  } catch (err) {
    if (err instanceof ApiError) return { ok: false, message: err.message };
    throw err;
  }
}

export interface BatchResult extends SaveResult {
  batchId?: string;
  rowErrors?: Record<string, unknown>;
}

export async function createBatch(workflowId: string, form: FormData): Promise<BatchResult> {
  const token = await accessToken();
  if (!token) redirect("/login");
  // Multipart goes straight through (api() speaks JSON).
  const response = await fetch(`${API_URL}/api/v1/workflows/${encodeURIComponent(workflowId)}/batches`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
    cache: "no-store",
  }).catch(() => null);
  if (!response) return { ok: false, message: "Can't reach the WatchOnce API." };
  if (response.status === 401) redirect("/login");
  const body = (await response.json().catch(() => null)) as {
    id?: string;
    error?: { message?: string; details?: { errors?: Record<string, unknown>; missing?: string[] } };
  } | null;
  if (!response.ok) {
    const missing = body?.error?.details?.missing;
    return {
      ok: false,
      message: (body?.error?.message ?? "Couldn't start the batch.") + (missing ? ` Missing: ${missing.join(", ")}.` : ""),
      rowErrors: body?.error?.details?.errors,
    };
  }
  return { ok: true, batchId: body?.id };
}

export async function approveAllBatch(batchId: string): Promise<SaveResult> {
  try {
    await api(`/batches/${encodeURIComponent(batchId)}/approve-all`, { method: "POST" });
    refresh();
    return { ok: true };
  } catch (err) {
    if (err instanceof ApiError) return { ok: false, message: err.message };
    throw err;
  }
}

export async function cancelBatch(batchId: string): Promise<SaveResult> {
  try {
    await api(`/batches/${encodeURIComponent(batchId)}/cancel`, { method: "POST" });
    refresh();
    return { ok: true };
  } catch (err) {
    if (err instanceof ApiError) return { ok: false, message: err.message };
    throw err;
  }
}

export interface AuthoringResult extends SaveResult {
  fieldErrors?: Record<string, string[]>;
}

/** Start the agent: a new workflow from instructions, or (with runId) a fix for a failed run. */
export async function startAuthoring(input: { instructions: string; startUrl?: string; runId?: string }): Promise<AuthoringResult> {
  let id: string;
  try {
    const session = await api<{ id: string }>("/authoring", {
      method: "POST",
      body: JSON.stringify({
        instructions: input.instructions,
        ...(input.startUrl ? { start_url: input.startUrl } : {}),
        ...(input.runId ? { run_id: input.runId } : {}),
      }),
    });
    id = session.id;
  } catch (err) {
    if (err instanceof ApiError) {
      return { ok: false, message: err.message, fieldErrors: err.details as Record<string, string[]> };
    }
    throw err;
  }
  redirect(`/authoring/${id}`);
}

export async function decideAuthoring(sessionId: string, decision: "approve" | "reject"): Promise<SaveResult> {
  try {
    await api(`/authoring/${encodeURIComponent(sessionId)}/decision`, { method: "POST", body: JSON.stringify({ decision }) });
    return { ok: true };
  } catch (err) {
    if (err instanceof ApiError) return { ok: false, message: err.message };
    throw err;
  }
}

export async function cancelAuthoring(sessionId: string): Promise<SaveResult> {
  try {
    await api(`/authoring/${encodeURIComponent(sessionId)}/cancel`, { method: "POST" });
    return { ok: true };
  } catch (err) {
    if (err instanceof ApiError) return { ok: false, message: err.message };
    throw err;
  }
}
