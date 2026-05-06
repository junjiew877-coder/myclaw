"""
记忆存储、运行时单例与自动召回（供提示词注入）。
"""

from __future__ import annotations

from .runtime_memory import memory_store
from .recall import auto_recall
from .store_memory import MemoryStore

__all__ = ["MemoryStore", "memory_store", "auto_recall"]
