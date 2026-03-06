# RenderDoc/RDC GPU Debug Skill

## 描述

这个 skill 的目标是让 Agent 明确自己要使用 RenderDoc/RDC 平台 tools 来调试 GPU 渲染问题，而不是停留在抽象框架层面。

任务入口：

- 理解用户的渲染问题、capture、session、event、resource、shader、driver 线索
- 根据平台接入模式选择 `MCP` 或 `CLI`
- 通过 `rd.*` tools 或平台工具入口收集证据、验证假设、生成报告和知识条目

必读：

- `../../../../common/AGENT_CORE.md`
- `../../../../docs/platform-capability-model.md`
- `../../../../docs/platform-capability-matrix.md`
- `../../../../docs/model-routing.md`
- 若用户要求 `CLI` 模式：`../../../../docs/cli-mode-reference.md`

模式规则：

- `MCP` 模式允许 tool discovery。
- `CLI` 模式禁止靠 `--help`、枚举命令、随机试跑、观察式试错来摸索能力面。
- 当前 skill 是 GPU 调试主技能，不只是“知识载入说明”。
