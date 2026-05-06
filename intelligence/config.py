"""
环境变量、Anthropic 客户端、工作区路径与全局数值上限。
供 Bootstrap、会话、工具与上下文保护等模块共用。
"""

from __future__ import annotations

import os
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

MODEL_ID = os.getenv("MODEL_ID", "claude-sonnet-4-20250514")
MODEL_ID_CHAT = os.getenv("MODEL_ID_CHAT", MODEL_ID)
MODEL_ID_REASON = os.getenv("MODEL_ID_REASON", MODEL_ID)

client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    base_url=os.getenv("ANTHROPIC_BASE_URL") or None,
)

WORKSPACE_DIR = Path(__file__).resolve().parents[1] / "workspace"

BOOTSTRAP_FILES = [
    "SOUL.md",
    "IDENTITY.md",
    "TOOLS.md",
    "USER.md",
    "HEARTBEAT.md",
    "BOOTSTRAP.md",
    "AGENTS.md",
    "MEMORY.md",
]

MAX_FILE_CHARS = 20000
MAX_TOTAL_CHARS = 150000
MAX_SKILLS = 150
MAX_SKILLS_PROMPT = 30000

CONTEXT_SAFE_LIMIT = 180000

MAX_TOOL_OUTPUT = 50000
