"""
根据用户输入自动检索记忆片段，注入系统提示（自动召回）。

位于 intelligence/memory/recall.py。
"""

from __future__ import annotations

from .runtime_memory import memory_store


def auto_recall(user_message: str) -> str:
    """根据用户消息自动搜索相关记忆, 注入到系统提示词中."""
    results = memory_store.hybrid_search(user_message, top_k=3)
    if not results:
        return ""
    return "\n".join(f"- [{r['path']}] {r['snippet']}" for r in results)
