import { beforeEach, describe as group, expect, it } from "vitest";

import { accessibleName, actionTarget, cssPath, describe, isGeneratedClass, isGeneratedId, roleOf, xPath } from "./descriptor";

const $ = (selector: string) => document.querySelector(selector)!;

beforeEach(() => {
  document.body.innerHTML = `
    <div id="toolbar" class="toolbar">
      <button class="btn css-8f2a1c" data-testid="export-btn">Export CSV</button>
      <button id="btn-new" class="btn btn-primary" type="button"><span class="icon">+</span> New invoice</button>
    </div>
    <form id="invoice-form">
      <label for="amount">Amount</label>
      <input id="amount" name="amount" class="form-control">
      <label>Due date <input name="due" placeholder="MM/DD/YYYY"></label>
      <span id="vendor-label">Vendor</span>
      <button type="button" role="combobox" aria-labelledby="vendor-label" id=":r3:">— Select —</button>
      <input type="submit" value="Save">
      <input type="checkbox" id="urgent"><label for="urgent">Urgent</label>
      <a href="/invoices?page=2#top">Next</a>
    </form>
    <ul><li><button>Delete</button></li><li><button>Delete</button></li></ul>`;
});

group("roles and accessible names", () => {
  it.each([
    ["#btn-new", "button", "+ New invoice"],
    ["#amount", "textbox", "Amount"],
    ["input[name=due]", "textbox", "Due date"],
    ["[role=combobox]", "combobox", "Vendor"],
    ["input[type=submit]", "button", "Save"],
    ["#urgent", "checkbox", "Urgent"],
    ["a", "link", "Next"],
  ])("%s → role %s, name %j", (selector, role, name) => {
    expect(roleOf($(selector))).toBe(role);
    expect(accessibleName($(selector))).toBe(name);
  });
});

group("generated identifiers are ignored", () => {
  it.each([":r3:", "ember1234", "a1b2c3d4e5f6", "radix-12", "x9f8e7d6c5b4a3"])("id %s is generated", (id) =>
    expect(isGeneratedId(id)).toBe(true),
  );
  it.each(["btn-new", "username", "submit-invoice", "submitinvoice", "due-date"])("id %s is stable", (id) =>
    expect(isGeneratedId(id)).toBe(false),
  );
  it.each(["css-8f2a1c", "sc-bdVaJa", "jsx-123", "Button_root__3xk9z", "button-1x2y3z"])("class %s is generated", (c) =>
    expect(isGeneratedClass(c)).toBe(true),
  );
  it.each(["btn", "btn-primary", "form-control", "card__title", "toolbar"])("class %s is stable", (c) =>
    expect(isGeneratedClass(c)).toBe(false),
  );
});

group("paths", () => {
  it("prefers a stable id, then test id, then name", () => {
    expect(cssPath($("#btn-new"))).toBe("#btn-new");
    expect(cssPath($("[data-testid=export-btn]"))).toBe('[data-testid="export-btn"]');
    expect(cssPath($("input[name=due]"))).toBe('input[name="due"]');
  });

  it("never uses a generated id and stays unique", () => {
    const combo = $("[role=combobox]");
    const path = cssPath(combo);
    expect(path).not.toContain(":r3:");
    expect(document.querySelectorAll(path)).toHaveLength(1);
    expect(document.querySelector(path)).toBe(combo);
  });

  it("disambiguates identical siblings with nth-of-type", () => {
    const second = document.querySelectorAll("li button")[1]!;
    const path = cssPath(second);
    expect(document.querySelector(path)).toBe(second);
  });

  it("builds a positional xpath", () => {
    expect(xPath($("#amount"))).toBe("/html/body/form/input[1]");
  });
});

group("describe()", () => {
  it("captures what healing needs", () => {
    const d = describe($("#btn-new"));
    expect(d).toMatchObject({
      tag: "button",
      role: "button",
      accessible_name: "+ New invoice",
      id: "btn-new",
      classes: ["btn", "btn-primary"],
      css_path: "#btn-new",
    });
    expect(d.is_unique.role_name).toBe(true);
    expect(d.is_unique.css).toBe(true);
    expect(d.attrs.type).toBe("button");
  });

  it("flags ambiguity", () => {
    const d = describe(document.querySelectorAll("li button")[0]!);
    expect(d.is_unique.role_name).toBe(false);
    expect(d.is_unique.text).toBe(false);
  });

  it("drops generated ids/classes and URL fragments", () => {
    expect(describe($("[role=combobox]")).id).toBeNull();
    expect(describe($("[data-testid=export-btn]")).classes).toEqual(["btn"]);
    expect(describe($("a")).attrs.href).toBe("/invoices?page=2");
  });

  it("records the label for form fields and no text for inputs", () => {
    const d = describe($("#amount"));
    expect(d.label_text).toBe("Amount");
    expect(d.text).toBeNull();
    expect(d.is_unique.label).toBe(true);
  });

  it("supports open shadow roots", () => {
    const host = document.createElement("x-widget");
    host.id = "widget";
    document.body.append(host);
    const shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML = `<button id="inner">Go</button>`;
    const d = describe(shadow.querySelector("button")!);
    expect(d.shadow_hosts).toEqual(["#widget"]);
    expect(d.css_path).toBe("#inner");
  });
});

it("actionTarget walks up from inner icons to the control", () => {
  expect(actionTarget($("#btn-new .icon"))).toBe($("#btn-new"));
});
