import type { ReactNode } from "react";

import type { Ui } from "@/lib/variant";

/** M6: wraps content in extra elements so recorded CSS paths stop matching. */
export function Wrap({ ui, children }: { ui: Ui; children: ReactNode }) {
  if (!ui.has("m6")) return <>{children}</>;
  return (
    <div className={ui.cls("field-wrap")}>
      <div className={ui.cls("field-inner")}>{children}</div>
    </div>
  );
}

/** A label + control row in the form grid. */
export function Field({
  ui,
  id,
  label,
  help,
  children,
}: {
  ui: Ui;
  id: string;
  label: string;
  help?: string;
  children: ReactNode;
}) {
  return (
    <>
      <label id={`${id}-label`} htmlFor={id} className={ui.cls("form-label")}>
        {label}
      </label>
      <Wrap ui={ui}>{children}</Wrap>
      {help ? <div className={ui.cls("help")}>{help}</div> : null}
    </>
  );
}
