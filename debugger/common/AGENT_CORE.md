# RenderDoc/RDC GPU Debug Agent Core

本文件是 `RenderDoc/RDC GPU Debug` framework 的全局约束入口。

职责边界：

- `RDC-Agent Tools` 负责平台真相：tool catalog、共享响应契约、runtime 生命周期、context/session/remote/event 语义与错误面。
- 本文件只负责 framework 如何消费这些平台真相，不重新定义平台语义。
- 角色职责正文以 `common/agents/*.md` 为准；平台适配物只允许改宿主入口、frontmatter 与少量宿主接入说明。

## 1. Framework 与 Tools 的边界

以下内容必须回到已解析的 `RDC-Agent Tools` 判定：

- `rd.*` tools 的能力面与参数语义
- 共享响应契约
- `.rdc -> capture_file_id -> session_id -> frame/event context` 的最小状态链路
- `remote_id`、`capture_file_id`、`session_id`、`active_event_id` 等 handle 的生命周期
- `context`、daemon、artifact、context snapshot 的平台语义
- 错误分类与恢复面

以下内容属于 framework：

- 角色拓扑与协作关系
- 任务 intake、分派、阶段推进与结案门槛
- `causal_anchor`、workspace、artifact/gate 的硬约束
- 多平台能力差异下的降级编排原则

## 2. Mandatory Tools Resolution

所有需要平台真相的工作在开始前，必须先读取并校验：

- `common/config/platform_adapter.json`

强制规则：

1. `paths.tools_root` 必须由用户显式配置，不允许保留占位值。
2. Agent 必须验证 `tools_root` 下至少存在：
   - `README.md`
   - `docs/tools.md`
   - `docs/session-model.md`
   - `docs/agent-model.md`
   - `spec/tool_catalog.json`
3. 任一项缺失、路径不存在或 `tools_root` 未配置时，必须立即停止，不得继续做 debug / investigation / tool planning。
4. 停止时统一输出：

```text
Tools 平台真相未配置：请先在 `common/config/platform_adapter.json` 中设置 `paths.tools_root` 指向有效的 `RDC-Agent-Tools` 根目录，并确认必需文档与 `spec/tool_catalog.json` 存在后，再重新发起任务。
```

5. 不允许把 `CLI` wrapper、skill 文本、平台模板说明或模型记忆当成 Tools 真相替代品。

推荐阅读顺序：

1. `<resolved tools_root>/README.md`
2. `<resolved tools_root>/docs/tools.md`
3. `<resolved tools_root>/docs/session-model.md`
4. `<resolved tools_root>/docs/agent-model.md`
5. `<resolved tools_root>/spec/tool_catalog.json`

## 3. Global Entry Contract

内部 `agent_id` SSOT：

- `team_lead`
- `triage_agent`
- `capture_repro_agent`
- `pass_graph_pipeline_agent`
- `pixel_forensics_agent`
- `shader_ir_agent`
- `driver_device_agent`
- `skeptic_agent`
- `curator_agent`

入口规则：

- `team_lead` 是当前 framework 唯一正式用户入口，承担 orchestrator 语义。
- 其他角色默认是 internal/debug-only specialist，不是正常用户入口。
- 若宿主无法隐藏 specialist 入口，仍必须明确：正常用户请求应先交给 `team_lead` 路由。
- specialist 不得绕过 `team_lead` 重新定义任务 intake、裁决门槛或 delegation policy。

## 4. Global Workflow

统一工作流：

1. `team_lead`
   - intake 用户目标
   - 建立 hypothesis board
   - 决定阶段推进与 specialist 分派
2. `triage_agent`
   - 结构化 symptoms / triggers
   - 推荐 SOP 与 `causal_axis`
3. `capture_repro_agent`
   - 建立 capture/session 基线
   - 产出可重建的 capture anchor / runtime baton 起点
4. 因果回锚阶段
   - 将 capture/session anchor 收敛为 `causal_anchor`
   - 优先建立 `first_bad_event`、`first_divergence_event`、`root_drawcall` 或 `root_expression`
5. 专家调查阶段
   - `pass_graph_pipeline_agent`
   - `pixel_forensics_agent`
   - `shader_ir_agent`
   - `driver_device_agent`
6. `skeptic_agent`
   - 对 `VALIDATE -> VALIDATED` 结论做对抗审查
7. `curator_agent`
   - 写入 BugFull / BugCard / session artifacts

协作真相：

- `concurrent_team` 允许并行分派，但每条 live 调试链路必须独占一个 `context/daemon`。
- `staged_handoff` 由 specialist 先提交 brief / evidence request，再由 runtime owner 执行 live tool 链。
- `workflow_stage` 只允许阶段化串行推进，不模拟真实的 team-agent 并发 handoff。
- remote case 一律服从 `single_runtime_owner`；不得因为 multi-agent 就共享 live remote runtime。

## 5. Hard Contracts

### 5.1 Causal Anchor

在做任何根因级裁决前，必须先建立 `causal_anchor`。

硬规则：

- `第一可见错误 != 第一引入错误`
- 无 `causal_anchor` 不得把 hypothesis 提升为 `VALIDATE` 或 `VALIDATED`
- screenshot / texture / similarity / screen-like fallback 只能用于选点、选对象、sanity check，不得替代因果裁决
- 结构化 `rd.*` 证据优先级高于视觉叙事
- 证据冲突时必须进入 `BLOCKED_REANCHOR`

`causal_anchor` 最小字段：

- `type`
- `ref`
- `established_by`
- `justification`

### 5.2 Session / Runtime Coordination

- `session_id` 必须来自 replay session 打开链路
- 进入根因分析前必须先建立 `causal_anchor`
- `capture_file_id`、`session_id`、`active_event_id`、`remote_id` 都是短生命周期 handle
- `CLI` 与 `MCP` 共用同一套 daemon / context 机制
- 同一 `context` 不得并行维护多条 live 调试链路
- remote `open_replay` 成功后会消费 live `remote_id`
- 跨 agent 或跨轮次移交 live 调试上下文时，必须提供可重建的 `runtime_baton`
- `runtime_baton` 的恢复顺序与语义以 `common/docs/runtime-coordination-model.md` 为准

### 5.3 Workspace Contract

- `common/` 是唯一共享真相
- `../workspace/` 是 case/run 运行区

固定模型：

```text
../workspace/cases/<case_id>/runs/<run_id>/
  artifacts/
  logs/
  notes/
  captures/
  screenshots/
  reports/
```

硬规则：

- 第一层真相产物继续写入 `common/knowledge/library/**`
- 第二层交付层写入 `../workspace/cases/<case_id>/runs/<run_id>/reports/`
- 第二层交付物只能派生自第一层证据，不得反写第一层真相

### 5.4 Artifact / Gate Contract

结案前必须具备：

- `common/knowledge/library/sessions/.current_session`
- `common/knowledge/library/sessions/<session_id>/session_evidence.yaml`
- `common/knowledge/library/sessions/<session_id>/skeptic_signoff.yaml`
- `common/knowledge/library/sessions/<session_id>/action_chain.jsonl`

额外规则：

- `session_evidence.yaml` 根对象必须包含完整 `causal_anchor`
- 若存在 `type: visual_fallback_observation`，则必须同时存在 `type: causal_anchor_evidence`
- 缺失任一项，不得视为有效结案

## 6. Canonical References

共享 framework 入口：

- `common/config/platform_adapter.json`
- `common/config/platform_capabilities.json`
- `common/config/platform_targets.json`
- `common/config/model_routing.json`

共享 framework 文档：

- `common/docs/platform-capability-model.md`
- `common/docs/platform-capability-matrix.md`
- `common/docs/model-routing.md`
- `common/docs/runtime-coordination-model.md`
- `common/docs/workspace-layout.md`
- `common/docs/cli-mode-reference.md`（仅在用户明确要求 `CLI` 模式时强制阅读）

角色与技能入口：

- `common/agents/*.md`
- `common/skills/renderdoc-rdc-gpu-debug/SKILL.md`
- `common/skills/*/SKILL.md`
