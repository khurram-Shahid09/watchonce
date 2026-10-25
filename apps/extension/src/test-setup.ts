// jsdom has no CSS.escape. Minimal spec-compatible version for selectors built in tests.
if (typeof globalThis.CSS === "undefined" || typeof globalThis.CSS.escape !== "function") {
  const escape = (value: string): string =>
    String(value).replace(/([\0-\x1f\x7f]|^-?\d)|^-$|[^\0-\x1f\x7f-￿\w-]/g, (ch, ctrl) => {
      if (ch === "\0") return "�";
      if (ctrl) return `\\${ch.charCodeAt(ch.length - 1).toString(16)} `.replace(/^\\(\d)/, "\\3$1 ").trim() + " ";
      return `\\${ch}`;
    });
  (globalThis as unknown as { CSS: { escape: (v: string) => string } }).CSS = { escape };
}
