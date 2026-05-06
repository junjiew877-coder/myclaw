"""
终端斜杠命令处理：会话切换、上下文用量、/skills /memory /prompt 等调试命令。
"""

from __future__ import annotations

from .config import MAX_TOTAL_CHARS, MODEL_ID, client
from .console import (
    BLUE,
    DIM,
    GREEN,
    RED,
    RESET,
    YELLOW,
    print_info,
    print_section,
    print_session,
    print_warn,
)
from .context_guard import ContextGuard
from .memory import auto_recall, memory_store
from .prompt import build_system_prompt
from .session import SessionStore
from .skills import SkillsManager


def handle_repl_command(
    cmd: str,
    store: SessionStore,
    guard: ContextGuard,
    messages: list[dict],
    bootstrap_data: dict[str, str],
    skills_mgr: SkillsManager,
    skills_block: str,
) -> tuple[bool, list[dict]]:
    """处理 REPL 斜杠命令. 返回 (是否已处理, 更新后的 messages)."""
    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command == "/new":
        label = arg or ""
        sid = store.create_session(label)
        print_session(
            f"  已新建会话: {sid}" + (f" ({label})" if label else "")
        )
        return True, []

    if command == "/list":
        sessions = store.list_sessions()
        if not sessions:
            print_info("  (暂无会话记录)")
            return True, messages
        print_info("  会话列表:")
        for sid, meta in sessions:
            active = " <-- 当前" if sid == store.current_session_id else ""
            label = meta.get("label", "")
            label_str = f" ({label})" if label else ""
            count = meta.get("message_count", 0)
            last = meta.get("last_active", "?")[:19]
            print_info(
                f"    {sid}{label_str}  "
                f"msgs={count}  last={last}{active}"
            )
        return True, messages

    if command == "/switch":
        if not arg:
            print_warn("  用法: /switch <session_id>")
            return True, messages
        target_id = arg.strip()
        matched = [
            sid for sid in store._index if sid.startswith(target_id)
        ]
        if len(matched) == 0:
            print_warn(f"  未找到会话: {target_id}")
            return True, messages
        if len(matched) > 1:
            print_warn(f"  前缀不唯一, 匹配到: {', '.join(matched)}")
            return True, messages

        sid = matched[0]
        new_messages = store.load_session(sid)
        print_session(f"  已切换到会话: {sid} ({len(new_messages)} 条消息)")
        return True, new_messages

    if command == "/context":
        estimated = guard.estimate_messages_tokens(messages)
        pct = (estimated / guard.max_tokens) * 100
        bar_len = 30
        filled = int(bar_len * min(pct, 100) / 100)
        bar = "#" * filled + "-" * (bar_len - filled)
        color = GREEN if pct < 50 else (YELLOW if pct < 80 else RED)
        print_info(
            f"  上下文用量: ~{estimated:,} / {guard.max_tokens:,} tokens"
        )
        print(f"  {color}[{bar}] {pct:.1f}%{RESET}")
        print_info(f"  消息条数: {len(messages)}")
        return True, messages

    if command == "/compact":
        if len(messages) <= 4:
            print_info("  消息过少, 无需压缩 (需要 > 4 条).")
            return True, messages
        print_session("  正在压缩历史...")
        new_messages = guard.compact_history(messages, client, MODEL_ID)
        print_session(f"  {len(messages)} -> {len(new_messages)} 条消息")
        return True, new_messages

    if command == "/help":
        print_info("  会话: /new [标签]  /list  /switch <id>  /context  /compact")
        print_info("  智能: /soul  /skills  /memory  /search <q>  /prompt  /bootstrap")
        print_info("  退出: quit 或 exit")
        return True, messages

    if command == "/soul":
        print_section("SOUL.md")
        soul = bootstrap_data.get("SOUL.md", "")
        print(soul if soul else f"{DIM}(未找到 SOUL.md){RESET}")
        return True, messages

    if command == "/skills":
        print_section("已发现的技能")
        if not skills_mgr.skills:
            print(f"{DIM}(未找到技能){RESET}")
        else:
            for s in skills_mgr.skills:
                print(f"  {BLUE}{s['invocation']}{RESET}  {s['name']} - {s['description']}")
                print(f"    {DIM}path: {s['path']}{RESET}")
        return True, messages

    if command == "/memory":
        print_section("记忆统计")
        stats = memory_store.get_stats()
        print(f"  长期记忆 (MEMORY.md): {stats['evergreen_chars']} 字符")
        print(f"  每日文件: {stats['daily_files']}")
        print(f"  每日条目: {stats['daily_entries']}")
        return True, messages

    if command == "/search":
        if not arg:
            print(f"{YELLOW}用法: /search <query>{RESET}")
            return True, messages
        print_section(f"记忆搜索: {arg}")
        results = memory_store.hybrid_search(arg)
        if not results:
            print(f"{DIM}(无结果){RESET}")
        else:
            for r in results:
                color = GREEN if r["score"] > 0.3 else DIM
                print(f"  {color}[{r['score']:.4f}]{RESET} {r['path']}")
                print(f"    {r['snippet']}")
        return True, messages

    if command == "/prompt":
        print_section("完整系统提示词")
        prompt = build_system_prompt(
            mode="full",
            bootstrap=bootstrap_data,
            skills_block=skills_block,
            memory_context=auto_recall("show prompt"),
            agent_id=store.current_session_id or "main",
        )
        if len(prompt) > 3000:
            print(prompt[:3000])
            print(f"\n{DIM}... ({len(prompt) - 3000} more chars, total {len(prompt)}){RESET}")
        else:
            print(prompt)
        print(f"\n{DIM}提示词总长度: {len(prompt)} 字符{RESET}")
        return True, messages

    if command == "/bootstrap":
        print_section("Bootstrap 文件")
        if not bootstrap_data:
            print(f"{DIM}(未加载 Bootstrap 文件){RESET}")
        else:
            for name, content in bootstrap_data.items():
                print(f"  {BLUE}{name}{RESET}: {len(content)} chars")
        total = sum(len(v) for v in bootstrap_data.values())
        print(f"\n  {DIM}总计: {total} 字符 (上限: {MAX_TOTAL_CHARS}){RESET}")
        return True, messages

    return False, messages
