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
  pending_heals: number;
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

export type RunStatus =
  | "queued"
  | "running"
  | "awaiting_approval"
  | "succeeded"
  | "failed"
  | "rejected"
  | "cancelled"
  | "timed_out";

export interface Run {
  id: string;
  workflow_id: string;
  workflow_name: string;
  version: number;
  status: RunStatus;
  triggered_by: string;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  current_step_id: string;
  error_code: string;
  error_message: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface RunStep {
  step_id: string;
  seq: number;
  status: "running" | "ok" | "healed" | "failed" | "skipped" | "awaiting_approval";
  rung: string;
  screenshot_ref: string;
  error: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface RunDetail extends Run {
  steps: RunStep[];
  decisions: { step_id: string; decision: "approve" | "reject"; decided_by: string | null; note: string; created_at: string }[];
}

export interface Secret {
  id: string;
  name: string;
  fields: string[];
  created_at: string;
  rotated_at: string | null;
}

export const FINISHED: RunStatus[] = ["succeeded", "failed", "rejected", "cancelled", "timed_out"];

export interface Heal {
  id: string;
  run_id: string;
  workflow_id: string;
  step_id: string;
  step_intent: string;
  rung: "L2" | "L3";
  score: number;
  model_confidence: number | null;
  explanation: string;
  before_locators: { kind: string; value?: string; role?: string; name?: string }[];
  after_locators: { kind: string; value?: string; role?: string; name?: string }[];
  before_image_ref: string;
  after_image_ref: string;
  resulting_version: { version: number; status: string } | null;
  decision: "pending" | "approved" | "rejected" | "auto";
  decided_by: string | null;
  decided_at: string | null;
  cost_usd: string;
  created_at: string;
}

export interface Batch {
  id: string;
  workflow_id: string;
  workflow_name: string;
  version: number;
  status: "queued" | "running" | "finished" | "cancelled";
  file_name: string;
  columns: string[];
  column_map: Record<string, string>;
  total: number;
  succeeded: number;
  failed: number;
  approve_all: boolean;
  approved_by: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface BatchDetail extends Batch {
  runs: {
    id: string;
    row_index: number;
    status: RunStatus;
    inputs: Record<string, unknown>;
    outputs: Record<string, unknown>;
    current_step_id: string;
    error_message: string;
  }[];
}

export interface AnalyticsSummary {
  range_days: number;
  since: string;
  runs: number;
  succeeded: number;
  success_rate: number | null;
  hours_saved: number;
  workflows_without_duration: number;
  heals: number;
  heals_approved: number;
  heals_pending: number;
  llm_spend_usd: string;
  workflows: {
    workflow_id: string;
    name: string;
    runs: number;
    succeeded: number;
    manual_duration_sec: number | null;
    hours_saved: number;
  }[];
  daily: { date: string; runs: number; succeeded: number }[];
}

export type AuthoringStatus = "queued" | "running" | "awaiting_approval" | "succeeded" | "failed" | "cancelled" | "timed_out";

export const AUTHORING_FINISHED: AuthoringStatus[] = ["succeeded", "failed", "cancelled", "timed_out"];

/** One thing the authoring agent did (or is doing). */
export interface AgentStep {
  n: number;
  intent?: string;
  action?: string;
  status: "running" | "ok" | "failed" | "awaiting_approval" | "skipped";
  error?: string;
  explanation?: string;
  value?: string;
}

export interface AuthoringSession {
  id: string;
  mode: "create" | "fix";
  status: AuthoringStatus;
  start_url: string;
  instructions: string;
  base_version: string | null;
  source_run: string | null;
  steps: AgentStep[];
  question: { n?: number; intent?: string; reason?: string };
  workflow: string | null;
  workflow_name: string;
  version_number: number | null;
  error_code: string;
  error_message: string;
  llm_cost_usd: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}
