"""
全局 MemoryStore 单例（与工作区根绑定），供工具函数与自动召回共用。
"""

from __future__ import annotations

from ..config import WORKSPACE_DIR
from .store_memory import MemoryStore

memory_store = MemoryStore(WORKSPACE_DIR)
