/* eslint-disable */
// GENERATED from packages/spec/workflow.schema.json by scripts/gen-types.mjs. Do not edit.

/**
 * Hostname (optionally with port), no scheme or path.
 */
export type Domain = string;
/**
 * snake_case name used in templates, e.g. vendor_name.
 */
export type Identifier = string;
export type Step =
  NavigateStep | ClickStep | FillStep | SelectStep | CheckStep | PressStep | WaitForStep | AssertStep | ExtractStep;
/**
 * Stable step id, e.g. s7.
 */
export type StepId = string;
export type StepIntent = string;
/**
 * String that may contain {{input}}, {{secrets.name.field}}, {{outputs.name}} and filters.
 */
export type Template = string;
export type TimeoutMs = number;
export type Condition = UrlMatchesCondition | ElementVisibleCondition | TextVisibleCondition | NetworkIdleCondition;
export type Locator =
  TestIdLocator | RoleLocator | TextLocator | LabelLocator | PlaceholderLocator | CssLocator | XPathLocator;
/**
 * Exactly one of value (option value) or label (visible text).
 */
export type SelectStep = {
  id: StepId;
  action: "select";
  intent: StepIntent;
  target: Target;
  value?: Template;
  label?: Template;
  checkpoint?: Checkpoint;
  timeout_ms?: TimeoutMs;
  screenshot_ref?: string;
  assert_after?: Condition;
} & SelectStep1;
export type SelectStep1 =
  | {
      [k: string]: unknown;
    }
  | {
      [k: string]: unknown;
    };

/**
 * WatchOnce workflow spec v1. Human-readable reference: docs/05-workflow-spec.md.
 */
export interface WorkflowSpec {
  spec_version: "1.0";
  name: string;
  description?: string;
  /**
   * @minItems 1
   */
  allowed_domains: [Domain, ...Domain[]];
  start_url: string;
  inputs: Input[];
  secrets: SecretRef[];
  outputs: Output[];
  /**
   * @minItems 1
   */
  steps: [Step, ...Step[]];
  settings: Settings;
  source?: Source;
}
export interface Input {
  name: Identifier;
  type: "string" | "number" | "integer" | "boolean" | "date";
  required?: boolean;
  example?: string | number | boolean;
  description?: string;
  format_hint?: string;
}
export interface SecretRef {
  name: Identifier;
  /**
   * @minItems 1
   */
  fields: [Identifier, ...Identifier[]];
}
export interface Output {
  name: Identifier;
  type: "string" | "number";
  description?: string;
}
export interface NavigateStep {
  id: StepId;
  action: "navigate";
  intent: StepIntent;
  url: Template;
  checkpoint?: Checkpoint;
  timeout_ms?: TimeoutMs;
  screenshot_ref?: string;
  assert_after?: Condition;
}
export interface Checkpoint {
  type: "approval" | "none";
  reason?: string;
}
export interface UrlMatchesCondition {
  type: "url_matches";
  value: string;
}
export interface ElementVisibleCondition {
  type: "element_visible";
  target: Target;
}
export interface Target {
  /**
   * Ordered most robust to least robust.
   *
   * @minItems 1
   */
  locators: [Locator, ...Locator[]];
  fingerprint?: Fingerprint;
  anchor_image_ref?: string;
}
export interface TestIdLocator {
  kind: "testid";
  value: string;
}
export interface RoleLocator {
  kind: "role";
  role: string;
  name?: string;
  exact?: boolean;
}
export interface TextLocator {
  kind: "text";
  value: string;
  exact?: boolean;
}
export interface LabelLocator {
  kind: "label";
  value: string;
  exact?: boolean;
}
export interface PlaceholderLocator {
  kind: "placeholder";
  value: string;
  exact?: boolean;
}
export interface CssLocator {
  kind: "css";
  value: string;
}
export interface XPathLocator {
  kind: "xpath";
  value: string;
}
/**
 * Recorded element descriptor used for L2 fuzzy matching.
 */
export interface Fingerprint {
  tag?: string;
  role?: string | null;
  accessible_name?: string | null;
  text?: string | null;
  attributes?: {
    [k: string]: string | null;
  };
  nearby_text?: string[];
  /**
   * [x, y, width, height] normalized to the viewport (0..1).
   *
   * @minItems 4
   * @maxItems 4
   */
  bbox_norm?: [number, number, number, number];
  frame_path?: string[];
}
export interface TextVisibleCondition {
  type: "text_visible";
  value: Template;
}
export interface NetworkIdleCondition {
  type: "network_idle";
}
export interface ClickStep {
  id: StepId;
  action: "click";
  intent: StepIntent;
  target: Target;
  checkpoint?: Checkpoint;
  timeout_ms?: TimeoutMs;
  screenshot_ref?: string;
  assert_after?: Condition;
}
export interface FillStep {
  id: StepId;
  action: "fill";
  intent: StepIntent;
  target: Target;
  value: Template;
  checkpoint?: Checkpoint;
  timeout_ms?: TimeoutMs;
  screenshot_ref?: string;
  assert_after?: Condition;
}
export interface CheckStep {
  id: StepId;
  action: "check" | "uncheck";
  intent: StepIntent;
  target: Target;
  checkpoint?: Checkpoint;
  timeout_ms?: TimeoutMs;
  screenshot_ref?: string;
  assert_after?: Condition;
}
export interface PressStep {
  id: StepId;
  action: "press";
  intent: StepIntent;
  key: string;
  target?: Target;
  checkpoint?: Checkpoint;
  timeout_ms?: TimeoutMs;
  screenshot_ref?: string;
  assert_after?: Condition;
}
export interface WaitForStep {
  id: StepId;
  action: "wait_for";
  intent: StepIntent;
  condition: Condition;
  checkpoint?: Checkpoint;
  timeout_ms?: TimeoutMs;
  screenshot_ref?: string;
}
export interface AssertStep {
  id: StepId;
  action: "assert";
  intent: StepIntent;
  condition: Condition;
  checkpoint?: Checkpoint;
  timeout_ms?: TimeoutMs;
  screenshot_ref?: string;
}
export interface ExtractStep {
  id: StepId;
  action: "extract";
  intent: StepIntent;
  target: Target;
  attribute?: string;
  output: Identifier;
  pattern?: string;
  checkpoint?: Checkpoint;
  timeout_ms?: TimeoutMs;
  screenshot_ref?: string;
}
export interface Settings {
  default_timeout_ms?: number;
  heal_policy?: "approve" | "auto";
  auto_approve_heal_min_confidence?: number;
  slow_mo_ms?: number;
}
export interface Source {
  recording_id?: string;
  compiled_by?: string;
  compiled_at?: string;
}
