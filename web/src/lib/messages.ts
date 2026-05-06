/**
 * 将后端返回的未知结构 JSON 安全转换为 ChatMessage / AssistantBlock。
 * 纯函数，无网络与 DOM，便于单测与复用。
 */

import type { AssistantBlock, ChatMessage } from "../types";

export function parseAssistantBlocks(raw: unknown): AssistantBlock[] {
  if (!Array.isArray(raw)) return [];
  const out: AssistantBlock[] = [];
  for (const b of raw) {
    if (!b || typeof b !== "object") continue;
    const o = b as Record<string, unknown>;
    const kind = o.kind;
    if (kind === "text" && typeof o.text === "string") {
      out.push({ kind: "text", text: o.text });
    } else if (kind === "reasoning" && typeof o.text === "string") {
      out.push({ kind: "reasoning", text: o.text });
    } else if (kind === "tool" && typeof o.toolName === "string") {
      out.push({
        kind: "tool",
        toolName: o.toolName,
        preview: typeof o.preview === "string" ? o.preview : "",
      });
    } else if (kind === "tool_result" && typeof o.toolName === "string") {
      out.push({
        kind: "tool_result",
        toolName: o.toolName,
        preview: typeof o.preview === "string" ? o.preview : "",
      });
    }
  }
  return out;
}

export function normalizeHydratedMessages(raw: unknown): ChatMessage[] {
  if (!Array.isArray(raw)) return [];
  const out: ChatMessage[] = [];
  for (const m of raw) {
    if (!m || typeof m !== "object") continue;
    const o = m as Record<string, unknown>;
    if (o.role === "user" && typeof o.content === "string") {
      out.push({ role: "user", content: o.content });
    } else if (o.role === "assistant" && o.blocks) {
      out.push({
        role: "assistant",
        blocks: parseAssistantBlocks(o.blocks),
      });
    }
  }
  return out;
}
