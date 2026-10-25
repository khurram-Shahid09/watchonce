"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { refresh } from "next/cache";

import { api, ApiError } from "@/lib/api";
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
