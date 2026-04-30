"""
FastAPI + SSE：为 s06_intelligence Web UI 提供 /api/chat。
启动（仓库根目录）:
  uvicorn web.server.app:app --host 127.0.0.1 --port 8765
前端（另一终端）:
  cd web && npm run dev
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import s06_intelligence as s06  # noqa: E402

_runtime: s06.S06Runtime | None = None
# dialog_id（浏览器 tab） -> SessionStore 里的 session_id
_DIALOG_TO_SESSION: dict[str, str] = {}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _runtime
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("缺少 ANTHROPIC_API_KEY，请在 claw0/.env 中配置")
    if not s06.WORKSPACE_DIR.is_dir():
        raise RuntimeError(f"未找到工作区: {s06.WORKSPACE_DIR}")
    _runtime = s06.S06Runtime(session_agent_id="claw0-web")
    yield
    _runtime = None


app = FastAPI(title="claw0 s06 Web", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _hydrate_ui_messages(api_messages: list[dict]) -> list[dict]:
    """
    将 SessionStore 重建的 Anthropic 风格 messages 转为前端 ChatMessage 列表。
    assistant 与紧随其后的 user(tool_result 列表) 合并为一条 assistant 消息块链。
    """
    out: list[dict] = []
    i = 0
    n = len(api_messages)
    while i < n:
        m = api_messages[i]
        role = m.get("role")
        if role == "user":
            c = m.get("content")
            if isinstance(c, str):
                out.append({"role": "user", "content": c})
                i += 1
            else:
                i += 1
        elif role == "assistant":
            c = m.get("content")
            next_msg = api_messages[i + 1] if i + 1 < n else None
            tool_results_msg = None
            if (
                next_msg
                and next_msg.get("role") == "user"
                and isinstance(next_msg.get("content"), list)
            ):
                tool_results_msg = next_msg
            blocks = _assistant_content_to_ui_blocks(c, tool_results_msg)
            out.append({"role": "assistant", "blocks": blocks})
            i += 1
            if tool_results_msg is not None:
                i += 1
        else:
            i += 1
    return out


def _assistant_content_to_ui_blocks(
    content: object,
    tool_results_msg: dict | None,
) -> list[dict]:
    tr_by_id: dict[str, str] = {}
    if tool_results_msg:
        for tb in tool_results_msg.get("content") or []:
            if isinstance(tb, dict) and tb.get("type") == "tool_result":
                tid = tb.get("tool_use_id")
                if tid:
                    tr_by_id[str(tid)] = tb.get("content", "")

    blocks: list[dict] = []
    if isinstance(content, str):
        return [{"kind": "text", "text": content}]
    if not isinstance(content, list):
        return [{"kind": "text", "text": str(content)}]

    for block in content:
        if not isinstance(block, dict):
            continue
        bt = block.get("type")
        if bt == "text":
            blocks.append({"kind": "text", "text": block.get("text", "")})
        elif bt == "tool_use":
            tid = block.get("id")
            name = block.get("name", "?")
            inp = block.get("input", {})
            preview = json.dumps(inp, ensure_ascii=False)
            if len(preview) > 1200:
                preview = preview[:1200] + "…"
            blocks.append(
                {"kind": "tool", "toolName": name, "preview": preview}
            )
            if tid is not None and str(tid) in tr_by_id:
                rc = tr_by_id[str(tid)]
                out_preview = (
                    rc if len(rc) <= 2000 else rc[:2000] + "\n…"
                )
                blocks.append(
                    {
                        "kind": "tool_result",
                        "toolName": name,
                        "preview": out_preview,
                    }
                )
    return blocks


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "model_chat": s06.MODEL_ID_CHAT, "model_reason": s06.MODEL_ID_REASON}


@app.get("/api/sessions")
def list_sessions_api(dialog_id: str = "default") -> dict:
    """列出 claw0-web 下的会话；dialog_id 用于返回当前 tab 绑定的 session。"""
    rt = _runtime
    if rt is None:
        raise HTTPException(503, "server not ready")
    did = (dialog_id or "default").strip() or "default"
    items = []
    for sid, meta in rt.store.list_sessions():
        items.append(
            {
                "id": sid,
                "label": meta.get("label", ""),
                "title": rt.store.derive_display_title(sid),
                "last_active": meta.get("last_active", ""),
                "message_count": meta.get("message_count", 0),
            }
        )
    current = _DIALOG_TO_SESSION.get(did)
    return {"sessions": items, "current_session_id": current}


@app.post("/api/sessions")
def create_session_api(body: dict) -> dict:
    """新建会话并可选绑定到 dialog_id。"""
    rt = _runtime
    if rt is None:
        raise HTTPException(503, "server not ready")
    label = (body.get("label") or "web-ui").strip() or "web-ui"
    did = (body.get("dialog_id") or "default").strip() or "default"
    sid = rt.store.create_session(label)
    _DIALOG_TO_SESSION[did] = sid
    return {"session_id": sid}


@app.post("/api/sessions/select")
def select_session_api(body: dict) -> dict:
    """将浏览器 dialog 切换到已有会话（不删除数据）。"""
    rt = _runtime
    if rt is None:
        raise HTTPException(503, "server not ready")
    did = (body.get("dialog_id") or "default").strip() or "default"
    sid = (body.get("session_id") or "").strip()
    if not sid:
        raise HTTPException(400, "session_id required")
    if not rt.store.session_exists(sid):
        raise HTTPException(404, "session not found")
    _DIALOG_TO_SESSION[did] = sid
    rt.store.load_session(sid)
    return {"ok": True, "session_id": sid}


@app.get("/api/sessions/{session_id}/messages")
def session_messages_api(session_id: str) -> dict:
    """返回用于渲染聊天区的消息列表（与前端 ChatMessage 形状一致）。"""
    rt = _runtime
    if rt is None:
        raise HTTPException(503, "server not ready")
    sid = session_id.strip()
    if not sid or not rt.store.session_exists(sid):
        raise HTTPException(404, "session not found")
    api_messages = rt.store.load_session(sid)
    ui_messages = _hydrate_ui_messages(api_messages)
    return {"messages": ui_messages}


@app.post("/api/chat")
def chat(body: dict) -> StreamingResponse:
    text = (body.get("text") or "").strip()
    dialog_id = (body.get("dialog_id") or "default").strip() or "default"
    # 与旧版 RayClaw 一致：body.model 为字符串；s06 使用 chat | reason
    model_mode = (body.get("model") or "chat").strip().lower()
    if model_mode not in ("chat", "reason"):
        model_mode = "chat"

    if not text:
        return StreamingResponse(
            iter([_sse({"type": "error", "message": "empty text"})]),
            media_type="text/event-stream",
        )

    rt = _runtime
    if rt is None:
        return StreamingResponse(
            iter([_sse({"type": "error", "message": "server not ready"})]),
            media_type="text/event-stream",
        )

    if dialog_id not in _DIALOG_TO_SESSION:
        sid = rt.store.create_session("web-ui")
        _DIALOG_TO_SESSION[dialog_id] = sid
    session_id = _DIALOG_TO_SESSION[dialog_id]

    model_id = s06.resolve_model_id(model_mode)

    def gen():
        for ev in s06.iter_s06_turn(
            user_input=text,
            session_id=session_id,
            model_id=model_id,
            runtime=rt,
            reason_mode=(model_mode == "reason"),
        ):
            yield _sse(ev)

    return StreamingResponse(gen(), media_type="text/event-stream")
