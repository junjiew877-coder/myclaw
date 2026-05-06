"""
Web UI 复用的 MyclawRuntime、模型档位解析，以及单轮流式事件生成器 iter_chat_turn。
"""

from __future__ import annotations

import json
from typing import Any, Iterator

from .bootstrap import BootstrapLoader
from .config import MODEL_ID_CHAT, MODEL_ID_REASON, WORKSPACE_DIR, client
from .context_guard import ContextGuard
from .prompt import build_system_prompt
from .memory import auto_recall
from .session import SessionStore
from .skills import SkillsManager
from .tools import TOOLS, process_tool_call


def resolve_model_id(mode: str) -> str:
    """Web UI: model 为 'reason' 时使用 MODEL_ID_REASON，否则使用 MODEL_ID_CHAT。"""
    if (mode or "").lower() == "reason":
        return MODEL_ID_REASON
    return MODEL_ID_CHAT


class MyclawRuntime:
    """供 FastAPI Web UI 复用的加载状态（与 CLI agent_loop 启动段一致）。"""

    def __init__(self, session_agent_id: str = "myclaw-web") -> None:
        loader = BootstrapLoader(WORKSPACE_DIR)
        self.bootstrap_data = loader.load_all(mode="full")
        self.skills_mgr = SkillsManager(WORKSPACE_DIR)
        self.skills_mgr.discover()
        self.skills_block = self.skills_mgr.format_prompt_block()
        self.store = SessionStore(agent_id=session_agent_id)
        self.guard = ContextGuard()


def iter_chat_turn(
    *,
    user_input: str,
    session_id: str,
    model_id: str,
    runtime: MyclawRuntime,
    reason_mode: bool = False,
    delta_chunk_size: int = 160,
) -> Iterator[dict[str, Any]]:
    """
    单轮用户输入 -> 流式事件 dict（供 SSE 推送）。
    事件 type: skills | phase | reasoning | tool | tool_result | delta | error | turn_done

    正文使用 Anthropic ``messages.stream`` 的 ``text_stream``（API 级增量），不再在服务端按
    delta_chunk_size 切片整段文本；delta_chunk_size 保留仅为兼容旧调用。
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
    memory_context = auto_recall(user_input)
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
            stream_kwargs: dict[str, Any] = {
                "model": model_id,
                "max_tokens": 8096,
                "system": system_prompt,
                "messages": messages,
            }
            if TOOLS:
                stream_kwargs["tools"] = TOOLS

            with client.messages.stream(**stream_kwargs) as stream:
                for text in stream.text_stream:
                    if text:
                        yield {"type": "delta", "text": text}
                response = stream.get_final_message()
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

        yield {
            "type": "turn_done",
            "ok": True,
            "stop_reason": response.stop_reason,
        }
        return
