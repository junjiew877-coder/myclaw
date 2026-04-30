import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./App.css";

/** 与参考 web 样式一致：灰色折叠面板 */
function GrayCollapsible({
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

function AssistantMarkdown({ text }: { text: string }) {
  return (
    <div className="assistant-md">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}

type AssistantBlock =
  | { kind: "reasoning"; text: string }
  | { kind: "tool"; toolName: string; preview: string }
  | { kind: "tool_result"; toolName: string; preview: string }
  | { kind: "text"; text: string };

type ChatMessage =
  | { role: "user"; content: string }
  | { role: "assistant"; blocks: AssistantBlock[] };

type SessionItem = {
  id: string;
  label: string;
  /** 由服务端从会话开头若干句生成的短标题 */
  title?: string;
  last_active: string;
  message_count: number;
};

const DIALOG_KEY = "claw0_s06_dialog_id";
const SIDEBAR_OPEN_KEY = "claw0_sidebar_open";

function loadDialogId(): string {
  try {
    let id = sessionStorage.getItem(DIALOG_KEY);
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem(DIALOG_KEY, id);
    }
    return id;
  } catch {
    return "web_session";
  }
}

function loadSidebarOpen(): boolean {
  try {
    return sessionStorage.getItem(SIDEBAR_OPEN_KEY) !== "0";
  } catch {
    return true;
  }
}

/** 侧栏开关：左侧分栏示意（与常见产品一致） */
function IconSidebarLayout() {
  return (
    <svg
      className="sidebar-toggle-icon"
      viewBox="0 0 24 24"
      width="20"
      height="20"
      aria-hidden
    >
      <rect x="3" y="4" width="18" height="16" rx="2" fill="none" stroke="currentColor" strokeWidth="2" />
      <line x1="9" y1="4" x2="9" y2="20" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

async function streamChat(
  payload: {
    text: string;
    model: "chat" | "reason";
    dialog_id: string;
  },
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

function parseAssistantBlocks(raw: unknown): AssistantBlock[] {
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

function normalizeHydratedMessages(raw: unknown): ChatMessage[] {
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

export function App() {
  const [input, setInput] = useState("");
  const [modelMode, setModelMode] = useState<"chat" | "reason">("chat");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [phase, setPhase] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [sessionReady, setSessionReady] = useState(false);
  const [sessionBusy, setSessionBusy] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(loadSidebarOpen);
  const bottomRef = useRef<HTMLDivElement>(null);
  const dialogId = useMemo(() => loadDialogId(), []);

  useEffect(() => {
    try {
      sessionStorage.setItem(SIDEBAR_OPEN_KEY, sidebarOpen ? "1" : "0");
    } catch {
      /* */
    }
  }, [sidebarOpen]);

  const headerSessionTitle = useMemo(() => {
    const s = sessions.find((x) => x.id === currentSessionId);
    return (s?.title?.trim() || s?.label || "").trim() || "myclaw";
  }, [sessions, currentSessionId]);

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }));
  }, []);

  const refreshSessions = useCallback(async () => {
    const r = await fetch(`/api/sessions?dialog_id=${encodeURIComponent(dialogId)}`);
    if (!r.ok) throw new Error(`sessions HTTP ${r.status}`);
    const data = (await r.json()) as {
      sessions?: SessionItem[];
      current_session_id?: string | null;
    };
    setSessions(data.sessions ?? []);
    if (data.current_session_id) {
      setCurrentSessionId(data.current_session_id);
    }
  }, [dialogId]);

  useEffect(() => {
    let cancelled = false;

    async function init() {
      setErr(null);
      try {
        const r = await fetch(`/api/sessions?dialog_id=${encodeURIComponent(dialogId)}`);
        if (!r.ok) throw new Error(`会话列表 HTTP ${r.status}`);
        const data = (await r.json()) as {
          sessions?: SessionItem[];
          current_session_id?: string | null;
        };
        if (cancelled) return;
        setSessions(data.sessions ?? []);

        let sid = data.current_session_id ?? null;
        if (!sid) {
          const cr = await fetch("/api/sessions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ dialog_id: dialogId, label: "web-ui" }),
          });
          if (!cr.ok) throw new Error(`创建会话失败 HTTP ${cr.status}`);
          const cj = (await cr.json()) as { session_id?: string };
          sid = cj.session_id ?? null;
          if (sid) setCurrentSessionId(sid);
          const r2 = await fetch(`/api/sessions?dialog_id=${encodeURIComponent(dialogId)}`);
          if (r2.ok && !cancelled) {
            const d2 = (await r2.json()) as { sessions?: SessionItem[] };
            setSessions(d2.sessions ?? []);
          }
        } else {
          setCurrentSessionId(sid);
          const h = await fetch(`/api/sessions/${encodeURIComponent(sid)}/messages`);
          if (h.ok && !cancelled) {
            const hm = (await h.json()) as { messages?: unknown };
            const normalized = normalizeHydratedMessages(hm.messages);
            if (normalized.length) setMessages(normalized);
          }
        }
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (!cancelled) setSessionReady(true);
      }
    }

    void init();
    return () => {
      cancelled = true;
    };
  }, [dialogId]);

  const startNewSession = useCallback(async () => {
    if (sessionBusy || loading) return;
    setSessionBusy(true);
    setErr(null);
    try {
      const cr = await fetch("/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dialog_id: dialogId, label: "web-ui" }),
      });
      if (!cr.ok) throw new Error(`创建会话失败 HTTP ${cr.status}`);
      const cj = (await cr.json()) as { session_id?: string };
      if (cj.session_id) setCurrentSessionId(cj.session_id);
      setMessages([]);
      await refreshSessions();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSessionBusy(false);
    }
  }, [dialogId, loading, refreshSessions, sessionBusy]);

  const switchSession = useCallback(
    async (sessionId: string) => {
      if (sessionBusy || loading || sessionId === currentSessionId) return;
      setSessionBusy(true);
      setErr(null);
      try {
        const sr = await fetch("/api/sessions/select", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ dialog_id: dialogId, session_id: sessionId }),
        });
        if (!sr.ok) throw new Error(`切换会话失败 HTTP ${sr.status}`);
        setCurrentSessionId(sessionId);
        const h = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/messages`);
        if (!h.ok) throw new Error(`加载历史失败 HTTP ${h.status}`);
        const hm = (await h.json()) as { messages?: unknown };
        setMessages(normalizeHydratedMessages(hm.messages));
        await refreshSessions();
        scrollToBottom();
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      } finally {
        setSessionBusy(false);
      }
    },
    [currentSessionId, dialogId, loading, refreshSessions, scrollToBottom, sessionBusy],
  );

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || loading || !sessionReady) return;
    setErr(null);
    setInput("");
    setPhase(null);

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);

    const blocks: AssistantBlock[] = [];
    setMessages((prev) => [...prev, { role: "assistant", blocks: [] }]);

    const pushBlock = (b: AssistantBlock) => {
      blocks.push(b);
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last && last.role === "assistant") {
          next[next.length - 1] = { role: "assistant", blocks: [...blocks] };
        }
        return next;
      });
      scrollToBottom();
    };

    const appendDelta = (t: string) => {
      if (blocks.length && blocks[blocks.length - 1].kind === "text") {
        (blocks[blocks.length - 1] as { kind: "text"; text: string }).text += t;
      } else {
        blocks.push({ kind: "text", text: t });
      }
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last && last.role === "assistant") {
          next[next.length - 1] = {
            role: "assistant",
            blocks: blocks.map((x) => ({ ...x })),
          };
        }
        return next;
      });
      scrollToBottom();
    };

    try {
      await streamChat(
        {
          text,
          model: modelMode,
          dialog_id: dialogId,
        },
        (ev) => {
          const type = ev.type as string;
          if (type === "phase" && typeof ev.phase === "string") {
            const p = ev.phase as string;
            const labels: Record<string, string> = {
              recall_start: "检索记忆中…",
              recall_done: ev.has_memory ? "已注入相关记忆" : "无自动召回记忆",
              prompt_ready: "系统提示已组装",
              llm_call: "调用模型…",
              tool_round_done: "工具回合完成，继续推理",
            };
            setPhase(labels[p] ?? p);
            return;
          }
          if (type === "reasoning" && typeof ev.text === "string") {
            pushBlock({ kind: "reasoning", text: ev.text });
            return;
          }
          if (type === "tool" && typeof ev.tool_name === "string") {
            pushBlock({
              kind: "tool",
              toolName: ev.tool_name,
              preview: typeof ev.preview === "string" ? ev.preview : "",
            });
            return;
          }
          if (type === "tool_result" && typeof ev.tool_name === "string") {
            pushBlock({
              kind: "tool_result",
              toolName: ev.tool_name,
              preview: typeof ev.preview === "string" ? ev.preview : "",
            });
            return;
          }
          if (type === "delta" && typeof ev.text === "string") {
            appendDelta(ev.text);
            return;
          }
          if (type === "error" && typeof ev.message === "string") {
            setErr(ev.message);
            return;
          }
          if (type === "turn_done") {
            setPhase(null);
            void refreshSessions();
          }
        },
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setMessages((prev) => prev.slice(0, -2));
    } finally {
      setLoading(false);
      setPhase(null);
      scrollToBottom();
    }
  }, [dialogId, input, loading, modelMode, refreshSessions, scrollToBottom, sessionReady]);

  return (
    <div className={`app-shell ${sidebarOpen ? "" : "is-sidebar-collapsed"}`}>
      <div className="session-sidebar-wrap">
        <aside className="session-sidebar" aria-label="会话列表">
          <div className="session-sidebar-brand">
            <span className="session-brand-name">myclaw</span>
            <button
              type="button"
              className="sidebar-toggle-btn"
              onClick={() => setSidebarOpen(false)}
              title="收起侧边栏"
              aria-label="收起侧边栏"
            >
              <IconSidebarLayout />
            </button>
          </div>
          <div className="session-sidebar-head">
            <h2 className="session-sidebar-title">会话</h2>
            <button
              type="button"
              className="session-new-btn"
              disabled={!sessionReady || sessionBusy || loading}
              onClick={() => void startNewSession()}
              title="创建新会话并切换到该会话"
            >
              ＋ 新建会话
            </button>
          </div>
          <div className="session-list">
          {!sessionReady && <p className="session-sidebar-hint">加载中…</p>}
          {sessionReady &&
            sessions.map((s) => (
              <button
                key={s.id}
                type="button"
                className={`session-item ${s.id === currentSessionId ? "is-active" : ""}`}
                disabled={sessionBusy || loading}
                onClick={() => void switchSession(s.id)}
              >
                <span
                  className="session-item-label"
                  title={
                    s.last_active
                      ? `最近活动 ${new Date(s.last_active).toLocaleString()}`
                      : undefined
                  }
                >
                  {s.title?.trim() || s.label || "对话"}
                </span>
                <span className="session-item-meta">
                  {s.message_count > 0 ? `${s.message_count} 条消息` : "尚无消息"}
                </span>
              </button>
            ))}
          </div>
        </aside>
      </div>

      <div className="main-column">
        <header className="header">
          <div className="header-left">
            <button
              type="button"
              className="sidebar-toggle-btn header-sidebar-toggle"
              onClick={() => setSidebarOpen((v) => !v)}
              title={sidebarOpen ? "收起侧边栏" : "展开侧边栏"}
              aria-label={sidebarOpen ? "收起侧边栏" : "展开侧边栏"}
              aria-expanded={sidebarOpen}
            >
              <IconSidebarLayout />
            </button>
            <h1 className="title header-chat-title" title={headerSessionTitle}>
              {headerSessionTitle}
            </h1>
          </div>
          <div className="header-controls">
            <div className="model-toggle" role="group" aria-label="模型档位">
              <button
                type="button"
                className={`mode-btn ${modelMode === "chat" ? "active" : ""}`}
                disabled={loading}
                onClick={() => setModelMode("chat")}
              >
                Chat
              </button>
              <button
                type="button"
                className={`mode-btn ${modelMode === "reason" ? "active" : ""}`}
                disabled={loading}
                onClick={() => setModelMode("reason")}
              >
                Reason
              </button>
            </div>
          </div>
        </header>

        {(phase || loading) && (
          <div className="phase-strip" aria-live="polite">
            {loading && <span className="phase-dot" />}
            {phase || (loading ? "处理中…" : "")}
          </div>
        )}

        <main className="chat">
          {messages.length === 0 && (
            <p className="hint">
              左侧可切换或新建会话；助手正文支持 <strong>Markdown</strong> 渲染。环境变量{" "}
              <code>MODEL_ID_CHAT</code> / <code>MODEL_ID_REASON</code> 可分别指定两档模型。
            </p>
          )}
          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="row user-row">
                <div className="bubble user-bubble">{m.content}</div>
              </div>
            ) : (
              <div key={i} className="row assistant-row">
                <div className="assistant-body">
                  {m.blocks.map((b, j) =>
                    b.kind === "reasoning" ? (
                      <GrayCollapsible key={j} summaryLabel="推理 / 说明（Reason）" body={b.text} />
                    ) : b.kind === "tool" ? (
                      <GrayCollapsible
                        key={j}
                        variant="tool"
                        summaryLabel={`调用工具 · ${b.toolName}`}
                        body={b.preview}
                      />
                    ) : b.kind === "tool_result" ? (
                      <GrayCollapsible
                        key={j}
                        variant="result"
                        summaryLabel={`工具结果 · ${b.toolName}`}
                        body={b.preview}
                      />
                    ) : (
                      <AssistantMarkdown key={j} text={b.text} />
                    ),
                  )}
                </div>
              </div>
            ),
          )}
          <div ref={bottomRef} />
        </main>

        {err && <div className="error-banner">{err}</div>}

        <footer className="composer">
          <textarea
            className="field"
            rows={2}
            placeholder={
              sessionReady ? "输入消息…（Enter 发送，Shift+Enter 换行）" : "正在初始化会话…"
            }
            value={input}
            disabled={loading || !sessionReady}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
          />
          <button
            type="button"
            className="send"
            disabled={loading || !sessionReady || !input.trim()}
            onClick={() => void send()}
          >
            {loading ? "…" : "发送"}
          </button>
        </footer>
      </div>
    </div>
  );
}
