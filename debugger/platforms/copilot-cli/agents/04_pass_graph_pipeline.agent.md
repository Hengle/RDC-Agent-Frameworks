---
description: "Trace pass divergence and resource dependency chains."
---

# RenderDoc/RDC Agent Wrapper

当前文件是 Copilot CLI 宿主入口。Agent 的目标是使用 RenderDoc/RDC platform tools 调试 GPU 渲染问题。

本文件只负责宿主入口与角色元数据；共享正文统一从当前平台根目录的 common/ 读取。

按顺序阅读：

1. ../common/AGENT_CORE.md
2. ../common/agents/04_pass_graph_pipeline.md
3. ../common/skills/renderdoc-rdc-gpu-debug/SKILL.md

未先将顶层 debugger/common/ 拷入当前平台根目录的 common/ 之前，不允许在宿主中使用当前平台模板。

运行时工作区固定为：../workspace
