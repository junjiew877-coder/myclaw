"""
LLM 可调用的记忆工具：写入每日 jsonl、混合检索记忆。

位于 intelligence/tools/memory_tools.py。
"""

from __future__ import annotations

from ..console import print_tool
from ..memory.runtime_memory import memory_store


def tool_memory_write(content: str, category: str = "general") -> str:
    print_tool("memory_write", f"[{category}] {content[:60]}...")
    return memory_store.write_memory(content, category)


def tool_memory_search(query: str, top_k: int = 5) -> str:
    print_tool("memory_search", query)
    results = memory_store.hybrid_search(query, top_k)
    if not results:
        return "No relevant memories found."
    return "\n".join(f"[{r['path']}] (score: {r['score']}) {r['snippet']}" for r in results)
