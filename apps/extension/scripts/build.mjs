// Builds the extension into dist/ (load it in Chrome via chrome://extensions → Load unpacked).
//   node scripts/build.mjs           production build
//   node scripts/build.mjs --watch   rebuild on change
//   node scripts/build.mjs --e2e     test build: grants <all_urls> up front so automated tests
//                                    can record without the permission prompt. Never ship it.
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { build } from "vite";

const root = fileURLToPath(new URL("..", import.meta.url));
const dist = `${root}dist`;
const watch = process.argv.includes("--watch") ? {} : null;
const e2e = process.argv.includes("--e2e");
const pkg = JSON.parse(await readFile(`${root}package.json`, "utf8"));

const manifest = {
  manifest_version: 3,
  name: e2e ? "WatchOnce Recorder (E2E build)" : "WatchOnce Recorder",
  version: pkg.version,
  description: "Record a browser task once; WatchOnce turns it into a documented, self-healing automation.",
  minimum_chrome_version: "120",
  icons: { 16: "icons/icon-16.png", 32: "icons/icon-32.png", 48: "icons/icon-48.png", 128: "icons/icon-128.png" },
  action: { default_popup: "popup/popup.html", default_icon: { 16: "icons/icon-16.png", 32: "icons/icon-32.png" } },
  background: { service_worker: "background.js", type: "module" },
  // Least privilege (docs/07): no static host access. Sites are requested one at a time
  // when recording starts; activeTab covers screenshots of the tab the user is on.
  permissions: ["activeTab", "scripting", "storage", "tabs"],
  optional_host_permissions: ["http://*/*", "https://*/*"],
  ...(e2e ? { host_permissions: ["<all_urls>"] } : {}),
  commands: {
    "toggle-recording": { suggested_key: { default: "Alt+Shift+R" }, description: "Start or stop recording" },
  },
};

const shared = { configFile: false, logLevel: "warn", publicDir: `${root}public` };

// 1. Service worker + popup (ES modules; shared chunks are fine here).
await build({
  ...shared,
  root: `${root}src`,
  build: {
    outDir: dist,
    emptyOutDir: true,
    target: "chrome120",
    watch,
    rollupOptions: {
      input: { background: `${root}src/background/index.ts`, popup: `${root}src/popup/popup.html` },
      output: { entryFileNames: (chunk) => (chunk.name === "background" ? "background.js" : "[name]-[hash].js") },
    },
  },
});

// 2. Content script: one self-contained classic script (content scripts can't be modules).
await build({
  ...shared,
  publicDir: false,
  build: {
    outDir: dist,
    emptyOutDir: false,
    target: "chrome120",
    watch,
    lib: { entry: `${root}src/content/index.ts`, formats: ["iife"], name: "WatchOnceRecorder", fileName: () => "content.js" },
  },
});

await writeFile(`${dist}/manifest.json`, `${JSON.stringify(manifest, null, 2)}\n`);
console.log(`built ${e2e ? "E2E " : ""}extension → ${dist}`);
