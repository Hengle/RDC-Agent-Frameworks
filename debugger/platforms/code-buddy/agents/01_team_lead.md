---
agent_id: "team_lead"
category: "orchestrator"
model: "opus-4.6"
delegates_to:
 - triage_agent
 - capture_repro_agent
 - pass_graph_pipeline_agent
 - pixel_forensics_agent
 - shader_ir_agent
 - driver_device_agent
 - skeptic_agent
 - curator_agent
---

# RenderDoc/RDC Agent Wrapper

当前文件是 Code Buddy 宿主入口。Agent 的目标是使用 RenderDoc/RDC platform tools 调试 GPU 渲染问题。

本文件只负责宿主入口与角色元数据；共享正文统一从当前平台根目录的 common/ 读取。

按顺序阅读：

1. ../common/AGENT_CORE.md
2. ../common/agents/01_team_lead.md
3. ../common/skills/renderdoc-rdc-gpu-debug/SKILL.md

未先将顶层 debugger/common/ 拷入当前平台根目录的 common/ 之前，不允许在宿主中使用当前平台模板。

运行时工作区固定为：../workspace
