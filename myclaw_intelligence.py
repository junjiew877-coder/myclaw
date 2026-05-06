"""
仓库根目录兼容模块（myclaw Intelligence）。

- Web：`import myclaw_intelligence`（FastAPI 依赖 WORKSPACE_DIR、MyclawRuntime、iter_chat_turn 等）。
- CLI：`python -m intelligence`（或 `python -m intelligence.entrypoints.main`、`python myclaw_intelligence.py`）。

实现位于 `intelligence/` 包；`main()` 仅在调用时加载 loop。
"""

from __future__ import annotations

from intelligence.config import MODEL_ID, MODEL_ID_CHAT, MODEL_ID_REASON, WORKSPACE_DIR, client
from intelligence.runtime import MyclawRuntime, iter_chat_turn, resolve_model_id

__all__ = [
    "MODEL_ID",
    "MODEL_ID_CHAT",
    "MODEL_ID_REASON",
    "WORKSPACE_DIR",
    "client",
    "MyclawRuntime",
    "iter_chat_turn",
    "resolve_model_id",
    "main",
]


def main() -> None:
    """委托至 `intelligence.entrypoints.main`，避免仅 import 本模块时加载 REPL。"""
    from intelligence.entrypoints.main import main as ep_main

    ep_main()


if __name__ == "__main__":
    main()
