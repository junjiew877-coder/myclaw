# myclaw

面向个人的 AI 助手栈：**工作区 Markdown 驱动提示词**、**Anthropic 工具调用**、**记忆与会话持久化**，以及基于 **React + FastAPI**、通过 **SSE 真流式**输出正文的聊天界面。

---

## 技术特性（Technical features）

- **分层 system prompt** — 按 Identity / Soul / Tools / Skills / Memory / Bootstrap 等部分组装（`intelligence/prompt.py`），内容主要来自 `workspace/` 下的 Markdown。提供 **full / minimal** 等模式（目前需在源码中选用；规划上主 agent 用 full、子 agent 用 minimal 以减少非必要 context）。
- **Bootstrap 加载** — 读取 `SOUL.md`、`IDENTITY.md`、`TOOLS.md`、`MEMORY.md` 等作为「人格、工具规范、记忆写入约定」，按单文件与总字数上限截断（`intelligence/bootstrap.py`）。
- **Agent 技能（Skills）** — 扫描 `workspace/skills/**/SKILL.md`，格式化后注入系统提示（`intelligence/skills.py`）。
- **记忆（Memory）** — **存储**：`workspace/MEMORY.md` 为常驻笔记；按日落盘 **`workspace/memory/daily/YYYY-MM-DD.jsonl`**，每行一条 JSON（`ts`、`category`、`content`）（`intelligence/memory/store_memory.py`）。**自动召回**：`auto_recall` 对用户输入调用 **`hybrid_search(..., top_k=3)`**，结果写入系统提示（`intelligence/memory/recall.py`）。**检索**：纯 Python、无外部向量库 — 关键词支路为 **TF-IDF + 余弦相似度**；另一支路为基于 token **哈希的 64 维符号向量 + 余弦**；两路按权重合并（约 **0.7 / 0.3**），再对带日期的片段做**时间衰减**，并用 **MMR（Jaccard）** 去冗余（`MemoryStore.hybrid_search` 等）。
- **会话（Sessions）与会话管理** — 每条对话有唯一 **`session_id`**，历史以 **JSONL** 落在工作区下的会话目录中，并带简单索引（标签、时间等）。**终端**可用 **`/list`**、**`/switch`**（后接目标 id）、**`/new`** 列出或切换会话。**Web** 为每个浏览器标签页生成 **`dialog_id`**（存在 `sessionStorage`），后端把 tab 映射到某条 **`session_id`**：提供列出、新建、按 id 选择、拉取历史等 REST 接口，侧栏点选即切换；发消息时带同一 **`dialog_id`**，在同一会话里续写。
- **工具调用** — 统一工具列表与派发；工作区文件/命令类工具、记忆类工具；**网页搜索**为可选能力，需单独配置 **`SERPAPI_API_KEY`**（SerpAPI，见 `intelligence/tools/workspace_tools.py`、`workspace/TOOLS.md`）（`intelligence/tools/`：`dispatch_tools.py`、`workspace_tools.py`、`memory_tools.py`）。
- **模型路由** — 支持：思考模式开启/关闭、思考/非思考模型切换，通过环境变量区分非思考与思考模型（`MODEL_ID_CHAT` / `MODEL_ID_REASON`）；
- **流式传输（Web）** — 聊天接口通过 **SSE** 推送事件；助手正文使用 Anthropic **`messages.stream`** 的 **`text_stream`**，将增量映射为 **`type: "delta"`**（`intelligence/runtime.py`、`web/server/app.py`）。终端 REPL 仍以 **`messages.create`** 非流式为主（`intelligence/loop.py`）。
- **上下文压缩与溢出保护** — **`ContextGuard`**（`intelligence/context_guard.py`）：以 **字符数 ÷ 4** 粗估 token；**`guard_api_call`** 在溢出时先**截断过大工具返回**，仍失败则 **`compact_history`**（将较早部分消息序列化后，再调 **`messages.create`** 生成摘要并折叠进历史）。终端可 **`/context`** 查看估算用量、**`/compact`** 手动压缩（`intelligence/repl.py`）。
- **终端斜杠命令** — 以 **`/`** 开头的输入在 **`intelligence/repl.py`** 中处理，不进入模型对话。含：**会话** `/new`、`/list`、`/switch`、`/context`、`/compact`；**调试/检视** `/help`、`/soul`、`/skills`、`/memory`、`/search <q>`、`/prompt`、`/bootstrap`（启动提示见 `intelligence/loop.py`）。

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
