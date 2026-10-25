// Generates src/workflow.ts from workflow.schema.json. Run: pnpm spec:gen
import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const root = new URL("..", import.meta.url);
const schema = JSON.parse(await readFile(new URL("workflow.schema.json", root), "utf8"));

const ts = await compile(schema, "WorkflowSpec", {
  bannerComment:
    "/* eslint-disable */\n// GENERATED from packages/spec/workflow.schema.json by scripts/gen-types.mjs. Do not edit.",
  additionalProperties: false,
  style: { singleQuote: false },
});

const out = fileURLToPath(new URL("src/workflow.ts", root));
await writeFile(out, ts);
console.log(`wrote ${out}`);
