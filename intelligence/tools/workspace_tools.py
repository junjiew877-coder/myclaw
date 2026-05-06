"""
工作区文件、Shell、时间与联网搜索等工具实现（路径限制在 workspace 内）。

位于 intelligence/tools/workspace_tools.py。
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import MAX_TOOL_OUTPUT, WORKSPACE_DIR
from ..console import print_tool


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
        serp_client = SerpApiClient(params)
        results = serp_client.get_dict()
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
