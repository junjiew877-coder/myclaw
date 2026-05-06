"""
JSONL 会话持久化：索引、切换会话、从磁盘重建 Anthropic 风格 messages。

位于 intelligence/session/store_session.py。
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import WORKSPACE_DIR
from .message_utils import title_piece_from_text


class SessionStore:
    """管理 agent 会话的持久化存储。"""

    def __init__(self, agent_id: str = "default"):
        self.agent_id = agent_id
        self.base_dir = WORKSPACE_DIR / ".sessions" / "agents" / agent_id / "sessions"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.base_dir.parent / "sessions.json"
        self._index: dict[str, dict] = self._load_index()
        self.current_session_id: str | None = None

    def _load_index(self) -> dict[str, dict]:
        if self.index_path.exists():
            try:
                return json.loads(self.index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_index(self) -> None:
        self.index_path.write_text(
            json.dumps(self._index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _session_path(self, session_id: str) -> Path:
        return self.base_dir / f"{session_id}.jsonl"

    def create_session(self, label: str = "") -> str:
        session_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        self._index[session_id] = {
            "label": label,
            "created_at": now,
            "last_active": now,
            "message_count": 0,
        }
        self._save_index()
        self._session_path(session_id).touch()
        self.current_session_id = session_id
        return session_id

    def load_session(self, session_id: str) -> list[dict]:
        """从 JSONL 重建 API 格式的 messages[]。"""
        path = self._session_path(session_id)
        if not path.exists():
            return []
        self.current_session_id = session_id
        return self._rebuild_history(path)

    def save_turn(self, role: str, content: Any) -> None:
        if not self.current_session_id:
            return
        self.append_transcript(self.current_session_id, {
            "type": role,
            "content": content,
            "ts": time.time(),
        })

    def save_tool_result(
        self, tool_use_id: str, name: str, tool_input: dict, result: str
    ) -> None:
        """只追加 tool_result 行; tool_use 已在 save_turn(assistant) 的 content 里, 避免重放时重复。"""
        if not self.current_session_id:
            return
        ts = time.time()
        self.append_transcript(self.current_session_id, {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": result,
            "ts": ts,
        })

    def append_transcript(self, session_id: str, record: dict) -> None:
        path = self._session_path(session_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        if session_id in self._index:
            self._index[session_id]["last_active"] = (
                datetime.now(timezone.utc).isoformat()
            )
            self._index[session_id]["message_count"] += 1
            self._save_index()

    def _rebuild_history(self, path: Path) -> list[dict]:
        messages: list[dict] = []
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return messages
        lines = raw.split("\n")

        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            rtype = record.get("type")

            if rtype == "user":
                messages.append({
                    "role": "user",
                    "content": record["content"],
                })

            elif rtype == "assistant":
                content = record["content"]
                if isinstance(content, str):
                    content = [{"type": "text", "text": content}]
                messages.append({
                    "role": "assistant",
                    "content": content,
                })

            elif rtype == "tool_use":
                tid = record.get("tool_use_id")
                block = {
                    "type": "tool_use",
                    "id": tid,
                    "name": record["name"],
                    "input": record["input"],
                }
                if messages and messages[-1]["role"] == "assistant":
                    content = messages[-1]["content"]
                    if isinstance(content, list):
                        existing_ids = {
                            b.get("id")
                            for b in content
                            if isinstance(b, dict) and b.get("type") == "tool_use"
                        }
                        if tid in existing_ids:
                            continue
                        content.append(block)
                    else:
                        messages[-1]["content"] = [
                            {"type": "text", "text": str(content)},
                            block,
                        ]
                else:
                    messages.append({
                        "role": "assistant",
                        "content": [block],
                    })

            elif rtype == "tool_result":
                result_block = {
                    "type": "tool_result",
                    "tool_use_id": record["tool_use_id"],
                    "content": record["content"],
                }
                if (messages and messages[-1]["role"] == "user"
                        and isinstance(messages[-1]["content"], list)
                        and messages[-1]["content"]
                        and isinstance(messages[-1]["content"][0], dict)
                        and messages[-1]["content"][0].get("type") == "tool_result"):
                    messages[-1]["content"].append(result_block)
                else:
                    messages.append({
                        "role": "user",
                        "content": [result_block],
                    })

        return messages

    def list_sessions(self) -> list[tuple[str, dict]]:
        items = list(self._index.items())
        items.sort(key=lambda x: x[1].get("last_active", ""), reverse=True)
        return items

    def session_exists(self, session_id: str) -> bool:
        return session_id in self._index

    def derive_display_title(
        self,
        session_id: str,
        *,
        max_total: int = 52,
        max_piece: int = 22,
        max_utterances: int = 3,
    ) -> str:
        """
        从会话 JSONL 开头按时间顺序取最多三条「可读发言」（用户句 + 助手首段正文），
        各截成短片段后用「 · 」拼成侧边栏标题；无内容时返回固定占位文案。
        """
        path = self._session_path(session_id)
        if not path.exists():
            return "空会话"
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return "新对话"

        pieces: list[str] = []
        for line in raw.split("\n"):
            if len(pieces) >= max_utterances:
                break
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            rtype = record.get("type")
            if rtype == "user":
                c = record.get("content")
                if isinstance(c, str) and c.strip():
                    p = title_piece_from_text(c.strip(), max_piece)
                    if p:
                        pieces.append(p)
            elif rtype == "assistant":
                c = record.get("content")
                if isinstance(c, list):
                    for block in c:
                        if len(pieces) >= max_utterances:
                            break
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "text":
                            tx = (block.get("text") or "").strip()
                            if tx:
                                p = title_piece_from_text(tx, max_piece)
                                if p:
                                    pieces.append(p)
                                    break
                elif isinstance(c, str) and c.strip():
                    p = title_piece_from_text(c.strip(), max_piece)
                    if p:
                        pieces.append(p)

        if not pieces:
            return "新对话"
        title = " · ".join(pieces)
        if len(title) > max_total:
            return title[: max_total - 1] + "…"
        return title
