import { describe, expect, it } from "vitest";

import { churn, formatVariant, makeUi, MUTATIONS, parseVariant, PRESETS } from "./variant";

describe("parseVariant", () => {
  it("parses presets and lists in canonical order", () => {
    expect(parseVariant("original")).toEqual([]);
    expect(parseVariant("V2")).toEqual(["m1", "m2", "m3", "m6", "m7"]);
    expect(parseVariant(" m3 , m1 ")).toEqual(["m1", "m3"]);
  });

  it("rejects unknown values", () => {
    expect(parseVariant("m9")).toBeNull();
    expect(parseVariant("m1,evil")).toBeNull();
    expect(parseVariant("")).toBeNull();
    expect(parseVariant(undefined)).toBeNull();
  });

  it("round-trips through formatVariant", () => {
    for (const name of Object.keys(PRESETS)) expect(formatVariant(parseVariant(name)!)).toBe(name);
    expect(formatVariant(["m8", "m4"])).toBe("m4,m8");
  });
});

describe("makeUi", () => {
  const original = makeUi([]);

  it("changes nothing in the original variant", () => {
    expect(original.id("btn-new")).toBe("btn-new");
    expect(original.cls("btn btn-primary")).toBe("btn btn-primary");
    expect(original.t("new_invoice")).toBe("New invoice");
    expect(original.testid("new-invoice-btn")).toBe("new-invoice-btn");
  });

  it("M1 renames every id", () => {
    const ui = makeUi(["m1"]);
    expect(ui.id("btn-new")).toBe("create-btn");
    expect(ui.id("anything-else")).toBe("anything-else-2");
  });

  it("M2 churns class names deterministically", () => {
    const ui = makeUi(["m2"]);
    const churned = ui.cls("btn btn-primary");
    expect(churned).toMatch(/^css-[0-9a-f]{6} css-[0-9a-f]{6}$/);
    expect(churned).toBe(makeUi(["m2"]).cls("btn  btn-primary"));
    expect(churn("btn")).not.toBe(churn("btn-primary"));
  });

  it("M3 changes labels, M7 strips test ids", () => {
    expect(makeUi(["m3"]).t("new_invoice")).toBe("Create invoice");
    expect(makeUi(["m7"]).testid("new-invoice-btn")).toBeUndefined();
  });

  it("only the active mutations apply", () => {
    const ui = makeUi(["m3"]);
    for (const m of MUTATIONS) expect(ui.has(m)).toBe(m === "m3");
    expect(ui.id("btn-new")).toBe("btn-new");
  });
});
