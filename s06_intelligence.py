r"""
Section 06: Intelligence (智能)
"赋予灵魂, 教会记忆"

每轮对话前, agent 的"大脑"是如何组装的?
本节是整个教学项目的核心集成点 -- 演示系统提示词的分层构建过程.

在 s01-s02 中, 系统提示词是硬编码的字符串.
在真实的 agent 框架中, 系统提示词由多个层级动态组装:
  Identity / 灵魂 / Tools / 技能 / Memory / Bootstrap / Runtime / Channel

架构:

    [SOUL.md]  [IDENTITY.md]  [TOOLS.md]  [MEMORY.md]  ...
         \          |            |           /
          v         v            v          v
        +-------------------------------+
        |     BootstrapLoader           |
        |  (load, truncate, cap)        |
        +-------------------------------+
                    |
                    v
        +-------------------------------+        +-------------------+
        |   build_system_prompt()       | <----> | SkillsManager     |
        |   (8 层组装)                  |        | (discover, parse) |
        +-------------------------------+        +-------------------+
                    |                                     ^
                    v                                     |
        +-------------------------------+        +-------------------+
        |   Agent Loop (每轮)           | <----> | MemoryStore       |
        |   search -> build -> call LLM |        | (write, search)   |
        +-------------------------------+        +-------------------+

用法:
    （在仓库根目录）python s06_intelligence.py

REPL 命令:
    会话与上下文: /new /list /switch /context /compact /help
    智能与记忆: /soul /skills /memory /search <q> /prompt /bootstrap
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 导入与配置
# ---------------------------------------------------------------------------
import json
import math
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

MODEL_ID = os.getenv("MODEL_ID", "claude-sonnet-4-20250514")
# Web UI：对话档 / 推理档（可选覆盖；默认回退到 MODEL_ID）
MODEL_ID_CHAT = os.getenv("MODEL_ID_CHAT", MODEL_ID)
MODEL_ID_REASON = os.getenv("MODEL_ID_REASON", MODEL_ID)

client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    base_url=os.getenv("ANTHROPIC_BASE_URL") or None,
)

WORKSPACE_DIR = Path(__file__).resolve().parent / "workspace"

# Bootstrap 文件名 -- 每个 agent 启动时加载这 8 个文件
BOOTSTRAP_FILES = [
    "SOUL.md", "IDENTITY.md", "TOOLS.md", "USER.md",
    "HEARTBEAT.md", "BOOTSTRAP.md", "AGENTS.md", "MEMORY.md",
]

MAX_FILE_CHARS = 20000
MAX_TOTAL_CHARS = 150000
MAX_SKILLS = 150
MAX_SKILLS_PROMPT = 30000

# 会话与上下文保护 (与 s03 对齐)
CONTEXT_SAFE_LIMIT = 180000

# 工具输出最大字符数 (与 s02/s03 对齐)
MAX_TOOL_OUTPUT = 50000

# ---------------------------------------------------------------------------
# ANSI 颜色
# ---------------------------------------------------------------------------
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"
MAGENTA = "\033[35m"
RED = "\033[31m"
BLUE = "\033[34m"


def colored_prompt() -> str:
    return f"{CYAN}{BOLD}You > {RESET}"


def print_assistant(text: str) -> None:
    print(f"\n{GREEN}{BOLD}Assistant:{RESET} {text}\n")


def print_tool(name: str, detail: str) -> None:
    print(f"  {DIM}[tool: {name}] {detail}{RESET}")


def print_info(text: str) -> None:
    print(f"{DIM}{text}{RESET}")


def print_warn(text: str) -> None:
    print(f"{YELLOW}{text}{RESET}")


def print_session(text: str) -> None:
    print(f"{MAGENTA}{text}{RESET}")


def print_section(title: str) -> None:
    print(f"\n{MAGENTA}{BOLD}--- {title} ---{RESET}")


# ---------------------------------------------------------------------------
# SessionStore -- JSONL 会话持久化 (与 s03 一致)
# ---------------------------------------------------------------------------


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
                    p = _title_piece_from_text(c.strip(), max_piece)
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
                                p = _title_piece_from_text(tx, max_piece)
                                if p:
                                    pieces.append(p)
                                    break
                elif isinstance(c, str) and c.strip():
                    p = _title_piece_from_text(c.strip(), max_piece)
                    if p:
                        pieces.append(p)

        if not pieces:
            return "新对话"
        title = " · ".join(pieces)
        if len(title) > max_total:
            return title[: max_total - 1] + "…"
        return title


def _title_piece_from_text(text: str, max_len: int) -> str:
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


def _serialize_messages_for_summary(messages: list[dict]) -> str:
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


# ---------------------------------------------------------------------------
# ContextGuard -- 上下文溢出保护 (与 s03 一致)
# ---------------------------------------------------------------------------


class ContextGuard:
    """保护 agent 免受上下文窗口溢出。"""

    def __init__(self, max_tokens: int = CONTEXT_SAFE_LIMIT):
        self.max_tokens = max_tokens

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return len(text) // 4

    def estimate_messages_tokens(self, messages: list[dict]) -> int:
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate_tokens(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if "text" in block:
                            total += self.estimate_tokens(block["text"])
                        elif block.get("type") == "tool_result":
                            rc = block.get("content", "")
                            if isinstance(rc, str):
                                total += self.estimate_tokens(rc)
                        elif block.get("type") == "tool_use":
                            total += self.estimate_tokens(
                                json.dumps(block.get("input", {}))
                            )
                    else:
                        if hasattr(block, "text"):
                            total += self.estimate_tokens(block.text)
                        elif hasattr(block, "input"):
                            total += self.estimate_tokens(
                                json.dumps(block.input)
                            )
        return total

    def truncate_tool_result(self, result: str, max_fraction: float = 0.3) -> str:
        """在换行边界处只保留头部进行截断。"""
        max_chars = int(self.max_tokens * 4 * max_fraction)
        if len(result) <= max_chars:
            return result
        cut = result.rfind("\n", 0, max_chars)
        if cut <= 0:
            cut = max_chars
        head = result[:cut]
        return head + f"\n\n[... truncated ({len(result)} chars total, showing first {len(head)}) ...]"

    def compact_history(
        self, messages: list[dict], api_client: Anthropic, model: str
    ) -> list[dict]:
        """将前 50% 的消息压缩为 LLM 生成的摘要。"""
        total = len(messages)
        if total <= 4:
            return messages

        keep_count = max(4, int(total * 0.2))
        compress_count = max(2, int(total * 0.5))
        compress_count = min(compress_count, total - keep_count)

        if compress_count < 2:
            return messages

        old_messages = messages[:compress_count]
        recent_messages = messages[compress_count:]

        old_text = _serialize_messages_for_summary(old_messages)

        summary_prompt = (
            "Summarize the following conversation concisely, "
            "preserving key facts and decisions. "
            "Output only the summary, no preamble.\n\n"
            f"{old_text}"
        )

        try:
            summary_resp = api_client.messages.create(
                model=model,
                max_tokens=2048,
                system="You are a conversation summarizer. Be concise and factual.",
                messages=[{"role": "user", "content": summary_prompt}],
            )
            summary_text = ""
            for block in summary_resp.content:
                if hasattr(block, "text"):
                    summary_text += block.text

            print_session(
                f"  [compact] {len(old_messages)} 条消息 -> 摘要 "
                f"({len(summary_text)} 字符)"
            )
        except Exception as exc:
            print_warn(f"  [compact] 摘要失败 ({exc}), 丢弃较早消息")
            return recent_messages

        compacted = [
            {
                "role": "user",
                "content": "[Previous conversation summary]\n" + summary_text,
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": (
                    "Understood, I have the context from our previous conversation."
                )}],
            },
        ]
        compacted.extend(recent_messages)
        return compacted

    def _truncate_large_tool_results(self, messages: list[dict]) -> list[dict]:
        """遍历消息列表, 截断过大的 tool_result 块。"""
        result = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                new_blocks = []
                for block in content:
                    if (isinstance(block, dict)
                            and block.get("type") == "tool_result"
                            and isinstance(block.get("content"), str)):
                        block = dict(block)
                        block["content"] = self.truncate_tool_result(
                            block["content"]
                        )
                    new_blocks.append(block)
                result.append({"role": msg["role"], "content": new_blocks})
            else:
                result.append(msg)
        return result

    def guard_api_call(
        self,
        api_client: Anthropic,
        model: str,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_retries: int = 2,
    ) -> Any:
        """三阶段重试: 正常 -> 截断工具结果 -> 压缩历史。"""
        current_messages = messages

        for attempt in range(max_retries + 1):
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "max_tokens": 8096,
                    "system": system,
                    "messages": current_messages,
                }
                if tools:
                    kwargs["tools"] = tools
                result = api_client.messages.create(**kwargs)
                if current_messages is not messages:
                    messages.clear()
                    messages.extend(current_messages)
                return result

            except Exception as exc:
                error_str = str(exc).lower()
                is_overflow = ("context" in error_str or "token" in error_str)

                if not is_overflow or attempt >= max_retries:
                    raise

                if attempt == 0:
                    print_warn(
                        "  [guard] 检测到上下文溢出, 正在截断过大的工具结果..."
                    )
                    current_messages = self._truncate_large_tool_results(
                        current_messages
                    )
                elif attempt == 1:
                    print_warn(
                        "  [guard] 仍然溢出, 正在压缩对话历史..."
                    )
                    current_messages = self.compact_history(
                        current_messages, api_client, model
                    )

        raise RuntimeError("guard_api_call: exhausted retries")


# ---------------------------------------------------------------------------
# 1. Bootstrap 文件加载器
# ---------------------------------------------------------------------------
# 在 agent 启动时加载工作区的 Bootstrap 文件.
# 不同加载模式 (full/minimal/none) 适用于不同场景:
#   full = 主 agent | minimal = 子 agent / cron | none = 最小化

class BootstrapLoader:

    def __init__(self, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir

    def load_file(self, name: str) -> str:
        path = self.workspace_dir / name
        if not path.is_file():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return ""

    def truncate_file(self, content: str, max_chars: int = MAX_FILE_CHARS) -> str:
        """截断超长文件内容. 仅保留头部, 在行边界处截断."""
        if len(content) <= max_chars:
            return content
        cut = content.rfind("\n", 0, max_chars)
        if cut <= 0:
            cut = max_chars
        return content[:cut] + f"\n\n[... truncated ({len(content)} chars total, showing first {cut}) ...]"

    def load_all(self, mode: str = "full") -> dict[str, str]:
        """可选none、minimal、full三种模式, 分别对应最小化、子agent、主agent."""
        if mode == "none":
            return {}
        names = ["AGENTS.md", "TOOLS.md"] if mode == "minimal" else list(BOOTSTRAP_FILES)
        result: dict[str, str] = {}
        total = 0
        for name in names:
            raw = self.load_file(name)
            if not raw:
                continue
            truncated = self.truncate_file(raw)
            if total + len(truncated) > MAX_TOTAL_CHARS:
                remaining = MAX_TOTAL_CHARS - total
                if remaining > 0:
                    truncated = self.truncate_file(raw, remaining)
                else:
                    break
            result[name] = truncated
            total += len(truncated)
        return result


# ---------------------------------------------------------------------------
# 2. 灵魂系统
# ---------------------------------------------------------------------------
# SOUL.md 定义 agent 的人格. 不同 agent 可以有不同的 SOUL.md 文件.
# 注入到系统提示词的靠前位置 -- 越靠前影响力越强.


def load_soul(workspace_dir: Path) -> str:
    path = workspace_dir / "SOUL.md"
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# 3. 技能发现与注入
# ---------------------------------------------------------------------------
# 一个技能 = 一个包含 SKILL.md (带 frontmatter) 的目录.
# 按优先级顺序扫描; 同名技能会被后发现的覆盖.


class SkillsManager:

    def __init__(self, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir
        self.skills: list[dict[str, str]] = []

    def _parse_frontmatter(self, text: str) -> dict[str, str]:
        """解析简单的 YAML frontmatter, 不依赖 pyyaml."""
        meta: dict[str, str] = {}
        if not text.startswith("---"):
            return meta
        parts = text.split("---", 2)
        if len(parts) < 3:
            return meta
        for line in parts[1].strip().splitlines():
            if ":" not in line:
                continue
            key, _, value = line.strip().partition(":")
            meta[key.strip()] = value.strip()
        return meta

    def _scan_dir(self, base: Path) -> list[dict[str, str]]:
        found: list[dict[str, str]] = []
        if not base.is_dir():
            return found
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            skill_md = child / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                content = skill_md.read_text(encoding="utf-8")
            except Exception:
                continue
            meta = self._parse_frontmatter(content)
            if not meta.get("name"):
                continue
            body = ""
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    body = parts[2].strip()
            found.append({
                "name": meta.get("name", ""),
                "description": meta.get("description", ""),
                "invocation": meta.get("invocation", ""),
                "body": body,
                "path": str(child),
            })
        return found

    def discover(self, extra_dirs: list[Path] | None = None) -> None:
        """按优先级扫描技能目录; 同名技能后者覆盖前者."""
        scan_order: list[Path] = []
        if extra_dirs:
            scan_order.extend(extra_dirs)
        scan_order.append(self.workspace_dir / "skills")           # 内置技能
        scan_order.append(self.workspace_dir / ".skills")          # 托管技能
        scan_order.append(self.workspace_dir / ".agents" / "skills")  # 个人 agent 技能
        scan_order.append(Path.cwd() / ".agents" / "skills")      # 项目 agent 技能
        scan_order.append(Path.cwd() / "skills")                  # 工作区技能

        seen: dict[str, dict[str, str]] = {}
        for d in scan_order:
            for skill in self._scan_dir(d):
                seen[skill["name"]] = skill
        self.skills = list(seen.values())[:MAX_SKILLS]

    def format_prompt_block(self) -> str:
        if not self.skills:
            return ""
        lines = ["## Available Skills", ""]
        total = 0
        for skill in self.skills:
            block = (
                f"### Skill: {skill['name']}\n"
                f"Description: {skill['description']}\n"
                f"Invocation: {skill['invocation']}\n"
            )
            if skill.get("body"):
                block += f"\n{skill['body']}\n"
            block += "\n"
            if total + len(block) > MAX_SKILLS_PROMPT:
                lines.append(f"(... more skills truncated)")
                break
            lines.append(block)
            total += len(block)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 4. 记忆系统
# ---------------------------------------------------------------------------
# 两层存储:
#   MEMORY.md = 长期事实 (手动维护)
#   daily/{date}.jsonl = 每日日志 (通过 agent 工具自动写入)
# 搜索: TF-IDF + 余弦相似度, 纯 Python 实现


class MemoryStore:

    def __init__(self, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir
        self.memory_dir = workspace_dir / "memory" / "daily"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def write_memory(self, content: str, category: str = "general") -> str:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self.memory_dir / f"{today}.jsonl"
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "category": category,
            "content": content,
        }
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            return f"Memory saved to {today}.jsonl ({category})"
        except Exception as exc:
            return f"Error writing memory: {exc}"

    def load_evergreen(self) -> str:
        path = self.workspace_dir / "MEMORY.md"
        if not path.is_file():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def _load_all_chunks(self) -> list[dict[str, str]]:
        """加载所有记忆并拆分为块 (path + text)."""
        chunks: list[dict[str, str]] = []
        # 按段落拆分长期记忆
        evergreen = self.load_evergreen()
        if evergreen:
            for para in evergreen.split("\n\n"):
                para = para.strip()
                if para:
                    chunks.append({"path": "MEMORY.md", "text": para})
        # 每日记忆: 每条 JSONL 记录作为一个块
        if self.memory_dir.is_dir():
            for jf in sorted(self.memory_dir.glob("*.jsonl")):
                try:
                    for line in jf.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        entry = json.loads(line)
                        text = entry.get("content", "")
                        if text:
                            cat = entry.get("category", "")
                            label = f"{jf.name} [{cat}]" if cat else jf.name
                            chunks.append({"path": label, "text": text})
                except Exception:
                    continue
        return chunks

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """分词: 小写英文 + 单个 CJK 字符, 过滤短 token."""
        tokens = re.findall(r"[a-z0-9\u4e00-\u9fff]+", text.lower())
        return [t for t in tokens if len(t) > 1 or "\u4e00" <= t <= "\u9fff"]

    def search_memory(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """TF-IDF + 余弦相似度搜索, 纯 Python 实现."""
        chunks = self._load_all_chunks()
        if not chunks:
            return []
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        chunk_tokens = [self._tokenize(c["text"]) for c in chunks]

        # 文档频率
        df: dict[str, int] = {}
        for tokens in chunk_tokens:
            for t in set(tokens):
                df[t] = df.get(t, 0) + 1
        n = len(chunks)

        def tfidf(tokens: list[str]) -> dict[str, float]:
            tf: dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            return {t: c * (math.log((n + 1) / (df.get(t, 0) + 1)) + 1) for t, c in tf.items()}

        def cosine(a: dict[str, float], b: dict[str, float]) -> float:
            common = set(a) & set(b)
            if not common:
                return 0.0
            dot = sum(a[k] * b[k] for k in common)
            na = math.sqrt(sum(v * v for v in a.values()))
            nb = math.sqrt(sum(v * v for v in b.values()))
            return dot / (na * nb) if na and nb else 0.0

        qvec = tfidf(query_tokens)
        scored: list[dict[str, Any]] = []
        for i, tokens in enumerate(chunk_tokens):
            if not tokens:
                continue
            score = cosine(qvec, tfidf(tokens))
            if score > 0.0:
                snippet = chunks[i]["text"]
                if len(snippet) > 200:
                    snippet = snippet[:200] + "..."
                scored.append({"path": chunks[i]["path"], "score": round(score, 4), "snippet": snippet})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    # --- Hybrid Memory Search Enhancement ---

    @staticmethod
    def _hash_vector(text: str, dim: int = 64) -> list[float]:
        """Simulated vector embedding using hash-based random projection.
        No external API needed -- teaches the PATTERN of a second search channel."""
        tokens = MemoryStore._tokenize(text)
        vec = [0.0] * dim
        for token in tokens:
            h = hash(token)
            for i in range(dim):
                bit = (h >> (i % 62)) & 1
                vec[i] += 1.0 if bit else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    @staticmethod
    def _vector_cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb) if na and nb else 0.0

    @staticmethod
    def _bm25_rank_to_score(rank: int) -> float:
        """Convert BM25 rank position to a [0, 1] score."""
        return 1.0 / (1.0 + rank)

    @staticmethod
    def _jaccard_similarity(tokens_a: list[str], tokens_b: list[str]) -> float:
        set_a, set_b = set(tokens_a), set(tokens_b)
        inter = len(set_a & set_b)
        union = len(set_a | set_b)
        return inter / union if union else 0.0

    def _vector_search(self, query: str, chunks: list[dict[str, str]], top_k: int = 10) -> list[dict[str, Any]]:
        """Search by simulated vector similarity."""
        q_vec = self._hash_vector(query)
        scored = []
        for chunk in chunks:
            c_vec = self._hash_vector(chunk["text"])
            score = self._vector_cosine(q_vec, c_vec)
            if score > 0.0:
                scored.append({"chunk": chunk, "score": score})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def _keyword_search(self, query: str, chunks: list[dict[str, str]], top_k: int = 10) -> list[dict[str, Any]]:
        """Reuse existing TF-IDF as the keyword channel, return ranked results."""
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []
        chunk_tokens = [self._tokenize(c["text"]) for c in chunks]
        n = len(chunks)
        df: dict[str, int] = {}
        for tokens in chunk_tokens:
            for t in set(tokens):
                df[t] = df.get(t, 0) + 1

        def tfidf(tokens: list[str]) -> dict[str, float]:
            tf: dict[str, int] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            return {t: c * (math.log((n + 1) / (df.get(t, 0) + 1)) + 1) for t, c in tf.items()}

        def cosine(a: dict[str, float], b: dict[str, float]) -> float:
            common = set(a) & set(b)
            if not common:
                return 0.0
            dot = sum(a[k] * b[k] for k in common)
            na = math.sqrt(sum(v * v for v in a.values()))
            nb = math.sqrt(sum(v * v for v in b.values()))
            return dot / (na * nb) if na and nb else 0.0

        qvec = tfidf(query_tokens)
        scored = []
        for i, tokens in enumerate(chunk_tokens):
            if not tokens:
                continue
            score = cosine(qvec, tfidf(tokens))
            if score > 0.0:
                scored.append({"chunk": chunks[i], "score": score})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    @staticmethod
    def _merge_hybrid_results(
        vector_results: list[dict[str, Any]],
        keyword_results: list[dict[str, Any]],
        vector_weight: float = 0.7,
        text_weight: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Merge vector and keyword results by weighted score combination."""
        merged: dict[str, dict[str, Any]] = {}
        for r in vector_results:
            key = r["chunk"]["text"][:100]
            merged[key] = {"chunk": r["chunk"], "score": r["score"] * vector_weight}
        for r in keyword_results:
            key = r["chunk"]["text"][:100]
            if key in merged:
                merged[key]["score"] += r["score"] * text_weight
            else:
                merged[key] = {"chunk": r["chunk"], "score": r["score"] * text_weight}
        result = list(merged.values())
        result.sort(key=lambda x: x["score"], reverse=True)
        return result

    @staticmethod
    def _temporal_decay(results: list[dict[str, Any]], decay_rate: float = 0.01) -> list[dict[str, Any]]:
        """Apply exponential temporal decay to scores based on chunk age."""
        now = datetime.now(timezone.utc)
        for r in results:
            path = r["chunk"].get("path", "")
            age_days = 0.0
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", path)
            if date_match:
                try:
                    chunk_date = datetime.strptime(date_match.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    age_days = (now - chunk_date).total_seconds() / 86400.0
                except ValueError:
                    pass
            r["score"] *= math.exp(-decay_rate * age_days)
        return results

    @staticmethod
    def _mmr_rerank(
        results: list[dict[str, Any]],
        lambda_param: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Maximal Marginal Relevance re-ranking for diversity.
        MMR = lambda * relevance - (1-lambda) * max_similarity_to_selected"""
        if len(results) <= 1:
            return results
        tokenized = [MemoryStore._tokenize(r["chunk"]["text"]) for r in results]
        selected: list[int] = []
        remaining = list(range(len(results)))
        reranked: list[dict[str, Any]] = []
        while remaining:
            best_idx = -1
            best_mmr = float("-inf")
            for idx in remaining:
                relevance = results[idx]["score"]
                max_sim = 0.0
                for sel_idx in selected:
                    sim = MemoryStore._jaccard_similarity(tokenized[idx], tokenized[sel_idx])
                    if sim > max_sim:
                        max_sim = sim
                mmr = lambda_param * relevance - (1 - lambda_param) * max_sim
                if mmr > best_mmr:
                    best_mmr = mmr
                    best_idx = idx
            selected.append(best_idx)
            remaining.remove(best_idx)
            reranked.append(results[best_idx])
        return reranked

    def hybrid_search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Full hybrid search pipeline: keyword -> vector -> merge -> decay -> MMR -> top_k"""
        chunks = self._load_all_chunks()
        if not chunks:
            return []
        keyword_results = self._keyword_search(query, chunks, top_k=10)
        vector_results = self._vector_search(query, chunks, top_k=10)
        merged = self._merge_hybrid_results(vector_results, keyword_results)
        decayed = self._temporal_decay(merged)
        reranked = self._mmr_rerank(decayed)
        result = []
        for r in reranked[:top_k]:
            snippet = r["chunk"]["text"]
            if len(snippet) > 200:
                snippet = snippet[:200] + "..."
            result.append({"path": r["chunk"]["path"], "score": round(r["score"], 4), "snippet": snippet})
        return result

    def get_stats(self) -> dict[str, Any]:
        evergreen = self.load_evergreen()
        daily_files = list(self.memory_dir.glob("*.jsonl")) if self.memory_dir.is_dir() else []
        total_entries = 0
        for f in daily_files:
            try:
                total_entries += sum(1 for line in f.read_text(encoding="utf-8").splitlines() if line.strip())
            except Exception:
                pass
        return {"evergreen_chars": len(evergreen), "daily_files": len(daily_files), "daily_entries": total_entries}


# ---------------------------------------------------------------------------
# 记忆工具: memory_write + memory_search
# ---------------------------------------------------------------------------

memory_store = MemoryStore(WORKSPACE_DIR)


def tool_memory_write(content: str, category: str = "general") -> str:
    print_tool("memory_write", f"[{category}] {content[:60]}...")
    return memory_store.write_memory(content, category)


def tool_memory_search(query: str, top_k: int = 5) -> str:
    print_tool("memory_search", query)
    results = memory_store.hybrid_search(query, top_k)
    if not results:
        return "No relevant memories found."
    return "\n".join(f"[{r['path']}] (score: {r['score']}) {r['snippet']}" for r in results)


# ---------------------------------------------------------------------------
# 工作区与 Shell 工具 (合并 s02 + s03; read_file 仅一份, 与 list_directory 同源)
# ---------------------------------------------------------------------------


def safe_path(raw: str) -> Path:
    """解析为工作区内绝对路径, 禁止路径穿越。"""
    target = (WORKSPACE_DIR / raw).resolve()
    root = WORKSPACE_DIR.resolve()
    if not str(target).startswith(str(root)):
        raise ValueError(f"Path traversal blocked: {raw}")
    return target


def truncate(text: str, limit: int = MAX_TOOL_OUTPUT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text)} total chars]"


def tool_bash(command: str, timeout: int = 30) -> str:
    dangerous = ["rm -rf /", "mkfs", "> /dev/sd", "dd if="]
    for pattern in dangerous:
        if pattern in command:
            return f"Error: Refused to run dangerous command containing '{pattern}'"
    print_tool("bash", command)
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(WORKSPACE_DIR),
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += ("\n--- stderr ---\n" + result.stderr) if output else result.stderr
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return truncate(output) if output else "[no output]"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
    except Exception as exc:
        return f"Error: {exc}"


def tool_read_file(file_path: str) -> str:
    print_tool("read_file", file_path)
    try:
        target = safe_path(file_path)
        if not target.exists():
            return f"Error: File not found: {file_path}"
        if not target.is_file():
            return f"Error: Not a file: {file_path}"
        return truncate(target.read_text(encoding="utf-8"))
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        return f"Error: {exc}"


def tool_write_file(file_path: str, content: str) -> str:
    print_tool("write_file", file_path)
    try:
        target = safe_path(file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} chars to {file_path}"
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        return f"Error: {exc}"


def tool_edit_file(file_path: str, old_string: str, new_string: str) -> str:
    print_tool("edit_file", f"{file_path} (replace {len(old_string)} chars)")
    try:
        target = safe_path(file_path)
        if not target.exists():
            return f"Error: File not found: {file_path}"
        content = target.read_text(encoding="utf-8")
        count = content.count(old_string)
        if count == 0:
            return "Error: old_string not found in file. Make sure it matches exactly."
        if count > 1:
            return (
                f"Error: old_string found {count} times. "
                "It must be unique. Provide more surrounding context."
            )
        target.write_text(content.replace(old_string, new_string, 1), encoding="utf-8")
        return f"Successfully edited {file_path}"
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        return f"Error: {exc}"


def tool_list_directory(directory: str = ".") -> str:
    print_tool("list_directory", directory)
    try:
        target = safe_path(directory)
        if not target.exists():
            return f"Error: Directory not found: {directory}"
        if not target.is_dir():
            return f"Error: Not a directory: {directory}"
        lines = []
        for entry in sorted(target.iterdir()):
            prefix = "[dir]  " if entry.is_dir() else "[file] "
            lines.append(prefix + entry.name)
        return "\n".join(lines) if lines else "[empty directory]"
    except ValueError as exc:
        return str(exc)
    except Exception as exc:
        return f"Error: {exc}"


def tool_get_current_time() -> str:
    print_tool("get_current_time", "")
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%d %H:%M:%S UTC")


def tool_web_search(query: str) -> str:
    """
    基于 SerpAPI 的网页搜索：解析 Google 等引擎结果，优先返回答案框 / 知识图谱 / 自然结果摘要。
    需配置 SERPAPI_API_KEY；详见 https://serpapi.com
    """
    print_tool("web_search", query[:120])
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        return (
            "Error: SERPAPI_API_KEY not set. "
            "Add your key to .env (see https://serpapi.com/manage-api-key)."
        )
    try:
        from serpapi import SerpApiClient
    except ImportError:
        return "Error: pip install google-search-results"

    params: dict[str, Any] = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "gl": "cn",
        "hl": "zh-cn",
    }

    try:
        client = SerpApiClient(params)
        results = client.get_dict()
    except Exception as exc:
        return f"Error: SerpAPI request failed: {exc}"

    out: str | None = None

    if "answer_box_list" in results and results["answer_box_list"]:
        raw_list = results["answer_box_list"]
        lines = [str(x) for x in raw_list]
        out = "\n".join(lines)

    if out is None and "answer_box" in results:
        ab = results["answer_box"]
        if isinstance(ab, dict) and ab.get("answer"):
            out = str(ab["answer"])

    if out is None and "knowledge_graph" in results:
        kg = results["knowledge_graph"]
        if isinstance(kg, dict) and kg.get("description"):
            out = str(kg["description"])

    if out is None and results.get("organic_results"):
        snippets = [
            f"[{i + 1}] {res.get('title', '')}\n{res.get('snippet', '')}"
            for i, res in enumerate(results["organic_results"][:3])
        ]
        out = "\n\n".join(snippets)

    if out is None:
        out = f"No results found for '{query}'."

    return truncate(out)


# ---------------------------------------------------------------------------
# 工具定义: Schema + Handler (s02 + s03 工作区工具 + 本节记忆工具)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "bash",
        "description": (
            "Run a shell command and return its output. "
            "Use for system commands, git, package managers, etc. "
            "Working directory is the workspace root."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds. Default 30.",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file under the workspace directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path relative to workspace directory.",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write content to a file under the workspace. "
            "Creates parent directories if needed. Overwrites existing content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path relative to workspace directory.",
                },
                "content": {"type": "string", "description": "The content to write."},
            },
            "required": ["file_path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Replace an exact string in a file with a new string. "
            "old_string must appear exactly once. Always read_file first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path relative to workspace directory.",
                },
                "old_string": {
                    "type": "string",
                    "description": "Exact text to find; must be unique in the file.",
                },
                "new_string": {"type": "string", "description": "Replacement text."},
            },
            "required": ["file_path", "old_string", "new_string"],
        },
    },
    {
        "name": "list_directory",
        "description": "List files and subdirectories under a path in the workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Path relative to workspace; default is root (\".\")",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_current_time",
        "description": "Get the current date and time in UTC.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "web_search",
        "description": (
            "Internet search via SerpAPI / Google (requires SERPAPI_API_KEY in .env). "
            "Use for up-to-date facts, news, or URLs. Billing is per SerpAPI usage."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language search question or keywords.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_write",
        "description": (
            "Save an important fact or observation to long-term memory. "
            "Use when you learn something worth remembering about the user or context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The fact or observation to remember.",
                },
                "category": {
                    "type": "string",
                    "description": "Category: preference, fact, context, etc.",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "memory_search",
        "description": "Search stored memories for relevant information, ranked by similarity.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "top_k": {"type": "integer", "description": "Max results. Default: 5."},
            },
            "required": ["query"],
        },
    },
]

TOOL_HANDLERS: dict[str, Any] = {
    "bash": tool_bash,
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "edit_file": tool_edit_file,
    "list_directory": tool_list_directory,
    "get_current_time": tool_get_current_time,
    "web_search": tool_web_search,
    "memory_write": tool_memory_write,
    "memory_search": tool_memory_search,
}


def process_tool_call(tool_name: str, tool_input: dict) -> str:
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return f"Error: Unknown tool '{tool_name}'"
    try:
        return handler(**tool_input)
    except TypeError as exc:
        return f"Error: Invalid arguments for {tool_name}: {exc}"
    except Exception as exc:
        return f"Error: {tool_name} failed: {exc}"


# ---------------------------------------------------------------------------
# 5. 系统提示词组装 -- 核心函数
# ---------------------------------------------------------------------------
# 教学演示 8 个关键提示词层级.
# 每轮重建 -- 上一轮可能更新了记忆.
# 模式: full (主 agent) / minimal (子 agent / cron) / none (最小化)


def build_system_prompt(
    mode: str = "full",
    bootstrap: dict[str, str] | None = None,
    skills_block: str = "",
    memory_context: str = "",
    agent_id: str = "main",
    channel: str = "terminal",
) -> str:
    if bootstrap is None:
        bootstrap = {}
    sections: list[str] = []

    # 第 1 层: 身份 -- 来自 IDENTITY.md 或默认值
    identity = bootstrap.get("IDENTITY.md", "").strip()
    sections.append(identity if identity else "You are a helpful personal AI assistant.")

    # 第 2 层: 灵魂 -- 人格注入, 越靠前影响力越强
    if mode == "full":
        soul = bootstrap.get("SOUL.md", "").strip()
        if soul:
            sections.append(f"## Personality\n\n{soul}")

    # 第 3 层: 工具使用指南
    tools_md = bootstrap.get("TOOLS.md", "").strip()
    if tools_md:
        sections.append(f"## Tool Usage Guidelines\n\n{tools_md}")

    # 第 4 层: 技能
    if mode == "full" and skills_block:
        sections.append(skills_block)

    # 第 5 层: 记忆 -- 长期记忆 + 本轮自动搜索结果
    if mode == "full":
        mem_md = bootstrap.get("MEMORY.md", "").strip()
        parts: list[str] = []
        if mem_md:
            parts.append(f"### Evergreen Memory\n\n{mem_md}")
        if memory_context:
            parts.append(f"### Recalled Memories (auto-searched)\n\n{memory_context}")
        if parts:
            sections.append("## Memory\n\n" + "\n\n".join(parts))
        sections.append(
            "## Memory Instructions\n\n"
            "- Use memory_write to save important user facts and preferences.\n"
            "- Reference remembered facts naturally in conversation.\n"
            "- Use memory_search to recall specific past information."
        )

    # 第 6 层: Bootstrap 上下文 -- 剩余的 Bootstrap 文件
    if mode in ("full", "minimal"):
        for name in ["HEARTBEAT.md", "BOOTSTRAP.md", "AGENTS.md", "USER.md"]:
            content = bootstrap.get(name, "").strip()
            if content:
                sections.append(f"## {name.replace('.md', '')}\n\n{content}")

    # 第 7 层: 运行时上下文
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections.append(
        f"## Runtime Context\n\n"
        f"- Agent ID: {agent_id}\n- Model: {MODEL_ID}\n"
        f"- Channel: {channel}\n- Current time: {now}\n- Prompt mode: {mode}"
    )

    # 第 8 层: 渠道提示
    hints = {
        "terminal": "You are responding via a terminal REPL. Markdown is supported.",
        "telegram": "You are responding via Telegram. Keep messages concise.",
        "discord": "You are responding via Discord. Keep messages under 2000 characters.",
        "slack": "You are responding via Slack. Use Slack mrkdwn formatting.",
    }
    sections.append(f"## Channel\n\n{hints.get(channel, f'You are responding via {channel}.')}")

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# 6. Agent 循环 + REPL
# ---------------------------------------------------------------------------

def handle_repl_command(
    cmd: str,
    store: SessionStore,
    guard: ContextGuard,
    messages: list[dict],
    bootstrap_data: dict[str, str],
    skills_mgr: SkillsManager,
    skills_block: str,
) -> tuple[bool, list[dict]]:
    """处理 REPL 斜杠命令. 返回 (是否已处理, 更新后的 messages)."""
    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    # ----- 会话与上下文 (与 s03 对齐) -----
    if command == "/new":
        label = arg or ""
        sid = store.create_session(label)
        print_session(
            f"  已新建会话: {sid}" + (f" ({label})" if label else "")
        )
        return True, []

    if command == "/list":
        sessions = store.list_sessions()
        if not sessions:
            print_info("  (暂无会话记录)")
            return True, messages
        print_info("  会话列表:")
        for sid, meta in sessions:
            active = " <-- 当前" if sid == store.current_session_id else ""
            label = meta.get("label", "")
            label_str = f" ({label})" if label else ""
            count = meta.get("message_count", 0)
            last = meta.get("last_active", "?")[:19]
            print_info(
                f"    {sid}{label_str}  "
                f"msgs={count}  last={last}{active}"
            )
        return True, messages

    if command == "/switch":
        if not arg:
            print_warn("  用法: /switch <session_id>")
            return True, messages
        target_id = arg.strip()
        matched = [
            sid for sid in store._index if sid.startswith(target_id)
        ]
        if len(matched) == 0:
            print_warn(f"  未找到会话: {target_id}")
            return True, messages
        if len(matched) > 1:
            print_warn(f"  前缀不唯一, 匹配到: {', '.join(matched)}")
            return True, messages

        sid = matched[0]
        new_messages = store.load_session(sid)
        print_session(f"  已切换到会话: {sid} ({len(new_messages)} 条消息)")
        return True, new_messages

    if command == "/context":
        estimated = guard.estimate_messages_tokens(messages)
        pct = (estimated / guard.max_tokens) * 100
        bar_len = 30
        filled = int(bar_len * min(pct, 100) / 100)
        bar = "#" * filled + "-" * (bar_len - filled)
        color = GREEN if pct < 50 else (YELLOW if pct < 80 else RED)
        print_info(
            f"  上下文用量: ~{estimated:,} / {guard.max_tokens:,} tokens"
        )
        print(f"  {color}[{bar}] {pct:.1f}%{RESET}")
        print_info(f"  消息条数: {len(messages)}")
        return True, messages

    if command == "/compact":
        if len(messages) <= 4:
            print_info("  消息过少, 无需压缩 (需要 > 4 条).")
            return True, messages
        print_session("  正在压缩历史...")
        new_messages = guard.compact_history(messages, client, MODEL_ID)
        print_session(f"  {len(messages)} -> {len(new_messages)} 条消息")
        return True, new_messages

    if command == "/help":
        print_info("  会话: /new [标签]  /list  /switch <id>  /context  /compact")
        print_info("  智能: /soul  /skills  /memory  /search <q>  /prompt  /bootstrap")
        print_info("  退出: quit 或 exit")
        return True, messages

    # ----- Intelligence 调试 -----
    if command == "/soul":
        print_section("SOUL.md")
        soul = bootstrap_data.get("SOUL.md", "")
        print(soul if soul else f"{DIM}(未找到 SOUL.md){RESET}")
        return True, messages

    if command == "/skills":
        print_section("已发现的技能")
        if not skills_mgr.skills:
            print(f"{DIM}(未找到技能){RESET}")
        else:
            for s in skills_mgr.skills:
                print(f"  {BLUE}{s['invocation']}{RESET}  {s['name']} - {s['description']}")
                print(f"    {DIM}path: {s['path']}{RESET}")
        return True, messages

    if command == "/memory":
        print_section("记忆统计")
        stats = memory_store.get_stats()
        print(f"  长期记忆 (MEMORY.md): {stats['evergreen_chars']} 字符")
        print(f"  每日文件: {stats['daily_files']}")
        print(f"  每日条目: {stats['daily_entries']}")
        return True, messages

    if command == "/search":
        if not arg:
            print(f"{YELLOW}用法: /search <query>{RESET}")
            return True, messages
        print_section(f"记忆搜索: {arg}")
        results = memory_store.hybrid_search(arg)
        if not results:
            print(f"{DIM}(无结果){RESET}")
        else:
            for r in results:
                color = GREEN if r["score"] > 0.3 else DIM
                print(f"  {color}[{r['score']:.4f}]{RESET} {r['path']}")
                print(f"    {r['snippet']}")
        return True, messages

    if command == "/prompt":
        print_section("完整系统提示词")
        prompt = build_system_prompt(
            mode="full", bootstrap=bootstrap_data,
            skills_block=skills_block, memory_context=_auto_recall("show prompt"),
            agent_id=store.current_session_id or "main",
        )
        if len(prompt) > 3000:
            print(prompt[:3000])
            print(f"\n{DIM}... ({len(prompt) - 3000} more chars, total {len(prompt)}){RESET}")
        else:
            print(prompt)
        print(f"\n{DIM}提示词总长度: {len(prompt)} 字符{RESET}")
        return True, messages

    if command == "/bootstrap":
        print_section("Bootstrap 文件")
        if not bootstrap_data:
            print(f"{DIM}(未加载 Bootstrap 文件){RESET}")
        else:
            for name, content in bootstrap_data.items():
                print(f"  {BLUE}{name}{RESET}: {len(content)} chars")
        total = sum(len(v) for v in bootstrap_data.values())
        print(f"\n  {DIM}总计: {total} 字符 (上限: {MAX_TOTAL_CHARS}){RESET}")
        return True, messages

    return False, messages


def _auto_recall(user_message: str) -> str:
    """根据用户消息自动搜索相关记忆, 注入到系统提示词中."""
    results = memory_store.hybrid_search(user_message, top_k=3)
    if not results:
        return ""
    return "\n".join(f"- [{r['path']}] {r['snippet']}" for r in results)


def resolve_model_id(mode: str) -> str:
    """Web UI: model 为 'reason' 时使用 MODEL_ID_REASON，否则使用 MODEL_ID_CHAT。"""
    if (mode or "").lower() == "reason":
        return MODEL_ID_REASON
    return MODEL_ID_CHAT


class S06Runtime:
    """供 FastAPI Web UI 复用的加载状态（与 CLI agent_loop 启动段一致）。"""

    def __init__(self, session_agent_id: str = "claw0-web") -> None:
        loader = BootstrapLoader(WORKSPACE_DIR)
        self.bootstrap_data = loader.load_all(mode="full")
        self.skills_mgr = SkillsManager(WORKSPACE_DIR)
        self.skills_mgr.discover()
        self.skills_block = self.skills_mgr.format_prompt_block()
        self.store = SessionStore(agent_id=session_agent_id)
        self.guard = ContextGuard()


def iter_s06_turn(
    *,
    user_input: str,
    session_id: str,
    model_id: str,
    runtime: S06Runtime,
    reason_mode: bool = False,
    delta_chunk_size: int = 160,
) -> Iterator[dict[str, Any]]:
    """
    单轮用户输入 -> 流式事件 dict（供 SSE 推送）。
    事件 type: skills | phase | reasoning | tool | tool_result | delta | error | turn_done
    """
    store = runtime.store
    messages = store.load_session(session_id)

    skill_items = [
        {"name": s.get("name", ""), "invocation": s.get("invocation", "")}
        for s in runtime.skills_mgr.skills[:80]
    ]
    yield {"type": "skills", "items": skill_items}

    if reason_mode:
        yield {
            "type": "reasoning",
            "text": (
                "当前为 **Reason（推理档）** 模型路径。\n"
                "下方回复将尽量结构化；工具调用与记忆检索会在灰色块中展示。"
            ),
        }

    yield {"type": "phase", "phase": "recall_start"}
    memory_context = _auto_recall(user_input)
    yield {
        "type": "phase",
        "phase": "recall_done",
        "has_memory": bool(memory_context),
        "preview": (memory_context[:300] + "…") if len(memory_context) > 300 else memory_context,
    }

    system_prompt = build_system_prompt(
        mode="full",
        bootstrap=runtime.bootstrap_data,
        skills_block=runtime.skills_block,
        memory_context=memory_context,
        agent_id=session_id or store.current_session_id or "main",
    )
    yield {"type": "phase", "phase": "prompt_ready"}

    messages.append({"role": "user", "content": user_input})
    store.save_turn("user", user_input)

    while True:
        yield {"type": "phase", "phase": "llm_call", "model": model_id}
        try:
            response = runtime.guard.guard_api_call(
                api_client=client,
                model=model_id,
                system=system_prompt,
                messages=messages,
                tools=TOOLS,
            )
        except Exception as exc:
            yield {"type": "error", "message": str(exc)}
            while messages and messages[-1]["role"] != "user":
                messages.pop()
            if messages:
                messages.pop()
            yield {"type": "turn_done", "ok": False}
            return

        messages.append({"role": "assistant", "content": response.content})

        serialized_content: list[dict[str, Any]] = []
        for block in response.content:
            if hasattr(block, "text"):
                serialized_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                serialized_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
        store.save_turn("assistant", serialized_content)

        if response.stop_reason == "end_turn":
            text = "".join(
                b.text for b in response.content if hasattr(b, "text")
            )
            for i in range(0, len(text), delta_chunk_size):
                yield {"type": "delta", "text": text[i : i + delta_chunk_size]}
            yield {"type": "turn_done", "ok": True, "stop_reason": "end_turn"}
            return

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                inp_preview = json.dumps(block.input, ensure_ascii=False)
                if len(inp_preview) > 1200:
                    inp_preview = inp_preview[:1200] + "…"
                yield {
                    "type": "tool",
                    "tool_name": block.name,
                    "preview": inp_preview,
                }
                result = process_tool_call(block.name, block.input)
                out_preview = result if len(result) <= 2000 else result[:2000] + "\n…"
                yield {
                    "type": "tool_result",
                    "tool_name": block.name,
                    "preview": out_preview,
                }
                store.save_tool_result(
                    block.id, block.name, block.input, result
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
            messages.append({"role": "user", "content": tool_results})
            yield {"type": "phase", "phase": "tool_round_done"}
            continue

        text = "".join(
            b.text for b in response.content if hasattr(b, "text")
        )
        for i in range(0, len(text), delta_chunk_size):
            yield {"type": "delta", "text": text[i : i + delta_chunk_size]}
        yield {
            "type": "turn_done",
            "ok": True,
            "stop_reason": response.stop_reason,
        }
        return


def agent_loop() -> None:
    # 启动阶段: 加载 Bootstrap 文件, 发现技能 (技能仅在启动时发现一次)
    loader = BootstrapLoader(WORKSPACE_DIR)
    bootstrap_data = loader.load_all(mode="full")

    skills_mgr = SkillsManager(WORKSPACE_DIR)
    skills_mgr.discover()
    skills_block = skills_mgr.format_prompt_block()

    store = SessionStore(agent_id="claw0")
    guard = ContextGuard()

    sessions = store.list_sessions()
    if sessions:
        sid = sessions[0][0]
        messages = store.load_session(sid)
        print_session(f"  已恢复会话: {sid} ({len(messages)} 条消息)")
    else:
        store.create_session("initial")
        messages = []
        print_session(f"  已创建初始会话: {store.current_session_id}")

    print_info("=" * 60)
    print_info("  claw0  |  Section 06: Intelligence + Sessions")
    print_info(f"  Model: {MODEL_ID}")
    print_info(f"  Workspace: {WORKSPACE_DIR}")
    print_info(f"  当前会话: {store.current_session_id}")
    print_info(f"  Bootstrap 文件: {len(bootstrap_data)}")
    print_info(f"  已发现技能: {len(skills_mgr.skills)}")
    stats = memory_store.get_stats()
    print_info(f"  记忆: 长期 {stats['evergreen_chars']}字符, {stats['daily_files']} 个每日文件")
    print_info(
        f"  LLM 工具 ({len(TOOL_HANDLERS)}): "
        f"{', '.join(sorted(TOOL_HANDLERS.keys()))}"
    )
    print_info("  /help 查看全部命令.  输入 quit / exit 退出.")
    print_info("=" * 60)
    print()

    while True:
        try:
            user_input = input(colored_prompt()).strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{DIM}再见.{RESET}")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print(f"{DIM}再见.{RESET}")
            break

        if user_input.startswith("/"):
            handled, messages = handle_repl_command(
                user_input,
                store,
                guard,
                messages,
                bootstrap_data,
                skills_mgr,
                skills_block,
            )
            if handled:
                continue

        memory_context = _auto_recall(user_input)
        if memory_context:
            print_info("  [自动召回] 找到相关记忆")

        system_prompt = build_system_prompt(
            mode="full",
            bootstrap=bootstrap_data,
            skills_block=skills_block,
            memory_context=memory_context,
            agent_id=store.current_session_id or "main",
        )

        messages.append({"role": "user", "content": user_input})
        store.save_turn("user", user_input)

        while True:
            try:
                response = guard.guard_api_call(
                    api_client=client,
                    model=MODEL_ID,
                    system=system_prompt,
                    messages=messages,
                    tools=TOOLS,
                )
            except Exception as exc:
                print(f"\n{YELLOW}API Error: {exc}{RESET}\n")
                while messages and messages[-1]["role"] != "user":
                    messages.pop()
                if messages:
                    messages.pop()
                break

            messages.append({"role": "assistant", "content": response.content})

            serialized_content: list[dict[str, Any]] = []
            for block in response.content:
                if hasattr(block, "text"):
                    serialized_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    serialized_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
            store.save_turn("assistant", serialized_content)

            if response.stop_reason == "end_turn":
                text = "".join(
                    b.text for b in response.content if hasattr(b, "text")
                )
                if text:
                    print_assistant(text)
                break
            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    result = process_tool_call(block.name, block.input)
                    store.save_tool_result(
                        block.id, block.name, block.input, result
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
                messages.append({"role": "user", "content": tool_results})
                continue

            print_info(f"[stop_reason={response.stop_reason}]")
            text = "".join(
                b.text for b in response.content if hasattr(b, "text")
            )
            if text:
                print_assistant(text)
            break


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print(f"{YELLOW}错误: 未设置 ANTHROPIC_API_KEY.{RESET}")
        print(f"{DIM}将 .env.example 复制为 .env 并填入你的密钥.{RESET}")
        sys.exit(1)
    if not WORKSPACE_DIR.is_dir():
        print(f"{YELLOW}错误: 未找到工作区目录: {WORKSPACE_DIR}{RESET}")
        print(f"{DIM}请从本仓库根目录运行.{RESET}")
        sys.exit(1)
    agent_loop()


if __name__ == "__main__":
    main()
