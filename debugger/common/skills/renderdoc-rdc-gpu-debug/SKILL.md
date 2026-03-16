# RenderDoc/RDC GPU Debug Base Skill（基础技能）

## 任务目标

本 skill 是 domain/base skill。

作用：

- 明确当前任务是使用 RenderDoc/RDC platform tools 调试 GPU 渲染问题
- 在任何 role-specific skill 之前施加统一护栏
- 强制先回到 Tools 平台真相，再进入具体角色行为

## 必读顺序

1. `../../AGENT_CORE.md`
2. `../../config/platform_adapter.json`
3. `<resolved tools_root>/README.md`
4. `<resolved tools_root>/docs/tools.md`
5. `<resolved tools_root>/docs/session-model.md`
6. `<resolved tools_root>/docs/agent-model.md`
7. `<resolved tools_root>/spec/tool_catalog.json`
8. `../../docs/platform-capability-model.md`
9. `../../docs/platform-capability-matrix.md`
10. `../../docs/model-routing.md`
11. 若用户明确要求 `CLI` 模式：`../../docs/cli-mode-reference.md`
12. `../../docs/workspace-layout.md`

## Mandatory Preflight（强制预检）

开始任何平台真相相关工作前，必须先校验 `../../config/platform_adapter.json`：

- `paths.tools_root` 已由用户显式配置
- `validation.required_paths` 中的所有路径在 `<resolved tools_root>/` 下存在

如果未通过校验，必须直接输出：

```text
Tools 平台真相未配置：请先在 `common/config/platform_adapter.json` 中设置 `paths.tools_root` 指向有效的 `RDC-Agent-Tools` 根目录，并确认必需文档与 `spec/tool_catalog.json` 存在后，再重新发起任务。
```

然后停止，不得继续：

- debug / investigation
- tool planning
- session / runtime 推理
- remote / event / context 生命周期裁决

## 全局护栏

- 只使用 `rd.*` / platform tools 收集 capture、session、event、resource、shader、driver 证据
- 禁止自造工具名、参数名或错误语义
- `CLI` wrapper 不是规范源；tool catalog 与共享契约才是规范源
- 调用前优先读取 tool catalog 的 `prerequisites`，不要靠试错学习 tool 顺序
- 正常用户入口只有 `team_lead`
- specialist role 默认是 internal/debug-only，由 `team_lead` 决定是否分派
- 遇到 host 能力不足时，保持 orchestrator 语义，不把路由责任推回给用户

## 协作与工作区约束

- `coordination_mode` 以 `../../config/platform_capabilities.json` 与当前平台生成物为准
- remote case 一律采用 `single_runtime_owner`
- 跨轮次移交时必须附带可重建的 `runtime_baton`
- 第一层真相继续写入 `common/knowledge/library/**`
- case/run 现场与第二层交付物写入 `../workspace/cases/<case_id>/runs/<run_id>/`

## 方向约束

- 出现 `hair_shading`、`precision`、`washout`、`blackout`、`Adreno_GPU` 这类组合时，不得直接把 screen-like 观察提升为根因裁决
- 必须先建立 `causal_anchor`，再把 `RelaxedPrecision`、后处理阶段或 screen-space shader 线索提升为根因分析对象

## 结案约束

- `skeptic_agent` 未 signoff，不得当成最终结论
- `workspace/` 中的 notes、截图或 HTML 页面不是 gate 真相
- 只有 session artifacts 与结构化证据满足 gate contract 时，才允许结案
