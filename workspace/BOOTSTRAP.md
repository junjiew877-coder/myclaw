# 引导加载（Bootstrap）

本文件在智能体启动时提供额外上下文。

## 项目背景

本智能体属于 claw0 教学框架的一部分，用于演示如何从零搭建 AI 网关。工作区目录中的配置文件会塑造智能体行为：

- SOUL.md：人格与沟通风格
- IDENTITY.md：角色与边界
- TOOLS.md：可用工具与使用说明
- MEMORY.md：长期事实与偏好
- HEARTBEAT.md：主动行为（心跳）说明
- BOOTSTRAP.md：本文件——启动时的补充上下文
- AGENTS.md：多智能体协作说明
- CRON.json：定时任务定义

## 工作区布局

```
workspace/
  *.md          -- 引导文件（载入系统提示词）
  CRON.json     -- Cron 任务定义
  memory/       -- 每日记忆日志
  skills/       -- 技能定义
  .sessions/    -- 会话 transcript（自动维护）
  .agents/      -- 按智能体的状态（自动维护）
```
