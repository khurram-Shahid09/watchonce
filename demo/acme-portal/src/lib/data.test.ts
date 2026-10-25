import { describe, expect, it } from "vitest";

import { formatUsDate, parseAmount, parseUsDate, SEED_INVOICES, SEED_VENDORS } from "./data";

describe("parseAmount", () => {
  it.each([
    ["1250.5", 125050],
    ["1,250.50", 125050],
    ["$99", 9900],
  ])("%s → %d cents", (raw, cents) => expect(parseAmount(raw)).toBe(cents));

  it.each(["", "0", "-5", "12.345", "abc", "1e3"])("rejects %j", (raw) => expect(parseAmount(raw)).toBeNull());
});

describe("dates", () => {
  it("parses MM/DD/YYYY and rejects impossible dates", () => {
    expect(parseUsDate("11/15/2026")).toBe("2026-11-15");
    expect(parseUsDate("02/30/2026")).toBeNull();
    expect(parseUsDate("2026-11-15")).toBeNull();
    expect(formatUsDate("2026-11-15")).toBe("11/15/2026");
  });
});

describe("seed data", () => {
  it("is deterministic and well-formed", () => {
    expect(SEED_VENDORS).toHaveLength(24);
    expect(SEED_VENDORS[0].name).toBe("Northwind Ltd");
    expect(new Set(SEED_INVOICES.map((i) => i.number)).size).toBe(SEED_INVOICES.length);
    for (const inv of SEED_INVOICES) {
      expect(inv.number).toMatch(/^INV-\d{6}$/);
      expect(parseUsDate(formatUsDate(inv.due))).toBe(inv.due);
    }
  });
});
