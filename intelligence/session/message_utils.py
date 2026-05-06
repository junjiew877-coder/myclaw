"""
会话标题片段提取、以及将 messages 扁平化为摘要用纯文本。
供 SessionStore、ContextGuard 使用。

位于 intelligence/session/message_utils.py。
"""

from __future__ import annotations

import json
from typing import Any


def title_piece_from_text(text: str, max_len: int) -> str:
    """取首句或首段，便于与另几条拼成短标题。"""
    t = " ".join(text.split())
    if not t:
        return ""
    for sep in ("。", "！", "？", "……", "!", "?", "\n"):
        if sep in t and t.find(sep) <= 80:
            i = t.find(sep) + 1
            t = t[:i].strip()
            break
    t = t.replace("\n", " ")
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def serialize_messages_for_summary(messages: list[dict[str, Any]]) -> str:
    """将消息列表扁平化为纯文本, 用于 LLM 摘要。"""
    parts: list[str] = []
    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(f"[{role}]: {content}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    btype = block.get("type", "")
                    if btype == "text":
                        parts.append(f"[{role}]: {block['text']}")
                    elif btype == "tool_use":
                        parts.append(
                            f"[{role} called {block.get('name', '?')}]: "
                            f"{json.dumps(block.get('input', {}), ensure_ascii=False)}"
                        )
                    elif btype == "tool_result":
                        rc = block.get("content", "")
                        preview = rc[:500] if isinstance(rc, str) else str(rc)[:500]
                        parts.append(f"[tool_result]: {preview}")
                elif hasattr(block, "text"):
                    parts.append(f"[{role}]: {block.text}")
    return "\n".join(parts)
