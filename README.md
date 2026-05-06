# myclaw

面向个人的 AI 助手栈：**工作区 Markdown 驱动提示词**、**Anthropic 工具调用**、**记忆与会话持久化**，以及基于 **React + FastAPI**、通过 **SSE 真流式**输出正文的聊天界面。

---

## 技术特性（Technical features）

- **分层 system prompt** — 按 Identity / Soul / Tools / Skills / Memory / Bootstrap / Runtime / Channel 等区块组装（`intelligence/prompt.py`），内容主要来自 `workspace/` 下 Markdown。
- **Bootstrap 加载** — 读取 `SOUL.md`、`IDENTITY.md`、`TOOLS.md`、`MEMORY.md` 等，按单文件与总字数上限截断（`intelligence/bootstrap.py`）。
- **Agent 技能（Skills）** — 扫描 `workspace/skills/**/SKILL.md`，格式化后注入系统提示（`intelligence/skills.py`）。
- **记忆（Memory）** — 每轮对话前自动召回相关记忆；提供长期笔记的读写与存储抽象（`intelligence/memory/`，含 `recall.py`、`store_memory.py`、`runtime_memory.py`）。
- **会话（Sessions）** — 基于 JSONL 的 `SessionStore`，维护 Anthropic 风格的 `messages` 历史（`intelligence/session/`，含 `store_session.py`、`message_utils.py`）。
- **工具调用** — 统一工具列表与派发；工作区文件/命令类工具、记忆类工具，以及可选 SerpApi 网页搜索（`intelligence/tools/`：`dispatch_tools.py`、`workspace_tools.py`、`memory_tools.py`）。
- **模型路由** — 通过环境变量区分对话档与推理档模型（`MODEL_ID_CHAT` / `MODEL_ID_REASON`）；可选兼容 API 的 `ANTHROPIC_BASE_URL`（如 OpenRouter）（`intelligence/config.py`）。
- **Web API** — FastAPI 通过 **Server-Sent Events** 推送事件：阶段（phase）、技能列表、工具预览、**来自 Anthropic `messages.stream` 的 `text_stream` 增量（映射为 `delta`）**、`turn_done` 等（`web/server/app.py`、`intelligence/runtime.py`）。
- **终端 REPL** — `agent_loop` 驱动交互循环；对 LLM 调用使用 **ContextGuard** 做上下文溢出时的重试与压缩（`intelligence/loop.py`、`intelligence/context_guard.py`）；终端表现与辅助函数见 `intelligence/repl.py`、`intelligence/console.py`。
- **统一 Python 入口** — 根目录 `myclaw_intelligence.py` 与包内 `intelligence/__init__.py` 导出 Web 与脚本常用的符号（如 `MyclawRuntime`、`iter_chat_turn`、`WORKSPACE_DIR`、`client`）。

---

## 环境要求（Requirements）

| 组件 | 说明 |
|------|------|
| **Python** | 建议 3.10+（若与仓库内其他文档对齐，可用 3.11+） |
| **Node.js** | 当前 LTS，仅用于 `web/` 前端开发与构建 |
| **API** | `ANTHROPIC_API_KEY`（Anthropic 或兼容的 API 服务商） |

Python 依赖见 `requirements.txt`（Anthropic SDK、FastAPI、Uvicorn、httpx、python-dotenv 等；另含可选的 Telegram、cron、搜索等库）。前端为 React 19 + Vite 6（见 `web/package.json`）。

---

## 快速开始（Quick start）

均在**仓库根目录**执行（与 `myclaw_intelligence.py`、`workspace/` 同级）。

### 1. 环境变量

```bash
cp .env.example .env
# 编辑 .env：至少配置 ANTHROPIC_API_KEY、MODEL_ID；其余见 .env.example
```

确保存在可用的 `workspace/` 目录（仓库内已带示例树）。

### 2. Python 后端（API）

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

uvicorn web.server.app:app --host 127.0.0.1 --port 8765
```

### 3. Web 前端（开发模式）

另开终端：

```bash
cd web
npm install
npm run dev
```

- 开发服务器：**http://127.0.0.1:5173**
- `/api` 会代理到 **http://127.0.0.1:8765**（`web/vite.config.ts`）

### 4. 仅终端 REPL（不用浏览器）

```bash
python -m intelligence
# 或：python -m intelligence.entrypoints.main
# 或：python myclaw_intelligence.py
```

同样需要配置好的 `.env` 与 `workspace/`。

---

## 项目结构（Project layout）

| 路径 | 作用 |
|------|------|
| `myclaw_intelligence.py` | 根目录稳定导入入口：供 FastAPI 等引用 `WORKSPACE_DIR`、`MyclawRuntime`、`iter_chat_turn` 等。 |
| `requirements.txt` | Python 依赖列表。 |
| `.env.example` | 环境变量说明模板。 |
| **`intelligence/`** | **智能体核心包**。 |
| `intelligence/__init__.py` | 包级导出（配置、运行时、流式生成器等）。 |
| `intelligence/__main__.py` | 支持 `python -m intelligence`。 |
| `intelligence/config.py` | 环境变量、`Anthropic` 客户端、`WORKSPACE_DIR`、模型 ID、各类长度上限。 |
| `intelligence/runtime.py` | **`MyclawRuntime`**（与 CLI 启动段对齐的加载状态）、**`iter_chat_turn`**（单轮流式事件，供 SSE 使用）。 |
| `intelligence/prompt.py` | **`build_system_prompt`**：多层 system prompt 组装。 |
| `intelligence/bootstrap.py` | **`BootstrapLoader`**：工作区 Markdown 加载与截断策略。 |
| `intelligence/skills.py` | **`SkillsManager`**：发现与格式化 `SKILL.md`。 |
| `intelligence/context_guard.py` | **`ContextGuard`**：上下文过长时的 API 调用保护与历史压缩重试。 |
| `intelligence/loop.py` | **`agent_loop`**：终端主循环（工具轮次、与 Guard 配合的 LLM 调用）。 |
| `intelligence/repl.py` | 终端 REPL 的读写与交互辅助。 |
| `intelligence/console.py` | 终端 ANSI 颜色等输出辅助。 |
| `intelligence/entrypoints/main.py` | CLI 入口：检查密钥与工作区后进入 `agent_loop`。 |
| `intelligence/memory/` | 记忆召回、存储与运行时注入（`recall.py`、`store_memory.py`、`runtime_memory.py`）。 |
| `intelligence/session/` | 会话 JSONL 存储与消息工具（`store_session.py`、`message_utils.py`）。 |
| `intelligence/tools/` | 工具定义与派发（`__init__.py`、`dispatch_tools.py`、`workspace_tools.py`、`memory_tools.py`）。 |
| **`web/`** | **Web 前后端**。 |
| `web/server/app.py` | FastAPI 应用：**`/api/chat` SSE**、会话与 dialog 映射、消息水合逻辑。 |
| `web/vite.config.ts` | Vite 开发服务器与 `/api` 代理。 |
| `web/src/` | React 源码：`api/chat.ts`（SSE 解析）、`App.tsx`、Markdown 与布局组件、`lib/` 消息与会话辅助等。 |
| **`workspace/`** | **智能体可读写的「工作区」**：人格与工具说明 Markdown、`skills/` 技能目录、可选 `CRON.json` 等；路径约束由工具层保证不越界。 |

---
