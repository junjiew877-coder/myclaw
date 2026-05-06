/**
 * 调用后端 POST /api/chat，按 SSE（data: JSON）解析流式事件并回调。
 * 助手正文片段来自 Anthropic Messages streaming（后端映射为 type: delta）。
 * 开发环境下由 Vite 将 /api 代理到 FastAPI。
 */

import type { ChatStreamPayload } from "../types";

export async function streamChat(
  payload: ChatStreamPayload,
  onEvent: (ev: Record<string, unknown>) => void,
): Promise<void> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok || !res.body) {
    throw new Error(`HTTP ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const raw = line.slice(6).trim();
      if (!raw) continue;
      try {
        const ev = JSON.parse(raw) as Record<string, unknown>;
        onEvent(ev);
      } catch {
        /* partial chunk */
      }
    }
  }
  if (buf.startsWith("data: ")) {
    const raw = buf.slice(6).trim();
    if (raw) {
      try {
        onEvent(JSON.parse(raw) as Record<string, unknown>);
      } catch {
        /* */
      }
    }
  }
}
