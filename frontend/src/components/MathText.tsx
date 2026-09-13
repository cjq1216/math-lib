"use client";

import * as React from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * 把文本中的 $...$ / $$...$$ 渲染成 KaTeX HTML。
 * 先抽公式 → 转义正文 → 回填，避免公式内容被 HTML 转义污染。
 */
export function renderMathToHtml(src: string | null | undefined): string {
  if (!src) return "";
  const tokens: string[] = [];
  let out = String(src).replace(
    /\$\$([\s\S]+?)\$\$|\$([^$\n]+?)\$/g,
    (_m, block: string | undefined, inline: string | undefined) => {
      const tex = (block ?? inline ?? "").trim();
      try {
        const html = katex.renderToString(tex, {
          displayMode: Boolean(block),
          throwOnError: false,
          errorColor: "#dc2626",
        });
        tokens.push(html);
        return `\u0000${tokens.length - 1}\u0000`;
      } catch {
        return escapeHtml(`$${tex}$`);
      }
    },
  );
  out = escapeHtml(out).replace(/\u0000(\d+)\u0000/g, (_m, i) => tokens[Number(i)]);
  return out.replace(/\n/g, "<br/>");
}

/** 渲染题干/答案/解析 */
export function MathText({
  children,
  className,
}: {
  children: string | null | undefined;
  className?: string;
}) {
  const html = React.useMemo(() => renderMathToHtml(children), [children]);
  return (
    <div
      className={className}
      // KaTeX 输出为受控 HTML，正文已转义
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
