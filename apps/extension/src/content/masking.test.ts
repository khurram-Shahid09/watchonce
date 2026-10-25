import { describe, expect, it } from "vitest";

import { isSecretField, looksSensitive, luhnValid, maskValue, SECRET_PLACEHOLDER } from "./masking";

const input = (attrs: Record<string, string | undefined>) => {
  const el = document.createElement("input");
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined) el.setAttribute(k, v);
  return el;
};

describe("secret fields are never captured", () => {
  it.each([
    [{ type: "password" }, "password_field"],
    [{ autocomplete: "one-time-code" }, "secret_autocomplete"],
    [{ autocomplete: "section-a cc-number" }, "secret_autocomplete"],
    [{ name: "otp" }, "otp_field"],
    [{ id: "mfa-code" }, "otp_field"],
  ])("%o → %s", (attrs, reason) => {
    const el = input(attrs);
    expect(isSecretField(el)).toBe(reason);
    expect(maskValue(el, "hunter2")).toEqual({ value: SECRET_PLACEHOLDER, masked: true, reason });
  });

  it("leaves ordinary fields alone", () => {
    for (const attrs of [{ type: "text" }, { name: "shipping_option" }, { name: "topic" }]) {
      expect(isSecretField(input(attrs))).toBeNull();
    }
    expect(maskValue(input({ name: "vendor" }), "Northwind Ltd")).toEqual({ value: "Northwind Ltd", masked: false });
  });
});

describe("sensitive-looking values are masked anywhere", () => {
  it.each([
    ["4111 1111 1111 1111", "card_number"],
    ["4111-1111-1111-1111", "card_number"],
    ["35202-1234567-1", "national_id"], // CNIC
    ["123-45-6789", "national_id"], // SSN
    ["046 454 286", "national_id"], // SIN (Luhn-valid)
  ])("%s → %s", (value, reason) => {
    expect(looksSensitive(value)).toBe(reason);
    expect(maskValue(input({}), value).masked).toBe(true);
  });

  it.each(["1250.50", "INV-200345", "4111 1111 1111 1112", "11/15/2026", "123 456 789", "+1 416 555 0199"])(
    "%s is not masked",
    (value) => expect(looksSensitive(value)).toBeNull(),
  );

  it("redacts only the sensitive part of free text", () => {
    expect(maskValue(input({ name: "description" }), "Card 4111 1111 1111 1111 on file")).toEqual({
      value: `Card ${SECRET_PLACEHOLDER} on file`,
      masked: true,
      reason: "card_number",
    });
    expect(maskValue(input({}), "Order 12345 for INV-200345").masked).toBe(false);
  });

  it("implements Luhn", () => {
    expect(luhnValid("79927398713")).toBe(true);
    expect(luhnValid("79927398710")).toBe(false);
  });
});
