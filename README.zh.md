[入门与启动](README.md) | [本页·课程全文](README.zh.md)

# myclaw部分架构

"""
Section 06: Intelligence (智能)
"赋予灵魂, 教会记忆"

每轮对话前, agent 的"大脑"是如何组装的?
本节是整个教学项目的核心集成点 -- 演示系统提示词的分层构建过程.

在 s01-s02 中, 系统提示词是硬编码的字符串.
在真实的 agent 框架中, 系统提示词由多个层级动态组装:
  Identity / 灵魂 / Tools / 技能 / Memory / Bootstrap / Runtime / Channel

架构:

    [SOUL.md]  [IDENTITY.md]  [TOOLS.md]  [MEMORY.md]  ...
         \          |            |           /
          v         v            v          v
        +-------------------------------+
        |     BootstrapLoader           |
        |  (load, truncate, cap)        |
        +-------------------------------+
                    |
                    v
        +-------------------------------+        +-------------------+
        |   build_system_prompt()       | <----> | SkillsManager     |
        |   (8 层组装)                  |        | (discover, parse) |
        +-------------------------------+        +-------------------+
                    |                                     ^
                    v                                     |
        +-------------------------------+        +-------------------+
        |   Agent Loop (每轮)           | <----> | MemoryStore       |
        |   search -> build -> call LLM |        | (write, search)   |
        +-------------------------------+        +-------------------+

## 前置要求

- Python 3.11+
- Anthropic (或兼容服务商) 的 API key

## 依赖

```
anthropic>=0.39.0
python-dotenv>=1.0.0
websockets>=12.0
croniter>=2.0.0
python-telegram-bot>=21.0
httpx>=0.27.0
```

## 相关项目

- **[learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)** --  用 12 个递进课程从零构建一个智能体**框架** (nano Claude Code)。 learn-claude-code 深入智能体的内部设计: 结构化规划 (TodoManager + nag)、上下文压缩 (三层 compact)、基于文件的任务持久化与依赖图、团队协调 (JSONL 邮箱、关机/计划审批 FSM)、自治式自组织, 以及 git worktree 隔离的并行执行。如果你想理解一个生产级单元智能体的内部运作, 从那里开始。

## 许可证

MIT
