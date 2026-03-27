---
name: rdc-debugger
description: Public main skill for the RenderDoc/RDC GPU debugger framework. Use when the user wants defect diagnosis, root-cause analysis, regression explanation, or fix verification for a GPU rendering issue from one or more `.rdc` captures.
metadata:
  short-description: RenderDoc/RDC GPU debugging workflow for .rdc captures
---

# `RDC Debugger` Codex 入口包装

当前文件是 Codex 平台的 public main skill 包装层。

固定顺序：

1. `intent_gate`
2. `entry_gate`
3. binding/preflight + capture import + case/run bootstrap
4. `artifacts/intake_gate.yaml` pass
5. `artifacts/runtime_topology.yaml`
6. `staged_handoff`
7. `artifacts/run_compliance.yaml` pass

硬规则：

- 进入任何平台真相相关工作前，先读取 `common/config/platform_capabilities.json` 与 `common/config/runtime_mode_truth.snapshot.json`。
- 在 `artifacts/intake_gate.yaml` 通过前，不得进入 specialist dispatch 或 live `rd.*` 分析。
- 当前平台固定声明：
  - `specialist_dispatch_requirement = required`
  - `host_delegation_policy = platform_managed`
  - `host_delegation_fallback = none`
- 默认 `orchestration_mode = multi_agent`；只有用户显式要求不要 multi-agent context 时，才允许 `single_agent_by_user`
- `single_agent_by_user` 必须显式记录：
  - `orchestration_mode=single_agent_by_user`
  - `single_agent_reason=user_requested`
- specialist dispatch 后，主 agent 必须先进入 `waiting_for_specialist_brief` 并持续汇总阶段回报；短时 silence 不得触发 orchestrator 抢活
- 超过框架预算仍未收到阶段回报时，应进入 `BLOCKED_SPECIALIST_FEEDBACK_TIMEOUT` 或等价阻断状态
- direct RenderDoc Python fallback 只允许 local backend；若走直连路径，必须记录：
  - `fallback_execution_mode=local_renderdoc_python`
  - `WRAPPER_DEGRADED_LOCAL_DIRECT`
- `curator_agent` 在 `multi_agent` 下仍是 finalization-required；`single_agent_by_user` 下由 `rdc-debugger` 输出最终报告，但必须显式记录该模式。

工作区与输出：

- case/run 现场写入 `workspace/cases/<case_id>/runs/<run_id>/`
- specialist handoff 写入 `notes/**` 或 `capture_refs.yaml`
- 运行拓扑与 orchestrator mode 写入 `artifacts/runtime_topology.yaml`
- 最终审计结果写入 `artifacts/run_compliance.yaml`

本包装层只补充 Codex 宿主 contract，不替代共享正文。进入框架后继续阅读：

1. `common/AGENT_CORE.md`
2. `common/skills/rdc-debugger/SKILL.md`
3. `common/docs/runtime-coordination-model.md`
4. `platforms/codex/AGENTS.md`
