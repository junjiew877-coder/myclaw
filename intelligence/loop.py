"""
交互式 REPL：加载 Bootstrap 与技能、恢复或创建会话、读入用户输入并驱动 LLM 工具循环。
"""

from __future__ import annotations

from .bootstrap import BootstrapLoader
from .config import MODEL_ID, WORKSPACE_DIR, client
from .console import (
    DIM,
    RESET,
    YELLOW,
    colored_prompt,
    print_assistant,
    print_info,
    print_session,
)
from .context_guard import ContextGuard
from .memory import auto_recall, memory_store
from .prompt import build_system_prompt
from .repl import handle_repl_command
from .session import SessionStore
from .skills import SkillsManager
from .tools import TOOLS, TOOL_HANDLERS, process_tool_call


def agent_loop() -> None:
    loader = BootstrapLoader(WORKSPACE_DIR)
    bootstrap_data = loader.load_all(mode="full")

    skills_mgr = SkillsManager(WORKSPACE_DIR)
    skills_mgr.discover()
    skills_block = skills_mgr.format_prompt_block()

    store = SessionStore(agent_id="myclaw")
    guard = ContextGuard()

    sessions = store.list_sessions()
    if sessions:
        sid = sessions[0][0]
        messages = store.load_session(sid)
        print_session(f"  已恢复会话: {sid} ({len(messages)} 条消息)")
    else:
        store.create_session("initial")
        messages = []
        print_session(f"  已创建初始会话: {store.current_session_id}")

    print_info("=" * 60)
    print_info("  myclaw  |  Intelligence + Sessions")
    print_info(f"  Model: {MODEL_ID}")
    print_info(f"  Workspace: {WORKSPACE_DIR}")
    print_info(f"  当前会话: {store.current_session_id}")
    print_info(f"  Bootstrap 文件: {len(bootstrap_data)}")
    print_info(f"  已发现技能: {len(skills_mgr.skills)}")
    stats = memory_store.get_stats()
    print_info(f"  记忆: 长期 {stats['evergreen_chars']}字符, {stats['daily_files']} 个每日文件")
    print_info(
        f"  LLM 工具 ({len(TOOL_HANDLERS)}): "
        f"{', '.join(sorted(TOOL_HANDLERS.keys()))}"
    )
    print_info("  /help 查看全部命令.  输入 quit / exit 退出.")
    print_info("=" * 60)
    print()

    while True:
        try:
            user_input = input(colored_prompt()).strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{DIM}再见.{RESET}")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print(f"{DIM}再见.{RESET}")
            break

        if user_input.startswith("/"):
            handled, messages = handle_repl_command(
                user_input,
                store,
                guard,
                messages,
                bootstrap_data,
                skills_mgr,
                skills_block,
            )
            if handled:
                continue

        memory_context = auto_recall(user_input)
        if memory_context:
            print_info("  [自动召回] 找到相关记忆")

        system_prompt = build_system_prompt(
            mode="full",
            bootstrap=bootstrap_data,
            skills_block=skills_block,
            memory_context=memory_context,
            agent_id=store.current_session_id or "main",
        )

        messages.append({"role": "user", "content": user_input})
        store.save_turn("user", user_input)

        while True:
            try:
                response = guard.guard_api_call(
                    api_client=client,
                    model=MODEL_ID,
                    system=system_prompt,
                    messages=messages,
                    tools=TOOLS,
                )
            except Exception as exc:
                print(f"\n{YELLOW}API Error: {exc}{RESET}\n")
                while messages and messages[-1]["role"] != "user":
                    messages.pop()
                if messages:
                    messages.pop()
                break

            messages.append({"role": "assistant", "content": response.content})

            serialized_content: list[dict] = []
            for block in response.content:
                if hasattr(block, "text"):
                    serialized_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    serialized_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
            store.save_turn("assistant", serialized_content)

            if response.stop_reason == "end_turn":
                text = "".join(
                    b.text for b in response.content if hasattr(b, "text")
                )
                if text:
                    print_assistant(text)
                break
            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    result = process_tool_call(block.name, block.input)
                    store.save_tool_result(
                        block.id, block.name, block.input, result
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
                messages.append({"role": "user", "content": tool_results})
                continue

            print_info(f"[stop_reason={response.stop_reason}]")
            text = "".join(
                b.text for b in response.content if hasattr(b, "text")
            )
            if text:
                print_assistant(text)
            break
