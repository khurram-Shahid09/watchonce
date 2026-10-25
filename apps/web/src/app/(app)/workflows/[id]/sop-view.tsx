import Markdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";

import { ActionButton } from "@/components/client-bits";
import { screenshotUrl } from "@/lib/steps";
import type { Version } from "@/lib/types";

import { regenerateSop } from "../../actions";

export function SopView({ workflowId, version }: { workflowId: string; version: Version }) {
  // SOPs reference recording frames as "screenshot:frames/0007.webp". The default
  // transform drops unknown schemes (and raw HTML is never rendered).
  const urlTransform = (url: string) =>
    url.startsWith("screenshot:") ? screenshotUrl(workflowId, url.slice("screenshot:".length)) : defaultUrlTransform(url);
  const by = version.compile_info.sop?.by;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          {by === "plain" || !by
            ? "Plain SOP generated from the steps."
            : `Written by AI (${by}) from the steps and screenshots.`}
        </p>
        <ActionButton
          action={regenerateSop.bind(null, workflowId, version.version)}
          label="Rewrite with AI"
          pendingLabel="Writing… (up to a minute)"
        />
      </div>
      <article className="sop rounded-lg border border-line bg-surface p-6">
        <Markdown remarkPlugins={[remarkGfm]} urlTransform={urlTransform}>
          {version.sop_markdown}
        </Markdown>
      </article>
    </div>
  );
}
