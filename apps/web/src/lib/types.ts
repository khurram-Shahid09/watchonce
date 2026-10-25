// API response shapes (services/core serializers; OpenAPI at /api/v1/docs/).

import type { WorkflowSpec } from "@watchonce/spec";

export type { WorkflowSpec };
export type Step = WorkflowSpec["steps"][number];
export type SpecInput = WorkflowSpec["inputs"][number];

export interface Page<T> {
  results: T[];
  next: string | null;
  previous: string | null;
}

export interface Me {
  id: string;
  email: string;
  name: string;
  memberships: { id: string; role: "owner" | "member"; org: { id: string; name: string; plan: string } }[];
}

export interface VersionSummary {
  id: string;
  version: number;
  status: "draft" | "active" | "pending_heal" | "archived";
  created_by: string;
  change_note: string;
  created_at: string;
}

export interface Workflow {
  id: string;
  name: string;
  description: string;
  recording_id: string | null;
  active_version: VersionSummary | null;
  step_count: number;
  input_count: number;
  manual_duration_sec: number | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowDetail extends Workflow {
  versions: VersionSummary[];
}

export interface Version extends VersionSummary {
  workflow_id: string;
  spec: WorkflowSpec;
  spec_hash: string;
  sop_markdown: string;
  warnings: string[];
  parent_version_id: string | null;
  compile_info: {
    understand?: { by: string; prompt: string; attempts: number };
    sop?: { by: string; prompt?: string };
    frames_sent?: number;
    candidates?: number;
  };
}

export interface Recording {
  id: string;
  description: string;
  status: "uploading" | "uploaded" | "compiling" | "compiled" | "failed";
  start_url: string;
  event_count: number;
  frame_count: number;
  duration_ms: number | null;
  candidate_count: number | null;
  error: string;
  error_code: string;
  workflow_id: string | null;
  created_at: string;
  uploaded_at: string | null;
}
