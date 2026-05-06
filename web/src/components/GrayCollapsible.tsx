/**
 * 灰色折叠面板：用于展示推理片段、工具调用与工具结果（与参考样式一致）。
 */

import { useState } from "react";

export function GrayCollapsible({
  summaryLabel,
  body,
  variant = "default",
}: {
  summaryLabel: string;
  body: string;
  variant?: "default" | "tool" | "result";
}) {
  const [open, setOpen] = useState(false);
  const text = body ?? "";
  const panelClass =
    variant === "tool"
      ? "aux-grey-panel aux-panel-tool"
      : variant === "result"
        ? "aux-grey-panel aux-panel-result"
        : "aux-grey-panel";

  return (
    <div className={panelClass}>
      <button
        type="button"
        className="aux-grey-panel-head"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="aux-grey-panel-title">{summaryLabel}</span>
        <span className="aux-grey-chev" aria-hidden>
          {open ? " ∨" : " >"}
        </span>
      </button>
      <div className={`aux-grey-panel-body ${open ? "is-open" : "is-collapsed"}`}>
        <pre className="aux-grey-pre">{text.length ? text : " "}</pre>
      </div>
    </div>
  );
}
