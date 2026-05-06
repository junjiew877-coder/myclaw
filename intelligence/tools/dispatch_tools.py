"""
Anthropic tools JSON Schema 与各工具实现函数的注册表、统一派发入口。

位于 intelligence/tools/dispatch_tools.py。
"""

from __future__ import annotations

from typing import Any

from .memory_tools import tool_memory_search, tool_memory_write
from .workspace_tools import (
    tool_bash,
    tool_edit_file,
    tool_get_current_time,
    tool_list_directory,
    tool_read_file,
    tool_web_search,
    tool_write_file,
)

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
                    "description": 'Path relative to workspace; default is root (".")',
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
