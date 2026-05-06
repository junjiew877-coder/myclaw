# 工具说明

本节描述在运行 **`myclaw_intelligence.py`（仓库根目录，Intelligence + Sessions）** 时，模型可用的 **LLM 工具**。所有**文件类**路径均相对于工作区根目录 **`workspace/`**，且不能穿越到其外。

## 工具一览（9 个）

### Shell

- **bash**：执行 shell 命令并返回标准输出/错误。工作目录固定为 **`workspace/`** 根（不是仓库根目录）。带简单危险命令拒绝与时间限制。

### 文件

- **read_file**：读取工作区内文件全文（过长会截断并附说明）。
- **write_file**：写入文件；父目录不存在会自动创建；覆盖已存在内容。
- **edit_file**：用 `old_string` 精确替换为 `new_string`；`old_string` 在文件中必须**恰好出现一次**。编辑前务必先 `read_file`。
- **list_directory**：列出某目录下条目；路径相对于工作区，缺省为根目录（`"."`）。

### 系统

- **get_current_time**：返回当前 UTC 时间字符串。

### 联网（Kimi）

- **web_search**：通过 [SerpAPI](https://serpapi.com)（Google 等引擎，需配置 **`SERPAPI_API_KEY`**，依赖 `google-search-results`）。与 curl/其他技能互补；计费以 SerpAPI 为准。

### 记忆

- **memory_write**：把值得长期保留的事实写入 `memory/daily/{日期}.jsonl`（可带 `category`）。
- **memory_search**：在 `MEMORY.md` 与每日 jsonl 等记忆源中做混合检索并返回相关片段。

## 使用建议

- **先读后改**：`edit_file` / `write_file` 前用 `read_file` 确认内容与精确字符串。
- **记忆**：用户偏好、约定、重要事实用 `memory_write`；需要查历史事实时用 `memory_search`（系统提示里也可能已自动注入部分召回结果）。
- **输出体积**：大文件/长命令输出会被截断，避免假设工具返回了完整无截断的原文。
- 其他章节脚本（如仅 s02/s03）工具集可能更瘦；以当前运行的 `*.py` 里注册的 `TOOLS` 为准。
