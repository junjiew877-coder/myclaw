/**
 * 前端与后端会话 / 聊天 UI 共用的 TypeScript 类型定义。
 * 将 API 返回的 JSON 归一化后，组件使用这些类型保证结构一致。
 */

export type ModelMode = "chat" | "reason";

export type AssistantBlock =
  | { kind: "reasoning"; text: string }
  | { kind: "tool"; toolName: string; preview: string }
  | { kind: "tool_result"; toolName: string; preview: string }
  | { kind: "text"; text: string };

export type ChatMessage =
  | { role: "user"; content: string }
  | { role: "assistant"; blocks: AssistantBlock[] };

export type SessionItem = {
  id: string;
  label: string;
  /** 由服务端从会话开头若干句生成的短标题 */
  title?: string;
  last_active: string;
  message_count: number;
};

export type ChatStreamPayload = {
  text: string;
  model: ModelMode;
  dialog_id: string;
};
