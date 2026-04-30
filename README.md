[简体中文](#我的爪子-myclaw-入门与启动) · Extended curriculum · [README.zh.md](README.zh.md)

---

## 我的爪子 (myclaw) · 入门与启动

未知

---

### 仓库里大致有什么｜What’s inside

| 路径 | 说明 |
|------|------|
| `s06_intelligence.py` | **第六节 Intelligence**：会话、`BootstrapLoader`、工具调用、记忆检索等 REPL / 逻辑入口（请在仓库根目录运行）。 |
| `workspace/` | 示例「工作区」：`SOUL.md`、`TOOLS.md`、`MEMORY.md`、`.sessions/` 等；运行时读写相对于该目录。 |
| `web/` | Web UI：`web/server/` FastAPI + SSE，`web/src/` Vite + React；开发时通过 Vite 将 `/api` 代理到后端。 |
| `.env.example` | **配置模板**（可提交到 Git）；复制为 `.env` 后填入密钥（`.env` 勿提交）。 |
| `requirements.txt` | Python 依赖。 |
| [README.zh.md](README.zh.md) | 完整 claw0 **课程体系与章节一览**（与本剪裁仓库的文件布局不一定完全一致）。 |

---

### 配置：`.env.example` 与 `.env`（类比说明）

与多数开源项目一样：**仓库里只放不含密钥的示例**，本地密钥放在 **不入库** 的文件里。

| 文件 | 是否提交 Git | 作用 |
|------|----------------|------|
| **`.env.example`** | ✅ 是 | 列出有哪些环境变量、占位格式与注释；新人克隆后对照填写。 |
| **`.env`** | ❌ 否（应在 `.gitignore`） | 你的真实 `ANTHROPIC_API_KEY`、`MODEL_ID` 等；仅在本地或 CI 密钥管理中生效。 |

典型步骤：

```bash
cp .env.example .env
# 编辑 .env：至少填写 ANTHROPIC_API_KEY；按需填写 MODEL_ID、SERPAPI_API_KEY 等
```

后端启动时会读取环境变量（常与 `python-dotenv` 加载 `.env` 配合使用）。

---

### 环境与版本建议

- **Python**：建议 **3.10+**（README.zh 中写的是 3.11+；若使用 **3.9**，请确认代码含 `from __future__ import annotations`，否则会触发类型注解相关报错）。
- **Node.js**：建议 **18+**（用于 `web/` 前端打包与开发服务器）。
- **包管理**：Python 可用 **uv**、pip、pipenv 等；下文以 **uv** 为例。

---

### 使用 uv：从虚拟环境到跑通前后端

在**仓库根目录**（与 `s06_intelligence.py`、`web/` 同级）执行。

**1）创建并激活虚拟环境，安装依赖**

```bash
uv venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
```

**2）配置环境变量**

```bash
cp .env.example .env
# 编辑 .env
```

**3）终端 A：启动后端 API**

```bash
uvicorn web.server.app:app --host 127.0.0.1 --port 8765
```

**4）终端 B：安装前端依赖并启动开发服务器**

```bash
cd web
npm install
npm run dev
```

**5）浏览器**

开发模式下前端一般为 **http://127.0.0.1:5173**（见 `web/vite.config.ts`），并通过代理访问 **http://127.0.0.1:8765** 上的 `/api`。

**6）（可选）仅终端 REPL，不用 Web**

```bash
# 仍在仓库根目录，且已激活 venv、已配置 .env
python s06_intelligence.py
```

---

### 常见问题

- **后端报错缺少 `ANTHROPIC_API_KEY` 或找不到 `workspace/`**：检查 `.env` 与是否在**仓库根目录**启动。
- **Python 3.9 与 `list[dict] | None` 报错**：升级到 3.10+，或确保源码中有 `from __future__ import annotations`（本仓库已针对该问题做过兼容处理）。
- **端口占用**：修改 `uvicorn` 端口或 `web/vite.config.ts` 中的 `proxy.target`，并保持前后端一致。

---

### 开源仓库的 README 通常要写什么？（速查）

便于他人 **一眼看懂、能跑起来、知道如何参与**，常见区块如下（不必一次写全，可按需迭代）：

| 区块 | 作用 |
|------|------|
| **项目名称 + 一句话介绍** | 解决什么问题、面向谁。 |
| **功能 / 截图 / Demo** | 可选；UI 项目尤其有用。 |
| **快速开始（Quick Start）** | 克隆、依赖、配置、一条命令跑起来。 |
| **环境变量** | 说明 `.env.example` → `.env`，列出必填项。 |
| **目录结构** | 主要文件夹含义（见上文表格）。 |
| **开发与构建** | 测试、lint、前后端启动命令。 |
| **兼容性** | 语言版本、操作系统。 |
| **许可证（License）** | 常见为 MIT / Apache-2.0；需在仓库里放 `LICENSE` 文件并与声明一致。 |
| **贡献（Contributing）** | 可单独写 `CONTRIBUTING.md`：PR 流程、代码风格。 |
| **链接** | 文档站点、讨论区、上游项目致谢。 |

本仓库另提供一份 **带注释的占位模板**：[README.example.md](README.example.md)，可作为你以后新项目复制修改的起点（类似 `.env.example` 之于 `.env`：模板人人可复制，真实 README 随项目迭代）。

---

### 延伸阅读

- 完整章节叙事与架构图：见 [README.zh.md](README.zh.md)。  
- 模板示例：见 [README.example.md](README.example.md)。
