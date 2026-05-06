"""
终端 REPL 启动入口：校验环境变量与工作区后进入 agent_loop。

运行（仓库根目录、已安装依赖）：`python -m intelligence`，或本模块
`python -m intelligence.entrypoints.main`，或根目录 `python myclaw_intelligence.py`。
"""

from __future__ import annotations

import os
import sys

from intelligence.config import WORKSPACE_DIR
from intelligence.console import DIM, RESET, YELLOW
from intelligence.loop import agent_loop


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
