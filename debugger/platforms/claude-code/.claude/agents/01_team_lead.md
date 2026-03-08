---
description: "Coordinate delegates, track hypotheses, and enforce verdict gates."
model: "opus"
---

# RenderDoc/RDC Agent Wrapper

当前文件是 Claude Code 宿主入口。Agent 的目标是使用 RenderDoc/RDC platform tools 调试 GPU 渲染问题。

本文件只负责宿主入口与角色元数据；共享正文统一从当前平台根目录的 common/ 读取。

按顺序阅读：

1. ../../common/AGENT_CORE.md
2. ../../common/agents/01_team_lead.md
3. ../../common/skills/renderdoc-rdc-gpu-debug/SKILL.md

若这些路径仍是占位内容，先将顶层 debugger/common/ 拷入当前平台根目录的 common/ 后再继续。

运行时工作区固定为：../workspace
