// Sensitive values never leave the browser (threat T1, docs/11-security-privacy.md).

export const SECRET_PLACEHOLDER = "__SECRET__";

const SECRET_AUTOCOMPLETE = new Set(["current-password", "new-password", "one-time-code", "cc-number", "cc-csc", "cc-exp"]);

type Reason = "password_field" | "secret_autocomplete" | "card_number" | "national_id" | "otp_field";

export interface MaskResult {
  value: string;
  masked: boolean;
  reason?: Reason;
}

/** Fields whose content is never captured at all (and are blurred in screenshots). */
export function isSecretField(el: Element): Reason | null {
  if (el.tagName === "INPUT" && (el.getAttribute("type") ?? "").toLowerCase() === "password") return "password_field";
  const autocomplete = (el.getAttribute("autocomplete") ?? "").toLowerCase().split(/\s+/);
  if (autocomplete.some((t) => SECRET_AUTOCOMPLETE.has(t))) return "secret_autocomplete";
  const hint = `${el.getAttribute("name") ?? ""} ${el.getAttribute("id") ?? ""}`.toLowerCase();
  if (/(?:^|[\s_-])(?:otp|totp|mfa|2fa)(?:$|[\s_-])|one[\s_-]?time/.test(hint)) return "otp_field";
  return null;
}

export function luhnValid(digits: string): boolean {
  let sum = 0;
  for (let i = 0; i < digits.length; i++) {
    let d = digits.charCodeAt(digits.length - 1 - i) - 48;
    if (i % 2 === 1) {
      d *= 2;
      if (d > 9) d -= 9;
    }
    sum += d;
  }
  return digits.length > 0 && sum % 10 === 0;
}

// Patterns found anywhere in a value, including inside free text ("Card 4111 … on file").
const PATTERNS: { re: RegExp; reason: Reason; luhn?: boolean }[] = [
  { re: /(?<![\d-])\d(?:[ -]?\d){12,18}(?![\d-])/g, reason: "card_number", luhn: true },
  { re: /(?<![\d-])\d{5}-\d{7}-\d(?![\d-])/g, reason: "national_id" }, // Pakistan CNIC
  { re: /(?<![\d-])\d{13}(?![\d-])/g, reason: "national_id" }, // CNIC without dashes
  { re: /(?<![\d-])\d{3}-\d{2}-\d{4}(?![\d-])/g, reason: "national_id" }, // US SSN
  { re: /(?<![\d-])\d{3}[ -]\d{3}[ -]\d{3}(?![\d-])/g, reason: "national_id", luhn: true }, // Canada SIN
];

/** Replace sensitive numbers inside ``value``. Returns the first reason found, or null. */
export function redactSensitive(value: string): { value: string; reason: Reason | null } {
  let reason: Reason | null = null;
  let out = value;
  for (const p of PATTERNS) {
    out = out.replace(p.re, (match) => {
      if (p.luhn && !luhnValid(match.replace(/[ -]/g, ""))) return match;
      reason ??= p.reason;
      return SECRET_PLACEHOLDER;
    });
  }
  return { value: out, reason };
}

export function looksSensitive(value: string): Reason | null {
  return redactSensitive(value).reason;
}

export function maskValue(el: Element, value: string): MaskResult {
  const field = isSecretField(el);
  if (field) return { value: SECRET_PLACEHOLDER, masked: true, reason: field };
  const redacted = redactSensitive(value);
  if (redacted.reason) return { value: redacted.value, masked: true, reason: redacted.reason };
  return { value, masked: false };
}
